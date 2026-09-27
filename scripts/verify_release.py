#!/usr/bin/env python3
from __future__ import annotations
import argparse
from pathlib import Path
from common import BuildError, sha256_file, require

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('directory', nargs='?', default='artifacts'); ns = ap.parse_args()
    d = Path(ns.directory); sums = d / 'SHA256SUMS'
    require(sums.is_file(), f'missing {sums}')
    count = 0
    for line in sums.read_text(encoding='utf-8').splitlines():
        if not line.strip(): continue
        digest, name = line.split(None, 1); name = name.strip().lstrip('*')
        p = d / name
        require(p.is_file(), f'missing release file: {name}')
        require(sha256_file(p) == digest, f'checksum mismatch: {name}')
        count += 1
    require(count > 0, 'empty checksum manifest')
    print(f'verified {count} release files')

if __name__ == '__main__':
    try:
        main()
    except BuildError as e:
        raise SystemExit(str(e))
