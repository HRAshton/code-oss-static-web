#!/usr/bin/env python3
"""Fail-closed content guard for the privileged Renovate auto-approval job.

The job passes base and PR-head file copies downloaded from GitHub's Contents API.
The guard runs from trusted master, never from the untrusted PR checkout.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

EXPECTED_PATHS = frozenset(
    {
        'upstream.lock.json',
        'builder-apt-snapshot.json',
    }
)
STAMP = re.compile(r'\d{8}T\d{6}Z\Z')
VERSION = re.compile(r'\d+\.\d+\.\d+\Z')
COMMIT = re.compile(r'[0-9a-f]{40}\Z')


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def replace_once(original: str, old: str, new: str, label: str) -> str:
    require(original.count(old) == 1, f'{label}: original reference not unique')
    return original.replace(old, new, 1)


def verify(
    base: Path,
    head: Path,
    changed: set[str],
    *,
    expected_upstream_epoch: int,
    now: datetime | None = None,
) -> None:
    require(changed == set(EXPECTED_PATHS), f'unexpected Renovate paths: {sorted(changed)}')

    def checked(path: str) -> tuple[str, str]:
        return (
            (base / path).read_text(encoding='utf-8'),
            (head / path).read_text(encoding='utf-8'),
        )

    before_upstream, after_upstream = checked('upstream.lock.json')
    previous = json.loads(before_upstream)
    updated = json.loads(after_upstream)
    require(set(updated) == set(previous), 'upstream lock keys changed')
    require(VERSION.fullmatch(previous['tag']) is not None, 'invalid prior upstream tag')
    require(VERSION.fullmatch(updated['tag']) is not None, 'invalid updated upstream tag')
    require(COMMIT.fullmatch(updated['commit']) is not None, 'invalid upstream commit')
    old_tag, new_tag = previous['tag'], updated['tag']
    old_commit, new_commit = previous['commit'], updated['commit']
    old_epoch, new_epoch = previous['sourceDateEpoch'], updated['sourceDateEpoch']
    require(type(old_epoch) is int and old_epoch > 0, 'invalid prior sourceDateEpoch')
    require(type(new_epoch) is int and new_epoch > 0, 'invalid updated sourceDateEpoch')
    require(
        type(expected_upstream_epoch) is int and expected_upstream_epoch > 0,
        'invalid upstream commit timestamp',
    )
    old_parts = tuple(int(part) for part in old_tag.split('.'))
    new_parts = tuple(int(part) for part in new_tag.split('.'))
    require(new_parts > old_parts, 'upstream version did not advance')
    require(new_commit != old_commit, 'upstream commit did not change')
    require(new_epoch > old_epoch, 'sourceDateEpoch did not advance')
    require(new_epoch == expected_upstream_epoch, 'sourceDateEpoch does not match upstream commit')
    require(
        updated == {**previous, 'tag': new_tag, 'commit': new_commit, 'sourceDateEpoch': new_epoch},
        'unexpected upstream lock fields',
    )
    expected_upstream = replace_once(
        before_upstream,
        f'"tag": "{old_tag}"',
        f'"tag": "{new_tag}"',
        'upstream tag',
    )
    expected_upstream = replace_once(
        expected_upstream,
        f'"commit": "{old_commit}"',
        f'"commit": "{new_commit}"',
        'upstream commit',
    )
    expected_upstream = replace_once(
        expected_upstream,
        f'"sourceDateEpoch": {old_epoch}',
        f'"sourceDateEpoch": {new_epoch}',
        'upstream sourceDateEpoch',
    )
    require(after_upstream == expected_upstream, 'unapproved upstream lock changes')

    before_builder, after_builder = checked('builder-apt-snapshot.json')
    previous_builder = json.loads(before_builder)
    updated_builder = json.loads(after_builder)
    require(previous_builder.get('schemaVersion') == 1, 'invalid prior snapshot schema')
    require(
        set(previous_builder) == {'schemaVersion', 'aptSnapshot'},
        'invalid prior snapshot keys',
    )
    require(set(previous_builder) == set(updated_builder), 'snapshot lock keys changed')
    old_stamp = previous_builder['aptSnapshot']
    new_stamp = updated_builder['aptSnapshot']
    require(STAMP.fullmatch(old_stamp) is not None, 'invalid prior APT snapshot')
    require(STAMP.fullmatch(new_stamp) is not None, 'invalid new APT snapshot')
    old_date = datetime.strptime(old_stamp, '%Y%m%dT%H%M%SZ').replace(tzinfo=UTC)
    new_date = datetime.strptime(new_stamp, '%Y%m%dT%H%M%SZ').replace(tzinfo=UTC)
    require(new_date > old_date, 'APT snapshot did not advance')
    require(
        new_date.hour == new_date.minute == new_date.second == 0,
        'snapshot not midnight UTC',
    )
    now = now or datetime.now(UTC)
    require(new_date <= now - timedelta(days=2), 'APT snapshot less than 48 hours old')
    require(
        updated_builder == {**previous_builder, 'aptSnapshot': new_stamp},
        'unexpected snapshot lock fields',
    )
    expected_builder = replace_once(
        before_builder,
        f'"aptSnapshot": "{old_stamp}"',
        f'"aptSnapshot": "{new_stamp}"',
        'APT snapshot lock',
    )
    require(after_builder == expected_builder, 'unapproved snapshot lock changes')


def main(argv: list[str]) -> int:
    if len(argv) < 5:
        print(
            'usage: verify_renovate_update.py BASE_DIR HEAD_DIR EXPECTED_UPSTREAM_EPOCH FILE ...',
            file=sys.stderr,
        )
        return 2
    try:
        require(argv[3].isdigit(), 'invalid upstream commit timestamp')
        verify(
            Path(argv[1]),
            Path(argv[2]),
            set(argv[4:]),
            expected_upstream_epoch=int(argv[3]),
        )
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f'Renovate approval denied: {exc}', file=sys.stderr)
        return 1
    print('Renovate upstream and APT snapshot update matches the approved transform')
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
