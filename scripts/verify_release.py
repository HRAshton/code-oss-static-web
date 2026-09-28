#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any, cast

from common import BuildError, load_json, require, sha256_file

COMMIT_RE = re.compile(r'^[0-9a-f]{40}$')
DIGEST_RE = re.compile(r'^[0-9a-f]{64}$')


def _object(value: Any, message: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise BuildError(message)
    return cast(dict[str, Any], value)


def _array(value: Any, message: str) -> list[Any]:
    if not isinstance(value, list):
        raise BuildError(message)
    return cast(list[Any], value)


def _string(value: Any, message: str) -> str:
    if not isinstance(value, str) or not value:
        raise BuildError(message)
    return value


def _integer(value: Any, message: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise BuildError(message)
    return value


def verify_checksums(directory: Path) -> int:
    sums = directory / 'SHA256SUMS'
    require(sums.is_file(), f'missing {sums}')
    count = 0

    for line in sums.read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        digest, name = line.split(None, 1)
        name = name.strip().lstrip('*')
        path = directory / name
        require(path.is_file(), f'missing release file: {name}')
        require(sha256_file(path) == digest, f'checksum mismatch: {name}')
        count += 1

    require(count > 0, 'empty checksum manifest')
    return count


def verify_artifact_manifest(directory: Path) -> None:
    manifest_path = directory / 'artifact-manifest.json'
    require(manifest_path.is_file(), f'missing {manifest_path}')
    manifest = load_json(manifest_path)
    require(manifest.get('schemaVersion') == 1, 'unsupported artifact manifest schema')
    _string(manifest.get('version'), 'artifact manifest version missing')

    project = _object(manifest.get('project'), 'artifact manifest project missing')
    project_commit = _string(project.get('commit'), 'artifact manifest project commit invalid')
    require(
        COMMIT_RE.fullmatch(project_commit) is not None,
        'artifact manifest project commit invalid',
    )

    upstream = _object(manifest.get('upstream'), 'artifact manifest upstream missing')
    upstream_commit = _string(upstream.get('commit'), 'artifact manifest upstream commit invalid')
    require(
        COMMIT_RE.fullmatch(upstream_commit) is not None,
        'artifact manifest upstream commit invalid',
    )

    distribution = _object(manifest.get('distribution'), 'artifact manifest distribution missing')
    tree_digest = _string(
        distribution.get('treeSha256'),
        'artifact manifest distribution digest invalid',
    )
    require(
        DIGEST_RE.fullmatch(tree_digest) is not None,
        'artifact manifest distribution digest invalid',
    )
    file_count = _integer(
        distribution.get('fileCount'),
        'artifact manifest distribution file count invalid',
    )
    require(file_count > 0, 'artifact manifest distribution file count invalid')

    artifacts = _array(manifest.get('artifacts'), 'artifact manifest artifacts missing')
    require(len(artifacts) > 0, 'artifact manifest artifacts missing')
    artifact_objects = [
        _object(artifact, 'artifact manifest artifact invalid') for artifact in artifacts
    ]
    artifact_names = {
        _string(artifact.get('name'), 'artifact manifest artifact name missing')
        for artifact in artifact_objects
    }
    require('sbom.cdx.json' in artifact_names, 'artifact manifest must include sbom.cdx.json')
    require(
        'license-inventory.json' in artifact_names,
        'artifact manifest must include license-inventory.json',
    )
    require(
        'LICENSE.Code-OSS.txt' in artifact_names, 'artifact manifest must include Code-OSS license'
    )
    require(
        'ThirdPartyNotices.Code-OSS.txt' in artifact_names,
        'artifact manifest must include Code-OSS notices',
    )
    for artifact in artifact_objects:
        name = _string(artifact.get('name'), 'artifact manifest artifact name missing')
        expected_digest = _string(
            artifact.get('sha256'),
            f'artifact manifest digest invalid: {name}',
        )
        expected_size = _integer(
            artifact.get('size'),
            f'artifact manifest size invalid: {name}',
        )
        require(
            DIGEST_RE.fullmatch(expected_digest) is not None,
            f'artifact manifest digest invalid: {name}',
        )
        require(expected_size >= 0, f'artifact manifest size invalid: {name}')
        path = directory / name
        require(path.is_file(), f'artifact manifest file missing: {name}')
        require(sha256_file(path) == expected_digest, f'artifact digest mismatch: {name}')
        require(path.stat().st_size == expected_size, f'artifact size mismatch: {name}')


def verify_sbom(directory: Path) -> None:
    sbom_path = directory / 'sbom.cdx.json'
    require(sbom_path.is_file(), f'missing {sbom_path}')
    sbom = load_json(sbom_path)
    require(sbom.get('bomFormat') == 'CycloneDX', 'SBOM format must be CycloneDX')
    require(sbom.get('specVersion') == '1.7', 'SBOM must use CycloneDX 1.7')
    require(sbom.get('version') == 1, 'SBOM document version must be 1')
    serial = _string(sbom.get('serialNumber'), 'SBOM serialNumber must be a UUID URN')
    require(serial.startswith('urn:uuid:'), 'SBOM serialNumber must be a UUID URN')

    metadata = _object(sbom.get('metadata'), 'SBOM metadata missing')
    root_component = _object(metadata.get('component'), 'SBOM root component missing')
    root_ref = _string(root_component.get('bom-ref'), 'SBOM root bom-ref missing')

    components = _array(sbom.get('components'), 'SBOM components missing')
    require(len(components) > 0, 'SBOM components missing')
    component_refs: list[str] = []
    for component_value in components:
        component = _object(component_value, 'SBOM component invalid')
        component_refs.append(_string(component.get('bom-ref'), 'SBOM component bom-ref missing'))
    require(
        len(component_refs) == len(set(component_refs)), 'SBOM component bom-ref must be unique'
    )

    known_refs = set(component_refs)
    known_refs.add(root_ref)
    dependencies = _array(sbom.get('dependencies'), 'SBOM dependencies missing')
    for dependency_value in dependencies:
        dependency = _object(dependency_value, 'SBOM dependency entry invalid')
        ref = _string(dependency.get('ref'), 'SBOM dependency ref missing')
        require(ref in known_refs, f'SBOM dependency ref unknown: {ref}')
        depends_on = _array(dependency.get('dependsOn', []), f'SBOM dependsOn invalid: {ref}')
        for item in depends_on:
            dependency_ref = _string(item, f'SBOM dependsOn contains invalid ref: {ref}')
            require(
                dependency_ref in known_refs,
                f'SBOM dependsOn contains unknown refs: {ref}',
            )


def verify_license_inventory(directory: Path) -> None:
    inventory_path = directory / 'license-inventory.json'
    require(inventory_path.is_file(), f'missing {inventory_path}')
    inventory = load_json(inventory_path)
    require(inventory.get('schemaVersion') == 1, 'license inventory schema must be 1')

    components = _array(inventory.get('components'), 'license inventory components missing')
    require(len(components) > 0, 'license inventory components missing')
    refs: list[str] = []
    no_assertion = 0
    for component_value in components:
        component = _object(component_value, 'license inventory component invalid')
        ref = _string(component.get('bomRef'), 'license inventory bomRef missing')
        license_name = _string(component.get('declaredLicense'), f'license missing: {ref}')
        status = _string(component.get('licenseStatus'), f'license status invalid: {ref}')
        require(status in ('declared', 'no-assertion'), f'license status invalid: {ref}')
        require(
            (license_name == 'NOASSERTION') == (status == 'no-assertion'),
            f'license status inconsistent: {ref}',
        )
        refs.append(ref)
        if license_name == 'NOASSERTION':
            no_assertion += 1

    require(len(refs) == len(set(refs)), 'license inventory bomRef must be unique')
    summary = _object(inventory.get('summary'), 'license inventory summary missing')
    require(summary.get('totalComponents') == len(components), 'license inventory total mismatch')
    require(
        summary.get('noAssertion') == no_assertion, 'license inventory NOASSERTION count mismatch'
    )
    require(
        summary.get('declaredLicenses') == len(components) - no_assertion,
        'license inventory declared license count mismatch',
    )

    for required_file in (
        'LICENSE',
        'THIRD_PARTY_NOTICES.md',
        'LICENSE.Code-OSS.txt',
        'ThirdPartyNotices.Code-OSS.txt',
    ):
        require(
            (directory / required_file).is_file(), f'license notice file missing: {required_file}'
        )

    sbom = load_json(directory / 'sbom.cdx.json')
    metadata = _object(
        sbom.get('metadata'),
        'SBOM metadata missing for license inventory comparison',
    )
    root = _object(
        metadata.get('component'),
        'SBOM root component missing for license inventory comparison',
    )
    root_ref = _string(root.get('bom-ref'), 'SBOM root bom-ref missing')
    sbom_components = _array(
        sbom.get('components'),
        'SBOM components missing for license inventory comparison',
    )
    sbom_refs: set[str] = set()
    for component_value in sbom_components:
        component = _object(component_value, 'SBOM component invalid')
        sbom_refs.add(_string(component.get('bom-ref'), 'SBOM component bom-ref missing'))
    sbom_refs.add(root_ref)
    require(
        set(refs) == sbom_refs, 'license inventory must cover every SBOM component exactly once'
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', nargs='?', default='artifacts')
    args = parser.parse_args()
    directory = Path(args.directory)

    count = verify_checksums(directory)
    verify_artifact_manifest(directory)
    verify_sbom(directory)
    verify_license_inventory(directory)
    print(
        f'verified {count} release files, artifact manifest, CycloneDX SBOM and license inventory'
    )


if __name__ == '__main__':
    try:
        main()
    except BuildError as exc:
        raise SystemExit(str(exc)) from None
