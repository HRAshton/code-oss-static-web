from __future__ import annotations
from pathlib import Path
import hashlib, json, os, subprocess

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / '.work'
DIST = ROOT / 'dist'
ARTIFACTS = ROOT / 'artifacts'

class BuildError(RuntimeError):
    pass

def load_json(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))

def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

def run(args, *, cwd=None, env=None):
    print('+', ' '.join(map(str, args)), flush=True)
    merged = os.environ.copy()
    if env:
        merged.update({str(k): str(v) for k, v in env.items()})
    p = subprocess.run([str(x) for x in args], cwd=cwd, env=merged)
    if p.returncode:
        raise BuildError(f'command failed ({p.returncode}): {args}')

def require(condition: bool, message: str):
    if not condition:
        raise BuildError(message)
