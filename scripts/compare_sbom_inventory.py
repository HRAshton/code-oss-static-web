#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any, cast

import generate_sbom
from common import BuildError, load_json, require, write_json

SYFT_LOCATION = re.compile(r'^syft:location:\d+:path$')
ALLOWED_DIRECTIONS = {'missingFromNative', 'missingFromIndependent'}
ALLOWED_MATCH_FIELDS = {'type', 'name', 'version', 'purl', 'path', 'bomRef'}


def _object(value: Any, label: str) -> dict[str, Any]:
    require(isinstance(value, dict), f'{label} must be an object')
    return cast(dict[str, Any], value)


def _array(value: Any, label: str) -> list[Any]:
    require(isinstance(value, list), f'{label} must be an array')
    return cast(list[Any], value)


def _string(value: Any, label: str) -> str:
    require(isinstance(value, str) and bool(value), f'{label} must be a non-empty string')
    return cast(str, value)


def _properties(component: dict[str, Any]) -> dict[str, str]:
    properties: dict[str, str] = {}
    for raw in _array(component.get('properties', []), 'CycloneDX component properties'):
        item = _object(raw, 'CycloneDX component property')
        name = _string(item.get('name'), 'CycloneDX property name')
        value = item.get('value')
        require(isinstance(value, str), f'CycloneDX property value must be a string: {name}')
        properties[name] = cast(str, value)
    return properties


def _normalize_path(value: str) -> str:
    path = value.replace('\\', '/').strip()
    while path.startswith('./'):
        path = path[2:]
    return path.lstrip('/').rstrip('/')


def _package_root(location: str) -> str:
    path = _normalize_path(location)
    if path.endswith('/package.json'):
        return path[: -len('/package.json')]
    if path == 'package.json':
        return ''
    return path


def _component_key(purl: str | None, path: str, bom_ref: str) -> str:
    if purl:
        return f'{purl}|{path}'
    return f'bom-ref:{bom_ref}'


def _syft_descriptor(sbom: dict[str, Any]) -> dict[str, str]:
    metadata = _object(sbom.get('metadata'), 'independent SBOM metadata')
    tools = metadata.get('tools')
    candidates: list[dict[str, Any]] = []
    if isinstance(tools, dict):
        tools_object = cast(dict[str, Any], tools)
        components_value = tools_object.get('components', [])
        if isinstance(components_value, list):
            components = cast(list[Any], components_value)
            candidates.extend(
                cast(dict[str, Any], item) for item in components if isinstance(item, dict)
            )
    elif isinstance(tools, list):
        tool_list = cast(list[Any], tools)
        candidates.extend(
            cast(dict[str, Any], item) for item in tool_list if isinstance(item, dict)
        )

    for tool in candidates:
        name = tool.get('name')
        if isinstance(name, str) and name.lower() == 'syft':
            return {
                'name': 'syft',
                'version': _string(
                    tool.get('version'),
                    'independent scanner version',
                ).removeprefix('v'),
            }
    raise BuildError('independent SBOM must identify Syft in metadata.tools')


def _native_records(sbom: dict[str, Any]) -> list[dict[str, Any]]:
    require(sbom.get('bomFormat') == 'CycloneDX', 'native SBOM format must be CycloneDX')
    records: list[dict[str, Any]] = []
    for raw in _array(sbom.get('components'), 'native SBOM components'):
        component = _object(raw, 'native SBOM component')
        bom_ref = _string(component.get('bom-ref'), 'native SBOM component bom-ref')
        component_type = _string(component.get('type'), f'native component type: {bom_ref}')
        name = _string(component.get('name'), f'native component name: {bom_ref}')
        version_value = component.get('version')
        version = version_value if isinstance(version_value, str) else ''
        purl_value = component.get('purl')
        purl = purl_value if isinstance(purl_value, str) and purl_value else None
        properties = _properties(component)
        path = _normalize_path(properties.get('code-oss-static-web:artifactPath', ''))

        extension_id = properties.get('code-oss-static-web:extensionId')
        if purl is None and extension_id is not None:
            require(bool(version), f'native extension version missing: {bom_ref}')
            purl = generate_sbom.npm_purl(name, version)
        elif purl is None and component_type == 'application' and name == 'Code - OSS':
            require(bool(version), f'native Code - OSS version missing: {bom_ref}')
            purl = generate_sbom.npm_purl(name, version)

        records.append(
            {
                'key': _component_key(purl, path, bom_ref),
                'type': component_type,
                'name': name,
                'version': version,
                'purl': purl,
                'path': path,
                'bomRef': bom_ref,
            }
        )
    records.sort(key=lambda item: str(item['key']))
    return records


