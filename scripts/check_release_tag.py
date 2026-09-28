#!/usr/bin/env python3
from __future__ import annotations

import argparse

from common import ROOT, BuildError, load_json, require


def expected_release_tag(lock: dict) -> str:
    return f"v{lock['tag']}-web.0"


def main() -> None:
    parser = argparse.ArgumentParser(description='Verify the immutable release tag contract')
    parser.add_argument('tag')
    args = parser.parse_args()

    lock = load_json(ROOT / 'upstream.lock.json')
    require(lock.get('qualified') is True, 'upstream revision is not qualified')
    expected = expected_release_tag(lock)
    require(args.tag == expected, f'release tag mismatch: expected {expected}, got {args.tag}')
    print(f'release tag contract: {args.tag}')


if __name__ == '__main__':
    try:
        main()
    except BuildError as exc:
        raise SystemExit(str(exc))
