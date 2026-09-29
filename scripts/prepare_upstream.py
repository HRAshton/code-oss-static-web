#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from common import ROOT, WORK, BuildError, load_json, require, write_json


def validate_enabled_api_proposals(src: Path, value: object) -> None:
    if not isinstance(value, dict):
        raise BuildError('extensionEnabledApiProposals must be an object')
    grants = cast(dict[object, object], value)

    for extension_id, raw_proposals in grants.items():
        if not isinstance(extension_id, str) or not extension_id:
            raise BuildError('extensionEnabledApiProposals keys must be non-empty extension IDs')
        if not isinstance(raw_proposals, list):
            raise BuildError(f"extensionEnabledApiProposals['{extension_id}'] must be an array")

        for proposal in cast(list[object], raw_proposals):
            if not isinstance(proposal, str) or not proposal:
                raise BuildError(
                    f"extensionEnabledApiProposals['{extension_id}'] entries must be strings"
                )
            proposal_path = src / 'src/vscode-dts' / f'vscode.proposed.{proposal}.d.ts'
            if not proposal_path.is_file():
                raise BuildError(
                    f"configured API proposal '{proposal}' for extension '{extension_id}' "
                    'does not exist in the pinned Code-OSS revision'
                )


def main():
    src = WORK / 'vscode'
    require((src / '.git').exists(), 'run scripts/fetch_upstream.py first')
    product_path = src / 'product.json'
    product = load_json(product_path)
    transform = load_json(ROOT / 'config/product-transform.json')
    set_values = transform.get('set', {})
    validate_enabled_api_proposals(
        src,
        set_values.get('extensionEnabledApiProposals', {})
        if isinstance(set_values, dict)
        else set_values,
    )

    previous = {}
    for key, value in transform.get('set', {}).items():
        previous[key] = product.get(key, '<absent>')
        product[key] = value
    for key in transform.get('remove', []):
        previous[key] = product.get(key, '<absent>')
        product.pop(key, None)
    product_path.write_text(
        json.dumps(product, indent=2, ensure_ascii=False) + '\n', encoding='utf-8'
    )
    write_json(
        WORK / 'product-transform-report.json',
        {
            'set': transform.get('set', {}),
            'removed': transform.get('remove', []),
            'previousValues': previous,
        },
    )
    print('applied deterministic product transform')


if __name__ == '__main__':
    try:
        main()
    except BuildError as e:
        raise SystemExit(str(e)) from None
