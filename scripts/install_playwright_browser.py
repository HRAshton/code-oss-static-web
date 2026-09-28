#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

from common import WORK, BuildError, require


def playwright_cli() -> Path:
    candidates = [
        WORK / 'playwright-runtime' / 'node_modules' / 'playwright' / 'cli.js',
        WORK / 'vscode' / 'node_modules' / 'playwright' / 'cli.js',
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise BuildError(
        'Playwright runtime not found; download the qualification runtime artifact or run ./build.sh'
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Install browsers using the Playwright version locked by Code-OSS'
    )
    parser.add_argument('browsers', nargs='+', choices=['chromium', 'firefox', 'webkit'])
    parser.add_argument('--with-deps', action='store_true')
    args = parser.parse_args()

    cli = playwright_cli()
    node = shutil.which('node')
    require(node is not None, 'node executable not found')

    command = [node, str(cli), 'install']
    if args.with_deps:
        command.append('--with-deps')
    command.extend(args.browsers)
    raise SystemExit(subprocess.call(command))


if __name__ == '__main__':
    try:
        main()
    except BuildError as exc:
        raise SystemExit(str(exc)) from None
