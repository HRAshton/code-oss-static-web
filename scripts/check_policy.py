#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, cast

from common import ROOT, BuildError, load_json, require

ACTION_REF = re.compile(r'uses:\s*[^@\s]+@([^\s#]+)')
FULL_SHA = re.compile(r'^[0-9a-f]{40}$')
JOB_HEADER = re.compile(r'^  ([A-Za-z0-9_-]+):\s*$')
WRITE_PERMISSION = re.compile(r'^\s{6}[A-Za-z0-9-]+:\s*write\s*$', re.MULTILINE)
FORBIDDEN_PATTERNS = {
    'curl-pipe-shell': re.compile(r'\bcurl\b[^\n|]*\|\s*(?:ba)?sh\b'),
    'wget-pipe-shell': re.compile(r'\bwget\b[^\n|]*\|\s*(?:ba)?sh\b'),
    'npx': re.compile(r'(^|[;&|\s])npx\s+'),
    'pnpm-dlx': re.compile(r'\bpnpm\s+dlx\s+'),
    'npm-exec': re.compile(r'\bnpm\s+exec\s+'),
}


def check_actions() -> None:
    for workflow in sorted((ROOT / '.github/workflows').glob('*.yml')):
        for line_number, line in enumerate(workflow.read_text(encoding='utf-8').splitlines(), 1):
            match = ACTION_REF.search(line)
            if match:
                require(
                    FULL_SHA.fullmatch(match.group(1)) is not None,
                    f'{workflow.relative_to(ROOT)}:{line_number}: action must use a full commit SHA',
                )


def check_shell_scripts() -> None:
    for script in (ROOT / 'build.sh', ROOT / 'package.sh'):
        lines = script.read_text(encoding='utf-8').splitlines()
        require(
            bool(lines) and lines[0] == '#!/usr/bin/env bash',
            f'{script.name}: bash shebang required',
        )
        require(
            any(line.strip() == 'set -euo pipefail' for line in lines[:5]),
            f'{script.name}: set -euo pipefail required near the top',
        )


def check_forbidden_execution_patterns() -> None:
    paths = [ROOT / 'build.sh', ROOT / 'package.sh']
    paths.extend(sorted((ROOT / 'scripts').glob('*.py')))
    paths.extend(sorted((ROOT / '.github/workflows').glob('*.yml')))
    for path in paths:
        text = path.read_text(encoding='utf-8')
        for name, pattern in FORBIDDEN_PATTERNS.items():
            require(
                pattern.search(text) is None, f'{path.relative_to(ROOT)}: forbidden pattern: {name}'
            )


def check_extension_lock() -> None:
    lock = load_json(ROOT / 'extensions/extensions.lock.json')
    for extension in lock.get('extensions', []):
        require(extension.get('version') != 'latest', 'extension lock must not use version=latest')
        require(extension.get('sha256') != 'latest', 'extension lock must not use mutable hashes')


def workflow_job_blocks(text: str) -> list[tuple[str, str]]:
    lines = text.splitlines()
    try:
        jobs_index = lines.index('jobs:')
    except ValueError:
        return []

    blocks: list[tuple[str, str]] = []
    current_name: str | None = None
    current_start = 0

    for index in range(jobs_index + 1, len(lines)):
        match = JOB_HEADER.fullmatch(lines[index])
        if match is None:
            continue
        if current_name is not None:
            blocks.append((current_name, '\n'.join(lines[current_start:index])))
        current_name = match.group(1)
        current_start = index

    if current_name is not None:
        blocks.append((current_name, '\n'.join(lines[current_start:])))

    return blocks


def check_build_job_block(workflow: Path, job_name: str, block: str) -> None:
    if './build.sh' not in block:
        return

    display = f'{workflow.relative_to(ROOT)}:{job_name}'
    require(
        re.search(r'^    permissions:\s*$', block, re.MULTILINE) is not None,
        f'{display}: build job must declare explicit permissions',
    )
    require(
        re.search(r'^      contents:\s*read\s*$', block, re.MULTILINE) is not None,
        f'{display}: build job must use contents: read',
    )
    require(
        WRITE_PERMISSION.search(block) is None,
        f'{display}: build job must not receive write permissions',
    )
    require(
        'persist-credentials: false' in block,
        f'{display}: checkout in build job must disable persisted credentials',
    )