def _independent_records(sbom: dict[str, Any]) -> tuple[dict[str, str], list[dict[str, Any]]]:
    require(sbom.get('bomFormat') == 'CycloneDX', 'independent SBOM format must be CycloneDX')
    scanner = _syft_descriptor(sbom)

    records_by_key: dict[str, dict[str, Any]] = {}
    for raw in _array(sbom.get('components', []), 'independent SBOM components'):
        component = _object(raw, 'independent SBOM component')
        purl_value = component.get('purl')
        if not isinstance(purl_value, str) or not purl_value:
            # Syft also emits file components in CycloneDX. They are evidence, not software
            # composition records, and are intentionally outside the component-set comparison.
            continue

        component_type_value = component.get('type')
        component_type = (
            component_type_value
            if isinstance(component_type_value, str) and component_type_value
            else 'library'
        )
        name = _string(component.get('name'), f'independent component name: {purl_value}')
        version_value = component.get('version')
        version = version_value if isinstance(version_value, str) else ''
        bom_ref_value = component.get('bom-ref')
        bom_ref = bom_ref_value if isinstance(bom_ref_value, str) else purl_value
        properties = _properties(component)
        found_by = properties.get('syft:package:foundBy', '')
        locations = sorted(
            {
                _normalize_path(value)
                for key, value in properties.items()
                if SYFT_LOCATION.fullmatch(key)
            }
        )
        roots = sorted({_package_root(location) for location in locations}) or ['']

        for root in roots:
            key = _component_key(purl_value, root, bom_ref)
            record = records_by_key.get(key)
            if record is None:
                records_by_key[key] = {
                    'key': key,
                    'type': component_type,
                    'name': name,
                    'version': version,
                    'purl': purl_value,
                    'path': root,
                    'bomRef': bom_ref,
                    'locations': locations,
                    'foundBy': found_by,
                }
                continue
            record_locations = cast(list[str], record['locations'])
            record['locations'] = sorted(set(record_locations).union(locations))

    require(
        bool(records_by_key),
        'independent SBOM discovered no software components',
    )
    return scanner, sorted(records_by_key.values(), key=lambda item: str(item['key']))


def _load_policy(data: dict[str, Any]) -> tuple[dict[str, str], list[dict[str, Any]]]:
    require(data.get('schemaVersion') == 1, 'SBOM comparison policy schemaVersion must be 1')
    scanner = _object(data.get('scanner'), 'SBOM comparison scanner policy')
    scanner_name = _string(scanner.get('name'), 'SBOM comparison scanner name')
    scanner_version = _string(scanner.get('version'), 'SBOM comparison scanner version')

    exceptions: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for raw in _array(data.get('exceptions'), 'SBOM comparison exceptions'):
        exception = _object(raw, 'SBOM comparison exception')
        exception_id = _string(exception.get('id'), 'SBOM comparison exception id')
        require(
            exception_id not in seen_ids,
            f'duplicate SBOM comparison exception id: {exception_id}',
        )
        seen_ids.add(exception_id)
        direction = _string(exception.get('direction'), f'exception direction: {exception_id}')
        require(
            direction in ALLOWED_DIRECTIONS,
            f'invalid SBOM comparison exception direction: {exception_id}',
        )
        reason = _string(exception.get('reason'), f'exception reason: {exception_id}')
        match = _object(exception.get('match'), f'exception match: {exception_id}')
        require(bool(match), f'exception match must not be empty: {exception_id}')
        require(
            set(match).issubset(ALLOWED_MATCH_FIELDS),
            f'exception match has unsupported fields: {exception_id}',
        )
        normalized_match: dict[str, str] = {}
        for field, value in match.items():
            normalized_match[field] = _string(value, f'exception {exception_id} match {field}')
        exceptions.append(
            {
                'id': exception_id,
                'direction': direction,
                'reason': reason,
                'match': normalized_match,
            }
        )

    return {'name': scanner_name, 'version': scanner_version}, exceptions


def _matches(record: dict[str, Any], match: dict[str, str]) -> bool:
    return all(record.get(field) == value for field, value in match.items())


def _apply_exceptions(
    direction: str,
    records: list[dict[str, Any]],
    exceptions: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], set[str]]:
    unexplained: list[dict[str, Any]] = []
    applied: list[dict[str, Any]] = []
    used_ids: set[str] = set()

    for record in records:
        matching = [
            exception
            for exception in exceptions
            if exception['direction'] == direction
            and _matches(record, cast(dict[str, str], exception['match']))
        ]
        require(
            len(matching) <= 1,
            f'multiple SBOM comparison exceptions match component: {record["key"]}',
        )
        if not matching:
            unexplained.append(record)
            continue
        exception = matching[0]
        exception_id = cast(str, exception['id'])
        used_ids.add(exception_id)
        applied.append(
            {
                'id': exception_id,
                'direction': direction,
                'componentKey': record['key'],
                'reason': exception['reason'],
            }
        )

    return unexplained, applied, used_ids


