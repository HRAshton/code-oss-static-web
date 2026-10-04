#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any, cast

from common import BuildError, load_json, require, sha256_file, write_json

COMMIT_RE = re.compile(r'^[0-9a-f]{40}$')
DIGEST_RE = re.compile(r'^[0-9a-f]{64}$')
RELEASE_TAG_RE = re.compile(r'^v(?P<version>.+-web\.(?:0|[1-9][0-9]*))$')


def _object(value: Any, label: str) -> dict[str, Any]:
    require(isinstance(value, dict), f'{label} must be an object')
    return cast(dict[str, Any], value)


def _string(value: Any, label: str) -> str:
    require(isinstance(value, str) and bool(value), f'{label} must be a non-empty string')
    return cast(str, value)


def _integer(value: Any, label: str) -> int:
    require(isinstance(value, int) and not isinstance(value, bool), f'{label} must be an integer')
    return cast(int, value)


def _exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    require(
        actual == expected,
        f'{label} keys mismatch: expected {sorted(expected)}, got {sorted(actual)}',
    )


def load_promotion_policy(path: Path) -> dict[str, Any]:
    data = _object(load_json(path), 'promotion policy')
    _exact_keys(data, {'schemaVersion', 'profile', 'automatic', 'channels'}, 'promotion policy')
    require(data['schemaVersion'] == 1, 'promotion policy schemaVersion must be 1')
    _string(data['profile'], 'promotion policy profile')

    automatic = _object(data['automatic'], 'promotion policy automatic')
    _exact_keys(automatic, {'enabled', 'order'}, 'promotion policy automatic')
    require(automatic['enabled'] is True, 'routine release promotion must remain automatic')
    require(
        automatic['order'] == ['canary', 'stable'],
        'automatic promotion order must be canary then stable',
    )

    channels = _object(data['channels'], 'promotion policy channels')
    _exact_keys(channels, {'canary', 'stable'}, 'promotion policy channels')

    canary = _object(channels['canary'], 'promotion policy canary channel')
    _exact_keys(canary, {'environment'}, 'promotion policy canary channel')
    require(canary['environment'] == 'canary', 'canary environment must be named canary')

    stable = _object(channels['stable'], 'promotion policy stable channel')
    _exact_keys(
        stable,
        {'environment', 'requiresCanary', 'deployPages'},
        'promotion policy stable channel',
    )
    require(stable['environment'] == 'stable', 'stable environment must be named stable')
    require(stable['requiresCanary'] is True, 'stable promotion must require canary')
    require(stable['deployPages'] is True, 'stable promotion must deploy GitHub Pages')
    return data


def checksum_entries(path: Path) -> dict[str, str]:
    require(path.is_file(), f'missing checksum manifest: {path}')
    entries: dict[str, str] = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        fields = line.split(None, 1)
        require(len(fields) == 2, f'invalid checksum line: {line!r}')
        digest, name = fields
        name = name.strip().lstrip('*')
        require(DIGEST_RE.fullmatch(digest) is not None, f'invalid checksum digest: {name}')
        require(bool(name), 'checksum entry name must be non-empty')
        require(name not in entries, f'duplicate checksum entry: {name}')
        entries[name] = digest
    require(bool(entries), 'checksum manifest is empty')
    return entries


def release_archive(manifest: dict[str, Any]) -> dict[str, Any]:
    artifacts_value = manifest.get('artifacts')
    require(isinstance(artifacts_value, list), 'artifact manifest artifacts must be an array')
    artifacts = cast(list[object], artifacts_value)
    candidates: list[dict[str, Any]] = []
    for value in artifacts:
        artifact = _object(value, 'artifact manifest artifact')
        name = _string(artifact.get('name'), 'artifact manifest artifact name')
        if name.endswith('.tar.gz'):
            candidates.append(artifact)
    require(
        len(candidates) == 1,
        f'artifact manifest must contain exactly one release tar.gz, got {len(candidates)}',
    )
    return candidates[0]


