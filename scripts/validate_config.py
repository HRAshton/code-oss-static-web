#!/usr/bin/env python3
from __future__ import annotations

import datetime
import json
import re
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit

from common import ROOT, BuildError, load_json, require
from deployment_profile import load_profile, load_selected_profile
from extension_lock import (
    enforce_source_policy,
    load_extension_lock,
    load_license_policy,
    load_source_policy,
)
from promotion import load_promotion_policy

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
        },
        'upstream lock',
    )
    require(data['schemaVersion'] == 1, 'upstream lock schemaVersion must be 1')
    require(
        data['repository'] == 'https://github.com/microsoft/vscode.git',
        'unexpected upstream repository',
    )
    require(isinstance(data['tag'], str) and bool(data['tag']), 'upstream tag must be a string')
    require(
        isinstance(data['commit'], str) and COMMIT_RE.fullmatch(data['commit']) is not None,
        'upstream commit must be a full SHA',
    )
    require(
        isinstance(data['sourceDateEpoch'], int) and data['sourceDateEpoch'] > 0,
        'sourceDateEpoch must be a positive integer',
    )


def validate_runtime(path: Path) -> None:
    data = require_object(load_json(path), 'runtime config')
    require_exact_keys(
        data,
        {'schemaVersion', 'productName', 'telemetry', 'gallery', 'webviews'},
        'runtime config',
    )
    require(data['schemaVersion'] == 1, 'runtime schemaVersion must be 1')
    require(
        isinstance(data['productName'], str) and bool(data['productName']),
        'runtime productName must be non-empty',
    )
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
    require(
        isinstance(remove_values, list)
        and all(isinstance(item, str) for item in cast(list[object], remove_values)),
        'product transform remove must be a string array',
    )
    require(
        set_values.get('builtInExtensions') == [],
        'upstream downloaded built-in extensions must be removed',
    )
    require(
        set_values.get('builtInExtensionsEnabledWithAutoUpdates') == [],
        'built-in auto updates must be disabled',
    )
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
        require(
            isinstance(patch['file'], str) and patch['file'].endswith('.patch'),
            f'patches[{index}] file must end in .patch',
        )
        patch_id = patch.get('id', patch['file'])
        require(
            isinstance(patch_id, str) and patch_id not in ids, f'duplicate patch id: {patch_id}'
        )
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


def validate_proposed_api_policy(data: dict[str, Any]) -> None:
    allowed_keys = {'schemaVersion', 'grants', 'approval'}
    require(set(data) <= allowed_keys, 'proposed API policy contains unknown keys')
    require({'schemaVersion', 'grants'} <= set(data), 'proposed API policy required keys missing')
    require(data['schemaVersion'] == 1, 'proposed API policy schemaVersion must be 1')
    grants = require_object(data['grants'], 'proposed API grants')
    for extension_id, raw_proposals in grants.items():
        require(bool(extension_id), 'proposed API extension id invalid')
        require(
            isinstance(raw_proposals, list)
            and all(
                isinstance(item, str) and bool(item) for item in cast(list[object], raw_proposals)
            ),
            f'proposed API grants must be string arrays: {extension_id}',
        )
        proposals = cast(list[str], raw_proposals)
        require(
            len(proposals) == len(set(proposals)),
            f'proposed API grants must not contain duplicates: {extension_id}',
        )

    if grants:
        approval = require_object(data.get('approval'), 'proposed API approval')
        require_exact_keys(
            approval,
            {'extensionId', 'reviewer', 'reason', 'expires'},
            'proposed API approval',
        )
        require(
            approval['extensionId'] in grants and len(grants) == 1,
            'proposed API approval must bind the single granted extension id',
        )
        for key in ('reviewer', 'reason', 'expires'):
            require(
                isinstance(approval[key], str) and bool(approval[key]),
                f'proposed API approval {key} must be non-empty',
            )
        try:
            expiry = datetime.date.fromisoformat(cast(str, approval['expires']))
        except ValueError as exc:
            raise BuildError('proposed API approval expires must be YYYY-MM-DD') from exc
        require(expiry >= datetime.date.today(), 'proposed API approval has expired')
    else:
        require(
            'approval' not in data,
            'empty proposed API policy must not carry approval metadata',
        )


