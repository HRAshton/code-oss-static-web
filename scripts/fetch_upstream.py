#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

from common import ROOT, WORK, BuildError, load_json, require, run


def head(path: Path) -> str:
    return subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=path, text=True).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--clean', action='store_true')
    ns = ap.parse_args()
    lock = load_json(ROOT / 'upstream.lock.json')
    dest = WORK / 'vscode'
    if ns.clean and dest.exists():
        shutil.rmtree(dest)
    if not dest.exists():
        dest.mkdir(parents=True)
        run(['git', 'init', '-q'], cwd=dest)
        run(['git', 'remote', 'add', 'origin', lock['repository']], cwd=dest)
        run(['git', 'fetch', '--depth=1', 'origin', lock['commit']], cwd=dest)
        run(['git', 'checkout', '--detach', 'FETCH_HEAD'], cwd=dest)
    actual = head(dest)
    require(actual == lock['commit'], f'upstream HEAD mismatch: {actual} != {lock["commit"]}')
    print(f'verified upstream {lock["tag"]} @ {lock["commit"]}')


if __name__ == '__main__':
    try:
        main()
    except BuildError as e:
        raise SystemExit(str(e)) from None
