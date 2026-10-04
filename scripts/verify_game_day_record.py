#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from datetime import date
from pathlib import Path
from typing import Any, cast

from common import BuildError, load_json, require

SHA256_RE = re.compile(r'^[0-9a-f]{64}$')
SHA_RE = re.compile(r'^[0-9a-f]{40}$')
TAG_RE = re.compile(r'^v.+-web\.(0|[1-9][0-9]*)$')
GITHUB_LOGIN_RE = re.compile(r'^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$')
ISSUE_URL_RE = re.compile(r'^https://github\.com/[^/]+/[^/]+/issues/[1-9][0-9]*$')
REVIEW_URL_RE = re.compile(
    r'^https://github\.com/[^/]+/[^/]+/(?:issues/[1-9][0-9]*#issuecomment-[1-9][0-9]*|pull/[1-9][0-9]*(?:#pullrequestreview-[1-9][0-9]*|#issuecomment-[1-9][0-9]*))$'
)


def _require_exact_keys(
    value: dict[str, object],
    expected: set[str],
    *,
    label: str,
) -> None:
    require(set(value) == expected, f'{label} keys invalid')


def _require_sha(value: object, *, label: str) -> str:
    require(
        isinstance(value, str) and SHA_RE.fullmatch(value) is not None,
        f'{label} invalid',
    )
    return cast(str, value)


def _require_sha256(value: object, *, label: str) -> str:
    require(
        isinstance(value, str) and SHA256_RE.fullmatch(value) is not None,
        f'{label} invalid',
    )
    return cast(str, value)


def _require_tag(value: object, *, label: str) -> str:
    require(
        isinstance(value, str) and TAG_RE.fullmatch(value) is not None,
        f'{label} invalid',
    )
    return cast(str, value)


def _require_positive_int(value: object, *, label: str) -> int:
    require(
        isinstance(value, int) and not isinstance(value, bool) and value > 0,
        f'{label} invalid',
    )
    return cast(int, value)


def _validate_operator(value: object, *, label: str) -> dict[str, object]:
    require(isinstance(value, dict), f'{label} must be an object')
    operator = cast(dict[str, object], value)
    _require_exact_keys(operator, {'githubLogin', 'githubUserId'}, label=label)
    login = operator.get('githubLogin')
    require(
        isinstance(login, str) and GITHUB_LOGIN_RE.fullmatch(login) is not None,
        f'{label}.githubLogin invalid',
    )
    _require_positive_int(operator.get('githubUserId'), label=f'{label}.githubUserId')
    return operator


def _validate_identity(
    value: object,
    *,
    label: str,
) -> dict[str, object]:
    require(isinstance(value, dict), f'{label} must be an object')
    identity = cast(dict[str, object], value)
    _require_exact_keys(
        identity,
        {'id', 'releaseTag', 'releaseCommit', 'distributionTreeSha256'},
        label=label,
    )
    _require_positive_int(identity.get('id'), label=f'{label}.id')
    _require_tag(identity.get('releaseTag'), label=f'{label}.releaseTag')
    _require_sha(identity.get('releaseCommit'), label=f'{label}.releaseCommit')
    _require_sha256(
        identity.get('distributionTreeSha256'),
        label=f'{label}.distributionTreeSha256',
    )
    return identity


