from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import verify_game_day_record  # noqa: E402
from common import BuildError  # noqa: E402


def record() -> dict[str, object]:
    return {
        'schemaVersion': 1,
        'exerciseDate': '2026-10-04',
        'releaseTag': 'v1.2.3-web.0',
        'releaseCommit': 'a' * 40,
        'operators': {
            'executor': {'githubLogin': 'release-operator', 'githubUserId': 101},
            'reviewer': {'githubLogin': 'release-reviewer', 'githubUserId': 202},
        },
        'independentReviewUrl': (
            'https://github.com/HRAshton/code-oss-static-web/issues/123#issuecomment-456'
        ),
        'workflowRuns': {
            'qualification': 1,
            'release': 2,
            'publicationRetry': 3,
            'publicationRecovery': 4,
            'canaryToStable': 5,
            'rollback': 6,
            'forwardRepromotion': 7,
        },
        'release': {
            'githubReleaseId': 8,
            'archiveSha256': 'b' * 64,
            'distributionTreeSha256': 'c' * 64,
            'playwrightRuntimeSha256': 'd' * 64,
            'ociDigest': 'sha256:' + 'e' * 64,
        },
        'rollbackTarget': {
            'releaseTag': 'v1.2.2-web.0',
            'releaseCommit': 'f' * 40,
            'distributionTreeSha256': '1' * 64,
        },
        'deployments': {
            'canary': {
                'id': 9,
                'releaseTag': 'v1.2.3-web.0',
                'releaseCommit': 'a' * 40,
                'distributionTreeSha256': 'c' * 64,
            },
            'stableBeforeRollback': {
                'id': 10,
                'releaseTag': 'v1.2.3-web.0',
                'releaseCommit': 'a' * 40,
                'distributionTreeSha256': 'c' * 64,
            },
            'stableAfterRollback': {
                'id': 11,
                'releaseTag': 'v1.2.2-web.0',
                'releaseCommit': 'f' * 40,
                'distributionTreeSha256': '1' * 64,
            },
            'stableAfterForward': {
                'id': 12,
                'releaseTag': 'v1.2.3-web.0',
                'releaseCommit': 'a' * 40,
                'distributionTreeSha256': 'c' * 64,
            },
        },
        'operatorNotes': ['No tag or immutable asset moved during rollback.'],
        'followUpIssues': [],
    }


class GameDayRecordTests(unittest.TestCase):
    def test_complete_record_passes(self) -> None:
        verify_game_day_record.validate(record())

    def test_executor_and_reviewer_user_ids_must_be_distinct(self) -> None:
        value = record()
        operators = value['operators']
        assert isinstance(operators, dict)
        executor = operators['executor']
        reviewer = operators['reviewer']
        assert isinstance(executor, dict)
        assert isinstance(reviewer, dict)
        reviewer['githubUserId'] = executor['githubUserId']
        with self.assertRaisesRegex(BuildError, 'user IDs must be distinct'):
            verify_game_day_record.validate(value)

    def test_executor_and_reviewer_logins_must_be_distinct(self) -> None:
        value = record()
        operators = value['operators']
        assert isinstance(operators, dict)
        reviewer = operators['reviewer']
        assert isinstance(reviewer, dict)
        reviewer['githubLogin'] = 'RELEASE-OPERATOR'
        with self.assertRaisesRegex(BuildError, 'logins must be distinct'):
            verify_game_day_record.validate(value)

    def test_independent_review_requires_durable_github_permalink(self) -> None:
        value = record()
        value['independentReviewUrl'] = 'https://example.com/review'
        with self.assertRaisesRegex(BuildError, 'independentReviewUrl'):
            verify_game_day_record.validate(value)

    def test_missing_recovery_evidence_fails(self) -> None:
        value = record()
        runs = value['workflowRuns']
        assert isinstance(runs, dict)
        del runs['publicationRecovery']
        with self.assertRaisesRegex(BuildError, 'workflowRuns keys invalid'):
            verify_game_day_record.validate(value)

    def test_candidate_identity_mismatch_fails(self) -> None:
        value = record()
        deployments = value['deployments']
        assert isinstance(deployments, dict)
        stable = deployments['stableAfterForward']
        assert isinstance(stable, dict)
        stable['distributionTreeSha256'] = '9' * 64
        with self.assertRaisesRegex(BuildError, 'distributionTreeSha256 mismatch'):
            verify_game_day_record.validate(value)

    def test_rollback_must_bind_distinct_recorded_target(self) -> None:
        value = record()
        rollback = value['rollbackTarget']
        assert isinstance(rollback, dict)
        rollback['releaseTag'] = 'v1.2.3-web.0'
        with self.assertRaisesRegex(BuildError, 'must differ from releaseTag'):
            verify_game_day_record.validate(value)

    def test_workflow_run_ids_must_be_distinct(self) -> None:
        value = record()
        runs = value['workflowRuns']
        assert isinstance(runs, dict)
        runs['publicationRetry'] = runs['release']
        with self.assertRaisesRegex(BuildError, 'workflowRuns must be distinct'):
            verify_game_day_record.validate(value)

    def test_filename_binds_exercise_date_and_release(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            good = root / '2026-10-04-v1.2.3-web.0.json'
            good.write_text(json.dumps(record()), encoding='utf-8')
            verify_game_day_record.validate_file(good)

            bad = root / '2026-10-05-v1.2.3-web.0.json'
            bad.write_text(json.dumps(record()), encoding='utf-8')
            with self.assertRaisesRegex(BuildError, 'filename must match'):
                verify_game_day_record.validate_file(bad)

    def test_repository_game_day_records_are_valid(self) -> None:
        evidence_dir = ROOT / 'release-evidence/game-days'
        for path in sorted(evidence_dir.glob('*.json')):
            with self.subTest(path=path):
                verify_game_day_record.validate_file(path)


if __name__ == '__main__':
    unittest.main()
