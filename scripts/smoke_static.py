#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

from common import BuildError, assert_no_symlinks

root = Path(sys.argv[1] if len(sys.argv) > 1 else 'dist')
try:
    assert_no_symlinks(root, label='static distribution')
except BuildError as exc:
    raise SystemExit(str(exc)) from None

required = [
    'index.html',
    'static-bootstrap.mjs',
    'runtime.json',
    'deployment-profile.json',
    'extensions.json',
    'additional-extensions.json',
    'out/nls.messages.js',
    'out/vs/workbench/workbench.web.main.internal.js',
    'out/vs/workbench/workbench.web.main.internal.css',
]
missing = [path for path in required if not (root / path).is_file()]
if missing:
    raise SystemExit('missing static files: ' + ', '.join(missing))

index = (root / 'index.html').read_text(encoding='utf-8')
if "connect-src 'self'" not in index:
    raise SystemExit('default CSP must restrict connect-src to self')

additional = json.loads((root / 'additional-extensions.json').read_text(encoding='utf-8'))
if additional.get('schemaVersion') != 1 or not isinstance(additional.get('extensions'), list):
    raise SystemExit('invalid additional extension manifest')

runtime = json.loads((root / 'runtime.json').read_text(encoding='utf-8'))
if runtime.get('telemetry') is not False:
    raise SystemExit('telemetry must be false in base runtime')

profile = json.loads((root / 'deployment-profile.json').read_text(encoding='utf-8'))
if profile.get('schemaVersion') != 1 or not isinstance(profile.get('id'), str):
    raise SystemExit('invalid deployment profile metadata')
digest = profile.get('configSha256')
if not isinstance(digest, str) or len(digest) != 64:
    raise SystemExit('invalid deployment profile digest')
if not isinstance(profile.get('bindings'), dict):
    raise SystemExit('deployment profile bindings missing')

bootstrap = (root / 'static-bootstrap.mjs').read_text(encoding='utf-8')
if 'invalid.invalid' not in bootstrap:
    raise SystemExit('fail-closed webview guard missing')
if 'workbench.web.main.internal.js' not in bootstrap:
    raise SystemExit('standalone workbench entrypoint missing')
if 'create(document.body, config)' not in bootstrap:
    raise SystemExit('standalone workbench create() call missing')
if "fetch(new URL('extensions.json'" in bootstrap:
    raise SystemExit('bootstrap must not re-register packaged system extensions')
if 'additional-extensions.json' not in bootstrap:
    raise SystemExit('bootstrap must load only the additional extension manifest')

print('static artifact structural smoke: ok')
