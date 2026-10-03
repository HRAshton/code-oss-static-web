#!/usr/bin/env python3
from __future__ import annotations

import re
import sys

from common import BuildError, require

FULL_SHA = re.compile(r'^[0-9a-f]{40}$')


def verify_source_sha(expected_source_sha: str, actual_source_sha: str) -> None:
    require(
        FULL_SHA.fullmatch(expected_source_sha) is not None,
        f'invalid expected qualification source SHA: {expected_source_sha}',
    )
    require(
        FULL_SHA.fullmatch(actual_source_sha) is not None,
        f'invalid actual qualification source SHA: {actual_source_sha}',
    )
    require(
        expected_source_sha == actual_source_sha,
        (
            'qualification source SHA mismatch: '
            f'expected {expected_source_sha}, got {actual_source_sha}'
        ),
    )


def main(argv: list[str]) -> None:
    require(len(argv) == 3, 'usage: verify_qualification_source.py EXPECTED_SHA ACTUAL_SHA')
    verify_source_sha(argv[1], argv[2])
    print(f'qualification source SHA verified: {argv[2]}')


if __name__ == '__main__':
    try:
        main(sys.argv)
    except BuildError as exc:
        raise SystemExit(str(exc)) from None
