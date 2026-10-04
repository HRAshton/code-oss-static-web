#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import promotion
from common import BuildError, load_json, write_json


def main() -> None:
    parser = argparse.ArgumentParser(description='Build or verify the live Pages release identity')
    subparsers = parser.add_subparsers(dest='command', required=True)

    write_parser = subparsers.add_parser('write')
    write_parser.add_argument('--promotion-identity', required=True, type=Path)
    write_parser.add_argument('--output', required=True, type=Path)

    verify_parser = subparsers.add_parser('verify')
    verify_parser.add_argument('--expected', required=True, type=Path)
    verify_parser.add_argument('--actual', required=True, type=Path)

    args = parser.parse_args()
    if args.command == 'write':
        identity = promotion.build_pages_deployment_identity(load_json(args.promotion_identity))
        write_json(args.output, identity)
        print(f'Pages deployment identity: {args.output}')
        return

    promotion.verify_pages_deployment_identity(
        load_json(args.expected),
        load_json(args.actual),
    )
    print('live Pages deployment identity: verified')


if __name__ == '__main__':
    try:
        main()
    except BuildError as exc:
        raise SystemExit(str(exc)) from None
