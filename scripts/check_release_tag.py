#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from typing import Any

from common import ROOT, BuildError, load_json, require

RELEASE_REVISION_RE = re.compile(r'^(0|[1-9][0-9]*)$')


def expected_release_tag(lock: dict[str, Any], revision: int = 0) -> str:
    require(
        not isinstance(revision, bool) and revision >= 0,
        'release revision must be a non-negative integer',
    )
    return f'v{lock["tag"]}-web.{revision}'


def release_revision(lock: dict[str, Any], tag: str) -> int:
    prefix = f'v{lock["tag"]}-web.'
    require(tag.startswith(prefix), f'release tag must start with {prefix}')
    suffix = tag[len(prefix) :]
    require(
        RELEASE_REVISION_RE.fullmatch(suffix) is not None,
        f'invalid web release revision in tag: {tag}',
    )
    return int(suffix)


def release_version(lock: dict[str, Any], tag: str) -> str:
    revision = release_revision(lock, tag)
    return f'{lock["tag"]}-web.{revision}'


def main() -> None:
    parser = argparse.ArgumentParser(description='Verify the immutable release tag contract')
    parser.add_argument('tag')
    args = parser.parse_args()

    lock = load_json(ROOT / 'upstream.lock.json')
    revision = release_revision(lock, args.tag)
    print(f'release tag contract: {expected_release_tag(lock, revision)}')


if __name__ == '__main__':
    try:
        main()
    except BuildError as exc:
        raise SystemExit(str(exc)) from None
