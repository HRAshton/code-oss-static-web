#!/usr/bin/env python3
from __future__ import annotations

import re
import sys

PATTERN = re.compile(
    r'^(?:build|chore|ci|docs|feat|fix|perf|refactor|revert|style|test)'
    r'(?:\([a-z0-9._/-]+\))?!?: [A-Z].+$'
)
GITHUB_MERGE_PATTERN = re.compile(
    r'^Merge pull request #[1-9][0-9]* from [^\s/]+/[^\r\n]+\n\n(?P<title>[^\r\n]+)$'
)


def validate_subject(message: str) -> None:
    if '\n' in message or '\r' in message:
        raise ValueError('commit message must be a single line')
    if PATTERN.fullmatch(message) is None:
        raise ValueError(
            'commit message must use Conventional Commits and start its description with an uppercase letter'
        )


def validate_message(message: str, *, allow_github_merge: bool = False) -> None:
    if allow_github_merge:
        match = GITHUB_MERGE_PATTERN.fullmatch(message)
        if match is not None:
            validate_subject(match.group('title'))
            return
    validate_subject(message)


def main() -> None:
    args = sys.argv[1:]
    allow_github_merge = False
    if args[:1] == ['--allow-github-merge']:
        allow_github_merge = True
        args = args[1:]

    if len(args) != 1:
        raise SystemExit('usage: check_commit_message.py [--allow-github-merge] <message>')

    try:
        validate_message(args[0], allow_github_merge=allow_github_merge)
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    print('commit message policy: ok')


if __name__ == '__main__':
    main()
