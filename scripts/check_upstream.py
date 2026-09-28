#!/usr/bin/env python3
from __future__ import annotations

import json
import urllib.request

from common import ROOT, load_json


def main():
    current = load_json(ROOT / 'upstream.lock.json')
    req = urllib.request.Request(
        'https://api.github.com/repos/microsoft/vscode/releases/latest',
        headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'code-oss-static-web'},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        latest = json.load(r)
    tag = latest['tag_name']
    print(
        json.dumps(
            {
                'current': current['tag'],
                'latest': tag,
                'updateAvailable': tag != current['tag'],
                'htmlUrl': latest.get('html_url'),
            },
            indent=2,
        )
    )
    raise SystemExit(10 if tag != current['tag'] else 0)


if __name__ == '__main__':
    main()
