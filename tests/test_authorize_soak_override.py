from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

from authorize_soak_override import TRUSTED_CALLER, authorize
from common import BuildError

SOURCE_SHA = 'a' * 40


def valid_request() -> dict[str, str]:
    return {
        'repository': 'HRAshton/code-oss-static-web',
        'ref': 'refs/heads/master',
        'event_name': 'workflow_dispatch',
        'caller_workflow_ref': TRUSTED_CALLER,
        'actor': 'HRAshton',
        'triggering_actor': 'vodyanica',
        'expected_source_sha': SOURCE_SHA,
        'source_sha': SOURCE_SHA,
        'browser': 'all',
        'release_mode': 'upstream',
        'reason': 'Urgent upstream security fix',
    }


class SoakOverrideAuthorizationTests(unittest.TestCase):
    def test_approved_operator_with_trusted_dispatch(self) -> None:
        authorize(**valid_request())

    def test_unapproved_original_or_rerun_actor_fails(self) -> None:
        for field in ('actor', 'triggering_actor'):
            with self.subTest(field=field), self.assertRaises(BuildError):
                authorize(**(valid_request() | {field: 'ordinary-writer'}))

    def test_untrusted_caller_or_branch_fails(self) -> None:
        for field, value in (
            ('repository', 'someone-else/project'),
            ('ref', 'refs/heads/unprotected'),
            ('event_name', 'push'),
            (
                'caller_workflow_ref',
                'HRAshton/code-oss-static-web/.github/workflows/qualify.yml@refs/heads/master',
            ),
            ('expected_source_sha', 'b' * 40),
            ('source_sha', 'invalid'),
            ('browser', 'chromium'),
            ('release_mode', 'patch'),
        ):
            with self.subTest(field=field), self.assertRaises(BuildError):
                authorize(**(valid_request() | {field: value}))

    def test_blank_or_oversized_reason_fails(self) -> None:
        for reason in ('', ' \t  ', 'x' * 501):
            with self.subTest(reason=reason[:20]), self.assertRaises(BuildError):
                authorize(**(valid_request() | {'reason': reason}))


if __name__ == '__main__':
    unittest.main()
