#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, cast

from common import ROOT, BuildError, load_json, require

ACTION_REF = re.compile(r'uses:\s*[^@\s]+@([^\s#]+)')
FULL_SHA = re.compile(r'^[0-9a-f]{40}$')
DOCKER_DIGEST = re.compile(r'^sha256:[0-9a-f]{64}$')
JOB_HEADER = re.compile(r'^  ([A-Za-z0-9_-]+):\s*$')
WRITE_PERMISSION = re.compile(r'^\s{6}[A-Za-z0-9-]+:\s*write\s*$', re.MULTILINE)
TOOLCHAIN_VERSION = re.compile(r'^\d+\.\d+\.\d+$')
WORKFLOW_TOOLCHAIN_LITERAL = re.compile(
    r'^\s+(?:node|python)-version:\s*[\'\"]?\d',
    re.MULTILINE,
)
WORKFLOW_TOOLCHAIN_CACHE_LITERAL = re.compile(r'(?:node|python)-\d+(?:\.\d+){1,2}')
FORBIDDEN_PATTERNS = {
    'curl-pipe-shell': re.compile(r'\bcurl\b[^\n|]*\|\s*(?:ba)?sh\b'),
    'wget-pipe-shell': re.compile(r'\bwget\b[^\n|]*\|\s*(?:ba)?sh\b'),
    'npx': re.compile(r'(^|[;&|\s])npx\s+'),
    'pnpm-dlx': re.compile(r'\bpnpm\s+dlx\s+'),
    'npm-exec': re.compile(r'\bnpm\s+exec\s+'),
}


def workflow_definition_paths() -> list[Path]:
    workflows_root = ROOT / '.github/workflows'
    if not workflows_root.is_dir():
        return []
    return sorted([*workflows_root.glob('*.yml'), *workflows_root.glob('*.yaml')])


def composite_action_definition_paths() -> list[Path]:
    actions_root = ROOT / '.github/actions'
    if not actions_root.is_dir():
        return []
    return sorted([*actions_root.rglob('action.yml'), *actions_root.rglob('action.yaml')])


def action_definition_paths() -> list[Path]:
    return sorted([*workflow_definition_paths(), *composite_action_definition_paths()])


def canonical_toolchain_versions() -> dict[str, str]:
    manifest = load_json(ROOT / '.github/toolchain-versions.json')
    require(manifest.get('schemaVersion') == 1, 'unsupported toolchain manifest schema')
    versions: dict[str, str] = {}
    for name in ('node', 'python'):
        value = manifest.get(name)
        require(isinstance(value, str) and bool(value), f'toolchain {name} version missing')
        assert isinstance(value, str)
        require(
            TOOLCHAIN_VERSION.fullmatch(value) is not None,
            f'invalid toolchain {name} version: {value}',
        )
        versions[name] = value
    return versions


def check_actions() -> None:
    for workflow in action_definition_paths():
        for line_number, line in enumerate(workflow.read_text(encoding='utf-8').splitlines(), 1):
            match = ACTION_REF.search(line)
            if match:
                reference = match.group(1)
                if 'uses: docker://' in line:
                    require(
                        DOCKER_DIGEST.fullmatch(reference) is not None,
                        (
                            f'{workflow.relative_to(ROOT)}:{line_number}: '
                            'container action must use a sha256 digest'
                        ),
                    )
                else:
                    require(
                        FULL_SHA.fullmatch(reference) is not None,
                        f'{workflow.relative_to(ROOT)}:{line_number}: action must use a full commit SHA',
                    )


