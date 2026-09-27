#!/usr/bin/env python3
from __future__ import annotations
from common import ROOT, WORK, BuildError, load_json, require, run

def main():
    src = WORK / 'vscode'
    require((src / '.git').exists(), 'run scripts/fetch_upstream.py first')
    manifest = load_json(ROOT / 'patches/manifest.json')
    entries = manifest.get('patches', [])
    for entry in entries:
        patch = ROOT / 'patches' / entry['file']
        require(patch.is_file(), f'missing patch: {patch}')
        print(f"patch {entry.get('id', patch.name)}: {entry.get('purpose', '')}")
        run(['git', 'apply', '--check', str(patch)], cwd=src)
        run(['git', 'apply', str(patch)], cwd=src)
    print(f'applied {len(entries)} patch(es)')

if __name__ == '__main__':
    try:
        main()
    except BuildError as e:
        raise SystemExit(str(e))