def compare_documents(
    native_sbom: dict[str, Any],
    independent_sbom: dict[str, Any],
    policy: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    expected_scanner, exceptions = _load_policy(policy)
    scanner, independent = _independent_records(independent_sbom)
    require(
        scanner == expected_scanner,
        (
            'independent scanner mismatch: '
            f'expected {expected_scanner["name"]} {expected_scanner["version"]}, '
            f'got {scanner["name"]} {scanner["version"]}'
        ),
    )
    native = _native_records(native_sbom)

    native_by_key = {cast(str, item['key']): item for item in native}
    independent_by_key = {cast(str, item['key']): item for item in independent}
    require(len(native_by_key) == len(native), 'duplicate normalized native SBOM component key')
    require(
        len(independent_by_key) == len(independent),
        'duplicate normalized independent SBOM component key',
    )

    matched_keys = sorted(set(native_by_key).intersection(independent_by_key))
    missing_from_native = [
        independent_by_key[key] for key in sorted(set(independent_by_key) - set(native_by_key))
    ]
    missing_from_independent = [
        native_by_key[key] for key in sorted(set(native_by_key) - set(independent_by_key))
    ]

    unexplained_native, applied_native, used_native = _apply_exceptions(
        'missingFromNative',
        missing_from_native,
        exceptions,
    )
    unexplained_independent, applied_independent, used_independent = _apply_exceptions(
        'missingFromIndependent',
        missing_from_independent,
        exceptions,
    )
    used = used_native.union(used_independent)
    configured = {cast(str, item['id']) for item in exceptions}
    unused = sorted(configured - used)
    require(
        not unused,
        f'unused SBOM comparison exception(s): {", ".join(unused)}',
    )

    inventory = {
        'schemaVersion': 1,
        'scanner': scanner,
        'components': independent,
    }
    status = 'pass' if not unexplained_native and not unexplained_independent else 'fail'
    report = {
        'schemaVersion': 1,
        'status': status,
        'scanner': scanner,
        'summary': {
            'nativeComponents': len(native),
            'independentComponents': len(independent),
            'matchedComponents': len(matched_keys),
            'missingFromNative': len(missing_from_native),
            'missingFromIndependent': len(missing_from_independent),
            'unexplainedMissingFromNative': len(unexplained_native),
            'unexplainedMissingFromIndependent': len(unexplained_independent),
            'appliedExceptions': len(applied_native) + len(applied_independent),
        },
        'missingFromNative': missing_from_native,
        'missingFromIndependent': missing_from_independent,
        'unexplainedMissingFromNative': unexplained_native,
        'unexplainedMissingFromIndependent': unexplained_independent,
        'appliedExceptions': sorted(
            applied_native + applied_independent,
            key=lambda item: (str(item['direction']), str(item['id']), str(item['componentKey'])),
        ),
    }
    return inventory, report


def compare_files(
    native_sbom_path: Path,
    independent_sbom_path: Path,
    policy_path: Path,
    inventory_output: Path,
    comparison_output: Path,
) -> dict[str, Any]:
    inventory, report = compare_documents(
        _object(load_json(native_sbom_path), 'native SBOM'),
        _object(load_json(independent_sbom_path), 'independent SBOM'),
        _object(load_json(policy_path), 'SBOM comparison policy'),
    )
    write_json(inventory_output, inventory)
    write_json(comparison_output, report)

    if report['status'] != 'pass':
        missing_native = cast(list[dict[str, Any]], report['unexplainedMissingFromNative'])
        missing_independent = cast(
            list[dict[str, Any]],
            report['unexplainedMissingFromIndependent'],
        )
        details: list[str] = []
        if missing_native:
            details.append(
                'missing from native SBOM: '
                + ', '.join(str(item['key']) for item in missing_native)
            )
        if missing_independent:
            details.append(
                'missing from independent inventory: '
                + ', '.join(str(item['key']) for item in missing_independent)
            )
        raise BuildError('independent SBOM comparison failed: ' + '; '.join(details))

    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Compare the project SBOM with an independently generated Syft inventory'
    )
    parser.add_argument('--native-sbom', required=True, type=Path)
    parser.add_argument('--independent-sbom', required=True, type=Path)
    parser.add_argument('--policy', required=True, type=Path)
    parser.add_argument('--inventory-output', required=True, type=Path)
    parser.add_argument('--comparison-output', required=True, type=Path)
    args = parser.parse_args()

    report = compare_files(
        args.native_sbom.resolve(),
        args.independent_sbom.resolve(),
        args.policy.resolve(),
        args.inventory_output.resolve(),
        args.comparison_output.resolve(),
    )
    summary = cast(dict[str, Any], report['summary'])
    print(
        'independent SBOM comparison: '
        f'{summary["matchedComponents"]} matched, '
        f'{summary["appliedExceptions"]} explicit exception(s)'
    )


if __name__ == '__main__':
    try:
        main()
    except BuildError as exc:
        raise SystemExit(str(exc)) from None
