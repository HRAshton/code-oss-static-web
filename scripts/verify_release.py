#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

from common import BuildError, load_json, require, sha256_file

COMMIT_RE = re.compile(r'^[0-9a-f]{40}$')
DIGEST_RE = re.compile(r'^[0-9a-f]{64}$')


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
    require(isinstance(manifest.get('version'), str), 'artifact manifest version missing')

    project = manifest.get('project')
    require(isinstance(project, dict), 'artifact manifest project missing')
    project_commit = project.get('commit')
    require(
        isinstance(project_commit, str) and COMMIT_RE.fullmatch(project_commit) is not None,
        'artifact manifest project commit invalid',
    )

    upstream = manifest.get('upstream')
    require(isinstance(upstream, dict), 'artifact manifest upstream missing')
    upstream_commit = upstream.get('commit')
    require(
        isinstance(upstream_commit, str) and COMMIT_RE.fullmatch(upstream_commit) is not None,
        'artifact manifest upstream commit invalid',
    )

    distribution = manifest.get('distribution')
    require(isinstance(distribution, dict), 'artifact manifest distribution missing')
    tree_digest = distribution.get('treeSha256')
    require(
        isinstance(tree_digest, str) and DIGEST_RE.fullmatch(tree_digest) is not None,
        'artifact manifest distribution digest invalid',
    )
    require(
        isinstance(distribution.get('fileCount'), int) and distribution['fileCount'] > 0,
        'artifact manifest distribution file count invalid',
    )

    artifacts = manifest.get('artifacts')
    require(isinstance(artifacts, list) and len(artifacts) > 0, 'artifact manifest artifacts missing')
    for artifact in artifacts:
        require(isinstance(artifact, dict), 'artifact manifest artifact invalid')
        name = artifact.get('name')
        expected_digest = artifact.get('sha256')
        expected_size = artifact.get('size')
        require(isinstance(name, str) and bool(name), 'artifact manifest artifact name missing')
        require(
            isinstance(expected_digest, str) and DIGEST_RE.fullmatch(expected_digest) is not None,
            f'artifact manifest digest invalid: {name}',
        )
        require(
            isinstance(expected_size, int) and expected_size >= 0,
            f'artifact manifest size invalid: {name}',
        )
        path = directory / name
        require(path.is_file(), f'artifact manifest file missing: {name}')
        require(sha256_file(path) == expected_digest, f'artifact digest mismatch: {name}')
        require(path.stat().st_size == expected_size, f'artifact size mismatch: {name}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', nargs='?', default='artifacts')
    args = parser.parse_args()
    directory = Path(args.directory)

    count = verify_checksums(directory)
    verify_artifact_manifest(directory)
    print(f'verified {count} release files and artifact manifest')


if __name__ == '__main__':
    try:
        main()
    except BuildError as exc:
        raise SystemExit(str(exc))
