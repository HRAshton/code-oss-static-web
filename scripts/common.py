from __future__ import annotations

import hashlib
import json
import os
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / '.work'
DIST = ROOT / 'dist'
ARTIFACTS = ROOT / 'artifacts'


class BuildError(RuntimeError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    value: object = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise BuildError(f'JSON root must be an object: {path}')
    return cast(dict[str, Any], value)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def assert_no_symlinks(root: Path, *, label: str = 'distribution') -> None:
    require(
        not root.is_symlink(),
        f'{label} root must not be a symlink: {root}',
    )
    require(
        root.is_dir(),
        f'{label} root is not a directory: {root}',
    )
    symlinks = sorted(
        path.relative_to(root).as_posix() for path in root.rglob('*') if path.is_symlink()
    )
    require(
        not symlinks,
        f'{label} contains symlink entries: {symlinks}',
    )


def run(
    args: Sequence[object],
    *,
    cwd: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> None:
    print('+', ' '.join(map(str, args)), flush=True)
    merged = os.environ.copy()
    if env:
        merged.update({str(k): str(v) for k, v in env.items()})
    p = subprocess.run([str(x) for x in args], cwd=cwd, env=merged)
    if p.returncode:
        raise BuildError(f'command failed ({p.returncode}): {args}')


def require(condition: bool, message: str) -> None:
    if not condition:
        raise BuildError(message)
