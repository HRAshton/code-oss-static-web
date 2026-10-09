from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ReleaseIntentGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        workflow = (ROOT / '.github/workflows/qualify.yml').read_text(encoding='utf-8')
        cls.gate = workflow.split('  release-intent-gate:\n', 1)[1]
        raw_script = cls.gate.split('        run: |\n', 1)[1]
        cls.script = '\n'.join(line.removeprefix('          ') for line in raw_script.splitlines())

    def _run(self, retry_tag: str = '', **changes: str) -> subprocess.CompletedProcess[str]:
        env = {
            **os.environ,
            'RETRY_TAG': retry_tag,
            'TOOLING_RESULT': 'success',
            'PLAN_RESULT': 'success',
            'RECOVERY_RESULT': 'skipped',
            'BUILD_RESULT': 'success',
            'BROWSER_RESULT': 'success',
            'SERVING_RESULT': 'success',
            'PACKAGE_RESULT': 'success',
            'ATTEST_RESULT': 'success',
            'RELEASE_RESULT': 'success',
            **changes,
        }
        return subprocess.run(
            ['bash', '-c', self.script],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_gate_waits_for_every_stage_and_runs_on_release_intent(self):
        self.assertIn(
            "if: ${{ always() && (inputs.release_mode == 'upstream' || inputs.release_mode == 'patch') }}",
            self.gate,
        )
        self.assertIn(
            'needs: [tooling, browser-plan, recover-publication, build, browser, '
            'production-serving, package, attest, release]',
            self.gate,
        )
        self.assertIn('permissions: {}', self.gate)

    def test_new_release_requires_every_stage_to_succeed(self):
        self.assertEqual(self._run().returncode, 0)
        for key in (
            'TOOLING_RESULT',
            'PLAN_RESULT',
            'BUILD_RESULT',
            'BROWSER_RESULT',
            'SERVING_RESULT',
            'PACKAGE_RESULT',
            'ATTEST_RESULT',
            'RELEASE_RESULT',
        ):
            with self.subTest(stage=key):
                result = self._run(**{key: 'skipped'})
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn('expected success', result.stderr)

    def test_new_release_rejects_failures_and_unexpected_recovery(self):
        self.assertNotEqual(self._run(BUILD_RESULT='failure').returncode, 0)
        self.assertNotEqual(self._run(RECOVERY_RESULT='success').returncode, 0)

    def test_existing_tag_requires_only_successful_recovery(self):
        skipped = {
            'RECOVERY_RESULT': 'success',
            'BUILD_RESULT': 'skipped',
            'BROWSER_RESULT': 'skipped',
            'SERVING_RESULT': 'skipped',
            'PACKAGE_RESULT': 'skipped',
            'ATTEST_RESULT': 'skipped',
            'RELEASE_RESULT': 'skipped',
        }
        self.assertEqual(self._run(retry_tag='v1.141.0-web.0', **skipped).returncode, 0)
        for changes in (
            {'RECOVERY_RESULT': 'skipped'},
            {'RECOVERY_RESULT': 'failure'},
            {'BUILD_RESULT': 'success'},
        ):
            with self.subTest(results=changes):
                result = self._run(retry_tag='v1.141.0-web.0', **{**skipped, **changes})
                self.assertNotEqual(result.returncode, 0, result.stdout)


if __name__ == '__main__':
    unittest.main()
