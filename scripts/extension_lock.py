#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime
import json
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, cast
from urllib.parse import quote, urlsplit

from common import ROOT, WORK, BuildError, load_json, require, sha256_file

SUPPORTED_SCHEMA_VERSION = 1
OPEN_VSX_DEFAULT_REGISTRY = 'https://open-vsx.org'
OPEN_VSX_USER_AGENT = 'code-oss-static-web/1'
SOURCE_POLICY_SCHEMA_VERSION = 2

MAX_ARCHIVE_ENTRIES = 4096
MAX_ARCHIVE_FILE_SIZE = 64 * 1024 * 1024
MAX_ARCHIVE_TOTAL_SIZE = 256 * 1024 * 1024
MAX_ARCHIVE_COMPRESSION_RATIO = 200
COMPRESSION_RATIO_MIN_FILE_SIZE = 1024 * 1024
MAX_VSIX_ARCHIVE_SIZE = MAX_ARCHIVE_TOTAL_SIZE + 16 * 1024 * 1024
DOWNLOAD_CHUNK_SIZE = 1024 * 1024
EXTRACTION_CHUNK_SIZE = 1024 * 1024


def _require_string(value: Any, field: str) -> str:
    require(isinstance(value, str) and value.strip() != '', f'{field} must be a non-empty string')
    return value


def _url_origin(value: str, field: str) -> str:
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise BuildError(f'{field} is not a valid URL') from exc
    require(parsed.scheme.lower() == 'https', f'{field} must use HTTPS')
    require(
        parsed.username is None and parsed.password is None, f'{field} must not include credentials'
    )
    hostname = parsed.hostname
    require(hostname is not None, f'{field} must include a host')
    assert hostname is not None
    host = hostname.lower()
    if ':' in host:
        host = f'[{host}]'
    if port not in (None, 443):
        host = f'{host}:{port}'
    return f'https://{host}'


def _normalize_open_vsx_registry(value: Any, field: str) -> str:
    registry = _require_string(value, field).strip()
    try:
        parsed = urlsplit(registry)
    except ValueError as exc:
        raise BuildError(f'{field} is not a valid URL') from exc
    require(parsed.path in ('', '/'), f'{field} must not include a path')
    require(parsed.query == '', f'{field} must not include a query')
    require(parsed.fragment == '', f'{field} must not include a fragment')
    return _url_origin(registry, field)


def load_source_policy(path: Path) -> dict[str, Any]:
    data = load_json(path)
    version = data.get('schemaVersion')
    require(version in (1, SOURCE_POLICY_SCHEMA_VERSION), 'unsupported extension source policy schemaVersion')

    if version == 1:
        require(
            set(data) == {'schemaVersion', 'allowedOpenVsxRegistries', 'allowedOpenVsxDownloadOrigins'},
            'extension source policy keys mismatch',
        )
        mirror_origins_raw: list[object] = []
        require_mirror = False
    else:
        require(
            set(data)
            == {
                'schemaVersion',
                'allowedOpenVsxRegistries',
                'allowedOpenVsxDownloadOrigins',
                'allowedMirrorOrigins',
                'requireMirrorForLockedExtensions',
            },
            'extension source policy keys mismatch',
        )
        raw_mirrors = data.get('allowedMirrorOrigins')
        require(
            isinstance(raw_mirrors, list),
            'extension source policy allowedMirrorOrigins must be an array',
        )
        mirror_origins_raw = cast(list[object], raw_mirrors)
        require(
            all(isinstance(item, str) for item in mirror_origins_raw),
            'extension source policy allowedMirrorOrigins must be a string array',
        )
        require_mirror_value = data.get('requireMirrorForLockedExtensions')
        require(
            isinstance(require_mirror_value, bool),
            'extension source policy requireMirrorForLockedExtensions must be boolean',
        )
        require_mirror = require_mirror_value

    registries_value = data.get('allowedOpenVsxRegistries')
    require(
        isinstance(registries_value, list), 'extension source policy registries must be an array'
    )
    registries_raw = cast(list[object], registries_value)
    require(
        len(registries_raw) > 0 and all(isinstance(item, str) for item in registries_raw),
        'extension source policy allowedOpenVsxRegistries must be a non-empty string array',
    )
    registries = [
        _normalize_open_vsx_registry(item, 'extension source policy registry')
        for item in registries_raw
    ]
    require(
        len(set(registries)) == len(registries),
        'extension source policy allowedOpenVsxRegistries must be unique',
    )

    download_origins_value = data.get('allowedOpenVsxDownloadOrigins')
    require(
        isinstance(download_origins_value, list),
        'extension source policy download origins must be an array',
    )
    download_origins_raw = cast(list[object], download_origins_value)
    require(
        len(download_origins_raw) > 0
        and all(isinstance(item, str) for item in download_origins_raw),
        'extension source policy allowedOpenVsxDownloadOrigins must be a non-empty string array',
    )
    download_origins = [
        _normalize_open_vsx_registry(item, 'extension source policy download origin')
        for item in download_origins_raw
    ]
    require(
        len(set(download_origins)) == len(download_origins),
        'extension source policy allowedOpenVsxDownloadOrigins must be unique',
    )
    require(
        set(registries).issubset(download_origins),
        'extension source policy download origins must include all registry origins',
    )

    mirror_origins = [
        _normalize_open_vsx_registry(item, 'extension source policy mirror origin')
        for item in mirror_origins_raw
    ]
    require(
        len(set(mirror_origins)) == len(mirror_origins),
        'extension source policy allowedMirrorOrigins must be unique',
    )
    return {
        'schemaVersion': SOURCE_POLICY_SCHEMA_VERSION,
        'allowedOpenVsxRegistries': registries,
        'allowedOpenVsxDownloadOrigins': download_origins,
        'allowedMirrorOrigins': mirror_origins,
        'requireMirrorForLockedExtensions': require_mirror,
    }


