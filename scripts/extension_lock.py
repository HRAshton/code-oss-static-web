#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote

from common import ROOT, WORK, BuildError, load_json, require, sha256_file

SUPPORTED_SCHEMA_VERSION = 1
OPEN_VSX_DEFAULT_REGISTRY = 'https://open-vsx.org'
OPEN_VSX_USER_AGENT = 'code-oss-static-web/1'


def _require_string(value: Any, field: str) -> str:
    require(isinstance(value, str) and value.strip() != '', f'{field} must be a non-empty string')
    return value


def load_extension_lock(path: Path) -> dict[str, Any]:
    data = load_json(path)
    require(isinstance(data, dict), 'extension lock must be a JSON object')
    require(
        data.get('schemaVersion') == SUPPORTED_SCHEMA_VERSION,
        'unsupported extension lock schemaVersion',
    )
    extensions = data.get('extensions')
    require(isinstance(extensions, list), 'extension lock extensions must be an array')

    ids: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(extensions):
        prefix = f'extensions[{index}]'
        require(isinstance(raw, dict), f'{prefix} must be an object')
        extension_id = _require_string(raw.get('id'), f'{prefix}.id')
        version = _require_string(raw.get('version'), f'{prefix}.version')
        require(version != 'latest', f'{prefix}.version must pin an exact version')
        digest = _require_string(raw.get('sha256'), f'{prefix}.sha256').lower()
        require(
            len(digest) == 64 and all(c in '0123456789abcdef' for c in digest),
            f'{prefix}.sha256 must be a lowercase SHA-256 hex digest',
        )
        require(extension_id not in ids, f'duplicate extension id in lock: {extension_id}')
        ids.add(extension_id)

        source = raw.get('source')
        require(isinstance(source, dict), f'{prefix}.source must be an object')
        source_type = _require_string(source.get('type'), f'{prefix}.source.type')
        if source_type == 'local-vsix':
            normalized_source = {
                'type': source_type,
                'path': _require_string(source.get('path'), f'{prefix}.source.path'),
            }
        elif source_type == 'open-vsx':
            registry = source.get('registry', OPEN_VSX_DEFAULT_REGISTRY)
            registry = _require_string(registry, f'{prefix}.source.registry').rstrip('/')
            require(registry.startswith('https://'), f'{prefix}.source.registry must use HTTPS')
            normalized_source = {'type': source_type, 'registry': registry}
        else:
            raise BuildError(f'unsupported extension source type: {source_type}')

        license_value = raw.get('license')
        if license_value is not None:
            _require_string(license_value, f'{prefix}.license')

        normalized.append(
            {
                'id': extension_id,
                'version': version,
                'sha256': digest,
                'license': license_value,
                'source': normalized_source,
            }
        )

    return {'schemaVersion': SUPPORTED_SCHEMA_VERSION, 'extensions': normalized}


def load_license_policy(path: Path) -> dict[str, Any]:
    data = load_json(path)
    require(isinstance(data, dict), 'extension license policy must be a JSON object')
    require(data.get('schemaVersion') == 1, 'unsupported extension license policy schemaVersion')
    allowed = data.get('allowed')
    denied = data.get('denied', [])
    overrides = data.get('overrides', {})
    require(
        isinstance(allowed, list) and all(isinstance(item, str) for item in allowed),
        'license policy allowed must be a string array',
    )
    require(
        isinstance(denied, list) and all(isinstance(item, str) for item in denied),
        'license policy denied must be a string array',
    )
    require(isinstance(overrides, dict), 'license policy overrides must be an object')
    for extension_id, licenses in overrides.items():
        require(isinstance(extension_id, str), 'license policy override id must be a string')
        require(
            isinstance(licenses, list) and all(isinstance(item, str) for item in licenses),
            f'license policy override must be a string array: {extension_id}',
        )
    return {
        'schemaVersion': 1,
        'requireDeclared': bool(data.get('requireDeclared', True)),
        'allowed': allowed,
        'denied': denied,
        'overrides': overrides,
    }


def enforce_license_policy(
    entry: dict[str, Any],
    manifest: dict[str, Any],
    policy: dict[str, Any],
) -> str | None:
    locked = entry.get('license')
    declared = manifest.get('license')
    if locked is not None and declared is not None:
        require(locked == declared, f'VSIX license mismatch for {entry["id"]}')
    effective = locked or declared
    if effective is None:
        require(not policy['requireDeclared'], f'extension license is required: {entry["id"]}')
        return None
    require(
        effective not in policy['denied'],
        f'extension license is denied for {entry["id"]}: {effective}',
    )
    allowed = policy['overrides'].get(entry['id'], policy['allowed'])
    require(
        effective in allowed, f'extension license is not allowed for {entry["id"]}: {effective}'
    )
    return effective


