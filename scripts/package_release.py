#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime
import gzip
import hashlib
import io
import os
import re
import shutil
import subprocess
import tarfile
from pathlib import Path
from typing import Any

import check_release_tag
import compare_sbom_inventory
import generate_license_inventory
import generate_runtime_metadata as runtime_metadata_generator
import generate_sbom
from builder_environment import load_builder
from common import (
    ARTIFACTS,
    DIST,
    ROOT,
    WORK,
    BuildError,
    assert_no_symlinks,
    load_json,
    require,
    sha256_file,
    write_json,
)

PROJECT_REPOSITORY = 'https://github.com/Codellei/code-oss-static-web'
PROJECT_COMMIT_RE = re.compile(r'^[0-9a-f]{40}$')


def iter_files(root: Path) -> list[Path]:
    return sorted(
        (path for path in root.rglob('*') if path.is_file()),
        key=lambda path: path.relative_to(root).as_posix(),
    )


def distribution_tree_digest(root: Path) -> tuple[str, int]:
    assert_no_symlinks(root, label='distribution identity')
    digest = hashlib.sha256()
    count = 0
    for path in iter_files(root):
        relative = path.relative_to(root).as_posix()
        mode = 0o755 if os.access(path, os.X_OK) else 0o644
        file_digest = sha256_file(path)
        digest.update(f'{relative}\0{mode:o}\0{file_digest}\n'.encode())
        count += 1
    return digest.hexdigest(), count


def build_tar(src: Path, out: Path, epoch: int) -> None:
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


def resolve_project_commit() -> str:
    github_sha = os.environ.get('GITHUB_SHA', '').strip().lower()
    if PROJECT_COMMIT_RE.fullmatch(github_sha):
        return github_sha

    try:
        project_commit = (
            subprocess.check_output(
                ['git', 'rev-parse', 'HEAD'],
                cwd=ROOT,
                text=True,
            )
            .strip()
            .lower()
        )
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
    upstream: dict[str, Any],
    release_files: list[Path],
    distribution: Path,
    runtime_metadata: Path,
) -> dict[str, Any]:
    tree_digest, file_count = distribution_tree_digest(distribution)
    deployment_profile_path = distribution / 'deployment-profile.json'
    require(
        deployment_profile_path.is_file(), 'deployment profile metadata missing from distribution'
    )
    deployment_profile = load_json(deployment_profile_path)
    require(
        isinstance(deployment_profile.get('id'), str)
        and isinstance(deployment_profile.get('configSha256'), str),
        'invalid deployment profile metadata',
    )
    toolchain = load_json(ROOT / '.github/toolchain-versions.json')
    builder_identity = load_builder(ROOT / 'builder-image.json')
    node_version = toolchain.get('node')
    python_version = toolchain.get('python')
    require(isinstance(node_version, str) and bool(node_version), 'toolchain Node version missing')
    require(
        isinstance(python_version, str) and bool(python_version),
        'toolchain Python version missing',
    )
    assert isinstance(node_version, str)
    assert isinstance(python_version, str)
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
        },
        'toolchain': {
            'node': node_version,
            'python': python_version,
        },
        'builder': builder_identity,
        'distribution': {
            'treeSha256': tree_digest,
            'fileCount': file_count,
        },
        'deploymentProfile': deployment_profile,
        'inputs': {
            'toolchainVersions': input_digest(ROOT / '.github/toolchain-versions.json'),
            'builderImage': input_digest(ROOT / 'builder-image.json'),
            'builderAptSnapshot': input_digest(ROOT / 'builder-apt-snapshot.json'),
            'upstreamLock': input_digest(ROOT / 'upstream.lock.json'),
            'patchManifest': input_digest(ROOT / 'patches/manifest.json'),
            'deploymentProfileMetadata': input_digest(deployment_profile_path),
            'runtimeComponents': input_digest(runtime_metadata),
            'sbomComparisonPolicy': input_digest(ROOT / 'security/sbom-comparison-policy.json'),
            'sbomScannerConfig': input_digest(ROOT / 'security/syft.yaml'),
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


def package_version(lock: dict[str, Any], release_tag: str | None = None) -> str:
    if release_tag is None:
        release_tag = os.environ.get('CODE_OSS_STATIC_WEB_RELEASE_TAG')
    if release_tag is None:
        release_tag = check_release_tag.expected_release_tag(lock)
    return check_release_tag.release_version(lock, release_tag)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--playwright-runtime', type=Path)
    args = parser.parse_args()

    require((DIST / 'index.html').is_file(), 'dist/ missing; run the build first')
    assert_no_symlinks(DIST, label='release distribution')
    lock = load_json(ROOT / 'upstream.lock.json')
    epoch = int(lock['sourceDateEpoch'])
    ARTIFACTS.mkdir(exist_ok=True)
    for path in ARTIFACTS.iterdir():
        if path.is_file():
            path.unlink()

    version = package_version(lock)
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
    build_tar(DIST, tar_path, epoch)

    playwright_runtime_path: Path | None = None
    if args.playwright_runtime is not None:
        require(args.playwright_runtime.is_dir(), 'Playwright runtime directory missing')
        require(
            (args.playwright_runtime / 'node_modules/@playwright/test/cli.js').is_file(),
            'Playwright test CLI missing from runtime',
        )
        require(
            (args.playwright_runtime / 'node_modules/playwright/cli.js').is_file(),
            'Playwright CLI missing from runtime',
        )
        playwright_runtime_path = ARTIFACTS / 'playwright-runtime.tar.gz'
        build_tar(args.playwright_runtime, playwright_runtime_path, epoch)

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

    independent_sbom_path = WORK / 'independent-sbom.cdx.json'
    require(
        independent_sbom_path.is_file(),
        'independent Syft SBOM missing; run the independent final-distribution scan first',
    )
    independent_inventory_path = ARTIFACTS / 'independent-component-inventory.json'
    sbom_comparison_path = ARTIFACTS / 'sbom-comparison.json'
    compare_sbom_inventory.compare_files(
        sbom_path,
        independent_sbom_path,
        ROOT / 'security/sbom-comparison-policy.json',
        independent_inventory_path,
        sbom_comparison_path,
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
                sbom_path,
                independent_inventory_path,
                sbom_comparison_path,
                license_inventory_path,
                project_license_path,
                upstream_license_path,
                upstream_notices_path,
                project_notices_path,
                *([playwright_runtime_path] if playwright_runtime_path is not None else []),
            ],
            distribution=DIST,
            runtime_metadata=runtime_metadata_path,
        ),
    )
    lines: list[str] = []
    for path in sorted(
        item for item in ARTIFACTS.iterdir() if item.is_file() and item.name != 'SHA256SUMS'
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
        raise SystemExit(str(exc)) from None