def enforce_source_policy(entry: dict[str, Any], policy: dict[str, Any]) -> None:
    source_type = entry['source']['type']
    if policy.get('requireMirrorForLockedExtensions', False):
        require(
            source_type == 'mirror-vsix',
            f'production extension source must use the internal mirror: {entry["id"]}',
        )

    if source_type == 'open-vsx':
        registry = entry['source']['registry']
        require(
            registry in policy['allowedOpenVsxRegistries'],
            f'Open VSX registry is not allowed by production source policy: {registry}',
        )
        return

    if source_type == 'mirror-vsix':
        mirror_url = entry['source']['url']
        origin = _url_origin(mirror_url, 'extension mirror URL')
        allowed = set(cast(list[str], policy.get('allowedMirrorOrigins', [])))
        require(
            origin in allowed,
            f'extension mirror origin is not allowed by production source policy: {origin}',
        )


def _copy_download_bounded(source: Any, destination: Any) -> int:
    total = 0
    while True:
        chunk = source.read(DOWNLOAD_CHUNK_SIZE)
        if not chunk:
            return total
        total += len(chunk)
        require(
            total <= MAX_VSIX_ARCHIVE_SIZE,
            f'VSIX archive download exceeds limit: {total} > {MAX_VSIX_ARCHIVE_SIZE}',
        )
        destination.write(chunk)


