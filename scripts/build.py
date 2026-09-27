#!/usr/bin/env python3
from __future__ import annotations
import argparse
from common import ROOT, WORK, BuildError, require, run

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--skip-install', action='store_true')
    ap.add_argument('--clean-upstream', action='store_true')
    ns = ap.parse_args()
    run([ROOT / 'scripts/fetch_upstream.py'] + (['--clean'] if ns.clean_upstream else []))
    src = WORK / 'vscode'
    run(['git', 'reset', '--hard', 'HEAD'], cwd=src)
    run(['git', 'clean', '-ffd'], cwd=src)
    run([ROOT / 'scripts/prepare_upstream.py'])
    run([ROOT / 'scripts/apply_patches.py'])
    if not ns.skip_install:
        run(['npm', 'ci'], cwd=src)
    run(['npm', 'run', 'gulp', '--', 'vscode-web-min'], cwd=src)
    built = WORK / 'vscode-web'
    require(built.exists(), f'expected upstream output missing: {built}')
    run([ROOT / 'scripts/make_static.py', '--input', built])

if __name__ == '__main__':
    try:
        main()
    except BuildError as e:
        raise SystemExit(str(e))
