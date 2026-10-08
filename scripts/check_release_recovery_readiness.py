#!/usr/bin/env python3
"""Check whether completed game-day evidence has been committed.

This is an explicit operational readiness gate, not a substitute for an exercise.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from common import ROOT, BuildError, require
from verify_game_day_record import validate_file

DEFAULT_EVIDENCE_DIR = ROOT / 'release-evidence/game-days'


def validate_readiness(evidence_dir: Path = DEFAULT_EVIDENCE_DIR) -> list[Path]:
    records = sorted(evidence_dir.glob('*.json'))
    require(
        bool(records),
        'release recovery has no recorded game day: '
        'complete the controlled exercise in docs/release-game-day.md '
        'and commit its reviewed JSON evidence',
    )
    for record in records:
        validate_file(record)
    return records


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Require and validate committed release recovery game-day evidence'
    )
    parser.add_argument(
        '--evidence-dir',
        type=Path,
        default=DEFAULT_EVIDENCE_DIR,
        help='directory with completed game-day JSON records',
    )
    args = parser.parse_args()
    records = validate_readiness(args.evidence_dir)
    print(f'release recovery game-day evidence: {len(records)} valid record(s)')


if __name__ == '__main__':
    try:
        main()
    except BuildError as exc:
        raise SystemExit(str(exc)) from None
