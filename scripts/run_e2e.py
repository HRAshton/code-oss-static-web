#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path

from common import ROOT, WORK, BuildError, require


def playwright_node_modules() -> Path:
    runtime = WORK / 'playwright-runtime' / 'node_modules'
    if (runtime / '@playwright/test/cli.js').is_file():
        return runtime

    upstream = WORK / 'vscode' / 'node_modules'
    if (upstream / '@playwright/test/cli.js').is_file():
        return upstream

    raise BuildError(
        'Playwright runtime not found; download the qualification runtime artifact or run ./build.sh'
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Run browser qualification against a built static distribution'
    )
    parser.add_argument('--project', default='chromium')
    parser.add_argument('--dist', type=Path, default=ROOT / 'dist')
    parser.add_argument('--base-url')
    parser.add_argument('--headed', action='store_true')
    args, extra = parser.parse_known_args()

    node_modules = playwright_node_modules()
    cli = node_modules / '@playwright/test/cli.js'
    node = shutil.which('node')
    if node is None:
        raise BuildError('node executable not found')
    require((args.dist / 'index.html').is_file(), f'static distribution missing: {args.dist}')

    env = os.environ.copy()
    env['CODE_OSS_STATIC_WEB_DIST'] = str(args.dist.resolve())
    env['CODE_OSS_STATIC_WEB_BASE_PATH'] = env.get(
        'CODE_OSS_STATIC_WEB_BASE_PATH',
        '/code-oss-web/',
    )
    if args.base_url:
        env['CODE_OSS_STATIC_WEB_EXTERNAL_BASE_URL'] = args.base_url
    env['NODE_PATH'] = str(node_modules) + (
        os.pathsep + env['NODE_PATH'] if env.get('NODE_PATH') else ''
    )

    command = [
        node,
        str(cli),
        'test',
        '--config',
        str(ROOT / 'tests' / 'e2e' / 'playwright.config.cjs'),
    ]
    if args.project != 'all':
        command.extend(['--project', args.project])
    if args.headed:
        command.append('--headed')
    command.extend(extra)
    raise SystemExit(subprocess.call(command, cwd=ROOT, env=env))


if __name__ == '__main__':
    try:
        main()
    except BuildError as exc:
        raise SystemExit(str(exc)) from None
