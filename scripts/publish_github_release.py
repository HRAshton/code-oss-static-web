#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, cast
from urllib.parse import quote

from common import BuildError, require


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def local_asset_digests(artifacts_dir: Path) -> dict[str, str]:
    assets: dict[str, str] = {}
    for path in sorted(artifacts_dir.iterdir()):
        if path.is_file():
            assets[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    require(bool(assets), 'release candidate contains no assets')
    return assets


def reconcile_assets(local: dict[str, str], remote: dict[str, str]) -> list[str]:
    unexpected = sorted(set(remote) - set(local))
    require(not unexpected, f'unexpected GitHub Release assets: {unexpected}')
    conflicts = sorted(name for name in set(local) & set(remote) if local[name] != remote[name])
    require(not conflicts, f'GitHub Release asset digest mismatch: {conflicts}')
    return sorted(set(local) - set(remote))


def pending_asset_uploads(
    local: dict[str, str], remote: dict[str, str], *, draft: bool
) -> list[str]:
    missing = reconcile_assets(local, remote)
    require(
        draft or not missing,
        f'published GitHub Release is incomplete; refusing to mutate it: {missing}',
    )
    return missing


def run(args: list[str], *, capture: bool = False, binary: bool = False) -> str | bytes:
    completed = subprocess.run(
        args,
        check=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        text=not binary,
    )
    if not capture:
        return b'' if binary else ''
    return completed.stdout


def release_json(repository: str, tag: str) -> dict[str, Any] | None:
    endpoint = f'repos/{repository}/releases/tags/{quote(tag, safe="")}'
    completed = subprocess.run(
        ['gh', 'api', endpoint],
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return None
    value = json.loads(completed.stdout)
    require(isinstance(value, dict), 'invalid GitHub Release response')
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


def download_remote_asset(repository: str, asset_id: int) -> bytes:
    data = run(
        [
            'gh',
            'api',
            '-H',
            'Accept: application/octet-stream',
            f'repos/{repository}/releases/assets/{asset_id}',
        ],
        capture=True,
        binary=True,
    )
    assert isinstance(data, bytes)
    return data


def remote_asset_digests(repository: str, release: dict[str, Any]) -> dict[str, str]:
    values_value: Any = release.get('assets')
    require(isinstance(values_value, list), 'GitHub Release response is missing assets')
    assert isinstance(values_value, list)
    values = cast(list[object], values_value)
    digests: dict[str, str] = {}
    for value in values:
        require(isinstance(value, dict), 'invalid GitHub Release asset')
        assert isinstance(value, dict)
        asset = cast(dict[str, Any], value)
        name = asset.get('name')
        asset_id = asset.get('id')
        state = asset.get('state')
        require(isinstance(name, str) and bool(name), 'invalid GitHub Release asset name')
        assert isinstance(name, str)
        require(isinstance(asset_id, int), f'invalid GitHub Release asset id: {name}')
        assert isinstance(asset_id, int)
        require(state == 'uploaded', f'GitHub Release asset is not uploaded: {name}')
        digest = asset.get('digest')
        if isinstance(digest, str) and digest.startswith('sha256:'):
            digests[name] = digest.removeprefix('sha256:')
        else:
            digests[name] = sha256_bytes(download_remote_asset(repository, asset_id))
    return digests


def validate_release(release: dict[str, Any], tag: str) -> None:
    require(release.get('tag_name') == tag, 'GitHub Release tag mismatch')
    require(release.get('prerelease') is False, 'GitHub Release must not be a prerelease')
    name = release.get('name')
    require(name in (None, '', tag), f'GitHub Release title mismatch: {name!r}')
    require(isinstance(release.get('draft'), bool), 'GitHub Release draft state is invalid')


def ensure_release(repository: str, tag: str) -> dict[str, Any]:
    release = release_json(repository, tag)
    if release is None:
        run(
            [
                'gh',
                'release',
                'create',
                tag,
                '--repo',
                repository,
                '--verify-tag',
                '--generate-notes',
                '--title',
                tag,
                '--draft',
            ]
        )
        release = release_json(repository, tag)
        require(release is not None, 'GitHub Release was not created')
    assert release is not None
    validate_release(release, tag)
    return release


def publish(repository: str, tag: str, artifacts_dir: Path) -> None:
    local = local_asset_digests(artifacts_dir)
    release = ensure_release(repository, tag)
    remote = remote_asset_digests(repository, release)
    draft = release.get('draft')
    assert isinstance(draft, bool)
    missing = pending_asset_uploads(local, remote, draft=draft)

    for name in missing:
        run(
            [
                'gh',
                'release',
                'upload',
                tag,
                str(artifacts_dir / name),
                '--repo',
                repository,
            ]
        )

    release = release_json(repository, tag)
    require(release is not None, 'GitHub Release disappeared during publication')
    assert release is not None
    validate_release(release, tag)
    remote = remote_asset_digests(repository, release)
    require(not reconcile_assets(local, remote), 'GitHub Release assets are incomplete')

    if release.get('draft') is True:
        release_id = release.get('id')
        require(isinstance(release_id, int), 'GitHub Release id missing')
        run(
            [
                'gh',
                'api',
                '--method',
                'PATCH',
                f'repos/{repository}/releases/{release_id}',
                '-F',
                'draft=false',
            ]
        )

    release = release_json(repository, tag)
    require(release is not None, 'GitHub Release missing after publication')
    assert release is not None
    validate_release(release, tag)
    require(release.get('draft') is False, 'GitHub Release is still a draft')
    remote = remote_asset_digests(repository, release)
    require(not reconcile_assets(local, remote), 'published GitHub Release assets are incomplete')
    print(f'GitHub Release publication complete: {tag}')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--repository', required=True)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--artifacts-dir', type=Path, required=True)
    args = parser.parse_args()
    publish(args.repository, args.tag, args.artifacts_dir)


if __name__ == '__main__':
    try:
        main()
    except BuildError as exc:
        raise SystemExit(str(exc)) from None
