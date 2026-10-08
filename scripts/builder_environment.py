#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path
from typing import cast

from common import ROOT, BuildError, load_json, require

DIGEST_RE = re.compile(r'^sha256:[0-9a-f]{64}$')
SNAPSHOT_RE = re.compile(r'^\d{8}T\d{6}Z$')
JOB_HEADER_RE = re.compile(r'^  ([A-Za-z0-9_-]+):\s*$', re.MULTILINE)


def load_builder(path: Path) -> dict[str, str]:
    data = load_json(path)
    require(
        set(data) == {'schemaVersion', 'image', 'digest', 'platform', 'aptSnapshot'},
        'builder image manifest keys invalid',
    )
    require(data.get('schemaVersion') == 2, 'builder image schemaVersion must be 2')
    image = data.get('image')
    digest = data.get('digest')
    platform = data.get('platform')
    snapshot = data.get('aptSnapshot')
    require(
        isinstance(image, str) and bool(image) and '@' not in image,
        'builder image name invalid',
    )
    require(
        isinstance(digest, str) and DIGEST_RE.fullmatch(digest) is not None,
        'builder image digest invalid',
    )
    require(platform == 'linux/amd64', 'builder platform must be linux/amd64')
    require(
        isinstance(snapshot, str) and SNAPSHOT_RE.fullmatch(snapshot) is not None,
        'builder APT snapshot invalid',
    )
    return {
        'image': cast(str, image),
        'digest': cast(str, digest),
        'platform': cast(str, platform),
        'aptSnapshot': cast(str, snapshot),
    }


def image_reference(builder: dict[str, str]) -> str:
    return f'{builder["image"]}@{builder["digest"]}'


def job_blocks(text: str) -> dict[str, str]:
    matches = list(JOB_HEADER_RE.finditer(text))
    blocks: dict[str, str] = {}
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        blocks[match.group(1)] = text[start:end]
    return blocks


def validate_build_job(label: str, block: str, reference: str, snapshot: str) -> None:
    require(
        f'      image: {reference}' in block,
        f'{label} must use the locked builder digest',
    )
    source = 'browser-plan' if label == 'qualification' else 'authorize'
    expected = 'APT_SNAPSHOT: ${{ needs.' + source + '.outputs.apt_snapshot }}'
    require(expected in block, f'{label} must use the locked APT snapshot')
    for required in (
        'name: Bootstrap snapshot-locked builder packages',
        '/etc/ssl/certs/ca-certificates.crt:/tmp/runner-ca-bundle.pem:ro',
        'test -s /tmp/runner-ca-bundle.pem',
        'apt-get update --snapshot "$APT_SNAPSHOT"',
        'apt-cache -o APT::Snapshot="$APT_SNAPSHOT" policy build-essential',
        'grep -F "$snapshot_origin"',
        'apt-get install \\',
        '--snapshot "$APT_SNAPSHOT" -y --no-install-recommends',
        'build-essential pkg-config libx11-dev libxkbfile-dev libkrb5-dev',
        'name: Verify builder APT snapshot lock',
        'test "$(jq -er \'.aptSnapshot\' builder-image.json)" = "$APT_SNAPSHOT"',
    ):
        require(required in block, f'{label} missing snapshot-locked prerequisite: {required}')
    require(
        block.count('Acquire::https::CaInfo=/tmp/runner-ca-bundle.pem') == 2,
        f'{label} must use trusted TLS for both snapshot downloads',
    )
    require(
        block.count('apt-get update') == 1 and block.count('apt-get install') == 1,
        f'{label} must not invoke extra mutable APT commands',
    )
    require('sudo apt-get' not in block, f'{label} must run apt inside the container')


def validate_repository(root: Path = ROOT) -> None:
    builder = load_builder(root / 'builder-image.json')
    reference = image_reference(builder)
    qualify = (root / '.github/workflows/qualify.yml').read_text(encoding='utf-8')
    release = (root / '.github/workflows/release.yml').read_text(encoding='utf-8')
    qualify_jobs = job_blocks(qualify)
    release_jobs = job_blocks(release)

    require(
        'apt_snapshot: ${{ steps.builder-lock.outputs.apt_snapshot }}' in qualify,
        'qualification must expose the checked-out builder snapshot',
    )
    require(
        'apt_snapshot: ${{ steps.binding.outputs.apt_snapshot }}' in release,
        'release authorization must expose the qualified builder snapshot',
    )
    expected = (
        ('qualification', qualify_jobs.get('build')),
        ('release build', release_jobs.get('build')),
        ('release reproducibility', release_jobs.get('reproducibility')),
    )
    for label, block in expected:
        require(block is not None, f'{label} job missing')
        assert block is not None
        validate_build_job(label, block, reference, builder['aptSnapshot'])

    require(
        "hashFiles('builder-image.json', '.github/workflows/qualify.yml'," in qualify,
        'qualification build cache must include the builder lock and prerequisite definition',
    )
    require(
        "- 'builder-image.json'" in qualify,
        'qualification workflow must trigger on builder lock changes',
    )
    for required in (
        '.builder == $builder',
        '.inputs.builderImage.path == "builder-image.json"',
        '.inputs.builderImage.sha256 == $builderInputSha256',
    ):
        require(required in release, f'release authorization missing builder binding: {required}')

    package_source = (root / 'scripts/package_release.py').read_text(encoding='utf-8')
    require("'builder': builder_identity" in package_source, 'artifact manifest missing builder')
    require(
        "'builderImage': input_digest(ROOT / 'builder-image.json')" in package_source,
        'artifact manifest missing builder lock digest',
    )

    import sys

    sys.path.insert(0, str(root / 'scripts'))
    import classify_pr

    require(
        classify_pr.classify_paths(['builder-image.json']) == 'full',
        'builder lock changes must require full qualification',
    )


def main() -> None:
    validate_repository()
    print('builder environment: ok')


if __name__ == '__main__':
    try:
        main()
    except BuildError as exc:
        raise SystemExit(str(exc)) from None