class _SourcePolicyRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, allowed_origins: set[str]) -> None:
        super().__init__()
        self._allowed_origins = allowed_origins

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> urllib.request.Request | None:
        origin = _url_origin(newurl, 'Open VSX redirect target')
        require(
            origin in self._allowed_origins,
            f'Open VSX redirect target is not allowed by production source policy: {origin}',
        )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def load_extension_lock(path: Path) -> dict[str, Any]:
    data = load_json(path)
    require(
        data.get('schemaVersion') == SUPPORTED_SCHEMA_VERSION,
        'unsupported extension lock schemaVersion',
    )
    extensions_value = data.get('extensions')
    require(isinstance(extensions_value, list), 'extension lock extensions must be an array')
    extensions = cast(list[object], extensions_value)

    ids: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for index, raw_value in enumerate(extensions):
        prefix = f'extensions[{index}]'
        require(isinstance(raw_value, dict), f'{prefix} must be an object')
        raw = cast(dict[str, Any], raw_value)
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

        source_value = raw.get('source')
        require(isinstance(source_value, dict), f'{prefix}.source must be an object')
        source = cast(dict[str, Any], source_value)
        source_type = _require_string(source.get('type'), f'{prefix}.source.type')
        if source_type == 'local-vsix':
            normalized_source = {
                'type': source_type,
                'path': _require_string(source.get('path'), f'{prefix}.source.path'),
            }
        elif source_type == 'open-vsx':
            registry = _normalize_open_vsx_registry(
                source.get('registry', OPEN_VSX_DEFAULT_REGISTRY),
                f'{prefix}.source.registry',
            )
            normalized_source = {'type': source_type, 'registry': registry}
        elif source_type == 'mirror-vsix':
            mirror_url = _require_string(source.get('url'), f'{prefix}.source.url').strip()
            try:
                parsed_mirror = urlsplit(mirror_url)
            except ValueError as exc:
                raise BuildError(f'{prefix}.source.url is not a valid URL') from exc
            _url_origin(mirror_url, f'{prefix}.source.url')
            require(parsed_mirror.query == '', f'{prefix}.source.url must not include a query')
            require(parsed_mirror.fragment == '', f'{prefix}.source.url must not include a fragment')
            require(
                digest in parsed_mirror.path.lower(),
                f'{prefix}.source.url must include the locked SHA-256 in its path',
            )
            normalized_source = {'type': source_type, 'url': mirror_url}
        else:
            raise BuildError(f'unsupported extension source type: {source_type}')

        license_value = raw.get('license')
        if license_value is not None:
            _require_string(license_value, f'{prefix}.license')

        approval_value = raw.get('approval')
        normalized_approval: dict[str, str] | None = None
        if source_type == 'mirror-vsix':
            require(
                isinstance(license_value, str) and bool(license_value),
                f'{prefix}.license is required for mirrored extensions',
            )
            require(isinstance(approval_value, dict), f'{prefix}.approval must be an object')
            approval = cast(dict[str, Any], approval_value)
            require(
                set(approval) == {'reviewer', 'source', 'scanResult', 'approvedAt'},
                f'{prefix}.approval keys mismatch',
            )
            reviewer = _require_string(approval.get('reviewer'), f'{prefix}.approval.reviewer')
            original_source = _require_string(approval.get('source'), f'{prefix}.approval.source')
            scan_result = _require_string(
                approval.get('scanResult'), f'{prefix}.approval.scanResult'
            )
            require(scan_result == 'clean', f'{prefix}.approval.scanResult must be clean')
            approved_at = _require_string(
                approval.get('approvedAt'), f'{prefix}.approval.approvedAt'
            )
            try:
                datetime.date.fromisoformat(approved_at)
            except ValueError as exc:
                raise BuildError(f'{prefix}.approval.approvedAt must be YYYY-MM-DD') from exc
            normalized_approval = {
                'reviewer': reviewer,
                'source': original_source,
                'scanResult': scan_result,
                'approvedAt': approved_at,
            }
        else:
            require(
                approval_value is None,
                f'{prefix}.approval is only valid for mirror-vsix sources',
            )

        normalized_entry: dict[str, Any] = {
            'id': extension_id,
            'version': version,
            'sha256': digest,
            'license': license_value,
            'source': normalized_source,
        }
        if normalized_approval is not None:
            normalized_entry['approval'] = normalized_approval
        normalized.append(normalized_entry)

    return {'schemaVersion': SUPPORTED_SCHEMA_VERSION, 'extensions': normalized}


def load_license_policy(path: Path) -> dict[str, Any]:
    data = load_json(path)
    require(data.get('schemaVersion') == 1, 'unsupported extension license policy schemaVersion')
    allowed_value = data.get('allowed')
    denied_value = data.get('denied', [])
    overrides_value = data.get('overrides', {})
    require(
        isinstance(allowed_value, list)
        and all(isinstance(item, str) for item in cast(list[object], allowed_value)),
        'license policy allowed must be a string array',
    )
    require(
        isinstance(denied_value, list)
        and all(isinstance(item, str) for item in cast(list[object], denied_value)),
        'license policy denied must be a string array',
    )
    require(isinstance(overrides_value, dict), 'license policy overrides must be an object')
    allowed = cast(list[str], allowed_value)
    denied = cast(list[str], denied_value)
    overrides_raw = cast(dict[str, object], overrides_value)
    overrides: dict[str, list[str]] = {}
    for extension_id, licenses_value in overrides_raw.items():
        require(
            isinstance(licenses_value, list)
            and all(isinstance(item, str) for item in cast(list[object], licenses_value)),
            f'license policy override must be a string array: {extension_id}',
        )
        overrides[extension_id] = cast(list[str], licenses_value)
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
    result = archive.infolist()
    require(
        len(result) <= MAX_ARCHIVE_ENTRIES,
        f'VSIX contains too many entries: {len(result)} > {MAX_ARCHIVE_ENTRIES}',
    )

    total_size = 0
    for info in result:
        require('\\' not in info.filename, f'VSIX contains backslash path: {info.filename}')
        path = PurePosixPath(info.filename)
        require(not path.is_absolute(), f'VSIX contains absolute path: {info.filename}')
        require('..' not in path.parts, f'VSIX contains parent traversal: {info.filename}')
        first_part = path.parts[0] if path.parts else ''
        require(
            not (len(first_part) == 2 and first_part[0].isalpha() and first_part[1] == ':'),
            f'VSIX contains drive path: {info.filename}',
        )
        mode = (info.external_attr >> 16) & 0xFFFF
        require((mode & 0o170000) != 0o120000, f'VSIX contains symlink: {info.filename}')
        if info.is_dir():
            continue

        require(
            info.file_size <= MAX_ARCHIVE_FILE_SIZE,
            f'VSIX entry is too large: {info.filename}',
        )
        total_size += info.file_size
        require(total_size <= MAX_ARCHIVE_TOTAL_SIZE, 'VSIX expanded size exceeds limit')

        if info.file_size >= COMPRESSION_RATIO_MIN_FILE_SIZE:
            require(
                info.compress_size > 0
                and info.file_size <= info.compress_size * MAX_ARCHIVE_COMPRESSION_RATIO,
                f'VSIX entry compression ratio exceeds limit: {info.filename}',
            )
    return result


