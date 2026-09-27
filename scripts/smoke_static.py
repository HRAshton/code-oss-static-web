#!/usr/bin/env python3
from pathlib import Path
import json, sys
root = Path(sys.argv[1] if len(sys.argv) > 1 else 'dist')
required = [
    'index.html', 'static-bootstrap.mjs', 'runtime.json', 'extensions.json',
    'out/vs/code/browser/workbench/workbench.js', 'out/nls.messages.js',
]
missing = [p for p in required if not (root / p).is_file()]
if missing: raise SystemExit('missing static files: ' + ', '.join(missing))
index = (root / 'index.html').read_text(encoding='utf-8')
if "connect-src 'self'" not in index: raise SystemExit('default CSP must restrict connect-src to self')
runtime = json.loads((root / 'runtime.json').read_text(encoding='utf-8'))
if runtime.get('telemetry') is not False: raise SystemExit('telemetry must be false in base runtime')
bootstrap = (root / 'static-bootstrap.mjs').read_text(encoding='utf-8')
if 'invalid.invalid' not in bootstrap: raise SystemExit('fail-closed webview guard missing')
print('static artifact structural smoke: ok')