def build_identity(
    *,
    release_tag: str,
    release_commit: str,
    release_id: int,
    manifest_path: Path,
    checksums_path: Path,
    archive_path: Path,
    policy_path: Path,
) -> dict[str, Any]:
    tag_match = RELEASE_TAG_RE.fullmatch(release_tag)
    require(tag_match is not None, f'invalid immutable release tag: {release_tag}')
    assert tag_match is not None
    require(
        COMMIT_RE.fullmatch(release_commit) is not None,
        'release commit must be a full 40-character SHA',
    )
    require(release_id > 0, 'GitHub Release id must be positive')

    manifest = _object(load_json(manifest_path), 'artifact manifest')
    require(manifest.get('schemaVersion') == 1, 'unsupported artifact manifest schema')
    require(
        manifest.get('version') == tag_match.group('version'),
        'artifact manifest version does not match immutable release tag',
    )

    project = _object(manifest.get('project'), 'artifact manifest project')
    require(
        project.get('commit') == release_commit,
        'artifact manifest project commit does not match immutable release ref',
    )

    distribution = _object(manifest.get('distribution'), 'artifact manifest distribution')
    tree_sha256 = _string(
        distribution.get('treeSha256'),
        'artifact manifest distribution tree digest',
    )
    require(
        DIGEST_RE.fullmatch(tree_sha256) is not None,
        'artifact manifest distribution tree digest is invalid',
    )
    file_count = _integer(
        distribution.get('fileCount'),
        'artifact manifest distribution file count',
    )
    require(file_count > 0, 'artifact manifest distribution file count must be positive')

    deployment_profile_value = manifest.get('deploymentProfile')
    deployment_profile: dict[str, str] | None = None
    if deployment_profile_value is not None:
        release_profile = _object(deployment_profile_value, 'artifact manifest deployment profile')
        profile_id = _string(release_profile.get('id'), 'artifact manifest deployment profile id')
        profile_digest = _string(
            release_profile.get('configSha256'),
            'artifact manifest deployment profile digest',
        )
        require(
            DIGEST_RE.fullmatch(profile_digest) is not None,
            'artifact manifest deployment profile digest is invalid',
        )
        deployment_profile = {'id': profile_id, 'configSha256': profile_digest}

    archive = release_archive(manifest)
    archive_name = _string(archive.get('name'), 'release archive name')
    require(archive_path.name == archive_name, 'downloaded release archive name mismatch')
    archive_digest = _string(archive.get('sha256'), 'release archive digest')
    require(DIGEST_RE.fullmatch(archive_digest) is not None, 'release archive digest is invalid')
    archive_size = _integer(archive.get('size'), 'release archive size')
    require(archive_size >= 0, 'release archive size must be non-negative')
    require(archive_path.is_file(), f'missing release archive: {archive_path}')
    require(archive_path.stat().st_size == archive_size, 'release archive size mismatch')
    require(sha256_file(archive_path) == archive_digest, 'release archive digest mismatch')

    checksums = checksum_entries(checksums_path)
    require(
        checksums.get('artifact-manifest.json') == sha256_file(manifest_path),
        'artifact manifest checksum mismatch',
    )
    require(checksums.get(archive_name) == archive_digest, 'release archive checksum mismatch')

    policy = load_promotion_policy(policy_path)
    profile = _string(policy['profile'], 'promotion policy profile')
    return {
        'schemaVersion': 1,
        'release': {
            'tag': release_tag,
            'commit': release_commit,
            'githubReleaseId': release_id,
        },
        'artifact': {
            'archive': {
                'name': archive_name,
                'sha256': archive_digest,
            },
            'distribution': {
                'treeSha256': tree_sha256,
                'fileCount': file_count,
            },
            'deploymentProfile': deployment_profile,
        },
        'policy': {
            'profile': profile,
            'sha256': sha256_file(policy_path),
        },
    }