def _read_member_bounded(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> bytes:
    with archive.open(info, 'r') as source:
        data = source.read(MAX_ARCHIVE_FILE_SIZE + 1)
    require(len(data) <= MAX_ARCHIVE_FILE_SIZE, f'VSIX entry is too large: {info.filename}')
    require(len(data) == info.file_size, f'VSIX entry size mismatch: {info.filename}')
    return data


def _extract_members_bounded(
    archive: zipfile.ZipFile,
    destination: Path,
    members: list[zipfile.ZipInfo],
) -> None:
    total_written = 0
    for info in members:
        path = PurePosixPath(info.filename)
        target = destination.joinpath(*path.parts)
        if info.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue

        target.parent.mkdir(parents=True, exist_ok=True)
        file_written = 0
        with archive.open(info, 'r') as source, target.open('wb') as output:
            while True:
                chunk = source.read(EXTRACTION_CHUNK_SIZE)
                if not chunk:
                    break
                file_written += len(chunk)
                total_written += len(chunk)
                require(
                    file_written <= MAX_ARCHIVE_FILE_SIZE,
                    f'VSIX entry is too large while extracting: {info.filename}',
                )
                require(
                    total_written <= MAX_ARCHIVE_TOTAL_SIZE,
                    'VSIX expanded size exceeds limit while extracting',
                )
                output.write(chunk)
        require(file_written == info.file_size, f'VSIX entry size mismatch: {info.filename}')


def _load_vsix_manifest(vsix: Path) -> tuple[dict[str, Any], str]:
    try:
        with zipfile.ZipFile(vsix) as archive:
            members = _safe_members(archive)
            members_by_name = {info.filename: info for info in members}
            manifest_name = 'extension/package.json'
            manifest_info = members_by_name.get(manifest_name)
            require(manifest_info is not None, f'VSIX is missing {manifest_name}: {vsix}')
            assert manifest_info is not None
            try:
                manifest_value: object = json.loads(
                    _read_member_bounded(archive, manifest_info).decode('utf-8')
                )
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise BuildError(f'invalid VSIX package.json: {vsix}: {exc}') from exc
    except zipfile.BadZipFile as exc:
        raise BuildError(f'invalid VSIX zip archive: {vsix}') from exc

    require(isinstance(manifest_value, dict), f'VSIX package.json must be an object: {vsix}')
    manifest = cast(dict[str, Any], manifest_value)
    publisher = _require_string(manifest.get('publisher'), f'{vsix}: publisher')
    name = _require_string(manifest.get('name'), f'{vsix}: name')
    return manifest, f'{publisher}.{name}'


def download_open_vsx(
    entry: dict[str, Any],
    *,
    cache_root: Path = WORK / 'extensions-cache',
    source_policy: dict[str, Any] | None = None,
) -> Path:
    if source_policy is None:
        source_policy = load_source_policy(ROOT / 'extensions/source-policy.json')
    enforce_source_policy(entry, source_policy)
    allowed_download_origins = set(cast(list[str], source_policy['allowedOpenVsxDownloadOrigins']))

    cache_root.mkdir(parents=True, exist_ok=True)
    target = cache_root / f'{entry["id"]}-{entry["version"]}.vsix'
    if target.is_file():
        if target.stat().st_size > MAX_VSIX_ARCHIVE_SIZE:
            target.unlink()
            raise BuildError(f'cached VSIX archive exceeds size limit: {entry["id"]}')
        if sha256_file(target) == entry['sha256']:
            return target
        target.unlink()

    request = urllib.request.Request(
        open_vsx_download_url(entry),
        headers={
            'Accept': 'application/octet-stream',
            'User-Agent': OPEN_VSX_USER_AGENT,
        },
    )
    opener = urllib.request.build_opener(_SourcePolicyRedirectHandler(allowed_download_origins))
    with tempfile.NamedTemporaryFile(
        prefix='open-vsx-',
        suffix='.vsix',
        dir=cache_root,
        delete=False,
    ) as temporary:
        temporary_path = Path(temporary.name)
        try:
            with opener.open(request, timeout=60) as response:
                response_origin = _url_origin(response.geturl(), 'Open VSX response URL')
                require(
                    response_origin in allowed_download_origins,
                    f'Open VSX response URL is not allowed by production source policy: '
                    f'{response_origin}',
                )
                _copy_download_bounded(response, temporary)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise

    actual = sha256_file(temporary_path)
    if actual != entry['sha256']:
        temporary_path.unlink(missing_ok=True)
        raise BuildError(f'VSIX SHA-256 mismatch: {entry["id"]}')
    temporary_path.replace(target)
    return target


def download_mirror_vsix(
    entry: dict[str, Any],
    *,
    cache_root: Path = WORK / 'extensions-cache',
    source_policy: dict[str, Any] | None = None,
) -> Path:
    if source_policy is None:
        source_policy = load_source_policy(ROOT / 'extensions/source-policy.json')
    enforce_source_policy(entry, source_policy)
    allowed_origins = set(cast(list[str], source_policy['allowedMirrorOrigins']))

    cache_root.mkdir(parents=True, exist_ok=True)
    target = cache_root / f'{entry["id"]}-{entry["version"]}.vsix'
    if target.is_file():
        if target.stat().st_size > MAX_VSIX_ARCHIVE_SIZE:
            target.unlink()
            raise BuildError(f'cached VSIX archive exceeds size limit: {entry["id"]}')
        if sha256_file(target) == entry['sha256']:
            return target
        target.unlink()

    request = urllib.request.Request(
        entry['source']['url'],
        headers={
            'Accept': 'application/octet-stream',
            'User-Agent': OPEN_VSX_USER_AGENT,
        },
    )
    opener = urllib.request.build_opener(_SourcePolicyRedirectHandler(allowed_origins))
    with tempfile.NamedTemporaryFile(
        prefix='mirror-vsix-',
        suffix='.vsix',
        dir=cache_root,
        delete=False,
    ) as temporary:
        temporary_path = Path(temporary.name)
        try:
            with opener.open(request, timeout=60) as response:
                response_origin = _url_origin(response.geturl(), 'extension mirror response URL')
                require(
                    response_origin in allowed_origins,
                    f'extension mirror response URL is not allowed by production source policy: '
                    f'{response_origin}',
                )
                _copy_download_bounded(response, temporary)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise

    actual = sha256_file(temporary_path)
    if actual != entry['sha256']:
        temporary_path.unlink(missing_ok=True)
        raise BuildError(f'VSIX SHA-256 mismatch: {entry["id"]}')
    temporary_path.replace(target)
    return target


def materialize_vsix(
    entry: dict[str, Any],
    *,
    root: Path = ROOT,
    source_policy: dict[str, Any] | None = None,
) -> Path:
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
            source_path.stat().st_size <= MAX_VSIX_ARCHIVE_SIZE,
            f'VSIX archive exceeds size limit: {entry["id"]}',
        )
        require(
            sha256_file(source_path) == entry['sha256'], f'VSIX SHA-256 mismatch: {entry["id"]}'
        )
        return source_path
    if source_type == 'open-vsx':
        return download_open_vsx(entry, source_policy=source_policy)
    if source_type == 'mirror-vsix':
        return download_mirror_vsix(entry, source_policy=source_policy)
    raise BuildError(f'unsupported extension source type: {source_type}')


