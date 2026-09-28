#!/usr/bin/env python3
from __future__ import annotations

import argparse

from common import ROOT, WORK, BuildError, require, run


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--skip-install', action='store_true')
    parser.add_argument('--clean-upstream', action='store_true')
    parser.add_argument('--reuse-upstream-build', action='store_true')
    args = parser.parse_args()

    run([ROOT / 'scripts/fetch_upstream.py'] + (['--clean'] if args.clean_upstream else []))
    source = WORK / 'vscode'
    built = WORK / 'vscode-web'
    runtime = WORK / 'playwright-runtime' / 'node_modules'

    if args.reuse_upstream_build:
        require(built.is_dir(), f'cached upstream web build missing: {built}')
        require(
            (runtime / '@playwright/test/cli.js').is_file(),
            'cached Playwright runtime missing',
        )
        print('reusing cached upstream Code-OSS web build')
    else:
        run(['git', 'reset', '--hard', 'HEAD'], cwd=source)
        run(['git', 'clean', '-ffd'], cwd=source)
        run([ROOT / 'scripts/prepare_upstream.py'])
        run([ROOT / 'scripts/apply_patches.py'])
        if not args.skip_install:
            run(['npm', 'ci'], cwd=source)
        run(['npm', 'run', 'gulp', '--', 'vscode-web-min'], cwd=source)
        require(built.exists(), f'expected upstream output missing: {built}')
        run([ROOT / 'scripts/export_playwright_runtime.py'])

    run([ROOT / 'scripts/make_static.py', '--input', built])


if __name__ == '__main__':
    try:
        main()
    except BuildError as exc:
        raise SystemExit(str(exc)) from None
