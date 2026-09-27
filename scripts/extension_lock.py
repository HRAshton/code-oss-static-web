#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from common import ROOT, BuildError, load_json, require, sha256_file

SUPPORTED_SCHEMA_VERSION = 1


def _require_string(value: Any, field: str) -> str:
    require(isinstance(value, str) and value.strip() != '', f'{field} must be a non-empty string')
    return value


def load_extension_lock(path: Path) -> dict[str, Any]:
    data = load_json(path)
    require(isinstance(data, dict), 'extension lock must be a JSON object')
    require(data.get('schemaVersion') == SUPPORTED_SCHEMA_VERSION, 'unsupported extension lock schemaVersion')
    extensions = data.get('extensions')
    require(isinstance(extensions, list), 'extension lock extensions must be an array')

    ids: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(extensions):
        prefix = f'extensions[{index}]'
        require(isinstance(raw, dict), f'{prefix} must be an object')
        extension_id = _require_string(raw.get('id'), f'{prefix}.id')
        version = _require_string(raw.get('version'), f'{prefix}.version')
        digest = _require_string(raw.get('sha256'), f'{prefix}.sha256').lower()
        require(len(digest) == 64 and all(c in '0123456789abcdef' for c in digest), f'{prefix}.sha256 must be a lowercase SHA-256 hex digest')
        require(extension_id not in ids, f'duplicate extension id in lock: {extension_id}')
        ids.add(extension_id)

        source = raw.get('source')
        require(isinstance(source, dict), f'{prefix}.source must be an object')
        source_type = _require_string(source.get('type'), f'{prefix}.source.type')
        require(source_type == 'local-vsix', f'unsupported extension source type: {source_type}')
        source_path = _require_string(source.get('path'), f'{prefix}.source.path')

        license_value = raw.get('license')
        if license_value is not None:
            _require_string(license_value, f'{prefix}.license')

        normalized.append({
            'id': extension_id,
            'version': version,
            'sha256': digest,
            'license': license_value,
            'source': {'type': source_type, 'path': source_path},
        })

    return {'schemaVersion': SUPPORTED_SCHEMA_VERSION, 'extensions': normalized}


def _safe_members(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    result: list[zipfile.ZipInfo] = []
    for info in archive.infolist():
        path = PurePosixPath(info.filename)
        require(not path.is_absolute(), f'VSIX contains absolute path: {info.filename}')
        require('..' not in path.parts, f'VSIX contains parent traversal: {info.filename}')
        mode = (info.external_attr >> 16) & 0xFFFF
        require((mode & 0o170000) != 0o120000, f'VSIX contains symlink: {info.filename}')
        result.append(info)
    return result


def _load_vsix_manifest(vsix: Path) -> tuple[dict[str, Any], str]:
    try:
        with zipfile.ZipFile(vsix) as archive:
            _safe_members(archive)
            manifest_name = 'extension/package.json'
            require(manifest_name in archive.namelist(), f'VSIX is missing {manifest_name}: {vsix}')
            try:
                manifest = json.loads(archive.read(manifest_name).decode('utf-8'))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise BuildError(f'invalid VSIX package.json: {vsix}: {exc}') from exc
    except zipfile.BadZipFile as exc:
        raise BuildError(f'invalid VSIX zip archive: {vsix}') from exc

    require(isinstance(manifest, dict), f'VSIX package.json must be an object: {vsix}')
    publisher = _require_string(manifest.get('publisher'), f'{vsix}: publisher')
    name = _require_string(manifest.get('name'), f'{vsix}: name')
    return manifest, f'{publisher}.{name}'


def validate_local_vsix(entry: dict[str, Any], *, root: Path = ROOT) -> tuple[Path, dict[str, Any]]:
    source_path = Path(entry['source']['path'])
    if not source_path.is_absolute():
        source_path = root / source_path
    source_path = source_path.resolve()
    require(source_path.is_file(), f'locked VSIX does not exist: {source_path}')
    require(source_path.suffix.lower() == '.vsix', f'local-vsix source must end in .vsix: {source_path}')
    require(sha256_file(source_path) == entry['sha256'], f'VSIX SHA-256 mismatch: {entry["id"]}')

    manifest, actual_id = _load_vsix_manifest(source_path)
    require(actual_id == entry['id'], f'VSIX id mismatch: locked {entry["id"]}, package contains {actual_id}')
    require(manifest.get('version') == entry['version'], f'VSIX version mismatch for {entry["id"]}')
    browser = manifest.get('browser')
    require(isinstance(browser, str) and browser.strip() != '', f'extension is not browser-compatible: {entry["id"]}')

    browser_path = PurePosixPath('extension') / PurePosixPath(browser.lstrip('./'))
    with zipfile.ZipFile(source_path) as archive:
        names = set(archive.namelist())
        require(browser_path.as_posix() in names, f'VSIX browser entrypoint missing for {entry["id"]}: {browser}')

    locked_license = entry.get('license')
    manifest_license = manifest.get('license')
    if locked_license is not None and manifest_license is not None:
        require(locked_license == manifest_license, f'VSIX license mismatch for {entry["id"]}')

    return source_path, manifest


def install_locked_extensions(dist: Path, lock_path: Path, *, root: Path = ROOT) -> list[dict[str, Any]]:
    lock = load_extension_lock(lock_path)
    installed: list[dict[str, Any]] = []
    extroot = dist / 'extensions'
    extroot.mkdir(parents=True, exist_ok=True)

    existing_ids: set[str] = set()
    for package_json in extroot.glob('*/package.json'):
        try:
            manifest = json.loads(package_json.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            continue
        publisher = manifest.get('publisher')
        name = manifest.get('name')
        if isinstance(publisher, str) and isinstance(name, str):
            existing_ids.add(f'{publisher}.{name}')

    for entry in lock['extensions']:
        require(entry['id'] not in existing_ids, f'extension id already exists in distribution: {entry["id"]}')
        vsix, manifest = validate_local_vsix(entry, root=root)
        destination = extroot / entry['id']
        require(not destination.exists(), f'extension destination already exists: {destination}')

        with tempfile.TemporaryDirectory(prefix='code-oss-static-web-vsix-') as td:
            temp = Path(td)
            with zipfile.ZipFile(vsix) as archive:
                members = _safe_members(archive)
                archive.extractall(temp, members=members)
            extracted = temp / 'extension'
            require(extracted.is_dir(), f'VSIX extension directory missing: {vsix}')
            shutil.copytree(extracted, destination, symlinks=False)

        installed.append({
            'id': entry['id'],
            'version': entry['version'],
            'sha256': entry['sha256'],
            'license': entry.get('license') or manifest.get('license'),
            'source': entry['source'],
        })
        existing_ids.add(entry['id'])

    return installed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--lock', type=Path, default=ROOT / 'extensions/extensions.lock.json')
    parser.add_argument('--dist', type=Path)
    args = parser.parse_args()
    lock = load_extension_lock(args.lock)
    if args.dist is None:
        for entry in lock['extensions']:
            validate_local_vsix(entry)
        print(f'validated {len(lock["extensions"])} locked extension(s)')
        return
    installed = install_locked_extensions(args.dist.resolve(), args.lock.resolve())
    print(f'installed {len(installed)} locked extension(s)')


if __name__ == '__main__':
    try:
        main()
    except BuildError as exc:
        raise SystemExit(str(exc))