def open_vsx_download_url(entry: dict[str, Any]) -> str:
    publisher, name = entry['id'].split('.', 1)
    version = entry['version']
    registry = entry['source'].get('registry', OPEN_VSX_DEFAULT_REGISTRY).rstrip('/')
    filename = f'{publisher}.{name}-{version}.vsix'
    return (
        f'{registry}/api/{quote(publisher, safe="")}/{quote(name, safe="")}/'
        f'{quote(version, safe="")}/file/{quote(filename, safe="")}'
    )


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


def download_open_vsx(
    entry: dict[str, Any],
    *,
    cache_root: Path = WORK / 'extensions-cache',
) -> Path:
    cache_root.mkdir(parents=True, exist_ok=True)
    target = cache_root / f'{entry["id"]}-{entry["version"]}.vsix'
    if target.is_file() and sha256_file(target) == entry['sha256']:
        return target
    target.unlink(missing_ok=True)

    request = urllib.request.Request(
        open_vsx_download_url(entry),
        headers={
            'Accept': 'application/octet-stream',
            'User-Agent': OPEN_VSX_USER_AGENT,
        },
    )
    with tempfile.NamedTemporaryFile(
        prefix='open-vsx-',
        suffix='.vsix',
        dir=cache_root,
        delete=False,
    ) as temporary:
        temporary_path = Path(temporary.name)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                shutil.copyfileobj(response, temporary)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise

    actual = sha256_file(temporary_path)
    if actual != entry['sha256']:
        temporary_path.unlink(missing_ok=True)
        raise BuildError(f'VSIX SHA-256 mismatch: {entry["id"]}')
    temporary_path.replace(target)
    return target


def materialize_vsix(entry: dict[str, Any], *, root: Path = ROOT) -> Path:
    source_type = entry['source']['type']
    if source_type == 'local-vsix':
        source_path = Path(entry['source']['path'])
        if not source_path.is_absolute():
            source_path = root / source_path
        source_path = source_path.resolve()
        require(source_path.is_file(), f'locked VSIX does not exist: {source_path}')
        require(
            source_path.suffix.lower() == '.vsix',
            f'local-vsix source must end in .vsix: {source_path}',
        )
        require(
            sha256_file(source_path) == entry['sha256'], f'VSIX SHA-256 mismatch: {entry["id"]}'
        )
        return source_path
    if source_type == 'open-vsx':
        return download_open_vsx(entry)
    raise BuildError(f'unsupported extension source type: {source_type}')


def validate_vsix(entry: dict[str, Any], source_path: Path) -> dict[str, Any]:
    manifest, actual_id = _load_vsix_manifest(source_path)
    require(
        actual_id == entry['id'],
        f'VSIX id mismatch: locked {entry["id"]}, package contains {actual_id}',
    )
    require(manifest.get('version') == entry['version'], f'VSIX version mismatch for {entry["id"]}')
    browser = manifest.get('browser')
    require(
        isinstance(browser, str) and browser.strip() != '',
        f'extension is not browser-compatible: {entry["id"]}',
    )

    browser_path = PurePosixPath('extension') / PurePosixPath(browser.lstrip('./'))
    with zipfile.ZipFile(source_path) as archive:
        names = set(archive.namelist())
        require(
            browser_path.as_posix() in names,
            f'VSIX browser entrypoint missing for {entry["id"]}: {browser}',
        )
    return manifest


def install_locked_extensions(
    dist: Path,
    lock_path: Path,
    *,
    root: Path = ROOT,
    license_policy_path: Path = ROOT / 'extensions/license-policy.json',
) -> list[dict[str, Any]]:
    lock = load_extension_lock(lock_path)
    policy = load_license_policy(license_policy_path)
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
        require(
            entry['id'] not in existing_ids,
            f'extension id already exists in distribution: {entry["id"]}',
        )
        vsix = materialize_vsix(entry, root=root)
        manifest = validate_vsix(entry, vsix)
        effective_license = enforce_license_policy(entry, manifest, policy)
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

        installed.append(
            {
                'id': entry['id'],
                'version': entry['version'],
                'sha256': entry['sha256'],
                'license': effective_license,
                'source': entry['source'],
            }
        )
        existing_ids.add(entry['id'])

    return installed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--lock', type=Path, default=ROOT / 'extensions/extensions.lock.json')
    parser.add_argument(
        '--license-policy', type=Path, default=ROOT / 'extensions/license-policy.json'
    )
    parser.add_argument('--dist', type=Path)
    args = parser.parse_args()
    lock = load_extension_lock(args.lock)
    policy = load_license_policy(args.license_policy)
    if args.dist is None:
        for entry in lock['extensions']:
            vsix = materialize_vsix(entry)
            manifest = validate_vsix(entry, vsix)
            enforce_license_policy(entry, manifest, policy)
        print(f'validated {len(lock["extensions"])} locked extension(s)')
        return
    installed = install_locked_extensions(
        args.dist.resolve(),
        args.lock.resolve(),
        license_policy_path=args.license_policy.resolve(),
    )
    print(f'installed {len(installed)} locked extension(s)')


if __name__ == '__main__':
    try:
        main()
    except BuildError as exc:
        raise SystemExit(str(exc)) from None
