#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from common import ROOT, WORK, BuildError, load_json, require, run

FULL_SHA = re.compile(r'^[0-9a-f]{40}$')


def head(path: Path) -> str:
    return subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=path, text=True).strip()


def resolve_remote_tag(repository: str, tag: str) -> str:
    tag_ref = f'refs/tags/{tag}'
    run(['git', 'check-ref-format', tag_ref])
    peeled_ref = f'{tag_ref}^{{}}'
    command = ['git', 'ls-remote', '--tags', repository, tag_ref, peeled_ref]
    print('+', ' '.join(command), flush=True)
    try:
        output = subprocess.check_output(
            command,
            text=True,
            stderr=subprocess.STDOUT,
        )
    except subprocess.CalledProcessError as exc:
        detail = exc.output.strip()
        suffix = f': {detail}' if detail else ''
        raise BuildError(
            f'failed to resolve upstream tag {tag} ({exc.returncode}){suffix}'
        ) from None

    refs: dict[str, str] = {}
    for line in output.splitlines():
        sha, separator, ref = line.partition('\t')
        require(bool(separator), f'invalid ls-remote output for upstream tag {tag}')
        require(
            FULL_SHA.fullmatch(sha) is not None,
            f'invalid object ID for upstream tag {tag}: {sha}',
        )
        refs[ref] = sha

    require(tag_ref in refs, f'upstream tag not found: {tag}')
    return refs.get(peeled_ref, refs[tag_ref])


def verify_tag_binding(lock: dict[str, Any]) -> str:
    repository = lock.get('repository')
    tag = lock.get('tag')
    commit = lock.get('commit')
    require(
        isinstance(repository, str) and bool(repository), 'upstream repository must be a string'
    )
    assert isinstance(repository, str)
    require(isinstance(tag, str) and bool(tag), 'upstream tag must be a string')
    assert isinstance(tag, str)
    require(
        isinstance(commit, str) and FULL_SHA.fullmatch(commit) is not None,
        'upstream commit must be a full SHA',
    )
    assert isinstance(commit, str)

    resolved = resolve_remote_tag(repository, tag)
    require(
        resolved == commit,
        f'upstream tag mismatch: {tag} resolves to {resolved}, expected {commit}',
    )
    print(f'verified upstream tag {tag} -> {resolved}')
    return resolved


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--clean', action='store_true')
    ap.add_argument('--verify-tag-only', action='store_true')
    ns = ap.parse_args()
    lock = load_json(ROOT / 'upstream.lock.json')

    verify_tag_binding(lock)
    if ns.verify_tag_only:
        return

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
