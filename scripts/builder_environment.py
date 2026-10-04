#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path
from typing import cast

from common import ROOT, BuildError, load_json, require

DIGEST_RE = re.compile(r'^sha256:[0-9a-f]{64}$')
JOB_HEADER_RE = re.compile(r'^  ([A-Za-z0-9_-]+):\s*$', re.MULTILINE)


def load_builder(path: Path) -> dict[str, str]:
    data = load_json(path)
    require(
        set(data) == {'schemaVersion', 'image', 'digest', 'platform'},
        'builder image manifest keys invalid',
    )
    require(data.get('schemaVersion') == 1, 'builder image schemaVersion must be 1')
    image = data.get('image')
    digest = data.get('digest')
    platform = data.get('platform')
    require(
        isinstance(image, str) and bool(image) and '@' not in image,
        'builder image name invalid',
    )
    require(
        isinstance(digest, str) and DIGEST_RE.fullmatch(digest) is not None,
        'builder image digest invalid',
    )
    require(platform == 'linux/amd64', 'builder platform must be linux/amd64')
    return {
        'image': cast(str, image),
        'digest': cast(str, digest),
        'platform': cast(str, platform),
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


def validate_repository(root: Path = ROOT) -> None:
    builder = load_builder(root / '.github/builder-image.json')
    reference = image_reference(builder)
    qualify = (root / '.github/workflows/qualify.yml').read_text(encoding='utf-8')
    release = (root / '.github/workflows/release.yml').read_text(encoding='utf-8')
    qualify_jobs = job_blocks(qualify)
    release_jobs = job_blocks(release)

    expected = (
        ('qualification', qualify_jobs.get('build')),
        ('release build', release_jobs.get('build')),
        ('release reproducibility', release_jobs.get('reproducibility')),
    )
    for label, block in expected:
        require(block is not None, f'{label} job missing')
        assert block is not None
        require(
            f'      image: {reference}' in block,
            f'{label} must use the locked builder digest',
        )
        require(
            'name: Bootstrap pinned builder packages' in block,
            f'{label} must bootstrap required packages explicitly',
        )
        require('sudo apt-get' not in block, f'{label} must run apt inside the container')
        require(
            'build-essential' in block,
            f'{label} must include the native build toolchain',
        )

    require(
        "hashFiles('.github/builder-image.json', '.github/workflows/qualify.yml'," in qualify,
        'qualification build cache must include the builder lock and prerequisite definition',
    )
    require(
        "- '.github/builder-image.json'" in qualify,
        'qualification workflow must trigger on builder lock changes',
    )
    for required in (
        '.builder == $builder',
        '.inputs.builderImage.path == ".github/builder-image.json"',
        '.inputs.builderImage.sha256 == $builderInputSha256',
    ):
        require(required in release, f'release authorization missing builder binding: {required}')

    package_source = (root / 'scripts/package_release.py').read_text(encoding='utf-8')
    require("'builder': builder_identity" in package_source, 'artifact manifest missing builder')
    require(
        "'builderImage': input_digest(ROOT / '.github/builder-image.json')" in package_source,
        'artifact manifest missing builder lock digest',
    )

    import sys

    sys.path.insert(0, str(root / 'scripts'))
    import classify_pr

    require(
        classify_pr.classify_paths(['.github/builder-image.json']) == 'full',
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
