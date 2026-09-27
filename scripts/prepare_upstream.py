#!/usr/bin/env python3
from __future__ import annotations
import json
from common import ROOT, WORK, BuildError, load_json, write_json, require

def main():
    src = WORK / 'vscode'
    require((src / '.git').exists(), 'run scripts/fetch_upstream.py first')
    product_path = src / 'product.json'
    product = load_json(product_path)
    transform = load_json(ROOT / 'config/product-transform.json')
    previous = {}
    for key, value in transform.get('set', {}).items():
        previous[key] = product.get(key, '<absent>')
        product[key] = value
    for key in transform.get('remove', []):
        previous[key] = product.get(key, '<absent>')
        product.pop(key, None)
    product_path.write_text(json.dumps(product, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    write_json(WORK / 'product-transform-report.json', {
        'set': transform.get('set', {}),
        'removed': transform.get('remove', []),
        'previousValues': previous,
    })
    print('applied deterministic product transform')

if __name__ == '__main__':
    try:
        main()
    except BuildError as e:
        raise SystemExit(str(e))
