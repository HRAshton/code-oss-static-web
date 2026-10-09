from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import render_codeowners  # noqa: E402
from common import BuildError  # noqa: E402


class OrganizationCodeownersTests(unittest.TestCase):
    def test_team_codeowners_are_role_separated(self) -> None:
        config = render_codeowners.mapping(
            'example-company',
            {
                'platform': 'platform',
                'security': 'security',
                'release': 'release',
                'extensionPolicy': 'extension-policy',
                'legal': 'legal',
            },
        )
        rendered = render_codeowners.render_codeowners(config)
        self.assertIn('/.github/ @example-company/platform @example-company/security', rendered)
        self.assertIn('/deploy/ @example-company/release @example-company/platform', rendered)
        self.assertIn(
            '/docs/organization-migration.md '
            '@example-company/platform @example-company/security @example-company/release',
            rendered,
        )
        self.assertIn(
            '/extensions/license-policy.json @example-company/legal @example-company/extension-policy',
            rendered,
        )
        self.assertIn(
            '/docs/extension-mirror.md '
            '@example-company/extension-policy @example-company/security @example-company/platform',
            rendered,
        )
        self.assertNotIn('@HRAshton', rendered)
        self.assertNotIn('@vodyanica', rendered)
        self.assertNotIn('/upstream.lock.json', rendered)
        self.assertNotIn('/builder-apt-snapshot.json', rendered)
        self.assertIn(
            '/builder-image.json @example-company/platform @example-company/security',
            rendered,
        )

    def test_roles_cannot_collapse_to_one_team(self) -> None:
        with self.assertRaisesRegex(BuildError, 'distinct team slugs'):
            render_codeowners.mapping(
                'example-company',
                {
                    'platform': 'owners',
                    'security': 'owners',
                    'release': 'release',
                    'extensionPolicy': 'extension-policy',
                    'legal': 'legal',
                },
            )


if __name__ == '__main__':
    unittest.main()
