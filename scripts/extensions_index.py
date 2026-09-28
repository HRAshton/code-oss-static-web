#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def build_extension_index(dist: Path) -> dict[str, Any]:
    result: list[dict[str, Any]] = []
    extroot = dist / 'extensions'
    if not extroot.exists():
        return {'schemaVersion': 1, 'extensions': []}

    for pkg in sorted(extroot.glob('*/package.json')):
        try:
            data = json.loads(pkg.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            continue

        publisher = data.get('publisher', 'unknown')
        name = data.get('name', pkg.parent.name)
        result.append(
            {
                'id': f'{publisher}.{name}',
                'version': data.get('version'),
                'path': pkg.parent.relative_to(dist).as_posix() + '/',
                'browserCompatible': bool(data.get('browser')),
                'license': data.get('license'),
            }
        )

    return {'schemaVersion': 1, 'extensions': result}
