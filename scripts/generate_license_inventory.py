#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from typing import Any

import generate_sbom
from common import require, write_json

NOASSERTION = 'NOASSERTION'


def declared_license(value: Any) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return NOASSERTION


def component_entry(
    *,
    bom_ref: str,
    kind: str,
    name: str,
    version: str,
    license_value: Any,
    artifact_path: str | None = None,
    source: str | None = None,
    license_file: str | None = None,
    notices_file: str | None = None,
) -> dict[str, Any]:
    license_name = declared_license(license_value)
    entry: dict[str, Any] = {
        'bomRef': bom_ref,
        'kind': kind,
        'name': name,
        'version': version,
        'declaredLicense': license_name,
        'licenseStatus': 'no-assertion' if license_name == NOASSERTION else 'declared',
    }
    if artifact_path is not None:
        entry['artifactPath'] = artifact_path
    if source is not None:
        entry['source'] = source
    if license_file is not None:
        entry['licenseFile'] = license_file
    if notices_file is not None:
        entry['noticesFile'] = notices_file
    return entry


def build_license_inventory(
    *,
    metadata: dict[str, Any],
    version: str,
    project_commit: str,
    upstream: dict[str, Any],
) -> dict[str, Any]:
    components: list[dict[str, Any]] = [
        component_entry(
            bom_ref=f'code-oss-static-web:{project_commit}',
            kind='project',
            name='Code OSS Static Web',
            version=version,
            license_value='MIT',
            source='project',
            license_file='LICENSE',
            notices_file='THIRD_PARTY_NOTICES.md',
        ),
        component_entry(
            bom_ref=f'code-oss:{upstream["commit"]}',
            kind='upstream',
            name='Code - OSS',
            version=str(upstream['tag']),
            license_value='MIT',
            source='microsoft/vscode',
            license_file='LICENSE.Code-OSS.txt',
            notices_file='ThirdPartyNotices.Code-OSS.txt',
        ),
    ]

    npm_entries = metadata.get('npm', [])
    require(isinstance(npm_entries, list), 'runtime npm metadata must be an array')
    for raw in npm_entries:
        require(isinstance(raw, dict), 'runtime npm metadata entry must be an object')
        name = raw.get('name')
        version_value = raw.get('version')
        path = raw.get('path')
        require(isinstance(name, str) and bool(name), 'runtime npm name missing')
        require(
            isinstance(version_value, str) and bool(version_value),
            f'runtime npm version missing: {name}',
        )
        require(isinstance(path, str) and bool(path), f'runtime npm artifact path missing: {name}')
        source_value = raw.get('source', 'upstream-package-lock')
        require(
            isinstance(source_value, str) and bool(source_value),
            f'runtime npm source missing: {name}',
        )
        components.append(
            component_entry(
                bom_ref=generate_sbom.npm_purl(name, version_value),
                kind='npm',
                name=name,
                version=version_value,
                license_value=raw.get('license'),
                artifact_path=path,
                source=source_value,
            )
        )

    extension_entries = metadata.get('extensions', [])
    require(isinstance(extension_entries, list), 'runtime extension metadata must be an array')
    for raw in extension_entries:
        require(isinstance(raw, dict), 'runtime extension metadata entry must be an object')
        extension_id = raw.get('id')
        version_value = raw.get('version')
        path = raw.get('path')
        require(
            isinstance(extension_id, str) and bool(extension_id), 'runtime extension id missing'
        )
        require(
            isinstance(version_value, str) and bool(version_value),
            f'runtime extension version missing: {extension_id}',
        )
        require(
            isinstance(path, str) and bool(path),
            f'runtime extension artifact path missing: {extension_id}',
        )
        components.append(
            component_entry(
                bom_ref=f'vscode-extension:{extension_id}@{version_value}',
                kind='extension',
                name=extension_id,
                version=version_value,
                license_value=raw.get('license'),
                artifact_path=path,
                source='extension-package-json',
            )
        )

    components.sort(key=lambda component: str(component['bomRef']))
    refs = [str(component['bomRef']) for component in components]
    require(len(refs) == len(set(refs)), 'duplicate component bomRef in license inventory')

    no_assertion = sum(1 for component in components if component['declaredLicense'] == NOASSERTION)
    return {
        'schemaVersion': 1,
        'project': {
            'repository': 'https://github.com/HRAshton/code-oss-static-web',
            'commit': project_commit,
        },
        'upstream': {
            'repository': upstream['repository'],
            'tag': upstream['tag'],
            'commit': upstream['commit'],
        },
        'summary': {
            'totalComponents': len(components),
            'declaredLicenses': len(components) - no_assertion,
            'noAssertion': no_assertion,
        },
        'components': components,
    }


def write_license_inventory(
    output: Path,
    *,
    metadata: dict[str, Any],
    version: str,
    project_commit: str,
    upstream: dict[str, Any],
) -> dict[str, Any]:
    inventory = build_license_inventory(
        metadata=metadata,
        version=version,
        project_commit=project_commit,
        upstream=upstream,
    )
    write_json(output, inventory)
    return inventory