def check_toolchain_versions() -> None:
    canonical_toolchain_versions()
    action_path = ROOT / '.github/actions/setup-toolchain/action.yml'
    require(action_path.is_file(), 'canonical toolchain setup action missing')
    action = action_path.read_text(encoding='utf-8')
    for required in (
        'manifest="$GITHUB_ACTION_PATH/../../toolchain-versions.json"',
        'node="$(jq -er \'.node\' "$manifest")"',
        'python="$(jq -er \'.python\' "$manifest")"',
        'node-version: ${{ steps.versions.outputs.node }}',
        'python-version: ${{ steps.versions.outputs.python }}',
    ):
        require(required in action, f'canonical toolchain setup action missing: {required}')

    for workflow in workflow_definition_paths():
        text = workflow.read_text(encoding='utf-8')
        display = workflow.relative_to(ROOT)
        require(
            'actions/setup-node@' not in text,
            f'{display}: use the canonical toolchain setup action for Node',
        )
        require(
            'actions/setup-python@' not in text,
            f'{display}: use the canonical toolchain setup action for Python',
        )
        require(
            WORKFLOW_TOOLCHAIN_LITERAL.search(text) is None,
            f'{display}: hard-coded Node/Python setup version is forbidden',
        )
        require(
            WORKFLOW_TOOLCHAIN_CACHE_LITERAL.search(text) is None,
            f'{display}: hard-coded Node/Python cache version is forbidden',
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
    paths.extend(action_definition_paths())
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


def workflow_job_needs(block: str) -> set[str]:
    match = re.search(r'^    needs:\s*(.+)$', block, re.MULTILINE)
    if match is None:
        return set()

    value = match.group(1).strip()
    if value.startswith('[') and value.endswith(']'):
        value = value[1:-1]
    return {item.strip().strip('"').strip("'") for item in value.split(',') if item.strip()}


def workflow_job_environment(block: str) -> str | None:
    prefix = '    environment:'
    lines = block.splitlines()
    for index, line in enumerate(lines):
        if not line.startswith(prefix):
            continue

        value = line[len(prefix) :].strip()
        if value:
            return value.strip('"').strip("'")

        for nested in lines[index + 1 :]:
            if nested.startswith('      name:'):
                return nested.split(':', 1)[1].strip().strip('"').strip("'")
            if nested.startswith('    ') and not nested.startswith('      '):
                break
        return None

    return None


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
    for workflow in workflow_definition_paths():
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
    for workflow in workflow_definition_paths():
        text = workflow.read_text(encoding='utf-8')
        for job_name, block in workflow_job_blocks(text):
            check_attestation_job_block(workflow, job_name, block)


def publication_write_permissions(block: str) -> set[str]:
    return set(re.findall(r'^      ([A-Za-z0-9-]+):\s*write\s*$', block, re.MULTILINE))


def check_publication_job_block(workflow: Path, job_name: str, block: str) -> None:
    write_permissions = publication_write_permissions(block)
    publication_permissions = write_permissions.intersection({'contents', 'packages', 'pages'})
    if not publication_permissions:
        return

    display = f'{workflow.relative_to(ROOT)}:{job_name}'
    needs = workflow_job_needs(block)
    require(
        'attest' in needs,
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

    environment = workflow_job_environment(block)
    if 'pages' in publication_permissions:
        require(
            publication_permissions.isdisjoint({'contents', 'packages'}),
            f'{display}: Pages publication must not receive contents/packages write permissions',
        )
        require(
            environment == 'github-pages',
            f'{display}: Pages publication must use github-pages deployment environment',
        )
        require(
            'pages-release-gate' in needs,
            f'{display}: Pages publication must depend on release environment gate',
        )
    else:
        require(
            environment == 'release',
            f'{display}: publication must use release environment',
        )


def check_pages_release_gate(workflow: Path, jobs: dict[str, str]) -> None:
    gate = jobs.get('pages-release-gate')
    require(gate is not None, f'{workflow.relative_to(ROOT)}: missing pages-release-gate job')
    assert gate is not None
    require(
        workflow_job_environment(gate) == 'release',
        f'{workflow.relative_to(ROOT)}:pages-release-gate: must use release environment',
    )
    require(
        workflow_job_needs(gate) == {'attest'},
        f'{workflow.relative_to(ROOT)}:pages-release-gate: must depend only on attestation',
    )
    require(
        re.search(r'^    permissions:\s*\{\}\s*$', gate, re.MULTILINE) is not None,
        f'{workflow.relative_to(ROOT)}:pages-release-gate: must declare no token permissions',
    )
    require(
        WRITE_PERMISSION.search(gate) is None,
        f'{workflow.relative_to(ROOT)}:pages-release-gate: must not receive write permissions',
    )
    require(
        'actions/checkout@' not in gate,
        f'{workflow.relative_to(ROOT)}:pages-release-gate: must not checkout source',
    )
    require(
        './build.sh' not in gate,
        f'{workflow.relative_to(ROOT)}:pages-release-gate: must not execute upstream builds',
    )


def check_publication_job_permissions() -> None:
    for workflow in workflow_definition_paths():
        text = workflow.read_text(encoding='utf-8')
        jobs = dict(workflow_job_blocks(text))
        has_pages_publication = False
        for job_name, block in jobs.items():
            publication_permissions = publication_write_permissions(block).intersection(
                {'contents', 'packages', 'pages'}
            )
            if 'pages' in publication_permissions:
                has_pages_publication = True
            check_publication_job_block(workflow, job_name, block)
        if has_pages_publication:
            check_pages_release_gate(workflow, jobs)


def check_release_publication_boundaries(workflow: Path, text: str) -> None:
    jobs = dict(workflow_job_blocks(text))

    for job_name in ('github-release', 'oci'):
        block = jobs.get(job_name)
        require(block is not None, f'{workflow.relative_to(ROOT)}: missing {job_name} job')
        assert block is not None
        require(
            workflow_job_environment(block) == 'release',
            f'{workflow.relative_to(ROOT)}:{job_name}: publication must use release environment',
        )
        require(
            'attest' in workflow_job_needs(block),
            f'{workflow.relative_to(ROOT)}:{job_name}: publication must depend on attestation',
        )

    check_pages_release_gate(workflow, jobs)

    pages = jobs.get('pages')
    require(pages is not None, f'{workflow.relative_to(ROOT)}: missing pages publication job')
    assert pages is not None
    require(
        workflow_job_environment(pages) == 'github-pages',
        f'{workflow.relative_to(ROOT)}:pages: must use github-pages deployment environment',
    )
    page_needs = workflow_job_needs(pages)
    require(
        {'attest', 'pages-release-gate'}.issubset(page_needs),
        f'{workflow.relative_to(ROOT)}:pages: must depend on attestation and release gate',
    )


def check_release_integrity_policy() -> None:
    workflow_path = ROOT / '.github/workflows/release.yml'
    workflow = workflow_path.read_text(encoding='utf-8')
    check_release_publication_boundaries(workflow_path, workflow)
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
        'name: Download release qualification evidence',
        'run-id: ${{ inputs.qualification_run_id }}',
        'name: Verify release qualification binding',
        '.tag == $tag',
        '.commit == $commit',
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
        'attest' in workflow_job_needs(pages),
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
    check_toolchain_versions()
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
