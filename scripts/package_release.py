#!/usr/bin/env python3
from __future__ import annotations

import datetime
import gzip
import hashlib
import io
import os
import re
import shutil
import subprocess
import tarfile
import zipfile
from pathlib import Path

from common import ARTIFACTS, DIST, ROOT, WORK, BuildError, load_json, require, sha256_file, write_json
import generate_runtime_metadata as runtime_metadata_generator
import generate_sbom
import generate_license_inventory

PROJECT_REPOSITORY = 'https://github.com/HRAshton/code-oss-static-web'
PROJECT_COMMIT_RE = re.compile(r'^[0-9a-f]{40}$')


def iter_files(root: Path):
    return sorted(
        (path for path in root.rglob('*') if path.is_file()),
        key=lambda path: path.relative_to(root).as_posix(),
    )


def distribution_tree_digest(root: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    count = 0
    for path in iter_files(root):
        relative = path.relative_to(root).as_posix()
        mode = 0o755 if os.access(path, os.X_OK) else 0o644
        file_digest = sha256_file(path)
        digest.update(f'{relative}\0{mode:o}\0{file_digest}\n'.encode())
        count += 1
    return digest.hexdigest(), count


def build_tar(src: Path, out: Path, epoch: int):
    with out.open('wb') as raw:
        with gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=epoch) as gz:
            with tarfile.open(fileobj=gz, mode='w', format=tarfile.PAX_FORMAT) as archive:
                for path in iter_files(src):
                    relative = path.relative_to(src).as_posix()
                    data = path.read_bytes()
                    info = tarfile.TarInfo(relative)
                    info.size = len(data)
                    info.mtime = epoch
                    info.mode = 0o755 if os.access(path, os.X_OK) else 0o644
                    info.uid = 0
                    info.gid = 0
                    info.uname = ''
                    info.gname = ''
                    archive.addfile(info, io.BytesIO(data))


def build_zip(src: Path, out: Path, epoch: int):
    timestamp = datetime.datetime.fromtimestamp(
        max(epoch, 315532800),
        datetime.timezone.utc,
    )
    stamp = (
        timestamp.year,
        timestamp.month,
        timestamp.day,
        timestamp.hour,
        timestamp.minute,
        timestamp.second,
    )
    with zipfile.ZipFile(
        out,
        'w',
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for path in iter_files(src):
            relative = path.relative_to(src).as_posix()
            info = zipfile.ZipInfo(relative, stamp)
            info.create_system = 3
            mode = 0o755 if os.access(path, os.X_OK) else 0o644
            info.external_attr = (mode & 0xFFFF) << 16
            archive.writestr(
                info,
                path.read_bytes(),
                compress_type=zipfile.ZIP_DEFLATED,
                compresslevel=9,
            )


def resolve_project_commit() -> str:
    github_sha = os.environ.get('GITHUB_SHA', '').strip().lower()
    if PROJECT_COMMIT_RE.fullmatch(github_sha):
        return github_sha

    try:
        project_commit = subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'],
            cwd=ROOT,
            text=True,
        ).strip().lower()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise BuildError('unable to resolve project commit') from exc

    require(
        PROJECT_COMMIT_RE.fullmatch(project_commit) is not None,
        f'invalid project commit: {project_commit}',
    )
    return project_commit


def input_digest(path: Path) -> dict[str, str]:
    require(path.is_file(), f'missing release input: {path}')
    return {
        'path': path.relative_to(ROOT).as_posix(),
        'sha256': sha256_file(path),
    }


def patch_inventory() -> list[dict[str, str]]:
    manifest_path = ROOT / 'patches/manifest.json'
    manifest = load_json(manifest_path)
    entries = manifest.get('patches', [])
    require(isinstance(entries, list), 'patch manifest patches must be an array')

    patches: list[dict[str, str]] = []
    for entry in entries:
        require(isinstance(entry, dict), 'patch manifest entry must be an object')
        file_name = entry.get('file')
        require(isinstance(file_name, str) and bool(file_name), 'patch manifest entry missing file')
        patch_path = ROOT / 'patches' / file_name
        require(patch_path.is_file(), f'missing patch: {patch_path}')
        patch = {
            'file': file_name,
            'sha256': sha256_file(patch_path),
        }
        patch_id = entry.get('id')
        if isinstance(patch_id, str) and patch_id:
            patch['id'] = patch_id
        patches.append(patch)
    return patches


