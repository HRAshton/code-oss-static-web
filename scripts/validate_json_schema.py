#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, cast

from common import ROOT, BuildError

SCHEMA_TARGETS = (
    ('upstream.lock.json', 'schemas/upstream.lock.schema.json'),
    ('config/deployment.json', 'schemas/deployment-selector.schema.json'),
    ('config/promotion-policy.json', 'schemas/promotion-policy.schema.json'),
    ('patches/manifest.json', 'schemas/patch-manifest.schema.json'),
    ('extensions/extensions.lock.json', 'extensions/extensions.lock.schema.json'),
    ('extensions/license-policy.json', 'schemas/license-policy.schema.json'),
    ('extensions/source-policy.json', 'schemas/source-policy.schema.json'),
)

SCHEMA_GLOBS = (
    ('config/profiles/*.json', 'schemas/deployment-profile.schema.json'),
    ('config/policies/runtime/*.json', 'schemas/runtime.schema.json'),
    ('config/policies/network/*.json', 'schemas/network-policy.schema.json'),
    ('config/policies/product/*.json', 'schemas/product-transform.schema.json'),
    ('config/policies/proposed-api/*.json', 'schemas/proposed-api-policy.schema.json'),
    ('config/policies/webview/*.json', 'schemas/webview-policy.schema.json'),
    ('config/policies/branding/*.json', 'schemas/branding-policy.schema.json'),
    ('config/policies/support/*.json', 'schemas/support-policy.schema.json'),
)


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8'))


def _fail(path: str, message: str) -> None:
    raise BuildError(f'{path}: {message}')


def _validate(value: Any, schema: dict[str, Any], path: str) -> None:
    if 'oneOf' in schema:
        matches = 0
        for candidate in cast(list[dict[str, Any]], schema['oneOf']):
            try:
                _validate(value, candidate, path)
            except BuildError:
                continue
            matches += 1
        if matches != 1:
            _fail(path, f'oneOf expected exactly one match, got {matches}')
        return

    if 'not' in schema:
        try:
            _validate(value, cast(dict[str, Any], schema['not']), path)
        except BuildError:
            pass
        else:
            _fail(path, 'matched forbidden schema')

    expected_type = schema.get('type')
    if expected_type is not None:
        valid = {
            'object': isinstance(value, dict),
            'array': isinstance(value, list),
            'string': isinstance(value, str),
            'integer': isinstance(value, int) and not isinstance(value, bool),
            'boolean': isinstance(value, bool),
            'number': isinstance(value, (int, float)) and not isinstance(value, bool),
            'null': value is None,
        }.get(expected_type)
        if valid is not True:
            _fail(path, f'expected {expected_type}')

    if 'const' in schema and value != schema['const']:
        _fail(path, f'expected constant {schema["const"]!r}')

    if 'enum' in schema and value not in schema['enum']:
        _fail(path, f'expected one of {schema["enum"]!r}')

    if isinstance(value, str):
        if 'minLength' in schema and len(value) < schema['minLength']:
            _fail(path, f'minLength is {schema["minLength"]}')
        pattern = schema.get('pattern')
        if pattern is not None and re.search(pattern, value) is None:
            _fail(path, f'does not match {pattern!r}')

    if isinstance(value, int) and not isinstance(value, bool):
        if 'minimum' in schema and value < schema['minimum']:
            _fail(path, f'minimum is {schema["minimum"]}')

    if isinstance(value, list):
        array_value = cast(list[Any], value)
        min_items = schema.get('minItems')
        if isinstance(min_items, int) and len(array_value) < min_items:
            _fail(path, f'minItems is {min_items}')
        item_schema = schema.get('items')
        if isinstance(item_schema, dict):
            typed_item_schema = cast(dict[str, Any], item_schema)
            for index, item in enumerate(array_value):
                _validate(item, typed_item_schema, f'{path}[{index}]')

    if isinstance(value, dict):
        object_value = cast(dict[str, Any], value)
        required = cast(list[str], schema.get('required', []))
        for key in required:
            if key not in object_value:
                _fail(path, f'missing required key {key!r}')
        properties = cast(dict[str, dict[str, Any]], schema.get('properties', {}))
        if schema.get('additionalProperties') is False:
            extra = set(object_value) - set(properties)
            if extra:
                _fail(path, f'unexpected keys: {sorted(extra)!r}')
        for key, child_schema in properties.items():
            if key in object_value:
                _validate(object_value[key], child_schema, f'{path}.{key}')


def _validate_target(target_path: Path, schema_path: Path) -> None:
    if not target_path.is_file():
        raise BuildError(f'missing schema target: {target_path.relative_to(ROOT)}')
    if not schema_path.is_file():
        raise BuildError(f'missing schema: {schema_path.relative_to(ROOT)}')
    target = _load(target_path)
    schema_value = _load(schema_path)
    if not isinstance(schema_value, dict):
        raise BuildError(f'schema root must be object: {schema_path.relative_to(ROOT)}')
    _validate(
        target,
        cast(dict[str, Any], schema_value),
        target_path.relative_to(ROOT).as_posix(),
    )


def validate_all() -> None:
    for target_name, schema_name in SCHEMA_TARGETS:
        _validate_target(ROOT / target_name, ROOT / schema_name)
    for pattern, schema_name in SCHEMA_GLOBS:
        targets = sorted(ROOT.glob(pattern))
        if not targets:
            raise BuildError(f'no schema targets matched: {pattern}')
        for target_path in targets:
            _validate_target(target_path, ROOT / schema_name)


def main() -> None:
    validate_all()
    print('JSON schema validation: ok')


if __name__ == '__main__':
    try:
        main()
    except (BuildError, json.JSONDecodeError) as exc:
        raise SystemExit(str(exc)) from None