def validate_local_vsix(entry: dict[str, Any], *, root: Path = ROOT) -> dict[str, Any]:
    source = entry.get('source')
    if not isinstance(source, dict):
        raise BuildError('local VSIX source must be an object')
    source = cast(dict[str, Any], source)
    source_type = source.get('type')
    require(source_type == 'local-vsix', 'extension source must be local-vsix')
    source_path = materialize_vsix(entry, root=root)
    return validate_vsix(entry, source_path)


def validate_vsix(entry: dict[str, Any], source_path: Path) -> dict[str, Any]:
    manifest, actual_id = _load_vsix_manifest(source_path)
    require(
        actual_id == entry['id'],
        f'VSIX id mismatch: locked {entry["id"]}, package contains {actual_id}',
    )
    require(manifest.get('version') == entry['version'], f'VSIX version mismatch for {entry["id"]}')
    browser = manifest.get('browser')
    if not isinstance(browser, str) or browser.strip() == '':
        raise BuildError(f'extension is not browser-compatible: {entry["id"]}')

    browser_path = PurePosixPath('extension') / PurePosixPath(browser.lstrip('./'))
    with zipfile.ZipFile(source_path) as archive:
        names = {info.filename for info in _safe_members(archive)}
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
    source_policy_path: Path = ROOT / 'extensions/source-policy.json',
) -> list[dict[str, Any]]:
    lock = load_extension_lock(lock_path)
    policy = load_license_policy(license_policy_path)
    source_policy = load_source_policy(source_policy_path)
    installed: list[dict[str, Any]] = []
    extroot = dist / 'extensions'
    extroot.mkdir(parents=True, exist_ok=True)

    existing_ids: set[str] = set()
    for package_json in extroot.glob('*/package.json'):
        try:
            manifest_value: object = json.loads(package_json.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(manifest_value, dict):
            continue
        manifest = cast(dict[str, Any], manifest_value)
        publisher = manifest.get('publisher')
        name = manifest.get('name')
        if isinstance(publisher, str) and isinstance(name, str):
            existing_ids.add(f'{publisher}.{name}')

    for entry in lock['extensions']:
        enforce_source_policy(entry, source_policy)
        require(
            entry['id'] not in existing_ids,
            f'extension id already exists in distribution: {entry["id"]}',
        )
        vsix = materialize_vsix(entry, root=root, source_policy=source_policy)
        manifest = validate_vsix(entry, vsix)
        effective_license = enforce_license_policy(entry, manifest, policy)
        destination = extroot / entry['id']
        require(not destination.exists(), f'extension destination already exists: {destination}')

        with tempfile.TemporaryDirectory(prefix='code-oss-static-web-vsix-') as td:
            temp = Path(td)
            with zipfile.ZipFile(vsix) as archive:
                members = _safe_members(archive)
                _extract_members_bounded(archive, temp, members)
            extracted = temp / 'extension'
            require(extracted.is_dir(), f'VSIX extension directory missing: {vsix}')
            shutil.copytree(extracted, destination, symlinks=False)

        installed_entry: dict[str, Any] = {
            'id': entry['id'],
            'version': entry['version'],
            'sha256': entry['sha256'],
            'license': effective_license,
            'source': entry['source'],
        }
        if 'approval' in entry:
            installed_entry['approval'] = entry['approval']
        installed.append(installed_entry)
        existing_ids.add(entry['id'])

    return installed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--lock', type=Path, default=ROOT / 'extensions/extensions.lock.json')
    parser.add_argument(
        '--license-policy', type=Path, default=ROOT / 'extensions/license-policy.json'
    )
    parser.add_argument(
        '--source-policy', type=Path, default=ROOT / 'extensions/source-policy.json'
    )
    parser.add_argument('--dist', type=Path)
    args = parser.parse_args()
    lock = load_extension_lock(args.lock)
    policy = load_license_policy(args.license_policy)
    source_policy = load_source_policy(args.source_policy)
    if args.dist is None:
        for entry in lock['extensions']:
            enforce_source_policy(entry, source_policy)
            vsix = materialize_vsix(entry, source_policy=source_policy)
            manifest = validate_vsix(entry, vsix)
            enforce_license_policy(entry, manifest, policy)
        print(f'validated {len(lock["extensions"])} locked extension(s)')
        return
    installed = install_locked_extensions(
        args.dist.resolve(),
        args.lock.resolve(),
        license_policy_path=args.license_policy.resolve(),
        source_policy_path=args.source_policy.resolve(),
    )
    print(f'installed {len(installed)} locked extension(s)')


if __name__ == '__main__':
    try:
        main()
    except BuildError as exc:
        raise SystemExit(str(exc)) from None
