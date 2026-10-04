#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import extension_lock
from common import ROOT, BuildError, require, sha256_file, write_json


def build_intake_record(
    *,
    vsix: Path,
    extension_id: str,
    version: str,
    license_name: str,
    original_source: str,
    reviewer: str,
    scan_result: str,
    approved_at: str,
    mirror_base_url: str,
    source_policy: dict[str, Any],
    license_policy: dict[str, Any],
) -> dict[str, Any]:
    require(vsix.is_file(), f'candidate VSIX missing: {vsix}')
    require(scan_result == 'clean', 'extension intake scan result must be clean')
    require(bool(reviewer.strip()), 'extension intake reviewer is required')
    require(bool(original_source.strip()), 'extension intake original source is required')
    try:
        approval_date = datetime.date.fromisoformat(approved_at)
    except ValueError as exc:
        raise BuildError('extension intake approved-at must be YYYY-MM-DD') from exc
    require(
        approval_date <= datetime.date.today(),
        'extension intake approved-at cannot be in the future',
    )

    digest = sha256_file(vsix)
    base = mirror_base_url.rstrip('/')
    parsed = urlsplit(base)
    extension_lock.url_origin(base, 'extension mirror base URL')
    require(
        parsed.query == '' and parsed.fragment == '',
        'extension mirror base URL must be stable',
    )
    mirror_url = f'{base}/sha256/{digest}/{extension_id}-{version}.vsix'

    entry: dict[str, Any] = {
        'id': extension_id,
        'version': version,
        'sha256': digest,
        'license': license_name,
        'source': {
            'type': 'mirror-vsix',
            'url': mirror_url,
        },
        'approval': {
            'reviewer': reviewer,
            'source': original_source,
            'scanResult': scan_result,
            'approvedAt': approved_at,
        },
    }
    extension_lock.enforce_source_policy(entry, source_policy)
    manifest = extension_lock.validate_vsix(entry, vsix)
    effective_license = extension_lock.enforce_license_policy(entry, manifest, license_policy)
    require(
        effective_license == license_name,
        f'extension intake license mismatch: expected {license_name}, got {effective_license}',
    )

    return {
        'schemaVersion': 1,
        'candidate': {
            'source': original_source,
            'sha256': digest,
            'size': vsix.stat().st_size,
        },
        'approval': entry['approval'],
        'mirror': {
            'url': mirror_url,
            'sha256': digest,
            'uploadRequired': True,
        },
        'lockEntry': entry,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Validate a candidate VSIX for internal mirror intake'
    )
    parser.add_argument('--vsix', type=Path, required=True)
    parser.add_argument('--id', required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--license', dest='license_name', required=True)
    parser.add_argument('--source', required=True)
    parser.add_argument('--reviewer', required=True)
    parser.add_argument('--scan-result', choices=['clean'], required=True)
    parser.add_argument('--approved-at', required=True)
    parser.add_argument('--mirror-base-url', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()

    record = build_intake_record(
        vsix=args.vsix.resolve(),
        extension_id=args.id,
        version=args.version,
        license_name=args.license_name,
        original_source=args.source,
        reviewer=args.reviewer,
        scan_result=args.scan_result,
        approved_at=args.approved_at,
        mirror_base_url=args.mirror_base_url,
        source_policy=extension_lock.load_source_policy(ROOT / 'extensions/source-policy.json'),
        license_policy=extension_lock.load_license_policy(ROOT / 'extensions/license-policy.json'),
    )
    write_json(args.output, record)
    print(f'extension intake validated: {args.id}@{args.version}')


if __name__ == '__main__':
    try:
        main()
    except BuildError as exc:
        raise SystemExit(str(exc)) from None
