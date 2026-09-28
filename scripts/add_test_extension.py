#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from common import ROOT, BuildError, load_json, require, write_json
from extensions_index import build_extension_index


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Inject the repository-owned qualification web extension'
    )
    parser.add_argument('--dist', type=Path, required=True)
    parser.add_argument(
        '--extension',
        type=Path,
        default=ROOT / 'tests' / 'fixtures' / 'web-extension',
    )
    args = parser.parse_args()

    dist = args.dist.resolve()
    extension = args.extension.resolve()
    require((dist / 'index.html').is_file(), f'not a static distribution: {dist}')
    require((extension / 'package.json').is_file(), f'not an extension fixture: {extension}')

    target = dist / 'extensions' / 'code-oss-static-web-test'
    if target.exists():
        shutil.rmtree(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(extension, target)
    package = load_json(target / 'package.json')
    extension_id = f'{package["publisher"]}.{package["name"]}'
    additional_path = dist / 'additional-extensions.json'
    additional = load_json(additional_path)
    additional['extensions'] = [
        entry for entry in additional.get('extensions', []) if entry.get('id') != extension_id
    ]
    additional['extensions'].append(
        {
            'id': extension_id,
            'path': target.relative_to(dist).as_posix() + '/',
        }
    )
    write_json(additional_path, additional)
    write_json(dist / 'extensions.json', build_extension_index(dist))
    print(f'qualification extension added: {target}')


if __name__ == '__main__':
    try:
        main()
    except BuildError as exc:
        raise SystemExit(str(exc)) from None
