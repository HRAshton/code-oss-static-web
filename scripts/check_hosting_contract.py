#!/usr/bin/env python3
from __future__ import annotations

import argparse
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping

from common import BuildError, require


def validate_response(target: str, status: int, headers: Mapping[str, str]) -> None:
    require(status == 200, f'{target} hosting returned HTTP {status}')
    normalized = {key.lower(): value.strip() for key, value in headers.items()}
    content_type = normalized.get('content-type', '').lower()
    require(
        'text/html' in content_type,
        f'{target} index content type must be text/html',
    )

    if target == 'oci':
        expected = {
            'cache-control': 'no-cache',
            'cross-origin-opener-policy': 'same-origin',
            'cross-origin-embedder-policy': 'require-corp',
            'cross-origin-resource-policy': 'same-origin',
            'x-content-type-options': 'nosniff',
            'referrer-policy': 'no-referrer',
        }
        for name, value in expected.items():
            actual = normalized.get(name, '')
            require(
                actual == value,
                f'OCI header {name} mismatch: expected {value!r}, got {actual!r}',
            )
        # Only the shipped HTTP-only OCI server is iframe-neutral. A production
        # edge may intentionally add a policy, and is qualified separately.
        for name, value in headers.items():
            if name.lower() == 'x-frame-options':
                raise BuildError('OCI default must not send X-Frame-Options')
            if name.lower() == 'content-security-policy':
                directives = (
                    part.strip().split(None, 1)[0].lower()
                    for part in value.replace(',', ';').split(';')
                    if part.strip()
                )
                require(
                    'frame-ancestors' not in directives,
                    'OCI default must not send frame-ancestors CSP',
                )

        permissions = normalized.get('permissions-policy', '')
        for directive in ('camera=()', 'microphone=()', 'geolocation=()'):
            require(
                directive in permissions,
                f'OCI Permissions-Policy missing {directive}',
            )


def _require_module_javascript(url: str) -> None:
    base = url if url.endswith('/') else f'{url}/'
    module_url = urllib.parse.urljoin(base, 'static-bootstrap.mjs')
    try:
        with urllib.request.urlopen(module_url, timeout=15) as response:
            status = response.status
            headers = dict(response.headers.items())
    except urllib.error.URLError as exc:
        raise BuildError(f'OCI module request failed: {exc}') from exc
    require(status == 200, f'OCI module returned HTTP {status}')
    content_type = headers.get('Content-Type', '').split(';', 1)[0].strip().lower()
    require(
        content_type in {'application/javascript', 'text/javascript'},
        f'OCI module content type must be JavaScript, got {content_type!r}',
    )


def _require_missing_asset_404(url: str) -> None:
    base = url if url.endswith('/') else f'{url}/'
    missing_url = urllib.parse.urljoin(base, '__code_oss_missing_asset__.js')
    try:
        with urllib.request.urlopen(missing_url, timeout=15) as response:
            status = response.status
    except urllib.error.HTTPError as exc:
        status = exc.code
    except urllib.error.URLError as exc:
        raise BuildError(f'OCI missing-asset request failed: {exc}') from exc
    require(status == 404, f'OCI missing asset returned HTTP {status}, expected 404')


def check_url(target: str, url: str) -> None:
    try:
        with urllib.request.urlopen(url, timeout=15) as response:
            # Preserve repeated CSP / X-Frame-Options fields for policy checks.
            validate_response(target, response.status, response.headers)
    except urllib.error.URLError as exc:
        raise BuildError(f'{target} hosting request failed: {exc}') from exc
    if target == 'oci':
        _require_module_javascript(url)
        _require_missing_asset_404(url)


def main() -> None:
    parser = argparse.ArgumentParser(description='Validate static-host response contracts')
    parser.add_argument('--target', choices=('oci', 'pages'), required=True)
    parser.add_argument('--url', required=True)
    args = parser.parse_args()
    check_url(args.target, args.url)
    print(f'{args.target} hosting contract: ok')


if __name__ == '__main__':
    try:
        main()
    except BuildError as exc:
        raise SystemExit(str(exc)) from None
