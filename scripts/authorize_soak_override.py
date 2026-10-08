"""Fail-closed repository-source authorization for emergency upstream soak bypass."""

from __future__ import annotations

import os

from common import BuildError, require

# Interim Release/Security owners from .github/CODEOWNERS. Changes require sensitive-path review.
APPROVED_OPERATORS = frozenset({'hrashton', 'vodyanica'})
TRUSTED_REPOSITORY = 'HRAshton/code-oss-static-web'
TRUSTED_WORKFLOW = '.github/workflows/upstream-soak-break-glass.yml'
TRUSTED_CALLER = f'{TRUSTED_REPOSITORY}/{TRUSTED_WORKFLOW}@refs/heads/master'


def authorize(
    *,
    repository: str,
    ref: str,
    event_name: str,
    caller_workflow_ref: str,
    actor: str,
    triggering_actor: str,
    expected_source_sha: str,
    source_sha: str,
    browser: str,
    release_mode: str,
    reason: str,
) -> None:
    require(repository == TRUSTED_REPOSITORY, 'untrusted override repository')
    require(ref == 'refs/heads/master', 'override must qualify protected master')
    require(event_name == 'workflow_dispatch', 'override requires manual dispatch')
    require(caller_workflow_ref == TRUSTED_CALLER, 'untrusted break-glass caller')
    require(actor.casefold() in APPROVED_OPERATORS, 'override actor is not approved')
    require(
        triggering_actor.casefold() in APPROVED_OPERATORS,
        'override re-run actor is not approved',
    )
    require(
        browser == 'all' and release_mode == 'upstream',
        'override requires full upstream qualification',
    )
    require(
        len(source_sha) == 40
        and all(char in '0123456789abcdefABCDEF' for char in source_sha)
        and expected_source_sha == source_sha,
        'override source SHA must match the checked-out release commit',
    )
    require(
        bool(reason.strip()) and len(reason) <= 500,
        'override requires a substantive reason (max 500 characters)',
    )


def main() -> None:
    authorize(
        repository=os.environ.get('GITHUB_REPOSITORY', ''),
        ref=os.environ.get('GITHUB_REF', ''),
        event_name=os.environ.get('GITHUB_EVENT_NAME', ''),
        caller_workflow_ref=os.environ.get('CALLER_WORKFLOW_REF', ''),
        actor=os.environ.get('GITHUB_ACTOR', ''),
        triggering_actor=os.environ.get('TRIGGERING_ACTOR', ''),
        expected_source_sha=os.environ.get('EXPECTED_SOURCE_SHA', ''),
        source_sha=os.environ.get('GITHUB_SHA', ''),
        browser=os.environ.get('REQUESTED_BROWSER', ''),
        release_mode=os.environ.get('RELEASE_MODE', ''),
        reason=os.environ.get('SECURITY_OVERRIDE_REASON', ''),
    )
    print('Upstream soak override authorized for approved operator on protected master')


if __name__ == '__main__':
    try:
        main()
    except BuildError as exc:
        raise SystemExit(str(exc)) from None
