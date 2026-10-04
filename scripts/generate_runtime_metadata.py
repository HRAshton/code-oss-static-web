#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, cast

from common import DIST, ROOT, WORK, BuildError, load_json, require, write_json


def shipped_npm_packages(dist: Path) -> list[tuple[str, str]]:
    node_modules = dist / 'node_modules'
    if not node_modules.is_dir():
        return []

    packages: list[tuple[str, str]] = []
    for entry in sorted(node_modules.iterdir(), key=lambda path: path.name):
        if not entry.is_dir():
            continue
        if entry.name.startswith('@'):
            for scoped in sorted(entry.iterdir(), key=lambda path: path.name):
                if scoped.is_dir():
                    packages.append(
                        (f'{entry.name}/{scoped.name}', scoped.relative_to(dist).as_posix())
                    )
        else:
            packages.append((entry.name, entry.relative_to(dist).as_posix()))
    return packages


def embedded_extension_npm_components(dist: Path) -> list[dict[str, Any]]:
    extensions_root = dist / 'extensions'
    if not extensions_root.is_dir():
        return []

    components: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for package_json in sorted(extensions_root.glob('*/server/package.json')):
        package = load_json(package_json)
        name = package.get('name')
        version = package.get('version')
        require(
            isinstance(name, str) and bool(name),
            f'embedded extension npm name missing: {package_json}',
        )
        require(
            isinstance(version, str) and bool(version),
            f'embedded extension npm version missing: {package_json}',
        )
        assert isinstance(name, str)
        assert isinstance(version, str)
        path = package_json.parent.relative_to(dist).as_posix()
        key = (name, path)
        require(key not in seen, f'duplicate embedded extension npm component: {name} at {path}')
        seen.add(key)

        component: dict[str, Any] = {
            'name': name,
            'version': version,
            'path': path,
            'source': 'extension-package-json',
        }
        license_value = package.get('license')
        if isinstance(license_value, str) and license_value:
            component['license'] = license_value
        components.append(component)

    return components


def extension_components(dist: Path) -> list[dict[str, Any]]:
    extensions_root = dist / 'extensions'
    if not extensions_root.is_dir():
        return []

    extensions: list[dict[str, Any]] = []
    seen: set[str] = set()
    for package_json in sorted(extensions_root.glob('*/package.json')):
        package = load_json(package_json)
        publisher = package.get('publisher')
        name = package.get('name')
        version = package.get('version')
        require(
            isinstance(publisher, str) and bool(publisher),
            f'extension publisher missing: {package_json}',
        )
        require(isinstance(name, str) and bool(name), f'extension name missing: {package_json}')
        require(
            isinstance(version, str) and bool(version), f'extension version missing: {package_json}'
        )
        extension_id = f'{publisher}.{name}'
        require(extension_id not in seen, f'duplicate extension id in artifact: {extension_id}')
        seen.add(extension_id)

        component: dict[str, Any] = {
            'id': extension_id,
            'publisher': publisher,
            'name': name,
            'version': version,
            'path': package_json.parent.relative_to(dist).as_posix(),
            'browserCompatible': bool(package.get('browser')),
        }
        license_value = package.get('license')
        if isinstance(license_value, str) and license_value:
            component['license'] = license_value
        extensions.append(component)

    return extensions


def build_runtime_metadata(
    dist: Path,
    package_lock: dict[str, Any],
    upstream: dict[str, Any],
) -> dict[str, Any]:
    packages_value = package_lock.get('packages')
    if not isinstance(packages_value, dict):
        raise BuildError('package-lock.json packages object missing')
    packages_section = cast(dict[str, Any], packages_value)

    npm_components: list[dict[str, Any]] = []
    for name, relative_path in shipped_npm_packages(dist):
        lock_value = packages_section.get(f'node_modules/{name}')
        if not isinstance(lock_value, dict):
            raise BuildError(f'shipped npm package missing from package lock: {name}')
        lock_entry = cast(dict[str, Any], lock_value)
        version = lock_entry.get('version')
        if not isinstance(version, str) or not version:
            raise BuildError(f'locked npm version missing: {name}')

        component: dict[str, Any] = {
            'name': name,
            'version': version,
            'path': relative_path,
        }
        license_value = lock_entry.get('license')
        if isinstance(license_value, str) and license_value:
            component['license'] = license_value
        integrity = lock_entry.get('integrity')
        if isinstance(integrity, str) and integrity:
            component['integrity'] = integrity
        npm_components.append(component)

    npm_components.extend(embedded_extension_npm_components(dist))

    return {
        'schemaVersion': 1,
        'upstream': {
            'repository': upstream['repository'],
            'tag': upstream['tag'],
            'commit': upstream['commit'],
        },
        'npm': npm_components,
        'extensions': extension_components(dist),
    }


def generate_runtime_metadata(
    dist: Path,
    lock_path: Path,
    output: Path,
    upstream_lock_path: Path = ROOT / 'upstream.lock.json',
) -> dict[str, Any]:
    require((dist / 'index.html').is_file(), f'not a static distribution: {dist}')
    require(lock_path.is_file(), f'package lock missing: {lock_path}')
    package_lock = load_json(lock_path)
    upstream = load_json(upstream_lock_path)
    metadata = build_runtime_metadata(dist, package_lock, upstream)
    write_json(output, metadata)
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Capture runtime component metadata for the built artifact'
    )
    parser.add_argument('--dist', type=Path, default=DIST)
    parser.add_argument('--lock', type=Path, default=WORK / 'vscode/package-lock.json')
    parser.add_argument('--output', type=Path, default=WORK / 'runtime-components.json')
    args = parser.parse_args()

    metadata = generate_runtime_metadata(
        args.dist.resolve(), args.lock.resolve(), args.output.resolve()
    )
    print(
        f'runtime metadata: {len(metadata["npm"])} npm package(s), '
        f'{len(metadata["extensions"])} extension(s)'
    )


if __name__ == '__main__':
    try:
        main()
    except BuildError as exc:
        raise SystemExit(str(exc)) from None