def build_artifact_manifest(
    *,
    version: str,
    project_commit: str,
    upstream: dict,
    release_files: list[Path],
    distribution: Path,
    runtime_metadata: Path,
) -> dict:
    tree_digest, file_count = distribution_tree_digest(distribution)
    return {
        'schemaVersion': 1,
        'project': {
            'repository': PROJECT_REPOSITORY,
            'commit': project_commit,
        },
        'version': version,
        'upstream': {
            'repository': upstream['repository'],
            'tag': upstream['tag'],
            'commit': upstream['commit'],
            'sourceDateEpoch': int(upstream['sourceDateEpoch']),
            'qualified': bool(upstream['qualified']),
        },
        'distribution': {
            'treeSha256': tree_digest,
            'fileCount': file_count,
        },
        'inputs': {
            'upstreamLock': input_digest(ROOT / 'upstream.lock.json'),
            'patchManifest': input_digest(ROOT / 'patches/manifest.json'),
            'extensionLock': input_digest(ROOT / 'extensions/extensions.lock.json'),
            'extensionLicensePolicy': input_digest(ROOT / 'extensions/license-policy.json'),
            'runtimeConfig': input_digest(ROOT / 'config/runtime.json'),
            'productTransform': input_digest(ROOT / 'config/product-transform.json'),
            'networkPolicy': input_digest(ROOT / 'config/network-policy.json'),
            'runtimeComponents': input_digest(runtime_metadata),
        },
        'patches': patch_inventory(),
        'artifacts': [
            {
                'name': path.name,
                'sha256': sha256_file(path),
                'size': path.stat().st_size,
            }
            for path in release_files
        ],
    }


def main():
    require((DIST / 'index.html').is_file(), 'dist/ missing; run the build first')
    lock = load_json(ROOT / 'upstream.lock.json')
    epoch = int(lock['sourceDateEpoch'])
    ARTIFACTS.mkdir(exist_ok=True)
    for path in ARTIFACTS.iterdir():
        if path.is_file():
            path.unlink()

    version = f"{lock['tag']}-web.0"
    project_commit = resolve_project_commit()
    runtime_metadata_path = WORK / 'runtime-components.json'
    if not runtime_metadata_path.is_file():
        package_lock = WORK / 'vscode/package-lock.json'
        require(
            package_lock.is_file(),
            'runtime component metadata missing; run a full build or generate it explicitly',
        )
        runtime_metadata_generator.generate_runtime_metadata(
            DIST,
            package_lock,
            runtime_metadata_path,
        )
    runtime_metadata = load_json(runtime_metadata_path)

    tar_path = ARTIFACTS / f'code-oss-static-web-{version}.tar.gz'
    zip_path = ARTIFACTS / f'code-oss-static-web-{version}.zip'
    build_tar(DIST, tar_path, epoch)
    build_zip(DIST, zip_path, epoch)

    distribution_tree_sha256, _ = distribution_tree_digest(DIST)
    sbom_path = ARTIFACTS / 'sbom.cdx.json'
    generate_sbom.write_sbom(
        sbom_path,
        dist=DIST,
        metadata=runtime_metadata,
        version=version,
        project_commit=project_commit,
        upstream=lock,
        distribution_tree_sha256=distribution_tree_sha256,
    )

    license_inventory_path = ARTIFACTS / 'license-inventory.json'
    generate_license_inventory.write_license_inventory(
        license_inventory_path,
        metadata=runtime_metadata,
        version=version,
        project_commit=project_commit,
        upstream=lock,
    )

    project_license_path = ARTIFACTS / 'LICENSE'
    upstream_license_path = ARTIFACTS / 'LICENSE.Code-OSS.txt'
    upstream_notices_path = ARTIFACTS / 'ThirdPartyNotices.Code-OSS.txt'
    project_notices_path = ARTIFACTS / 'THIRD_PARTY_NOTICES.md'
    require((DIST / 'LICENSE.Code-OSS.txt').is_file(), 'Code-OSS license missing from distribution')
    require(
        (DIST / 'ThirdPartyNotices.Code-OSS.txt').is_file(),
        'Code-OSS third-party notices missing from distribution',
    )
    shutil.copy2(ROOT / 'LICENSE', project_license_path)
    shutil.copy2(DIST / 'LICENSE.Code-OSS.txt', upstream_license_path)
    shutil.copy2(DIST / 'ThirdPartyNotices.Code-OSS.txt', upstream_notices_path)
    shutil.copy2(ROOT / 'THIRD_PARTY_NOTICES.md', project_notices_path)

    write_json(
        ARTIFACTS / 'upstream.json',
        {
            'repository': lock['repository'],
            'tag': lock['tag'],
            'commit': lock['commit'],
            'sourceDateEpoch': epoch,
            'qualified': lock['qualified'],
        },
    )
    write_json(
        ARTIFACTS / 'artifact-manifest.json',
        build_artifact_manifest(
            version=version,
            project_commit=project_commit,
            upstream=lock,
            release_files=[
                tar_path,
                zip_path,
                sbom_path,
                license_inventory_path,
                project_license_path,
                upstream_license_path,
                upstream_notices_path,
                project_notices_path,
            ],
            distribution=DIST,
            runtime_metadata=runtime_metadata_path,
        ),
    )
    lines = []
    for path in sorted(
        item
        for item in ARTIFACTS.iterdir()
        if item.is_file() and item.name != 'SHA256SUMS'
    ):
        lines.append(f'{sha256_file(path)}  {path.name}')
    (ARTIFACTS / 'SHA256SUMS').write_text(
        '\n'.join(lines) + '\n',
        encoding='utf-8',
    )
    print(f'packaged {version} into {ARTIFACTS}')


if __name__ == '__main__':
    try:
        main()
    except BuildError as exc:
        raise SystemExit(str(exc))
