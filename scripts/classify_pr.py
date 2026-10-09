#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections.abc import Iterable
from pathlib import Path
from typing import Literal

QualificationLevel = Literal['lightweight', 'release', 'artifact', 'full']

DOCUMENTATION_ONLY_FILES = {
    'CONTRIBUTING.md',
    'LICENSE',
    'OPERATIONS.md',
    'README.md',
    'SECURITY.md',
    'SUPPORT.md',
    'THIRD_PARTY_NOTICES.md',
}
DOCUMENTATION_ONLY_PREFIXES = (
    'docs/',
    'LICENSES/',
    '.github/ISSUE_TEMPLATE/',
)

RELEASE_ONLY_FILES = {
    '.github/actions/publish-github-release/action.yml',
    '.github/actions/publish-pages/action.yml',
    '.github/workflows/promote.yml',
    '.github/workflows/recover-release-publication.yml',
    'scripts/check_policy.py',
    'scripts/check_release_tag.py',
    'scripts/export_release_provenance.py',
    'scripts/pages_identity.py',
    'scripts/promotion.py',
    'scripts/publish_github_release.py',
    'scripts/validate_json_schema.py',
}
RELEASE_ONLY_PREFIXES = ('.github/actions/release-metadata-qualification/',)

ARTIFACT_FILES = {
    '.dockerignore',
    'builder-image.json',
    'builder-apt-snapshot.json',
    '.github/actions/independent-sbom/action.yml',
    '.github/actions/publish-oci/action.yml',
    '.github/toolchain-versions.json',
    'Makefile',
    'build.sh',
    'package.sh',
    'pyproject.toml',
    'schemas/sbom-comparison-policy.schema.json',
    'scripts/compare_sbom_inventory.py',
    'scripts/generate_license_inventory.py',
    'scripts/generate_runtime_metadata.py',
    'scripts/generate_sbom.py',
    'scripts/package_release.py',
    'scripts/verify_oci_image.sh',
    'scripts/verify_release.py',
    'security/sbom-comparison-policy.json',
    'upstream.lock.json',
}
ARTIFACT_PREFIXES = (
    '.github/actions/',
    '.github/workflows/',
    'config/',
    'deploy/',
    'extensions/',
    'patches/',
    'scripts/',
)

FULL_FILES = {
    'builder-image.json',
    'builder-apt-snapshot.json',
    '.github/toolchain-versions.json',
    '.github/workflows/qualify.yml',
    '.github/workflows/release.yml',
    '.github/workflows/upstream-qualification.yml',
    'scripts/add_test_extension.py',
    'scripts/apply_patches.py',
    'scripts/build.py',
    'scripts/builder_environment.py',
    'scripts/classify_pr.py',
    'scripts/deployment_profile.py',
    'scripts/fetch_upstream.py',
    'scripts/install_playwright_browser.py',
    'scripts/make_static.py',
    'scripts/prepare_upstream.py',
    'scripts/run_e2e.py',
    'scripts/serve_static.py',
    'scripts/verify_dist_identity.py',
    'security/network-policy.json',
    'upstream.lock.json',
}
FULL_PREFIXES = (
    '.github/actions/browser-qualification/',
    '.github/actions/setup-toolchain/',
    'config/',
    'extensions/',
    'patches/',
    'tests/e2e/',
    'tests/fixtures/',
)


def normalize_path(value: str) -> str:
    path = value.strip().replace('\\', '/')
    while path.startswith('./'):
        path = path[2:]
    return path


def matches(path: str, files: set[str], prefixes: tuple[str, ...]) -> bool:
    return path in files or path.startswith(prefixes)


def classify_paths(paths: Iterable[str]) -> QualificationLevel:
    normalized = [normalize_path(path) for path in paths]
    normalized = [path for path in normalized if path]
    if not normalized:
        raise ValueError('pull request file list is empty')

    if all(
        matches(path, DOCUMENTATION_ONLY_FILES, DOCUMENTATION_ONLY_PREFIXES) for path in normalized
    ):
        return 'lightweight'

    if any(matches(path, FULL_FILES, FULL_PREFIXES) for path in normalized):
        return 'full'

    if all(
        matches(path, DOCUMENTATION_ONLY_FILES, DOCUMENTATION_ONLY_PREFIXES)
        or matches(path, RELEASE_ONLY_FILES, RELEASE_ONLY_PREFIXES)
        for path in normalized
    ):
        return 'release'

    if any(matches(path, ARTIFACT_FILES, ARTIFACT_PREFIXES) for path in normalized):
        return 'artifact'

    # Unknown paths fail closed so newly added product inputs cannot silently bypass artifact checks.
    return 'artifact'


def main() -> None:
    parser = argparse.ArgumentParser(description='Classify pull request qualification requirements')
    parser.add_argument('paths_file', type=Path)
    args = parser.parse_args()
    print(classify_paths(args.paths_file.read_text(encoding='utf-8').splitlines()))


if __name__ == '__main__':
    main()
