#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import os
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import quote

from common import BuildError, require, sha256_file, write_json

CYCLONEDX_SCHEMA = 'http://cyclonedx.org/schema/bom-1.7.schema.json'
CYCLONEDX_VERSION = '1.7'
PROJECT_REPOSITORY = 'https://github.com/HRAshton/code-oss-static-web'


def tree_digest(root: Path) -> str:
    require(root.exists(), f'component path missing: {root}')
    if root.is_file():
        return sha256_file(root)

    digest = hashlib.sha256()
    files = sorted(
        (path for path in root.rglob('*') if path.is_file()),
        key=lambda path: path.relative_to(root).as_posix(),
    )
    for path in files:
        relative = path.relative_to(root).as_posix()
        mode = 0o755 if os.access(path, os.X_OK) else 0o644
        digest.update(f'{relative}\0{mode:o}\0{sha256_file(path)}\n'.encode())
    return digest.hexdigest()


def license_entries(value: Any) -> list[dict[str, Any]] | None:
    if not isinstance(value, str) or not value:
        return None
    return [{'license': {'name': value}}]


def npm_purl(name: str, version: str) -> str:
    if name.startswith('@') and '/' in name:
        scope, package = name[1:].split('/', 1)
        return f'pkg:npm/%40{quote(scope, safe="")}/{quote(package, safe="")}@{quote(version, safe="")}'
    return f'pkg:npm/{quote(name, safe="")}@{quote(version, safe="")}'


def npm_component(dist: Path, entry: dict[str, Any]) -> dict[str, Any]:
    full_name = str(entry['name'])
    version = str(entry['version'])
    group: str | None = None
    name = full_name
    if full_name.startswith('@') and '/' in full_name:
        group, name = full_name.split('/', 1)

    purl = npm_purl(full_name, version)
    component: dict[str, Any] = {
        'type': 'library',
        'bom-ref': purl,
        'name': name,
        'version': version,
        'purl': purl,
        'hashes': [
            {
                'alg': 'SHA-256',
                'content': tree_digest(dist / str(entry['path'])),
            }
        ],
        'properties': [
            {
                'name': 'code-oss-static-web:artifactPath',
                'value': str(entry['path']),
            }
        ],
    }
    if group is not None:
        component['group'] = group
    licenses = license_entries(entry.get('license'))
    if licenses is not None:
        component['licenses'] = licenses
    integrity = entry.get('integrity')
    if isinstance(integrity, str) and integrity:
        component['properties'].append(
            {
                'name': 'code-oss-static-web:npmIntegrity',
                'value': integrity,
            }
        )
    return component


def extension_component(dist: Path, entry: dict[str, Any]) -> dict[str, Any]:
    extension_id = str(entry['id'])
    version = str(entry['version'])
    component: dict[str, Any] = {
        'type': 'library',
        'bom-ref': f'vscode-extension:{extension_id}@{version}',
        'group': str(entry['publisher']),
        'name': str(entry['name']),
        'version': version,
        'hashes': [
            {
                'alg': 'SHA-256',
                'content': tree_digest(dist / str(entry['path'])),
            }
        ],
        'properties': [
            {
                'name': 'code-oss-static-web:extensionId',
                'value': extension_id,
            },
            {
                'name': 'code-oss-static-web:artifactPath',
                'value': str(entry['path']),
            },
            {
                'name': 'code-oss-static-web:browserCompatible',
                'value': 'true' if entry.get('browserCompatible') else 'false',
            },
        ],
    }
    licenses = license_entries(entry.get('license'))
    if licenses is not None:
        component['licenses'] = licenses
    return component


def build_sbom(
    *,
    dist: Path,
    metadata: dict[str, Any],
    version: str,
    project_commit: str,
    upstream: dict[str, Any],
    distribution_tree_sha256: str,
) -> dict[str, Any]:
    root_ref = f'code-oss-static-web:{project_commit}'
    code_oss_ref = f'code-oss:{upstream["commit"]}'

    components: list[dict[str, Any]] = [
        {
            'type': 'application',
            'bom-ref': code_oss_ref,
            'group': 'microsoft',
            'name': 'Code - OSS',
            'version': str(upstream['tag']),
            'licenses': [{'license': {'name': 'MIT'}}],
            'externalReferences': [
                {
                    'type': 'vcs',
                    'url': f'https://github.com/microsoft/vscode/tree/{upstream["commit"]}',
                }
            ],
            'properties': [
                {
                    'name': 'code-oss-static-web:gitCommit',
                    'value': str(upstream['commit']),
                }
            ],
        }
    ]
    components.extend(npm_component(dist, entry) for entry in metadata.get('npm', []))
    components.extend(extension_component(dist, entry) for entry in metadata.get('extensions', []))
    components.sort(key=lambda component: str(component['bom-ref']))

    refs = [str(component['bom-ref']) for component in components]
    require(len(refs) == len(set(refs)), 'duplicate component bom-ref in SBOM')

    serial = uuid.uuid5(
        uuid.NAMESPACE_URL,
        f'{PROJECT_REPOSITORY}@{project_commit}:{distribution_tree_sha256}',
    )
    runtime_refs = [ref for ref in refs if ref != code_oss_ref]

    return {
        '$schema': CYCLONEDX_SCHEMA,
        'bomFormat': 'CycloneDX',
        'specVersion': CYCLONEDX_VERSION,
        'serialNumber': f'urn:uuid:{serial}',
        'version': 1,
        'metadata': {
            'component': {
                'type': 'application',
                'bom-ref': root_ref,
                'name': 'Code OSS Static Web',
                'version': version,
                'externalReferences': [
                    {
                        'type': 'vcs',
                        'url': f'{PROJECT_REPOSITORY}/tree/{project_commit}',
                    }
                ],
                'properties': [
                    {
                        'name': 'code-oss-static-web:gitCommit',
                        'value': project_commit,
                    },
                    {
                        'name': 'code-oss-static-web:upstreamCommit',
                        'value': str(upstream['commit']),
                    },
                    {
                        'name': 'code-oss-static-web:distributionTreeSha256',
                        'value': distribution_tree_sha256,
                    },
                ],
            }
        },
        'components': components,
        'dependencies': [
            {
                'ref': root_ref,
                'dependsOn': [code_oss_ref],
            },
            {
                'ref': code_oss_ref,
                'dependsOn': sorted(runtime_refs),
            },
        ],
    }


def write_sbom(
    output: Path,
    *,
    dist: Path,
    metadata: dict[str, Any],
    version: str,
    project_commit: str,
    upstream: dict[str, Any],
    distribution_tree_sha256: str,
) -> dict[str, Any]:
    bom = build_sbom(
        dist=dist,
        metadata=metadata,
        version=version,
        project_commit=project_commit,
        upstream=upstream,
        distribution_tree_sha256=distribution_tree_sha256,
    )
    write_json(output, bom)
    return bom