def build_pages_deployment_identity(promotion_identity: Any) -> dict[str, Any]:
    identity = _object(promotion_identity, 'promotion identity')
    require(identity.get('schemaVersion') == 1, 'promotion identity schemaVersion must be 1')

    release = _object(identity.get('release'), 'promotion identity release')
    release_tag = _string(release.get('tag'), 'promotion identity release tag')
    require(
        RELEASE_TAG_RE.fullmatch(release_tag) is not None,
        'promotion identity release tag is invalid',
    )
    release_commit = _string(release.get('commit'), 'promotion identity release commit')
    require(
        COMMIT_RE.fullmatch(release_commit) is not None,
        'promotion identity release commit must be a full 40-character SHA',
    )

    artifact = _object(identity.get('artifact'), 'promotion identity artifact')
    distribution = _object(
        artifact.get('distribution'),
        'promotion identity artifact distribution',
    )
    tree_sha256 = _string(
        distribution.get('treeSha256'),
        'promotion identity distribution tree digest',
    )
    require(
        DIGEST_RE.fullmatch(tree_sha256) is not None,
        'promotion identity distribution tree digest is invalid',
    )

    profile = _object(
        artifact.get('deploymentProfile'),
        'promotion identity deployment profile',
    )
    profile_id = _string(profile.get('id'), 'promotion identity deployment profile id')
    profile_digest = _string(
        profile.get('configSha256'),
        'promotion identity deployment profile digest',
    )
    require(
        DIGEST_RE.fullmatch(profile_digest) is not None,
        'promotion identity deployment profile digest is invalid',
    )

    return {
        'schemaVersion': 1,
        'release': {
            'tag': release_tag,
            'commit': release_commit,
        },
        'distribution': {
            'treeSha256': tree_sha256,
        },
        'deploymentProfile': {
            'id': profile_id,
            'configSha256': profile_digest,
        },
    }


def validate_pages_deployment_identity(
    value: Any,
    label: str = 'Pages deployment identity',
) -> dict[str, Any]:
    identity = _object(value, label)
    _exact_keys(
        identity,
        {'schemaVersion', 'release', 'distribution', 'deploymentProfile'},
        label,
    )
    require(identity['schemaVersion'] == 1, f'{label} schemaVersion must be 1')

    release = _object(identity['release'], f'{label} release')
    _exact_keys(release, {'tag', 'commit'}, f'{label} release')
    release_tag = _string(release['tag'], f'{label} release tag')
    require(RELEASE_TAG_RE.fullmatch(release_tag) is not None, f'{label} release tag is invalid')
    release_commit = _string(release['commit'], f'{label} release commit')
    require(
        COMMIT_RE.fullmatch(release_commit) is not None,
        f'{label} release commit must be a full 40-character SHA',
    )

    distribution = _object(identity['distribution'], f'{label} distribution')
    _exact_keys(distribution, {'treeSha256'}, f'{label} distribution')
    tree_sha256 = _string(distribution['treeSha256'], f'{label} distribution tree digest')
    require(
        DIGEST_RE.fullmatch(tree_sha256) is not None,
        f'{label} distribution tree digest is invalid',
    )

    profile = _object(identity['deploymentProfile'], f'{label} deployment profile')
    _exact_keys(profile, {'id', 'configSha256'}, f'{label} deployment profile')
    _string(profile['id'], f'{label} deployment profile id')
    profile_digest = _string(
        profile['configSha256'],
        f'{label} deployment profile digest',
    )
    require(
        DIGEST_RE.fullmatch(profile_digest) is not None,
        f'{label} deployment profile digest is invalid',
    )
    return identity


def verify_pages_deployment_identity(expected: Any, actual: Any) -> None:
    expected_identity = validate_pages_deployment_identity(
        expected,
        'expected Pages deployment identity',
    )
    actual_identity = validate_pages_deployment_identity(
        actual,
        'live Pages deployment identity',
    )
    require(
        actual_identity == expected_identity,
        'live Pages deployment identity does not match expected promotion identity',
    )


def main() -> None:
    parser = argparse.ArgumentParser(description='Verify and record immutable promotion identity')
    parser.add_argument('--release-tag', required=True)
    parser.add_argument('--release-commit', required=True)
    parser.add_argument('--release-id', required=True, type=int)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--checksums', required=True, type=Path)
    parser.add_argument('--archive', required=True, type=Path)
    parser.add_argument('--policy', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()

    identity = build_identity(
        release_tag=args.release_tag,
        release_commit=args.release_commit,
        release_id=args.release_id,
        manifest_path=args.manifest,
        checksums_path=args.checksums,
        archive_path=args.archive,
        policy_path=args.policy,
    )
    write_json(args.output, identity)
    print(
        'promotion identity: '
        f'{identity["release"]["tag"]} '
        f'{identity["artifact"]["distribution"]["treeSha256"]} '
        f'{identity["artifact"]["deploymentProfile"]["id"] if identity["artifact"]["deploymentProfile"] else "legacy-unprofiled"} '
        f'{identity["policy"]["profile"]}'
    )


if __name__ == '__main__':
    try:
        main()
    except BuildError as exc:
        raise SystemExit(str(exc)) from None