def check_build_job_permissions() -> None:
    for workflow in sorted((ROOT / '.github/workflows').glob('*.yml')):
        text = workflow.read_text(encoding='utf-8')
        for job_name, block in workflow_job_blocks(text):
            check_build_job_block(workflow, job_name, block)


def check_attestation_job_block(workflow: Path, job_name: str, block: str) -> None:
    if 'actions/attest@' not in block:
        return

    display = f'{workflow.relative_to(ROOT)}:{job_name}'
    require(
        re.search(r'^    permissions:\s*$', block, re.MULTILINE) is not None,
        f'{display}: attestation job must declare explicit permissions',
    )
    require(
        re.search(r'^      contents:\s*read\s*$', block, re.MULTILINE) is not None,
        f'{display}: attestation job must use contents: read',
    )
    require(
        re.search(r'^      id-token:\s*write\s*$', block, re.MULTILINE) is not None,
        f'{display}: attestation job must use id-token: write',
    )
    require(
        re.search(r'^      attestations:\s*write\s*$', block, re.MULTILINE) is not None,
        f'{display}: attestation job must use attestations: write',
    )
    require(
        re.search(r'^      artifact-metadata:\s*write\s*$', block, re.MULTILINE) is not None,
        f'{display}: attestation job must use artifact-metadata: write',
    )
    require(
        'actions/checkout@' not in block, f'{display}: attestation job must not checkout source'
    )
    require(
        './build.sh' not in block, f'{display}: attestation job must not execute upstream builds'
    )
    require(
        re.search(r'^\s+-?\s*run:\s*', block, re.MULTILINE) is None,
        f'{display}: attestation job must not execute shell commands',
    )


def check_attestation_job_permissions() -> None:
    for workflow in sorted((ROOT / '.github/workflows').glob('*.yml')):
        text = workflow.read_text(encoding='utf-8')
        for job_name, block in workflow_job_blocks(text):
            check_attestation_job_block(workflow, job_name, block)


def check_publication_job_block(workflow: Path, job_name: str, block: str) -> None:
    write_permissions = set(re.findall(r'^      ([A-Za-z0-9-]+):\s*write\s*$', block, re.MULTILINE))
    if not write_permissions.intersection({'contents', 'packages', 'pages'}):
        return

    display = f'{workflow.relative_to(ROOT)}:{job_name}'
    needs = re.search(r'^    needs:\s*(.+)$', block, re.MULTILINE)
    require(
        needs is not None and 'attest' in needs.group(1),
        f'{display}: publication job must depend on attestation',
    )
    require(
        './build.sh' not in block, f'{display}: publication job must not execute upstream builds'
    )
    if 'actions/checkout@' in block:
        require(
            'persist-credentials: false' in block,
            f'{display}: publication checkout must disable persisted credentials',
        )


def check_publication_job_permissions() -> None:
    for workflow in sorted((ROOT / '.github/workflows').glob('*.yml')):
        text = workflow.read_text(encoding='utf-8')
        for job_name, block in workflow_job_blocks(text):
            check_publication_job_block(workflow, job_name, block)


