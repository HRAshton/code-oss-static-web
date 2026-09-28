#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from common import BuildError, require, sha256_file
from package_release import distribution_tree_digest


def compare_distributions(reference: Path, candidate: Path) -> tuple[str, int]:
    require((reference / 'index.html').is_file(), f'not a static distribution: {reference}')
    require((candidate / 'index.html').is_file(), f'not a static distribution: {candidate}')

    reference_files = {
        path.relative_to(reference).as_posix()
        for path in reference.rglob('*')
        if path.is_file()
    }
    candidate_files = {
        path.relative_to(candidate).as_posix()
        for path in candidate.rglob('*')
        if path.is_file()
    }
    missing = sorted(reference_files - candidate_files)
    extra = sorted(candidate_files - reference_files)

    reference_digest, reference_count = distribution_tree_digest(reference)
    candidate_digest, candidate_count = distribution_tree_digest(candidate)
    require(
        reference_count == candidate_count,
        'distribution file count mismatch: '
        f'{reference_count} != {candidate_count}; '
        f'missing from candidate={missing}; extra in candidate={extra}',
    )

    changed = [
        relative
        for relative in sorted(reference_files & candidate_files)
        if sha256_file(reference / relative) != sha256_file(candidate / relative)
    ]
    require(
        reference_digest == candidate_digest,
        'distribution tree digest mismatch: '
        f'{reference_digest} != {candidate_digest}; changed files={changed}',
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
        raise SystemExit(str(exc)) from None
