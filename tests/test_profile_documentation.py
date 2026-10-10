from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import deployment_profile  # noqa: E402


class ProfileDocumentationTests(unittest.TestCase):
    @staticmethod
    def documented_grants(markdown: str) -> dict[str, dict[str, list[str]]]:
        """Read the Profile / Proposed API grants table in a contract document."""
        rows = re.findall(
            r'^\| `([a-z][a-z0-9-]*)` \| ([^|\n]+) \|',
            markdown,
            re.MULTILINE,
        )
        grants: dict[str, dict[str, list[str]]] = {}
        for profile_id, policy in rows:
            if policy.strip() == 'None':
                grants[profile_id] = {}
                continue
            identifiers = re.findall(r'`([^`]+)`', policy)
            if len(identifiers) < 2:
                raise AssertionError(f'invalid proposed API documentation for {profile_id}')
            grants[profile_id] = {identifiers[0]: identifiers[1:]}
        return grants

    def test_readme_and_support_contract_match_profile_grants(self):
        profile_files = sorted((ROOT / 'config/profiles').glob('*.json'))
        expected = {}
        for path in profile_files:
            profile = deployment_profile.load_profile(path.stem)
            expected[path.stem] = profile['documents']['proposedApi']['grants']
        self.assertTrue(expected)

        for filename in ('README.md', 'COMPATIBILITY.md'):
            with self.subTest(document=filename):
                markdown = (ROOT / filename).read_text(encoding='utf-8')
                self.assertIn('`config/deployment.json`', markdown)
                self.assertEqual(self.documented_grants(markdown), expected)

    def test_no_outdated_deployment_claims(self):
        for filename in ('README.md', 'COMPATIBILITY.md'):
            with self.subTest(document=filename):
                markdown = (ROOT / filename).read_text(encoding='utf-8')
                self.assertNotIn('not yet a selectable deployment-profile system', markdown)


if __name__ == '__main__':
    unittest.main()
