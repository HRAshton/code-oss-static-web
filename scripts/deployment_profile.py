#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any, cast

from common import ROOT, BuildError, load_json, require, sha256_file

PROFILE_SCHEMA_VERSION = 1
SELECTOR_SCHEMA_VERSION = 1

BINDING_ROOTS = {
    'runtime': 'config/policies/runtime/',
    'network': 'config/policies/network/',
    'productTransform': 'config/policies/product/',
    'proposedApi': 'config/policies/proposed-api/',
    'webview': 'config/policies/webview/',
    'branding': 'config/policies/branding/',
    'support': 'config/policies/support/',
    'extensionLock': 'extensions/',
    'extensionLicensePolicy': 'extensions/',
    'extensionSourcePolicy': 'extensions/',
}


def _require_object(value: Any, label: str) -> dict[str, Any]:
    require(isinstance(value, dict), f'{label} must be an object')
    return cast(dict[str, Any], value)


def _require_exact_keys(value: dict[str, Any], keys: set[str], label: str) -> None:
    require(
        set(value) == keys,
        f'{label} keys mismatch: expected {sorted(keys)}, got {sorted(value)}',
    )


def _binding_path(root: Path, binding: str, value: Any) -> Path:
    require(isinstance(value, str) and bool(value), f'profile binding {binding} must be a string')
    require('\\' not in value, f'profile binding {binding} must use POSIX separators')
    posix = PurePosixPath(value)
    require(not posix.is_absolute(), f'profile binding {binding} must be repository-relative')
    require('..' not in posix.parts, f'profile binding {binding} must not traverse parents')
    prefix = BINDING_ROOTS[binding]
    require(value.startswith(prefix), f'profile binding {binding} must be under {prefix}')
    path = (root / value).resolve()
    resolved_root = root.resolve()
    require(
        path.is_relative_to(resolved_root), f'profile binding {binding} escapes repository root'
    )
    require(path.is_file(), f'profile binding {binding} does not exist: {value}')
    return path


def _canonical_digest(value: dict[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
    return hashlib.sha256(payload).hexdigest()


def load_profile(profile_id: str, *, root: Path = ROOT) -> dict[str, Any]:
    require(
        bool(profile_id)
        and all(char.islower() or char.isdigit() or char == '-' for char in profile_id),
        f'invalid deployment profile id: {profile_id!r}',
    )
    profile_path = root / 'config/profiles' / f'{profile_id}.json'
    require(profile_path.is_file(), f'unknown deployment profile: {profile_id}')
    profile = _require_object(load_json(profile_path), 'deployment profile')
    _require_exact_keys(profile, {'schemaVersion', 'id', 'bindings'}, 'deployment profile')
    require(
        profile['schemaVersion'] == PROFILE_SCHEMA_VERSION,
        'unsupported deployment profile schemaVersion',
    )
    require(profile['id'] == profile_id, 'deployment profile id does not match file name')
    bindings = _require_object(profile['bindings'], 'deployment profile bindings')
    _require_exact_keys(bindings, set(BINDING_ROOTS), 'deployment profile bindings')

    metadata_bindings: dict[str, dict[str, str]] = {}
    documents: dict[str, dict[str, Any]] = {}
    paths: dict[str, Path] = {}
    for binding in sorted(BINDING_ROOTS):
        path = _binding_path(root, binding, bindings[binding])
        relative = path.relative_to(root.resolve()).as_posix()
        metadata_bindings[binding] = {'path': relative, 'sha256': sha256_file(path)}
        documents[binding] = load_json(path)
        paths[binding] = path

    digest_payload = {
        'schemaVersion': PROFILE_SCHEMA_VERSION,
        'id': profile_id,
        'bindings': metadata_bindings,
    }
    return {
        'schemaVersion': PROFILE_SCHEMA_VERSION,
        'id': profile_id,
        'configSha256': _canonical_digest(digest_payload),
        'bindings': metadata_bindings,
        'documents': documents,
        'paths': paths,
    }


def load_selected_profile(*, root: Path = ROOT) -> dict[str, Any]:
    selector = _require_object(load_json(root / 'config/deployment.json'), 'deployment selector')
    _require_exact_keys(selector, {'schemaVersion', 'profile'}, 'deployment selector')
    require(
        selector['schemaVersion'] == SELECTOR_SCHEMA_VERSION,
        'unsupported deployment selector schemaVersion',
    )
    profile_id = selector['profile']
    require(
        isinstance(profile_id, str) and bool(profile_id),
        'deployment selector profile must be a string',
    )
    return load_profile(profile_id, root=root)


def profile_metadata(profile: dict[str, Any]) -> dict[str, Any]:
    return {
        'schemaVersion': PROFILE_SCHEMA_VERSION,
        'id': profile['id'],
        'configSha256': profile['configSha256'],
        'bindings': profile['bindings'],
    }


if __name__ == '__main__':
    try:
        print(json.dumps(profile_metadata(load_selected_profile()), indent=2, sort_keys=True))
    except BuildError as exc:
        raise SystemExit(str(exc)) from None
