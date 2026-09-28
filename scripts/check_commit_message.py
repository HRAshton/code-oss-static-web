#!/usr/bin/env python3
from __future__ import annotations

import re
import sys

PATTERN = re.compile(
    r'^(?:build|chore|ci|docs|feat|fix|perf|refactor|revert|style|test)'
    r'(?:\([a-z0-9._/-]+\))?!?: [A-Z].+$'
)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit('usage: check_commit_message.py <message>')
    message = sys.argv[1]
    if '\n' in message or '\r' in message:
        raise SystemExit('commit message must be a single line')
    if PATTERN.fullmatch(message) is None:
        raise SystemExit(
            'commit message must use Conventional Commits and start its description with an uppercase letter'
        )
    print('commit message policy: ok')


if __name__ == '__main__':
    main()
