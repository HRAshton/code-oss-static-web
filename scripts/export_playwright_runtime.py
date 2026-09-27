#!/usr/bin/env python3
from __future__ import annotations

import shutil
from pathlib import Path

from common import WORK, BuildError, require

PACKAGES = (
    Path('@playwright/test'),
    Path('playwright'),
    Path('playwright-core'),
)


def main() -> None:
    source_root = WORK / 'vscode' / 'node_modules'
    target_root = WORK / 'playwright-runtime' / 'node_modules'
    require(source_root.is_dir(), 'upstream node_modules missing; run npm ci first')

    if target_root.parent.exists():
        shutil.rmtree(target_root.parent)
    target_root.mkdir(parents=True, exist_ok=True)

    for package in PACKAGES:
        source = source_root / package
        target = target_root / package
        require(source.is_dir(), f'Playwright package missing from upstream install: {package}')
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, target, symlinks=True)

    require(
        (target_root / '@playwright/test/cli.js').is_file(),
        'exported @playwright/test CLI missing',
    )
    require(
        (target_root / 'playwright/cli.js').is_file(),
        'exported Playwright CLI missing',
    )
    print(f'exported Playwright runtime: {target_root.parent}')


if __name__ == '__main__':
    try:
        main()
    except BuildError as exc:
        raise SystemExit(str(exc))
