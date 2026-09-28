#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from common import ROOT, BuildError, load_json, require
from extension_lock import load_extension_lock, load_license_policy

COMMIT_RE = re.compile(r'^[0-9a-f]{40}$')
DIGEST_RE = re.compile(r'^[0-9a-f]{64}$')


def require_object(value: Any, label: str) -> dict[str, Any]:
    require(isinstance(value, dict), f'{label} must be an object')
    return value


def require_exact_keys(value: dict[str, Any], keys: set[str], label: str) -> None:
    actual = set(value)
    require(actual == keys, f'{label} keys mismatch: expected {sorted(keys)}, got {sorted(actual)}')


def validate_upstream_lock(path: Path) -> None:
    data = require_object(load_json(path), 'upstream lock')
    require_exact_keys(
        data,
        {
            'schemaVersion',
            'repository',
            'tag',
            'commit',
            'sourceDateEpoch',
            'qualified',
            'qualificationNote',
        },
        'upstream lock',
    )
    require(data['schemaVersion'] == 1, 'upstream lock schemaVersion must be 1')
    require(data['repository'] == 'https://github.com/microsoft/vscode.git', 'unexpected upstream repository')
    require(isinstance(data['tag'], str) and data['tag'], 'upstream tag must be a string')
    require(isinstance(data['commit'], str) and COMMIT_RE.fullmatch(data['commit']) is not None, 'upstream commit must be a full SHA')
    require(isinstance(data['sourceDateEpoch'], int) and data['sourceDateEpoch'] > 0, 'sourceDateEpoch must be a positive integer')
    require(isinstance(data['qualified'], bool), 'qualified must be boolean')
    require(isinstance(data['qualificationNote'], str) and data['qualificationNote'], 'qualificationNote must be non-empty')


def validate_runtime(path: Path) -> None:
    data = require_object(load_json(path), 'runtime config')
    require_exact_keys(
        data,
        {'schemaVersion', 'productName', 'telemetry', 'gallery', 'webviews'},
        'runtime config',
    )
    require(data['schemaVersion'] == 1, 'runtime schemaVersion must be 1')
    require(isinstance(data['productName'], str) and data['productName'], 'runtime productName must be non-empty')
    require(data['telemetry'] is False, 'base runtime telemetry must be false')
    gallery = require_object(data['gallery'], 'runtime gallery')
    require_exact_keys(gallery, {'mode'}, 'runtime gallery')
    require(gallery['mode'] in {'disabled'}, 'unsupported base gallery mode')
    webviews = require_object(data['webviews'], 'runtime webviews')
    require_exact_keys(webviews, {'mode'}, 'runtime webviews')
    require(webviews['mode'] == 'disabled', 'base webviews must fail closed')


def validate_network_policy(path: Path) -> None:
    data = require_object(load_json(path), 'network policy')
    require_exact_keys(data, {'schemaVersion', 'default', 'allowedOrigins'}, 'network policy')
    require(data['schemaVersion'] == 1, 'network policy schemaVersion must be 1')
    require(data['default'] == 'deny', 'network policy must default deny')
    require(data['allowedOrigins'] == ['self'], 'base network policy must allow self only')


def validate_product_transform(path: Path) -> None:
    data = require_object(load_json(path), 'product transform')
    require_exact_keys(data, {'schemaVersion', 'set', 'remove'}, 'product transform')
    require(data['schemaVersion'] == 1, 'product transform schemaVersion must be 1')
    set_values = require_object(data['set'], 'product transform set')
    remove_values = data['remove']
    require(isinstance(remove_values, list) and all(isinstance(item, str) for item in remove_values), 'product transform remove must be a string array')
    require(set_values.get('builtInExtensions') == [], 'upstream downloaded built-in extensions must be removed')
    require(set_values.get('builtInExtensionsEnabledWithAutoUpdates') == [], 'built-in auto updates must be disabled')
    webview_url = set_values.get('webviewContentExternalBaseUrlTemplate')
    require(isinstance(webview_url, str) and 'invalid.invalid' in webview_url, 'webview URL must fail closed')
    chat = require_object(set_values.get('defaultChatAgent'), 'defaultChatAgent')
    for key, value in chat.items():
        if key.endswith('Url') and isinstance(value, str):
            require('invalid.invalid' in value, f'defaultChatAgent URL must fail closed: {key}')


def validate_patch_manifest(path: Path) -> None:
    data = require_object(load_json(path), 'patch manifest')
    require_exact_keys(data, {'schemaVersion', 'patches'}, 'patch manifest')
    require(data['schemaVersion'] == 1, 'patch manifest schemaVersion must be 1')
    patches = data['patches']
    require(isinstance(patches, list), 'patch manifest patches must be an array')
    ids: set[str] = set()
    for index, patch in enumerate(patches):
        patch = require_object(patch, f'patches[{index}]')
        require('file' in patch, f'patches[{index}] missing file')
        require(isinstance(patch['file'], str) and patch['file'].endswith('.patch'), f'patches[{index}] file must end in .patch')
        patch_id = patch.get('id', patch['file'])
        require(isinstance(patch_id, str) and patch_id not in ids, f'duplicate patch id: {patch_id}')
        ids.add(patch_id)


def validate_json_syntax() -> None:
    roots = [ROOT / 'config', ROOT / 'extensions', ROOT / 'patches']
    paths = [ROOT / 'upstream.lock.json']
    for root in roots:
        paths.extend(sorted(root.rglob('*.json')))
    for path in paths:
        try:
            json.loads(path.read_text(encoding='utf-8'))
        except json.JSONDecodeError as exc:
            raise BuildError(f'invalid JSON: {path.relative_to(ROOT)}: {exc}') from exc


def validate_all() -> None:
    validate_json_syntax()
    validate_upstream_lock(ROOT / 'upstream.lock.json')
    validate_runtime(ROOT / 'config/runtime.json')
    validate_network_policy(ROOT / 'config/network-policy.json')
    validate_product_transform(ROOT / 'config/product-transform.json')
    validate_patch_manifest(ROOT / 'patches/manifest.json')
    load_extension_lock(ROOT / 'extensions/extensions.lock.json')
    load_license_policy(ROOT / 'extensions/license-policy.json')


def main() -> None:
    validate_all()
    print('configuration validation: ok')


if __name__ == '__main__':
    try:
        main()
    except BuildError as exc:
        raise SystemExit(str(exc))