def check_release_integrity_policy() -> None:
    workflow = (ROOT / '.github/workflows/release.yml').read_text(encoding='utf-8')
    jobs = dict(workflow_job_blocks(workflow))
    authorize = jobs.get('authorize')
    require(authorize is not None, 'release workflow must have an authorization job')
    assert authorize is not None
    for required in (
        'name: Verify release commit is on protected default branch',
        'repos/$GITHUB_REPOSITORY',
        "--jq '.default_branch'",
        'repos/$GITHUB_REPOSITORY/compare/$GITHUB_SHA...$default_branch',
        '"$compare_status" != \'ahead\'',
        '"$compare_status" != \'identical\'',
        'name: Verify release qualification evidence',
        'release-qualification',
        'Full build qualification',
    ):
        require(required in authorize, f'release authorization missing guard: {required}')

    build = jobs.get('build')
    require(build is not None, 'release workflow must have a build job')
    assert build is not None
    require(
        re.search(r'^    needs:\s*authorize\s*$', build, re.MULTILINE) is not None,
        'release build must depend on release authorization',
    )

    pages = jobs.get('pages')
    require(pages is not None, 'release workflow must have a Pages publication job')
    assert pages is not None
    require(
        re.search(
            r'^    needs:\s*attest\s*$',
            pages,
            re.MULTILINE,
        )
        is not None,
        'Pages publication must depend on attestation',
    )

    oci = jobs.get('oci')
    require(oci is not None, 'release workflow must have an OCI publication job')
    assert oci is not None
    require(
        'docker/setup-qemu-action@' not in oci,
        'OCI publication must not execute mutable QEMU/binfmt helper images',
    )
    buildkit_image = (
        'image=moby/buildkit@'
        'sha256:28a898719c18a33f4e8000685287fa36fd0dd9560c6440227d3a732d79bb41d8'
    )
    require(
        buildkit_image in oci,
        'OCI publication must pin the BuildKit daemon image by digest',
    )
    require(
        'platforms: linux/amd64,linux/arm64' in oci,
        'OCI publication must publish amd64 and arm64 images',
    )

    dockerfile = (ROOT / 'deploy/Dockerfile').read_text(encoding='utf-8')
    require(
        re.search(r'^\s*RUN(?:\s|$)', dockerfile, re.MULTILINE | re.IGNORECASE) is None,
        'multi-platform release Dockerfile must remain execution-free without QEMU',
    )

    require(
        workflow.count('name: Verify immutable release ref') == 3,
        'release workflow must verify the immutable tag before every publication path',
    )
    for required in (
        'repos/$GITHUB_REPOSITORY/commits/$GITHUB_REF_NAME',
        'repos/$GITHUB_REPOSITORY/rulesets',
        "expected_pattern='refs/tags/v*-web.*'",
        'index("update")',
        'index("deletion")',
        'length) == 0',
        'tag_sha_after',
    ):
        require(required in workflow, f'release workflow missing integrity guard: {required}')

    ruleset = load_json(ROOT / '.github/rulesets/immutable-release-tags.json')
    require(ruleset.get('target') == 'tag', 'release-tag ruleset must target tags')
    require(ruleset.get('enforcement') == 'active', 'release-tag ruleset must be active')
    require(ruleset.get('bypass_actors') == [], 'release-tag ruleset must not allow bypass actors')

    conditions_value = ruleset.get('conditions')
    if not isinstance(conditions_value, dict):
        raise BuildError('release-tag ruleset conditions must be an object')
    conditions = cast(dict[str, Any], conditions_value)

    ref_name_value = conditions.get('ref_name')
    if not isinstance(ref_name_value, dict):
        raise BuildError('release-tag ruleset ref_name condition must be an object')
    ref_name = cast(dict[str, Any], ref_name_value)
    require(
        ref_name.get('include') == ['refs/tags/v*-web.*'],
        'release-tag ruleset must cover refs/tags/v*-web.*',
    )

    rules_value = ruleset.get('rules')
    if not isinstance(rules_value, list):
        raise BuildError('release-tag ruleset rules must be an array')
    rule_types: set[str] = set()
    for rule_value in cast(list[object], rules_value):
        if not isinstance(rule_value, dict):
            continue
        rule = cast(dict[str, Any], rule_value)
        rule_type = rule.get('type')
        if isinstance(rule_type, str):
            rule_types.add(rule_type)
    require('update' in rule_types, 'release-tag ruleset must restrict updates')
    require('deletion' in rule_types, 'release-tag ruleset must restrict deletions')


def main() -> None:
    check_actions()
    check_shell_scripts()
    check_forbidden_execution_patterns()
    check_extension_lock()
    check_build_job_permissions()
    check_attestation_job_permissions()
    check_publication_job_permissions()
    check_release_integrity_policy()
    print('repository policy: ok')


if __name__ == '__main__':
    try:
        main()
    except BuildError as exc:
        raise SystemExit(str(exc)) from None