def validate_webview_policy(data: dict[str, Any]) -> None:
    require_exact_keys(
        data,
        {'schemaVersion', 'mode', 'externalBaseUrlTemplate'},
        'webview policy',
    )
    require(data['schemaVersion'] == 1, 'webview policy schemaVersion must be 1')
    require(data['mode'] == 'disabled', 'unsupported webview mode')
    template_value = data['externalBaseUrlTemplate']
    require(isinstance(template_value, str), 'disabled webview template must be a string')
    template = cast(str, template_value)
    try:
        parsed = urlsplit(template)
        port = parsed.port
    except ValueError as exc:
        raise BuildError('disabled webview template must be a valid URL') from exc
    hostname = parsed.hostname
    require(parsed.scheme.lower() == 'https', 'disabled webview template must use HTTPS')
    require(
        parsed.username is None and parsed.password is None,
        'disabled webview template must not include credentials',
    )
    require(
        hostname is not None
        and (hostname == 'invalid.invalid' or hostname.endswith('.invalid.invalid')),
        'disabled webview hostname must be invalid.invalid or a subdomain',
    )
    require(port in (None, 443), 'disabled webview template must use the default HTTPS port')


def validate_profile_documents(profile: dict[str, Any], *, baseline: bool = False) -> None:
    documents = profile['documents']
    validate_runtime(profile['paths']['runtime'])
    validate_network_policy(profile['paths']['network'])
    validate_product_transform(profile['paths']['productTransform'])
    validate_proposed_api_policy(documents['proposedApi'])
    validate_webview_policy(documents['webview'])

    branding = require_object(documents['branding'], 'branding policy')
    require_exact_keys(branding, {'schemaVersion', 'title'}, 'branding policy')
    require(branding['schemaVersion'] == 1, 'branding policy schemaVersion must be 1')
    require(
        branding['title'] == documents['runtime']['productName'],
        'branding title must match runtime productName',
    )

    support = require_object(documents['support'], 'support policy')
    require_exact_keys(
        support,
        {'schemaVersion', 'issuesUrl', 'securityPolicyPath'},
        'support policy',
    )
    require(support['schemaVersion'] == 1, 'support policy schemaVersion must be 1')

    extension_lock = load_extension_lock(profile['paths']['extensionLock'])
    load_license_policy(profile['paths']['extensionLicensePolicy'])
    source_policy = load_source_policy(profile['paths']['extensionSourcePolicy'])
    for entry in extension_lock['extensions']:
        enforce_source_policy(entry, source_policy)

    require(documents['runtime']['telemetry'] is False, 'profile runtime telemetry must be false')
    require(
        documents['runtime']['gallery']['mode'] == 'disabled', 'profile gallery must be disabled'
    )
    require(
        documents['runtime']['webviews']['mode'] == 'disabled',
        'profile runtime webviews must be disabled',
    )
    require(documents['network']['default'] == 'deny', 'profile network must default deny')
    require(
        documents['network']['allowedOrigins'] == ['self'], 'profile network must allow self only'
    )
    require(documents['webview']['mode'] == 'disabled', 'profile webviews must fail closed')

    if baseline:
        require(
            documents['proposedApi']['grants'] == {},
            'baseline-static must not grant proposed APIs',
        )


def validate_all() -> None:
    validate_json_syntax()
    validate_upstream_lock(ROOT / 'upstream.lock.json')
    validate_patch_manifest(ROOT / 'patches/manifest.json')
    load_promotion_policy(ROOT / 'config/promotion-policy.json')
    load_selected_profile()

    profiles: dict[str, dict[str, Any]] = {}
    for path in sorted((ROOT / 'config/profiles').glob('*.json')):
        profile_id = path.stem
        profile = load_profile(profile_id)
        validate_profile_documents(profile, baseline=profile_id == 'baseline-static')
        profiles[profile_id] = profile

    require('company-standard' in profiles, 'company-standard deployment profile missing')
    require(
        profiles['company-standard']['documents']['proposedApi']['grants'] == {},
        'company-standard must not grant proposed APIs',
    )


def main() -> None:
    validate_all()
    print('configuration validation: ok')


if __name__ == '__main__':
    try:
        main()
    except BuildError as exc:
        raise SystemExit(str(exc)) from None