def validate(record: dict[str, Any]) -> None:
    _require_exact_keys(
        cast(dict[str, object], record),
        {
            'schemaVersion',
            'exerciseDate',
            'releaseTag',
            'releaseCommit',
            'operators',
            'independentReviewUrl',
            'workflowRuns',
            'release',
            'rollbackTarget',
            'deployments',
            'operatorNotes',
            'followUpIssues',
        },
        label='game-day record',
    )
    require(record.get('schemaVersion') == 1, 'game-day schemaVersion must be 1')

    exercise_date_value = record.get('exerciseDate')
    require(isinstance(exercise_date_value, str), 'exerciseDate invalid')
    exercise_date = cast(str, exercise_date_value)
    try:
        date.fromisoformat(exercise_date)
    except ValueError as exc:
        raise BuildError('exerciseDate invalid') from exc

    tag = _require_tag(record.get('releaseTag'), label='releaseTag')
    commit = _require_sha(record.get('releaseCommit'), label='releaseCommit')

    operators = record.get('operators')
    require(isinstance(operators, dict), 'operators must be an object')
    operator_obj = cast(dict[str, object], operators)
    _require_exact_keys(operator_obj, {'executor', 'reviewer'}, label='operators')
    executor = _validate_operator(operator_obj['executor'], label='operators.executor')
    reviewer = _validate_operator(operator_obj['reviewer'], label='operators.reviewer')
    require(
        executor['githubUserId'] != reviewer['githubUserId'],
        'executor and reviewer GitHub user IDs must be distinct',
    )
    require(
        str(executor['githubLogin']).lower() != str(reviewer['githubLogin']).lower(),
        'executor and reviewer GitHub logins must be distinct',
    )

    review_url = record.get('independentReviewUrl')
    require(
        isinstance(review_url, str) and REVIEW_URL_RE.fullmatch(review_url) is not None,
        'independentReviewUrl must be a GitHub issue comment or pull-request review permalink',
    )

    runs = record.get('workflowRuns')
    require(isinstance(runs, dict), 'workflowRuns must be an object')
    run_obj = cast(dict[str, object], runs)
    required_runs = {
        'qualification',
        'release',
        'publicationRetry',
        'publicationRecovery',
        'canaryToStable',
        'rollback',
        'forwardRepromotion',
    }
    _require_exact_keys(run_obj, required_runs, label='workflowRuns')
    run_ids: list[int] = []
    for name, value in run_obj.items():
        run_ids.append(_require_positive_int(value, label=f'workflowRuns.{name}'))
    require(len(run_ids) == len(set(run_ids)), 'workflowRuns must be distinct')

    release = record.get('release')
    require(isinstance(release, dict), 'release must be an object')
    release_obj = cast(dict[str, object], release)
    _require_exact_keys(
        release_obj,
        {
            'githubReleaseId',
            'archiveSha256',
            'distributionTreeSha256',
            'playwrightRuntimeSha256',
            'ociDigest',
        },
        label='release',
    )
    _require_positive_int(
        release_obj.get('githubReleaseId'),
        label='release.githubReleaseId',
    )
    _require_sha256(release_obj.get('archiveSha256'), label='release.archiveSha256')
    release_tree = _require_sha256(
        release_obj.get('distributionTreeSha256'),
        label='release.distributionTreeSha256',
    )
    _require_sha256(
        release_obj.get('playwrightRuntimeSha256'),
        label='release.playwrightRuntimeSha256',
    )
    oci_digest = release_obj.get('ociDigest')
    require(
        isinstance(oci_digest, str)
        and oci_digest.startswith('sha256:')
        and SHA256_RE.fullmatch(oci_digest[7:]) is not None,
        'release.ociDigest invalid',
    )

    rollback = record.get('rollbackTarget')
    require(isinstance(rollback, dict), 'rollbackTarget must be an object')
    rollback_obj = cast(dict[str, object], rollback)
    _require_exact_keys(
        rollback_obj,
        {'releaseTag', 'releaseCommit', 'distributionTreeSha256'},
        label='rollbackTarget',
    )
    rollback_tag = _require_tag(
        rollback_obj.get('releaseTag'),
        label='rollbackTarget.releaseTag',
    )
    rollback_commit = _require_sha(
        rollback_obj.get('releaseCommit'),
        label='rollbackTarget.releaseCommit',
    )
    rollback_tree = _require_sha256(
        rollback_obj.get('distributionTreeSha256'),
        label='rollbackTarget.distributionTreeSha256',
    )
    require(
        rollback_tag != tag,
        'rollbackTarget.releaseTag must differ from releaseTag',
    )
    require(
        rollback_commit != commit,
        'rollbackTarget.releaseCommit must differ from releaseCommit',
    )

    deployments = record.get('deployments')
    require(isinstance(deployments, dict), 'deployments must be an object')
    deployment_obj = cast(dict[str, object], deployments)
    deployment_names = {
        'canary',
        'stableBeforeRollback',
        'stableAfterRollback',
        'stableAfterForward',
    }
    _require_exact_keys(deployment_obj, deployment_names, label='deployments')
    identities = {
        name: _validate_identity(deployment_obj[name], label=f'deployments.{name}')
        for name in deployment_names
    }
    deployment_ids = [cast(int, identity['id']) for identity in identities.values()]
    require(
        len(deployment_ids) == len(set(deployment_ids)),
        'deployment ids must be distinct',
    )

    for name in ('canary', 'stableBeforeRollback', 'stableAfterForward'):
        identity = identities[name]
        require(
            identity['releaseTag'] == tag,
            f'deployments.{name}.releaseTag mismatch',
        )
        require(
            identity['releaseCommit'] == commit,
            f'deployments.{name}.releaseCommit mismatch',
        )
        require(
            identity['distributionTreeSha256'] == release_tree,
            f'deployments.{name}.distributionTreeSha256 mismatch',
        )

    rolled_back = identities['stableAfterRollback']
    require(
        rolled_back['releaseTag'] == rollback_tag,
        'deployments.stableAfterRollback.releaseTag mismatch',
    )
    require(
        rolled_back['releaseCommit'] == rollback_commit,
        'deployments.stableAfterRollback.releaseCommit mismatch',
    )
    require(
        rolled_back['distributionTreeSha256'] == rollback_tree,
        'deployments.stableAfterRollback.distributionTreeSha256 mismatch',
    )

    notes_value = record.get('operatorNotes')
    require(isinstance(notes_value, list), 'operatorNotes must be an array')
    note_values = cast(list[object], notes_value)
    require(bool(note_values), 'operatorNotes must be a non-empty array')
    require(
        all(isinstance(item, str) and bool(item.strip()) for item in note_values),
        'operatorNotes entries must be non-empty strings',
    )

    follow_up_value = record.get('followUpIssues')
    require(isinstance(follow_up_value, list), 'followUpIssues must be an array')
    issue_values = cast(list[object], follow_up_value)
    require(
        all(
            isinstance(item, str) and ISSUE_URL_RE.fullmatch(item) is not None
            for item in issue_values
        ),
        'followUpIssues entries must be GitHub issue URLs',
    )


def validate_file(path: Path) -> None:
    record = load_json(path)
    validate(record)

    exercise_date = cast(str, record['exerciseDate'])
    release_tag = cast(str, record['releaseTag'])
    require(
        path.name == f'{exercise_date}-{release_tag}.json',
        'game-day filename must match exerciseDate and releaseTag',
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Validate a completed release game-day evidence record'
    )
    parser.add_argument('record', type=Path)
    args = parser.parse_args()
    validate_file(args.record)
    print(f'release game-day evidence: valid ({args.record})')


if __name__ == '__main__':
    try:
        main()
    except BuildError as exc:
        raise SystemExit(str(exc)) from None
