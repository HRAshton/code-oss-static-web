#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from common import BuildError, require
from package_release import distribution_tree_digest


def compare_distributions(reference: Path, candidate: Path) -> tuple[str, int]:
    require((reference / 'index.html').is_file(), f'not a static distribution: {reference}')
    require((candidate / 'index.html').is_file(), f'not a static distribution: {candidate}')

    reference_digest, reference_count = distribution_tree_digest(reference)
    candidate_digest, candidate_count = distribution_tree_digest(candidate)
    require(
        reference_count == candidate_count,
        f'distribution file count mismatch: {reference_count} != {candidate_count}',
    )
    require(
        reference_digest == candidate_digest,
        f'distribution tree digest mismatch: {reference_digest} != {candidate_digest}',
    )
    return reference_digest, reference_count


def main() -> None:
    parser = argparse.ArgumentParser(description='Compare two normalized static distributions')
    parser.add_argument('reference', type=Path)
    parser.add_argument('candidate', type=Path)
    args = parser.parse_args()

    digest, count = compare_distributions(
        args.reference.resolve(),
        args.candidate.resolve(),
    )
    print(f'reproducible distribution: {digest} ({count} files)')


if __name__ == '__main__':
    try:
        main()
    except BuildError as exc:
        raise SystemExit(str(exc))
