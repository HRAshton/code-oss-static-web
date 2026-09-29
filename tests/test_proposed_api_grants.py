from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import prepare_upstream  # noqa: E402
from common import BuildError  # noqa: E402


class ProposedApiGrantTests(unittest.TestCase):
    def test_remotish_grant_is_scoped_and_not_bundled(self):
        transform = json.loads((ROOT / 'config/product-transform.json').read_text())
        self.assertEqual(
            transform['set']['extensionEnabledApiProposals'],
            {'hrashton.remotish': ['scmHistoryProvider', 'timeline']},
        )

        extension_lock = json.loads((ROOT / 'extensions/extensions.lock.json').read_text())
        bundled_ids = {entry.get('id') for entry in extension_lock['extensions']}
        self.assertNotIn('hrashton.remotish', bundled_ids)

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
