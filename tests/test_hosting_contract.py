from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
SPEC = importlib.util.spec_from_file_location(
    'check_hosting_contract',
    ROOT / 'scripts/check_hosting_contract.py',
)
assert SPEC is not None and SPEC.loader is not None
check_hosting_contract = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check_hosting_contract)


class HostingContractTests(unittest.TestCase):
    @staticmethod
    def _oci_headers() -> dict[str, str]:
        return {
            'Content-Type': 'text/html; charset=utf-8',
            'Cache-Control': 'no-cache',
            'Cross-Origin-Opener-Policy': 'same-origin',
            'Cross-Origin-Embedder-Policy': 'require-corp',
            'Cross-Origin-Resource-Policy': 'same-origin',
            'X-Content-Type-Options': 'nosniff',
            'Referrer-Policy': 'no-referrer',
            'Permissions-Policy': 'camera=(), microphone=(), geolocation=()',
        }

    def test_oci_contract_requires_explicit_security_and_cache_headers(self) -> None:
        check_hosting_contract.validate_response('oci', 200, self._oci_headers())

    def test_oci_contract_rejects_wrong_cache_semantics(self) -> None:
        with self.assertRaisesRegex(
            check_hosting_contract.BuildError,
            'cache-control mismatch',
        ):
            check_hosting_contract.validate_response(
                'oci',
                200,
                {
                    'Content-Type': 'text/html',
                    'Cache-Control': 'public, max-age=86400',
                    'Cross-Origin-Opener-Policy': 'same-origin',
                    'Cross-Origin-Embedder-Policy': 'require-corp',
                    'Cross-Origin-Resource-Policy': 'same-origin',
                    'X-Content-Type-Options': 'nosniff',
                    'Referrer-Policy': 'no-referrer',
                    'Permissions-Policy': 'camera=(), microphone=(), geolocation=()',
                },
            )

    def test_oci_contract_rejects_anti_framing_headers(self) -> None:
        for name, value in (
            ('X-Frame-Options', 'DENY'),
            ('Content-Security-Policy', "default-src 'self'; frame-ancestors 'none'"),
            ('Content-Security-Policy', 'FRAME-ANCESTORS https://portal.example.com'),
        ):
            with self.subTest(header=name, value=value):
                headers = self._oci_headers()
                headers[name] = value
                with self.assertRaisesRegex(
                    check_hosting_contract.BuildError,
                    'must not send',
                ):
                    check_hosting_contract.validate_response('oci', 200, headers)

    def test_default_oci_host_is_iframe_neutral(self) -> None:
        nginx = (ROOT / 'deploy/nginx.conf').read_text().lower()
        self.assertNotIn('frame-ancestors', nginx)
        self.assertNotIn('x-frame-options', nginx)

    def test_nginx_contract_serves_modules_as_javascript(self) -> None:
        nginx = (ROOT / 'deploy/nginx.conf').read_text()
        self.assertIn(r'location ~ \.mjs$', nginx)
        self.assertIn('default_type application/javascript;', nginx)

    def test_nginx_contract_does_not_rewrite_missing_assets(self) -> None:
        nginx = (ROOT / 'deploy/nginx.conf').read_text()
        self.assertIn('try_files $uri $uri/ =404;', nginx)
        self.assertNotIn('/index.html;', nginx)

    def test_pages_contract_checks_reachability_without_claiming_header_control(self) -> None:
        check_hosting_contract.validate_response(
            'pages',
            200,
            {
                'Content-Type': 'text/html; charset=utf-8',
                'Cache-Control': 'max-age=600',
            },
        )


if __name__ == '__main__':
    unittest.main()
