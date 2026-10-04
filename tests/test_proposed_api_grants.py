from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import deployment_profile  # noqa: E402
import prepare_upstream  # noqa: E402
import validate_config  # noqa: E402
from common import BuildError  # noqa: E402


class ProposedApiGrantTests(unittest.TestCase):
    def test_company_standard_has_no_proposed_api_grants(self):
        selected = deployment_profile.load_selected_profile()
        self.assertEqual(selected['id'], 'company-standard')
        self.assertEqual(selected['documents']['proposedApi']['grants'], {})

        company = deployment_profile.load_profile('company-standard')
        baseline = deployment_profile.load_profile('baseline-static')
        self.assertEqual(company['documents']['proposedApi']['grants'], {})
        self.assertEqual(baseline['documents']['proposedApi']['grants'], {})

    def test_remotish_compatibility_is_explicit_opt_in(self):
        profile = deployment_profile.load_profile('remotish-compat')
        policy = profile['documents']['proposedApi']
        self.assertEqual(
            policy['grants'],
            {'hrashton.remotish': ['scmHistoryProvider', 'timeline']},
        )
        self.assertEqual(policy['approval']['extensionId'], 'hrashton.remotish')
        self.assertTrue(policy['approval']['reviewer'])
        self.assertTrue(policy['approval']['reason'])
        self.assertTrue(policy['approval']['expires'])

        extension_lock = json.loads((ROOT / 'extensions/extensions.lock.json').read_text())
        bundled_ids = {entry.get('id') for entry in extension_lock['extensions']}
        self.assertNotIn('hrashton.remotish', bundled_ids)

    def test_expired_approval_fails_even_for_an_opt_in_profile(self):
        policy = {
            'schemaVersion': 1,
            'grants': {'hrashton.remotish': ['scmHistoryProvider']},
            'approval': {
                'extensionId': 'hrashton.remotish',
                'reviewer': 'extension-policy',
                'reason': 'compatibility',
                'expires': '2020-01-01',
            },
        }
        with self.assertRaisesRegex(BuildError, 'approval has expired'):
            validate_config.validate_proposed_api_policy(policy)

    def test_duplicate_proposals_fail_closed(self):
        policy = {
            'schemaVersion': 1,
            'grants': {
                'hrashton.remotish': [
                    'scmHistoryProvider',
                    'scmHistoryProvider',
                ]
            },
            'approval': {
                'extensionId': 'hrashton.remotish',
                'reviewer': 'extension-policy',
                'reason': 'compatibility',
                'expires': '2027-04-01',
            },
        }
        with self.assertRaisesRegex(BuildError, 'must not contain duplicates'):
            validate_config.validate_proposed_api_policy(policy)

    def test_proposal_validation_accepts_existing_definitions(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td)
            proposals = src / 'src/vscode-dts'
            proposals.mkdir(parents=True)
            (proposals / 'vscode.proposed.scmHistoryProvider.d.ts').write_text('')
            (proposals / 'vscode.proposed.timeline.d.ts').write_text('')

            prepare_upstream.validate_enabled_api_proposals(
                src,
                {'hrashton.remotish': ['scmHistoryProvider', 'timeline']},
            )

    def test_proposal_validation_rejects_removed_definition(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td)
            (src / 'src/vscode-dts').mkdir(parents=True)

            with self.assertRaisesRegex(BuildError, 'scmHistoryProvider'):
                prepare_upstream.validate_enabled_api_proposals(
                    src,
                    {'hrashton.remotish': ['scmHistoryProvider']},
                )


if __name__ == '__main__':
    unittest.main()
