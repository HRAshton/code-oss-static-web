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


def check_browser_qualification_topology() -> None:
    action_path = ROOT / '.github/actions/browser-qualification/action.yml'
    require(action_path.is_file(), 'reusable browser qualification action missing')
    action = action_path.read_text(encoding='utf-8')
    for required in (
        'scripts/install_playwright_browser.py',
        'scripts/run_e2e.py',
        '--grep-invert @extension',
        'scripts/add_test_extension.py',
        '--grep @extension',
        'Verify locked Playwright runtime',
        'CODE_OSS_STATIC_WEB_EXTERNAL_BASE_URL',
        "inputs.scope != 'serving'",
    ):
        require(required in action, f'browser qualification action missing: {required}')

    boot_gate = re.search(
        r'(?ms)^    - name: Browser boot gate\n(?P<body>.*?)(?=^    - name: )',
        action,
    )
    require(boot_gate is not None, 'browser qualification action missing boot gate')
    assert boot_gate is not None
    boot_gate_body = boot_gate.group('body')
    require(
        '\n      if:' not in boot_gate_body,
        'browser boot gate must run for both smoke and full qualification',
    )
    require('--retries=0' in boot_gate_body, 'browser boot gate must disable retries')
    duplicate = ROOT / '.github/workflows/browser-matrix.yml'
    require(not duplicate.exists(), 'duplicate browser-matrix workflow must be removed')

    qualify_path = ROOT / '.github/workflows/qualify.yml'
    release_path = ROOT / '.github/workflows/release.yml'
    promote_path = ROOT / '.github/workflows/promote.yml'
    qualify = qualify_path.read_text(encoding='utf-8')
    release = release_path.read_text(encoding='utf-8')
    promote = promote_path.read_text(encoding='utf-8')
    shared_action = 'uses: ./.github/actions/browser-qualification'
    require(
        qualify.count(shared_action) == 2,
        'qualification must use browser action for browser and OCI serving gates',
    )
    require(release.count(shared_action) == 1, 'release must use one shared browser action')
    require(
        promote.count(shared_action) == 2,
        'promotion must use browser action for live canary and stable Pages qualification',
    )
    require('secondary-browsers:' not in qualify, 'duplicate secondary browser job is forbidden')
    require('browsers=\'["chromium"]\'' in qualify, 'pull requests must plan Chromium-only smoke')
    require(
        'browsers=\'["chromium","firefox","webkit"]\'' in qualify,
        'full qualification must plan Chromium, Firefox and WebKit',
    )
    require('scope=smoke' in qualify, 'pull request qualification must use smoke scope')
    release_action_path = ROOT / '.github/actions/release-metadata-qualification/action.yml'
    require(release_action_path.is_file(), 'release metadata qualification action missing')
    release_action = release_action_path.read_text(encoding='utf-8')
    for required in (
        'python3 scripts/check_policy.py',
        'python3 -m unittest discover -s tests -v',
    ):
        require(
            required in release_action,
            f'release metadata qualification action missing: {required}',
        )
    for required in (
        "needs.browser-plan.outputs.level == 'release'",
        'uses: ./.github/actions/release-metadata-qualification',
        'needs: [browser-plan, release-metadata, build, browser, production-serving, package]',
        'required release metadata evidence missing',
        'SERVING_RESULT: ${{ needs.production-serving.result }}',
        'PACKAGE_RESULT: ${{ needs.package.result }}',
        "github.event_name != 'pull_request' ||",
        "needs.browser-plan.outputs.level == 'artifact' ||",
        'required artifact evidence missing:',
        "needs.browser-plan.outputs.level == 'artifact' ||",
        "needs.browser-plan.outputs.level == 'full'",
        "if: github.event_name != 'pull_request'",
    ):
        require(required in qualify, f'qualification release-only topology missing: {required}')
    tooling_block = qualify.split('  tooling:\n', 1)[1].split('\n  browser-plan:\n', 1)[0]
    require('\n    if:' not in tooling_block, 'qualification tooling must run on non-PR events')
    plan_block = qualify.split('  browser-plan:\n', 1)[1].split('\n  recover-publication:\n', 1)[0]
    require(
        "always() && needs.tooling.result == 'success'" in plan_block,
        'qualification plan must require successful tooling on every event',
    )
    release_gate = qualify.split('  release-intent-gate:\n', 1)[1]
    for required in (
        "always() && (inputs.release_mode == 'upstream' || inputs.release_mode == 'patch')",
        'needs: [tooling, browser-plan, recover-publication, build, browser, production-serving, package, attest, release]',
        'permissions: {}',
        'require_result tooling "$TOOLING_RESULT" success',
        'require_result browser-plan "$PLAN_RESULT" success',
        'require_result recover-publication "$RECOVERY_RESULT" success',
        'require_result build "$BUILD_RESULT" success',
        'require_result browser "$BROWSER_RESULT" success',
        'require_result production-serving "$SERVING_RESULT" success',
        'require_result package "$PACKAGE_RESULT" success',
        'require_result attest "$ATTEST_RESULT" success',
        'require_result release "$RELEASE_RESULT" success',
    ):
        require(required in release_gate, f'release intent gate missing: {required}')
    require('browser: [chromium]' in release, 'release validation must use Chromium matrix')

    browser_scripts = (
        'scripts/install_playwright_browser.py',
        'scripts/run_e2e.py',
        'scripts/add_test_extension.py',
    )
    for workflow in workflow_definition_paths():
        text = workflow.read_text(encoding='utf-8')
        for script in browser_scripts:
            require(
                script not in text,
                f'{workflow.relative_to(ROOT)}: use the reusable browser qualification action',
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


def check_publication_job_block(
    workflow: Path, job_name: str, block: str, evidence_job: str
) -> None:
    write_permissions = publication_write_permissions(block)
    publication_permissions = write_permissions.intersection({'contents', 'packages', 'pages'})
    if not publication_permissions:
        return

    display = f'{workflow.relative_to(ROOT)}:{job_name}'
    if re.search(r'^    uses:', block, re.MULTILINE) is not None:
        # The caller grants token permissions to the reusable workflow. Only
        # the reviewed emergency qualifier may inherit publication authority.
        trusted_caller = (
            workflow.name == 'upstream-soak-break-glass.yml'
            and job_name == 'qualify'
            and '    uses: ./.github/workflows/qualify.yml' in block.splitlines()
        )
        require(
            trusted_caller,
            f'{display}: unapproved privileged reusable workflow call',
        )
        require(
            workflow_job_needs(block) == {'authorize-override'},
            f'{display}: unapproved privileged reusable workflow call',
        )
        caller_jobs = dict(workflow_job_blocks(workflow.read_text()))
        authorization = caller_jobs.get('authorize-override')
        require(
            authorization is not None
            and workflow_job_environment(authorization) == 'upstream-soak-break-glass'
            and 'python3 scripts/authorize_soak_override.py' in authorization,
            f'{display}: unapproved privileged reusable workflow call',
        )
        required_inputs = (
            'browser: all',
            'release_mode: upstream',
            'expected_source_sha: ${{ inputs.expected_source_sha }}',
            'security_override_reason: ${{ inputs.security_override_reason }}',
        )
        require(
            all(item in block for item in required_inputs),
            f'{display}: unapproved privileged reusable workflow call',
        )
        privileged_permissions = {
            'actions',
            'contents',
            'id-token',
            'attestations',
            'artifact-metadata',
        }
        require(
            write_permissions == privileged_permissions,
            f'{display}: privileged reusable qualifier has unexpected permissions',
        )
        return

    needs = workflow_job_needs(block)
    require(
        evidence_job in needs,
        f'{display}: publication job must depend on {evidence_job}',
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


def check_pages_release_gate(workflow: Path, jobs: dict[str, str], evidence_job: str) -> None:
    gate = jobs.get('pages-release-gate')
    require(gate is not None, f'{workflow.relative_to(ROOT)}: missing pages-release-gate job')
    assert gate is not None
    require(
        workflow_job_environment(gate) == 'release',
        f'{workflow.relative_to(ROOT)}:pages-release-gate: must use release environment',
    )
    require(
        workflow_job_needs(gate) == {evidence_job},
        f'{workflow.relative_to(ROOT)}:pages-release-gate: must depend only on {evidence_job}',
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
    evidence_jobs = {
        'recover-release-publication.yml': 'authorize-recovery',
        'promote.yml': 'authorize',
    }
    for workflow in workflow_definition_paths():
        text = workflow.read_text(encoding='utf-8')
        jobs = dict(workflow_job_blocks(text))
        evidence_job = evidence_jobs.get(workflow.name, 'attest')
        has_pages_publication = False
        for job_name, block in jobs.items():
            publication_permissions = publication_write_permissions(block).intersection(
                {'contents', 'packages', 'pages'}
            )
            if 'pages' in publication_permissions:
                has_pages_publication = True
            check_publication_job_block(workflow, job_name, block, evidence_job)
        if has_pages_publication:
            check_pages_release_gate(workflow, jobs, evidence_job)


def check_release_publication_boundaries(workflow: Path, text: str) -> None:
    jobs = dict(workflow_job_blocks(text))

    require('pages' not in jobs, 'immutable release workflow must not deploy GitHub Pages')
    require(
        'uses: ./.github/actions/publish-pages' not in text,
        'immutable release workflow must not contain mutable Pages promotion',
    )
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


def check_qualification_source_binding() -> None:
    qualify = (ROOT / '.github/workflows/qualify.yml').read_text(encoding='utf-8')
    for required in (
        'expected_source_sha:',
        'name: Verify expected source SHA',
        'EXPECTED_SOURCE_SHA: ${{ inputs.expected_source_sha }}',
        'python3 scripts/verify_qualification_source.py "$EXPECTED_SOURCE_SHA" "$GITHUB_SHA"',
        'expectedSourceSha: $expectedSourceSha',
        'Expected source SHA:',
    ):
        require(required in qualify, f'qualification source binding missing: {required}')

    require(
        qualify.index('name: Verify expected source SHA')
        < qualify.index('name: Select browser qualification plan'),
        'qualification source binding must run before qualification planning',
    )

    upstream = (ROOT / '.github/workflows/upstream-qualification.yml').read_text(encoding='utf-8')
    for required in (
        'commits/$default_branch',
        'upstream.lock.json?ref=$current_sha',
        'echo "source_sha=$current_sha" >> "$GITHUB_OUTPUT"',
        'SOURCE_SHA: ${{ steps.upstream.outputs.source_sha }}',
        '-f expected_source_sha="$SOURCE_SHA"',
    ):
        require(
            required in upstream,
            f'upstream qualification dispatch missing source binding: {required}',
        )
    require(
        'AFTER_SHA:' not in upstream and 'source_sha=$AFTER_SHA' not in upstream,
        'upstream qualification retry must not reuse the original push SHA',
    )

    patch = (ROOT / '.github/workflows/patch-release.yml').read_text(encoding='utf-8')
    for required in (
        'contents/upstream.lock.json?ref=$master_sha',
        'echo "source_sha=$master_sha" >> "$GITHUB_OUTPUT"',
        'SOURCE_SHA: ${{ steps.release.outputs.source_sha }}',
        '-f expected_source_sha="$SOURCE_SHA"',
    ):
        require(
            required in patch,
            f'patch qualification dispatch missing source binding: {required}',
        )

    release = (ROOT / '.github/workflows/release.yml').read_text(encoding='utf-8')
    require(
        '.expectedSourceSha == $commit' in release,
        'release authorization must verify the expected qualification source SHA',
    )


def check_qualification_release_retry_policy() -> None:
    workflow = ROOT / '.github/workflows/qualify.yml'
    text = workflow.read_text(encoding='utf-8')

    for required in (
        'release_tag: ${{ steps.plan.outputs.release_tag }}',
        'retry_tag: ${{ steps.plan.outputs.retry_tag }}',
        'release_tag="$latest_tag"',
        'retry_tag="$release_tag"',
        "needs.browser-plan.outputs.retry_tag == ''",
        'recover-publication:',
        'actions/workflows/release.yml/runs',
        '-f head_sha="$GITHUB_SHA"',
        '.head_branch == $tag',
        '.head_sha == $sha',
        'gh workflow run recover-release-publication.yml',
        '-f release_tag="$RELEASE_TAG"',
        '-f release_run_id="$release_run_id"',
        '-f channel=all',
    ):
        require(required in text, f'qualification retry path missing recovery guard: {required}')

    for forbidden in (
        'publication is complete',
        'gh release view "$RELEASE_TAG"',
        'already points to this qualification commit',
    ):
        require(
            forbidden not in text,
            f'qualification retry path must not infer publication completion: {forbidden}',
        )

    patch = (ROOT / '.github/workflows/patch-release.yml').read_text(encoding='utf-8')
    require(
        "intent='retry existing immutable publication'" in patch
        and 'target_tag="$latest_tag"' in patch,
        'patch release dispatcher must carry same-commit tags into publication recovery',
    )
    require(
        'already points to current master' not in patch,
        'patch release dispatcher must not reject same-commit publication retries',
    )


def check_recovery_publication_boundaries() -> None:
    workflow = ROOT / '.github/workflows/recover-release-publication.yml'
    require(workflow.is_file(), 'release publication recovery workflow missing')
    text = workflow.read_text(encoding='utf-8')
    jobs = dict(workflow_job_blocks(text))

    authorize = jobs.get('authorize-recovery')
    require(authorize is not None, 'publication recovery must have an authorization job')
    assert authorize is not None
    require(
        publication_write_permissions(authorize) == set(),
        'publication recovery authorization must be read-only',
    )
    for required in (
        'release_tag:',
        'release_run_id:',
        'channel:',
        'repos/$GITHUB_REPOSITORY/actions/runs/$RELEASE_RUN_ID',
        '.path == ".github/workflows/release.yml"',
        '.head_branch == $tag',
        '.head_sha == $sha',
        'release_sha: ${{ steps.source.outputs.release_sha }}',
        'current_sha="$(gh api "repos/$GITHUB_REPOSITORY/commits/$default_branch" --jq \'.sha\')"',
        'required preparation job did not succeed exactly once',
        'release-static-dist',
        'release-candidate',
        'release-attestation',
    ):
        require(
            required in authorize or required in text,
            f'publication recovery missing guard: {required}',
        )

    for forbidden in ('./build.sh', 'package.sh', 'actions/attest@'):
        require(
            forbidden not in text,
            f'publication recovery must not regenerate immutable release content: {forbidden}',
        )

    require('pages' not in jobs, 'immutable release recovery must not deploy GitHub Pages')
    require(
        'uses: ./.github/actions/publish-pages' not in text,
        'immutable release recovery must not change stable deployment state',
    )

    for job_name in ('github-release', 'oci'):
        block = jobs.get(job_name)
        require(block is not None, f'publication recovery missing {job_name} job')
        assert block is not None
        require(
            workflow_job_environment(block) == 'release',
            f'publication recovery {job_name} must use release environment',
        )
        require(
            'authorize-recovery' in workflow_job_needs(block),
            f'publication recovery {job_name} must depend on authorization',
        )

    for required in (
        'run-id: ${{ inputs.release_run_id }}',
        'uses: ./.github/actions/publish-github-release',
        'uses: ./.github/actions/publish-oci',
        "group: release-${{ inputs.release_tag && format('refs/tags/{0}', inputs.release_tag) || github.ref }}",
        'publication-status:',
    ):
        require(required in text, f'publication recovery missing: {required}')

    require(
        text.count('name: Verify immutable release ref') == 2,
        'publication recovery must verify the immutable tag before both publication paths',
    )


def check_promotion_boundaries() -> None:
    workflow = ROOT / '.github/workflows/promote.yml'
    require(workflow.is_file(), 'immutable release promotion workflow missing')
    text = workflow.read_text(encoding='utf-8')
    jobs = dict(workflow_job_blocks(text))

    for forbidden in (
        './build.sh',
        'package.sh',
        'actions/attest@',
        'uses: ./.github/actions/publish-oci',
        'uses: ./.github/actions/publish-github-release',
    ):
        require(
            forbidden not in text,
            f'promotion must not regenerate immutable release: {forbidden}',
        )

    authorize = jobs.get('authorize')
    require(authorize is not None, 'promotion workflow must have an authorization job')
    assert authorize is not None
    require(
        publication_write_permissions(authorize) == set(),
        'promotion authorization must be read-only',
    )

    canary = jobs.get('canary')
    require(canary is not None, 'promotion workflow must have a canary job')
    assert canary is not None
    require(
        {'authorize', 'pages-release-gate'}.issubset(workflow_job_needs(canary)),
        'canary promotion must depend on authorization and release gate',
    )
    require(
        workflow_job_environment(canary) == 'github-pages',
        'canary promotion must deploy through github-pages environment',
    )
    require('deployments: write' in canary, 'canary promotion must record GitHub deployment state')
    require('pages: write' in canary, 'canary promotion must own Pages deployment')
    require(
        publication_write_permissions(canary).intersection({'contents', 'packages'}) == set(),
        'canary promotion must not publish immutable release channels',
    )
    require(
        'uses: ./.github/actions/publish-pages' in canary,
        'canary promotion must use the shared Pages publication action',
    )

    check_pages_release_gate(workflow, jobs, 'authorize')
    stable = jobs.get('stable')
    require(stable is not None, 'promotion workflow must have a stable job')
    assert stable is not None
    require(
        workflow_job_environment(stable) == 'github-pages',
        'stable promotion must deploy through github-pages environment',
    )
    require(
        {'authorize', 'canary', 'pages-release-gate'}.issubset(workflow_job_needs(stable)),
        'stable promotion must depend on authorization, canary, and release gate',
    )
    require('deployments: write' in stable, 'stable promotion must record GitHub deployment state')
    require('pages: write' in stable, 'stable promotion must own Pages deployment')
    require(
        'uses: ./.github/actions/publish-pages' in stable,
        'stable promotion must use the shared Pages publication action',
    )

    for required in (
        'group: promotion-state',
        'release_tag:',
        'source_release_run_id:',
        'target:',
        'gh release download',
        'gh attestation verify',
        'scripts/promotion.py',
        'promotion-identity.json',
        'scripts/pages_identity.py write',
        'pages-deployment-identity.json',
        'cp .work/promotion/pages-deployment-identity.json dist/deployment-identity.json',
        'identity-path: .work/promotion/pages-deployment-identity.json',
        '--argjson identity "$target_identity"',
        '--argjson releaseArtifact "$target_release_artifact"',
        '[.[] | select(.state == "success")] | length',
        'environment: "canary"',
        'environment: "stable"',
        'automatic promotion refuses to move stable backward',
        'previous stable deployment history',
        'environment=github-pages&ref=$RELEASE_COMMIT',
        'deployments?environment=github-pages&per_page=100',
        'legacy-pages-identity.json',
        'for asset in artifact-manifest.json "$stable_archive"',
        'pages_identity.py verify',
        'promotion-status:',
    ):
        require(required in text, f'promotion workflow missing invariant: {required}')

    pages_action = (ROOT / '.github/actions/publish-pages/action.yml').read_text(encoding='utf-8')
    require(
        'pages/deployments/$GITHUB_SHA' in pages_action,
        'Pages publication must verify the exact Pages deployment created by the workflow',
    )
    for required in (
        'identity-path:',
        'identity-url-path:',
        'DEPLOYED_URL: ${{ steps.deployment.outputs.page_url }}',
        '${identity_path#/}?promotion_run=$GITHUB_RUN_ID',
        'Cache-Control: no-cache',
        'scripts/pages_identity.py verify',
    ):
        require(
            required in pages_action,
            f'Pages publication missing live release identity verification: {required}',
        )
    require(
        pages_action.index('name: Deploy GitHub Pages')
        < pages_action.index('name: Verify live Pages release identity'),
        'Pages live release identity must be verified after deployment',
    )
    require(
        'deployments?environment=github-pages' not in pages_action,
        'Pages publication must not infer completion from generic environment deployment state',
    )
    require(
        'steps.state.outputs.complete' not in pages_action,
        'Pages promotion must replay the verified immutable bytes on every attempt',
    )

    release = (ROOT / '.github/workflows/release.yml').read_text(encoding='utf-8')
    for required in (
        'immutable-publication-status:',
        'gh workflow run promote.yml',
        '--ref "$GITHUB_REF_NAME"',
        '-f source_release_run_id="$GITHUB_RUN_ID"',
        '-f target=auto',
    ):
        require(required in release, f'release workflow missing automatic promotion: {required}')


def check_independent_sbom_policy() -> None:
    policy_path = ROOT / 'security/sbom-comparison-policy.json'
    require(policy_path.is_file(), 'independent SBOM comparison policy missing')
    policy = load_json(policy_path)
    require(policy.get('schemaVersion') == 1, 'independent SBOM policy schema must be 1')
    scanner_value = policy.get('scanner')
    require(isinstance(scanner_value, dict), 'independent SBOM scanner policy missing')
    scanner = cast(dict[str, Any], scanner_value)
    require(scanner.get('name') == 'syft', 'independent SBOM scanner must be Syft')
    version_value = scanner.get('version')
    require(
        isinstance(version_value, str) and bool(version_value),
        'independent Syft version missing',
    )
    version = cast(str, version_value)

    exceptions_value = policy.get('exceptions')
    require(isinstance(exceptions_value, list), 'independent SBOM exceptions must be an array')
    exceptions = cast(list[Any], exceptions_value)
    for exception_value in exceptions:
        require(
            isinstance(exception_value, dict),
            'independent SBOM exception must be an object',
        )
        exception = cast(dict[str, Any], exception_value)
        match_value = exception.get('match')
        require(
            isinstance(match_value, dict),
            'independent SBOM exception match must be an object',
        )
        match = cast(dict[str, Any], match_value)
        require(
            isinstance(match.get('purl'), str)
            and bool(match.get('purl'))
            and isinstance(match.get('path'), str)
            and bool(match.get('path')),
            'independent SBOM exceptions must match exact purl and artifact path',
        )

    config_path = ROOT / 'security/syft.yaml'
    require(config_path.is_file(), 'independent Syft scanner config missing')
    config = config_path.read_text(encoding='utf-8')
    require(
        'select-catalogers:' in config and '- +javascript-package-cataloger' in config,
        'independent Syft scanner must enable the JavaScript package cataloger',
    )

    action_path = ROOT / '.github/actions/independent-sbom/action.yml'
    require(action_path.is_file(), 'independent SBOM action missing')
    action = action_path.read_text(encoding='utf-8')
    for required in (
        'anchore/sbom-action@66cbf4bc1f1c0d2edc94016e65bc221b6bb0ad6c',
        f'syft-version: v{version}',
        'config: security/syft.yaml',
        'format: cyclonedx-json',
        "dependency-snapshot: 'false'",
        "upload-artifact: 'false'",
        "upload-release-assets: 'false'",
    ):
        require(required in action, f'independent SBOM action missing invariant: {required}')

    package_sh = (ROOT / 'package.sh').read_text(encoding='utf-8')
    require(
        '-c "$ROOT/security/syft.yaml"' in package_sh,
        'local packaging must use the reviewed independent Syft scanner config',
    )

    for workflow_name in ('qualify.yml', 'release.yml'):
        workflow_path = ROOT / '.github/workflows' / workflow_name
        text = workflow_path.read_text(encoding='utf-8')
        jobs = dict(workflow_job_blocks(text))
        package = jobs.get('package')
        require(package is not None, f'{workflow_name}: package job missing')
        assert package is not None
        require(
            publication_write_permissions(package) == set(),
            f'{workflow_name}: independent SBOM package job must remain read-only',
        )
        for required in (
            'uses: ./.github/actions/independent-sbom',
            'path: dist',
            'output-file: .work/independent-sbom.cdx.json',
            'run: ./package.sh',
        ):
            require(required in package, f'{workflow_name}: package job missing {required}')

    qualify = (ROOT / '.github/workflows/qualify.yml').read_text(encoding='utf-8')
    qualify_jobs = dict(workflow_job_blocks(qualify))
    gate = qualify_jobs.get('artifact-gate')
    require(gate is not None, 'qualification artifact gate missing')
    assert gate is not None
    require(
        'package' in workflow_job_needs(gate),
        'qualification artifact gate must require independent SBOM packaging evidence',
    )
    require(
        'PACKAGE_RESULT: ${{ needs.package.result }}' in gate
        and '"$PACKAGE_RESULT" != success' in gate,
        'qualification artifact gate must fail when independent SBOM packaging fails',
    )
    attest = qualify_jobs.get('attest')
    require(attest is not None, 'qualification attestation job missing')
    assert attest is not None
    require(
        "if: github.event_name != 'pull_request'" in attest,
        'pull-request independent SBOM validation must not receive attestation authority',
    )

    package_release = (ROOT / 'scripts/package_release.py').read_text(encoding='utf-8')
    for required in (
        "WORK / 'independent-sbom.cdx.json'",
        'compare_sbom_inventory.compare_files(',
        "'independent-component-inventory.json'",
        "'sbom-comparison.json'",
        "'sbomComparisonPolicy': input_digest(",
        "'sbomScannerConfig': input_digest(",
    ):
        require(
            required in package_release,
            f'release packaging missing SBOM cross-check: {required}',
        )

    verifier = (ROOT / 'scripts/verify_release.py').read_text(encoding='utf-8')
    for required in (
        'verify_independent_sbom_evidence(directory)',
        "'independent-component-inventory.json'",
        "'sbom-comparison.json'",
        "comparison.get('status') == 'pass'",
    ):
        require(required in verifier, f'release verification missing SBOM cross-check: {required}')

    for workflow in workflow_definition_paths():
        text = workflow.read_text(encoding='utf-8')
        if 'anchore/scan-action@' in text:
            require(
                'sbom: .work/independent-sbom.cdx.json' in text,
                (
                    f'{workflow.relative_to(ROOT)}: vulnerability admission must reuse '
                    'the independent Syft SBOM'
                ),
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

    oci = jobs.get('oci')
    require(oci is not None, 'release workflow must have an OCI publication job')
    assert oci is not None
    require(
        'uses: ./.github/actions/publish-oci' in oci,
        'release OCI publication must use the shared publication action',
    )
    oci_action_path = ROOT / '.github/actions/publish-oci/action.yml'
    require(oci_action_path.is_file(), 'shared OCI publication action missing')
    oci_action = oci_action_path.read_text(encoding='utf-8')
    require(
        'docker/setup-qemu-action@' not in oci_action,
        'OCI publication must not execute mutable QEMU/binfmt helper images',
    )
    buildkit_image = (
        'image=moby/buildkit@'
        'sha256:28a898719c18a33f4e8000685287fa36fd0dd9560c6440227d3a732d79bb41d8'
    )
    require(
        buildkit_image in oci_action,
        'OCI publication must pin the BuildKit daemon image by digest',
    )
    require(
        'platforms: linux/amd64,linux/arm64' in oci_action,
        'OCI publication must publish amd64 and arm64 images',
    )
    require(
        'unable to determine GHCR publication state; refusing to publish' in oci_action,
        'OCI publication must fail closed when registry state is unknown',
    )
    require(
        "steps.state.outputs.exists == 'false'" in oci_action,
        'OCI publication must publish only after confirmed absence',
    )
    oci_verifier = (ROOT / 'scripts/verify_oci_image.sh').read_text(encoding='utf-8')
    require(
        'for arch in amd64 arm64; do' in oci_verifier
        and 'child="$image@$digest"' in oci_verifier
        and 'scripts/compare_dist.py "$dist" "$platform_dist"' in oci_verifier,
        'OCI publication must verify the complete static tree for both platform children',
    )

    dockerfile = (ROOT / 'deploy/Dockerfile').read_text(encoding='utf-8')
    nginx_base_image = re.compile(
        r'^FROM public\.ecr\.aws/nginx/nginx-unprivileged:[^\s@]+@sha256:[0-9a-f]{64},
        re.MULTILINE,
    )
    require(
        nginx_base_image.search(dockerfile) is not None,
        'OCI base image must use digest-pinned upstream NGINX on AWS ECR Public',
    )
    require(
        'COPY dist/ /srv/code-oss-static-web/' in dockerfile,
        'OCI image must copy the static distribution into a dedicated served root',
    )
    nginx_config = (ROOT / 'deploy/nginx.conf').read_text(encoding='utf-8')
    require(
        'root /srv/code-oss-static-web;' in nginx_config,
        'OCI nginx configuration must serve only the dedicated static distribution root',
    )
    require(
        re.search(r'^\s*RUN(?:\s|$)', dockerfile, re.MULTILINE | re.IGNORECASE) is None,
        'multi-platform release Dockerfile must remain execution-free without QEMU',
    )

    require(
        workflow.count('name: Verify immutable release ref') == 2,
        'release workflow must verify the immutable tag before both immutable publication paths',
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


def check_codeowners_policy() -> None:
    codeowners_path = ROOT / '.github/CODEOWNERS'
    require(codeowners_path.is_file(), 'sensitive-path CODEOWNERS file missing')

    entries: dict[str, tuple[str, ...]] = {}
    for line_number, raw_line in enumerate(
        codeowners_path.read_text(encoding='utf-8').splitlines(),
        1,
    ):
        line = raw_line.strip()
        if not line or line.startswith('#'):
            continue
        parts = line.split()
        require(len(parts) >= 2, f'.github/CODEOWNERS:{line_number}: owner list missing')
        pattern, *owners = parts
        require(
            pattern not in entries,
            f'.github/CODEOWNERS:{line_number}: duplicate pattern {pattern}',
        )
        entries[pattern] = tuple(owners)

    require(
        '/upstream.lock.json' not in entries
        and 'upstream.lock.json' not in entries
        and '/builder-apt-snapshot.json' not in entries
        and 'builder-apt-snapshot.json' not in entries,
        'Renovate data locks must remain outside CODEOWNERS for zero-touch updates',
    )

    team_mapping_path = ROOT / '.github/governance-teams.json'
    if not team_mapping_path.exists():
        expected_patterns = {
            '/.github/',
            '/GOVERNANCE.md',
            '/CONTRIBUTING.md',
            '/SECURITY.md',
            '/OPERATIONS.md',
            '/renovate.json',
            '/builder-image.json',
            '/security/',
            '/extensions/',
            '/deploy/',
            '/scripts/',
            '/config/',
            '/patches/',
            '/build.sh',
            '/package.sh',
            '/docs/release-security.md',
            '/docs/releasing.md',
            '/docs/organization-migration.md',
            '/docs/extension-mirror.md',
        }
        require(
            set(entries) == expected_patterns,
            'CODEOWNERS sensitive-path allowlist changed; review governance mapping explicitly',
        )
        expected_owners = {'@HRAshton', '@vodyanica'}
        for pattern, owners in entries.items():
            require(
                set(owners) == expected_owners and len(owners) == len(expected_owners),
                f'CODEOWNERS interim owner set changed for {pattern}',
            )
        return

    import render_codeowners

    config = load_json(team_mapping_path)
    require(config.get('schemaVersion') == 1, 'governance team mapping schemaVersion invalid')
    organization = config.get('organization')
    teams = config.get('teams')
    require(isinstance(organization, str), 'governance organization missing')
    require(isinstance(teams, dict), 'governance teams missing')
    assert isinstance(organization, str)
    assert isinstance(teams, dict)
    normalized = render_codeowners.mapping(organization, cast(dict[str, str], teams))
    expected = render_codeowners.render_codeowners(normalized)
    require(
        codeowners_path.read_text(encoding='utf-8') == expected,
        'organization CODEOWNERS does not match governance team mapping; rerun render_codeowners.py',
    )
    for owners in entries.values():
        require(
            all(owner.startswith(f'@{organization}/') for owner in owners),
            'organization CODEOWNERS must use only approved organization teams',
        )


def main() -> None:
    check_actions()
    check_toolchain_versions()
    check_browser_qualification_topology()
    check_shell_scripts()
    check_forbidden_execution_patterns()
    check_extension_lock()
    check_build_job_permissions()
    check_attestation_job_permissions()
    check_publication_job_permissions()
    check_codeowners_policy()
    check_qualification_source_binding()
    check_qualification_release_retry_policy()
    check_recovery_publication_boundaries()
    check_promotion_boundaries()
    check_independent_sbom_policy()
    check_release_integrity_policy()
    print('repository policy: ok')


if __name__ == '__main__':
    try:
        main()
    except BuildError as exc:
        raise SystemExit(str(exc)) from None
