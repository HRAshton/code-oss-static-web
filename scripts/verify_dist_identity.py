#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

from common import BuildError, require
from package_release import distribution_tree_digest

SHA256_RE = re.compile(r'^[0-9a-f]{64}$')


def verify_distribution_identity(
    distribution: Path,
    *,
    expected_sha256: str,
    expected_file_count: int,
) -> tuple[str, int]:
    require(
        (distribution / 'index.html').is_file(),
        f'not a static distribution: {distribution}',
    )
    require(
        SHA256_RE.fullmatch(expected_sha256) is not None,
        f'invalid qualified distribution tree digest: {expected_sha256}',
    )
    require(
        expected_file_count > 0,
        f'invalid qualified distribution file count: {expected_file_count}',
    )

    release_sha256, release_file_count = distribution_tree_digest(distribution)
    print(f'qualified distribution: {expected_sha256} ({expected_file_count} files)')
    print(f'release distribution:   {release_sha256} ({release_file_count} files)')

    require(
        release_file_count == expected_file_count,
        'qualified/release distribution file count mismatch: '
        f'{expected_file_count} != {release_file_count}',
    )
    require(
        release_sha256 == expected_sha256,
        'qualified/release distribution tree digest mismatch: '
        f'{expected_sha256} != {release_sha256}',
    )
    return release_sha256, release_file_count


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Verify a rebuilt distribution against its qualified identity'
    )
    parser.add_argument('--expected-sha256', required=True)
    parser.add_argument('--expected-file-count', required=True, type=int)
    parser.add_argument('distribution', type=Path)
    args = parser.parse_args()

    verify_distribution_identity(
        args.distribution.resolve(),
        expected_sha256=args.expected_sha256,
        expected_file_count=args.expected_file_count,
    )


if __name__ == '__main__':
    try:
        main()
    except BuildError as exc:
        raise SystemExit(str(exc)) from None
