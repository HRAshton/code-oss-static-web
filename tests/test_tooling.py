from __future__ import annotations

import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import check_policy
import compare_dist
import extension_lock
import extensions_index
import fetch_upstream
import generate_license_inventory
import generate_runtime_metadata
import generate_sbom
import make_static
import package_release
import publish_github_release
import validate_config
import verify_dist_identity
import verify_qualification_source


class ToolingTests(unittest.TestCase):
    def test_upstream_lock_is_exact_commit(self):
        lock = json.loads((ROOT / 'upstream.lock.json').read_text())
        self.assertRegex(lock['commit'], r'^[0-9a-f]{40}$')
        self.assertNotIn('qualified', lock)
        self.assertNotIn('qualificationNote', lock)

    def _create_upstream_tag_fixture(self, root: Path) -> tuple[Path, str, str]:
        remote = root / 'remote.git'
        source = root / 'source'
        remote.mkdir()
        source.mkdir()
        subprocess.run(['git', 'init', '-q', '--bare'], cwd=remote, check=True)
        subprocess.run(['git', 'init', '-q'], cwd=source, check=True)
        subprocess.run(
            ['git', 'config', 'user.email', 'fixture@example.invalid'],
            cwd=source,
            check=True,
        )
        subprocess.run(['git', 'config', 'user.name', 'Fixture'], cwd=source, check=True)

        tracked = source / 'fixture.txt'
        tracked.write_text('lightweight\n')
        subprocess.run(['git', 'add', 'fixture.txt'], cwd=source, check=True)
        subprocess.run(['git', 'commit', '-q', '-m', 'lightweight'], cwd=source, check=True)
        lightweight_commit = subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'],
            cwd=source,
            text=True,
        ).strip()
        subprocess.run(['git', 'tag', 'lightweight'], cwd=source, check=True)

        tracked.write_text('annotated\n')
        subprocess.run(['git', 'commit', '-q', '-am', 'annotated'], cwd=source, check=True)
        annotated_commit = subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'],
            cwd=source,
            text=True,
        ).strip()
        subprocess.run(
            ['git', 'tag', '-a', 'annotated', '-m', 'annotated release'],
            cwd=source,
            check=True,
        )

        subprocess.run(
            ['git', 'remote', 'add', 'origin', str(remote)],
            cwd=source,
            check=True,
        )
        subprocess.run(
            ['git', 'push', '-q', 'origin', 'HEAD:refs/heads/main', '--tags'],
            cwd=source,
            check=True,
        )
        return remote, lightweight_commit, annotated_commit

    def test_upstream_lightweight_tag_resolves_to_commit(self):
        with tempfile.TemporaryDirectory() as td:
            remote, lightweight_commit, _ = self._create_upstream_tag_fixture(Path(td))
            self.assertEqual(
                fetch_upstream.resolve_remote_tag(str(remote), 'lightweight'),
                lightweight_commit,
            )

    def test_upstream_annotated_tag_is_peeled_to_commit(self):
        with tempfile.TemporaryDirectory() as td:
            remote, _, annotated_commit = self._create_upstream_tag_fixture(Path(td))
            self.assertEqual(
                fetch_upstream.resolve_remote_tag(str(remote), 'annotated'),
                annotated_commit,
            )

    def test_upstream_tag_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            remote, lightweight_commit, annotated_commit = self._create_upstream_tag_fixture(
                Path(td)
            )
            self.assertNotEqual(lightweight_commit, annotated_commit)
            lock = {
                'repository': str(remote),
                'tag': 'lightweight',
                'commit': annotated_commit,
            }
            with self.assertRaisesRegex(fetch_upstream.BuildError, 'upstream tag mismatch'):
                fetch_upstream.verify_tag_binding(lock)

    def test_upstream_binding_is_validated_before_build(self):
        ci = (ROOT / '.github/workflows/ci.yml').read_text()
        qualify = (ROOT / '.github/workflows/qualify.yml').read_text()
        tooling = (ROOT / '.github/actions/tooling-checks/action.yml').read_text()
        self.assertIn('uses: ./.github/actions/tooling-checks', ci)
        self.assertIn('uses: ./.github/actions/tooling-checks', qualify)
        self.assertIn('name: Upstream tag-to-commit binding', tooling)
        self.assertIn('python3 scripts/fetch_upstream.py --verify-tag-only', tooling)

        fetch_source = (ROOT / 'scripts/fetch_upstream.py').read_text()
        self.assertIn('verify_tag_binding(lock)', fetch_source)
        self.assertIn(
            "run(['git', 'fetch', '--depth=1', 'origin', lock['commit']], cwd=dest)",
            fetch_source,
        )
        self.assertIn("require(actual == lock['commit']", fetch_source)

    def test_renovate_auto_approval_is_limited_to_upstream_lock(self):
        config = json.loads((ROOT / 'renovate.json').read_text())
        self.assertTrue(config['automerge'])
        self.assertEqual(config['automergeType'], 'pr')
        self.assertTrue(config['platformAutomerge'])
        self.assertEqual(config['automergeStrategy'], 'merge-commit')
        self.assertEqual(config['semanticCommits'], 'enabled')
        self.assertEqual(config['commitMessageLowerCase'], 'never')
        self.assertNotIn('reviewers', config)
        self.assertNotIn('assignAutomerge', config)

        manager = next(
            item
            for item in config['customManagers']
            if item.get('depNameTemplate') == 'microsoft/vscode'
        )
        self.assertEqual(manager['datasourceTemplate'], 'github-tags')
        replacement = manager['autoReplaceStringTemplate']
        self.assertEqual(
            replacement,
            '"tag": "{{{newValue}}}",\n  "commit": "{{{newDigest}}}"',
        )
        self.assertNotIn('\\', replacement)
        self.assertNotIn('qualified', replacement)

        workflow = (ROOT / '.github/workflows/renovate-auto-approve.yml').read_text()
        self.assertIn('.user.login == "renovate[bot]"', workflow)
        self.assertIn('pull-requests: write', workflow)
        self.assertIn('event=APPROVE', workflow)
        self.assertNotIn('gh pr merge', workflow)

        allowlist = workflow.split('case "$path" in', 1)[1].split('*)', 1)[0]
        auto_approvable = {
            line.strip().removesuffix(') ;;')
            for line in allowlist.splitlines()
            if line.strip().endswith(') ;;')
        }
        self.assertEqual(auto_approvable, {'upstream.lock.json'})
        self.assertIn('upstream.lock.json', auto_approvable)
        for denied in (
            'deploy/Dockerfile',
            '.github/workflows/ci.yml',
            '.github/actions/setup-toolchain/action.yml',
            'security/threat-model.md',
        ):
            with self.subTest(path=denied):
                self.assertNotIn(denied, auto_approvable)

    def test_sensitive_paths_require_codeowners_without_gating_upstream_updates(self):
        codeowners = (ROOT / '.github/CODEOWNERS').read_text()
        check_policy.check_codeowners_policy()

        lines = {
            line.split()[0]: set(line.split()[1:])
            for line in codeowners.splitlines()
            if line.strip() and not line.lstrip().startswith('#')
        }
        self.assertEqual(lines['/.github/'], {'@HRAshton', '@vodyanica'})
        self.assertEqual(lines['/security/'], {'@HRAshton', '@vodyanica'})
        self.assertEqual(lines['/deploy/'], {'@HRAshton', '@vodyanica'})
        self.assertEqual(lines['/renovate.json'], {'@HRAshton', '@vodyanica'})
        self.assertNotIn('/upstream.lock.json', lines)
        self.assertNotIn('upstream.lock.json', lines)

    def test_upstream_revision_change_dispatches_full_qualification(self):
        workflow = (ROOT / '.github/workflows/upstream-qualification.yml').read_text()
        self.assertIn('branches: [master]', workflow)
        self.assertIn('- upstream.lock.json', workflow)
        self.assertIn('old_revision=', workflow)
        self.assertIn('new_revision=', workflow)
        self.assertIn("steps.upstream.outputs.changed == 'true'", workflow)
        self.assertIn('gh workflow run qualify.yml', workflow)
        self.assertIn('-f browser=all', workflow)
        self.assertIn('-f release_mode=upstream', workflow)
        self.assertIn('default_branch=', workflow)
        self.assertIn("--jq '.default_branch'", workflow)
        self.assertIn('commits/$default_branch', workflow)
        self.assertIn('upstream.lock.json?ref=$current_sha', workflow)
        self.assertIn('echo "source_sha=$current_sha" >> "$GITHUB_OUTPUT"', workflow)
        self.assertNotIn('AFTER_SHA:', workflow)
        self.assertNotIn('source_sha=$AFTER_SHA', workflow)
        self.assertIn('SOURCE_SHA: ${{ steps.upstream.outputs.source_sha }}', workflow)
        self.assertIn('-f expected_source_sha="$SOURCE_SHA"', workflow)

    def test_qualification_source_mismatch_fails_closed(self):
        expected_source_sha = 'a' * 40
        moved_branch_sha = 'b' * 40

        verify_qualification_source.verify_source_sha(
            expected_source_sha,
            expected_source_sha,
        )
        with self.assertRaisesRegex(
            verify_qualification_source.BuildError,
            'qualification source SHA mismatch',
        ):
            verify_qualification_source.verify_source_sha(
                expected_source_sha,
                moved_branch_sha,
            )

        workflow = (ROOT / '.github/workflows/qualify.yml').read_text()
        self.assertIn('expected_source_sha:', workflow)
        self.assertIn('name: Verify expected source SHA', workflow)
        self.assertIn(
            'python3 scripts/verify_qualification_source.py "$EXPECTED_SOURCE_SHA" "$GITHUB_SHA"',
            workflow,
        )
        self.assertLess(
            workflow.index('name: Verify expected source SHA'),
            workflow.index('name: Select browser qualification plan'),
        )
        check_policy.check_qualification_source_binding()

    def test_full_qualification_supports_upstream_and_patch_release_modes(self):
        workflow = (ROOT / '.github/workflows/qualify.yml').read_text()
        self.assertIn('release_mode:', workflow)
        self.assertIn('default: none', workflow)
        self.assertIn("inputs.browser == 'all'", workflow)
        self.assertIn("inputs.release_mode != 'none'", workflow)
        self.assertIn('upstream)', workflow)
        self.assertIn('patch)', workflow)
        self.assertIn('matching-refs/tags/v${version}-web.', workflow)
        self.assertIn('release_tag="$latest_tag"', workflow)
        self.assertIn('retry_tag="$release_tag"', workflow)
        self.assertIn("needs.browser-plan.outputs.retry_tag == ''", workflow)
        self.assertIn('recover-publication:', workflow)
        self.assertIn('name: release-qualification', workflow)
        self.assertIn('releaseMode: $releaseMode', workflow)
        self.assertIn('expectedSourceSha: $expectedSourceSha', workflow)
        self.assertIn('distribution: $distribution', workflow)
        self.assertIn('name: qualification-provenance', workflow)
        self.assertIn('qualification-provenance.sigstore.json', workflow)
        self.assertIn('gh workflow run release.yml', workflow)
        self.assertIn('qualification_run_id="$GITHUB_RUN_ID"', workflow)
        self.assertIn('release_tag: ${{ steps.plan.outputs.release_tag }}', workflow)
        self.assertIn('retry_tag: ${{ steps.plan.outputs.retry_tag }}', workflow)
        self.assertIn('actions/workflows/release.yml/runs', workflow)
        self.assertIn('-f head_sha="$GITHUB_SHA"', workflow)
        self.assertIn('.head_branch == $tag', workflow)
        self.assertIn('.head_sha == $sha', workflow)
        self.assertIn('gh workflow run recover-release-publication.yml', workflow)
        self.assertIn('-f release_run_id="$release_run_id"', workflow)
        self.assertIn('-f channel=all', workflow)
        self.assertNotIn('publication is complete', workflow)
        self.assertNotIn('gh release view "$RELEASE_TAG"', workflow)
        check_policy.check_qualification_release_retry_policy()

        patch = (ROOT / '.github/workflows/patch-release.yml').read_text()
        self.assertIn('name: Patch release', patch)
        self.assertIn('No v${version}-web.0 exists', patch)
        self.assertIn("intent='retry existing immutable publication'", patch)
        self.assertIn('target_tag="$latest_tag"', patch)
        self.assertNotIn('already points to current master', patch)
        self.assertIn('-f browser=all', patch)
        self.assertIn('-f release_mode=patch', patch)
        self.assertIn('contents/upstream.lock.json?ref=$master_sha', patch)
        self.assertIn('SOURCE_SHA: ${{ steps.release.outputs.source_sha }}', patch)
        self.assertIn('-f expected_source_sha="$SOURCE_SHA"', patch)

        release = (ROOT / '.github/workflows/release.yml').read_text()
        self.assertIn('.expectedSourceSha == $commit', release)

    def test_release_binds_qualified_distribution_before_reproducibility(self):
        workflow = (ROOT / '.github/workflows/release.yml').read_text()
        self.assertIn('Verify qualification provenance', workflow)
        self.assertIn('qualification-provenance.sigstore.json', workflow)
        self.assertIn('qualified-tree-sha256', workflow)
        self.assertIn('scripts/verify_dist_identity.py', workflow)
        self.assertIn('scripts/compare_dist.py reference-dist dist', workflow)

        identity_gate = workflow.index('Verify qualified distribution identity')
        archive = workflow.index('Archive canonical static distribution')
        reproducibility = workflow.index('Independent clean rebuild')
        self.assertLess(identity_gate, archive)
        self.assertLess(archive, reproducibility)

    def test_independent_sbom_cross_check_is_release_gating(self):
        action = (ROOT / '.github/actions/independent-sbom/action.yml').read_text()
        self.assertIn(
            'anchore/sbom-action@3ad7283483fc7af8ff2b4ea19663c2d5ca935e26',
            action,
        )
        self.assertIn('syft-version: v1.48.0', action)
        self.assertIn('config: security/syft.yaml', action)
        self.assertIn("upload-artifact: 'false'", action)
        self.assertIn("upload-release-assets: 'false'", action)

        syft_config = (ROOT / 'security/syft.yaml').read_text()
        self.assertIn('- +javascript-package-cataloger', syft_config)

        policy = json.loads((ROOT / 'security/sbom-comparison-policy.json').read_text())
        self.assertEqual(policy['scanner'], {'name': 'syft', 'version': '1.48.0'})
        exceptions = policy['exceptions']
        self.assertEqual(len(exceptions), 26)
        self.assertTrue(
            all(
                item['direction'] == 'missingFromIndependent'
                and set(item['match']) == {'purl', 'path'}
                for item in exceptions
            )
        )

        qualify = (ROOT / '.github/workflows/qualify.yml').read_text()
        release = (ROOT / '.github/workflows/release.yml').read_text()
        for workflow in (qualify, release):
            self.assertIn('uses: ./.github/actions/independent-sbom', workflow)
            self.assertIn('output-file: .work/independent-sbom.cdx.json', workflow)

        self.assertIn("needs.browser-plan.outputs.level == 'artifact' ||", qualify)
        self.assertIn(
            'needs: [browser-plan, release-metadata, build, browser, production-serving, package]',
            qualify,
        )
        self.assertIn('SERVING_RESULT: ${{ needs.production-serving.result }}', qualify)
        self.assertIn('PACKAGE_RESULT: ${{ needs.package.result }}', qualify)
        self.assertIn('"$PACKAGE_RESULT" != success', qualify)

        attest_block = qualify.split('  attest:\n', 1)[1].split('  release:\n', 1)[0]
        self.assertIn("if: github.event_name != 'pull_request'", attest_block)

        package_source = (ROOT / 'scripts/package_release.py').read_text()
        self.assertIn('compare_sbom_inventory.compare_files(', package_source)
        self.assertIn("'independent-component-inventory.json'", package_source)
        self.assertIn("'sbom-comparison.json'", package_source)

        verifier = (ROOT / 'scripts/verify_release.py').read_text()
        self.assertIn('verify_independent_sbom_evidence(directory)', verifier)
        self.assertIn("comparison.get('status') == 'pass'", verifier)
        check_policy.check_independent_sbom_policy()

    def test_scorecard_sensitive_permissions_are_job_scoped(self):
        for path in (
            '.github/workflows/patch-release.yml',
            '.github/workflows/upstream-qualification.yml',
        ):
            workflow = (ROOT / path).read_text()
            header, jobs = workflow.split('\njobs:\n', 1)
            self.assertNotIn('actions: write', header)
            self.assertIn('contents: read', header)
            self.assertIn('permissions:\n      actions: write\n      contents: read', jobs)

    def test_reuse_ci_dependency_is_digest_pinned(self):
        tooling = (ROOT / '.github/actions/tooling-checks/action.yml').read_text()
        self.assertNotIn("pip install --disable-pip-version-check 'reuse==", tooling)
        self.assertIn(
            'docker://fsfe/reuse:6.2.0@sha256:'
            '85462a75c0f8efda09ddd190b92816b70e7662577c8427429e11e1b9f25a992e',
            tooling,
        )

    def test_repository_configuration_is_valid(self):
        validate_config.validate_all()

    def test_release_tag_contract_supports_patch_revisions(self):
        import check_release_tag

        lock = {'tag': '1.139.1'}
        self.assertEqual(check_release_tag.expected_release_tag(lock), 'v1.139.1-web.0')
        self.assertEqual(check_release_tag.expected_release_tag(lock, 3), 'v1.139.1-web.3')
        self.assertEqual(check_release_tag.release_revision(lock, 'v1.139.1-web.0'), 0)
        self.assertEqual(check_release_tag.release_revision(lock, 'v1.139.1-web.7'), 7)
        self.assertEqual(
            package_release.package_version(lock, 'v1.139.1-web.2'),
            '1.139.1-web.2',
        )
        with self.assertRaises(check_release_tag.BuildError):
            check_release_tag.release_revision(lock, 'v1.139.1-web.01')
        with self.assertRaises(check_release_tag.BuildError):
            check_release_tag.release_revision(lock, 'v1.140.0-web.0')

    def test_archives_are_deterministic(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            src = base / 'src'
            src.mkdir()
            (src / 'a.txt').write_text('a\n')
            (src / 'b').mkdir()
            (src / 'b/x.txt').write_text('x\n')
            a, b = base / 'a.tar.gz', base / 'b.tar.gz'
            za, zb = base / 'a.zip', base / 'b.zip'
            package_release.build_tar(src, a, 1790307657)
            package_release.build_tar(src, b, 1790307657)
            package_release.build_zip(src, za, 1790307657)
            package_release.build_zip(src, zb, 1790307657)
            self.assertEqual(
                hashlib.sha256(a.read_bytes()).digest(), hashlib.sha256(b.read_bytes()).digest()
            )
            self.assertEqual(
                hashlib.sha256(za.read_bytes()).digest(), hashlib.sha256(zb.read_bytes()).digest()
            )

    def test_distribution_comparison_detects_drift(self):
        import compare_dist

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            reference = root / 'reference'
            candidate = root / 'candidate'
            for directory in (reference, candidate):
                directory.mkdir()
                (directory / 'index.html').write_text('ok\\n')
                (directory / 'asset.js').write_text('same\\n')
            digest, count = compare_dist.compare_distributions(reference, candidate)
            self.assertRegex(digest, r'^[0-9a-f]{64}$')
            self.assertEqual(count, 2)
            (candidate / 'asset.js').write_text('changed\\n')
            with self.assertRaises(compare_dist.BuildError):
                compare_dist.compare_distributions(reference, candidate)

    def test_release_distribution_identity_rejects_changed_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            dist = Path(td) / 'dist'
            dist.mkdir()
            (dist / 'index.html').write_text('ok\n')
            (dist / 'asset.js').write_text('qualified\n')
            expected_sha256, expected_count = package_release.distribution_tree_digest(dist)

            self.assertEqual(
                verify_dist_identity.verify_distribution_identity(
                    dist,
                    expected_sha256=expected_sha256,
                    expected_file_count=expected_count,
                ),
                (expected_sha256, expected_count),
            )

            (dist / 'asset.js').write_text('released\n')
            with self.assertRaises(verify_dist_identity.BuildError):
                verify_dist_identity.verify_distribution_identity(
                    dist,
                    expected_sha256=expected_sha256,
                    expected_file_count=expected_count,
                )

    def test_distribution_tree_digest_is_deterministic(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / 'a.txt').write_text('a\n')
            nested = root / 'nested'
            nested.mkdir()
            (nested / 'b.txt').write_text('b\n')
            first, first_count = package_release.distribution_tree_digest(root)
            second, second_count = package_release.distribution_tree_digest(root)
            self.assertEqual(first, second)
            self.assertEqual(first_count, 2)
            self.assertEqual(second_count, 2)
            (nested / 'b.txt').write_text('changed\n')
            changed, changed_count = package_release.distribution_tree_digest(root)
            self.assertNotEqual(first, changed)
            self.assertEqual(changed_count, 2)

    def test_runtime_metadata_and_sbom_cover_shipped_components(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dist = root / 'dist'
            npm = dist / 'node_modules/@scope/pkg'
            npm.mkdir(parents=True)
            (npm / 'index.js').write_text('export default 1;\n')
            extension = dist / 'extensions/demo'
            extension.mkdir(parents=True)
            (extension / 'extension.js').write_text('module.exports = {};\n')
            (extension / 'package.json').write_text(
                json.dumps(
                    {
                        'publisher': 'demo',
                        'name': 'fixture',
                        'version': '1.2.3',
                        'license': 'MIT',
                        'browser': './extension.js',
                    }
                )
            )
            server = extension / 'server'
            server.mkdir()
            (server / 'server.js').write_text('module.exports = {};\n')
            (server / 'package.json').write_text(
                json.dumps(
                    {
                        'name': 'fixture-language-server',
                        'version': '2.3.4',
                        'license': 'BSD-3-Clause',
                    }
                )
            )
            lock = {
                'lockfileVersion': 3,
                'packages': {
                    'node_modules/@scope/pkg': {
                        'version': '4.5.6',
                        'license': 'Apache-2.0',
                        'integrity': 'sha512-fixture',
                    },
                },
            }
            upstream = {
                'repository': 'https://github.com/microsoft/vscode.git',
                'tag': '1.139.1',
                'commit': '0' * 40,
            }

            metadata = generate_runtime_metadata.build_runtime_metadata(dist, lock, upstream)
            npm_metadata = {item['name']: item for item in metadata['npm']}
            self.assertEqual(npm_metadata['@scope/pkg']['version'], '4.5.6')
            self.assertEqual(npm_metadata['fixture-language-server']['version'], '2.3.4')
            self.assertEqual(
                npm_metadata['fixture-language-server']['source'],
                'extension-package-json',
            )
            self.assertEqual(metadata['extensions'][0]['id'], 'demo.fixture')

            bom = generate_sbom.build_sbom(
                dist=dist,
                metadata=metadata,
                version='1.139.1-web.0',
                project_commit='a' * 40,
                upstream=upstream,
                distribution_tree_sha256='b' * 64,
            )
            repeated = generate_sbom.build_sbom(
                dist=dist,
                metadata=metadata,
                version='1.139.1-web.0',
                project_commit='a' * 40,
                upstream=upstream,
                distribution_tree_sha256='b' * 64,
            )
            self.assertEqual(bom, repeated)
            self.assertEqual(bom['bomFormat'], 'CycloneDX')
            self.assertEqual(bom['specVersion'], '1.7')
            refs = {component['bom-ref'] for component in bom['components']}
            self.assertIn('pkg:npm/%40scope/pkg@4.5.6', refs)
            self.assertIn('pkg:npm/fixture-language-server@2.3.4', refs)
            self.assertIn('vscode-extension:demo.fixture@1.2.3', refs)
            self.assertNotIn('timestamp', bom['metadata'])

            inventory = generate_license_inventory.build_license_inventory(
                metadata=metadata,
                version='1.139.1-web.0',
                project_commit='a' * 40,
                upstream=upstream,
            )
            inventory_refs = {component['bomRef'] for component in inventory['components']}
            self.assertEqual(
                inventory_refs,
                {bom['metadata']['component']['bom-ref']}
                | {component['bom-ref'] for component in bom['components']},
            )
            licenses = {
                component['bomRef']: component['declaredLicense']
                for component in inventory['components']
            }
            self.assertEqual(licenses['pkg:npm/%40scope/pkg@4.5.6'], 'Apache-2.0')
            self.assertEqual(
                licenses['pkg:npm/fixture-language-server@2.3.4'],
                'BSD-3-Clause',
            )
            self.assertEqual(licenses['vscode-extension:demo.fixture@1.2.3'], 'MIT')
            self.assertEqual(inventory['summary']['noAssertion'], 0)
            self.assertEqual(generate_license_inventory.declared_license(None), 'NOASSERTION')

    def test_extension_index_only_marks_browser_extensions(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            web = d / 'extensions/web'
            web.mkdir(parents=True)
            (web / 'package.json').write_text(
                json.dumps(
                    {'publisher': 'p', 'name': 'web', 'version': '1', 'browser': 'dist/web.js'}
                )
            )
            node = d / 'extensions/node'
            node.mkdir()
            (node / 'package.json').write_text(
                json.dumps(
                    {'publisher': 'p', 'name': 'node', 'version': '1', 'main': 'dist/node.js'}
                )
            )
            values = {
                x['id']: x['browserCompatible']
                for x in extensions_index.build_extension_index(d)['extensions']
            }
            self.assertEqual(values, {'p.node': False, 'p.web': True})

    def test_local_vsix_lock_validation_and_installation(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            vendor = root / 'vendor'
            vendor.mkdir()
            vsix = vendor / 'fixture.vsix'
            manifest = {
                'publisher': 'fixture',
                'name': 'browser',
                'version': '1.2.3',
                'license': 'MIT',
                'browser': './extension.js',
            }
            with zipfile.ZipFile(vsix, 'w') as archive:
                archive.writestr('extension/package.json', json.dumps(manifest))
                archive.writestr('extension/extension.js', 'exports.activate = () => {};\n')
            digest = hashlib.sha256(vsix.read_bytes()).hexdigest()
            lock_path = root / 'extensions.lock.json'
            lock_path.write_text(
                json.dumps(
                    {
                        'schemaVersion': 1,
                        'extensions': [
                            {
                                'id': 'fixture.browser',
                                'version': '1.2.3',
                                'sha256': digest,
                                'license': 'MIT',
                                'source': {'type': 'local-vsix', 'path': 'vendor/fixture.vsix'},
                            }
                        ],
                    }
                )
            )
            source_policy_path = root / 'source-policy.json'
            source_policy_path.write_text(
                json.dumps(
                    {
                        'schemaVersion': 1,
                        'allowedOpenVsxRegistries': ['https://open-vsx.org'],
                        'allowedOpenVsxDownloadOrigins': [
                            'https://open-vsx.org',
                            'https://openvsx.eclipsecontent.org',
                        ],
                    }
                )
            )
            dist = root / 'dist'
            dist.mkdir()
            installed = extension_lock.install_locked_extensions(
                dist,
                lock_path,
                root=root,
                source_policy_path=source_policy_path,
            )
            self.assertEqual(installed[0]['id'], 'fixture.browser')
            self.assertTrue((dist / 'extensions/fixture.browser/extension.js').is_file())
            index = extensions_index.build_extension_index(dist)
            self.assertTrue(index['extensions'][0]['browserCompatible'])

    def test_local_vsix_rejects_digest_mismatch_and_node_only_extension(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            vsix = root / 'fixture.vsix'
            manifest = {
                'publisher': 'fixture',
                'name': 'node',
                'version': '1.0.0',
                'main': './extension.js',
            }
            with zipfile.ZipFile(vsix, 'w') as archive:
                archive.writestr('extension/package.json', json.dumps(manifest))
                archive.writestr('extension/extension.js', 'module.exports = {};\n')
            digest = hashlib.sha256(vsix.read_bytes()).hexdigest()
            entry = {
                'id': 'fixture.node',
                'version': '1.0.0',
                'sha256': digest,
                'source': {'type': 'local-vsix', 'path': 'fixture.vsix'},
                'license': None,
            }
            with self.assertRaises(extension_lock.BuildError):
                extension_lock.validate_local_vsix(entry, root=root)
            entry['sha256'] = '0' * 64
            with self.assertRaises(extension_lock.BuildError):
                extension_lock.validate_local_vsix(entry, root=root)

    def test_local_vsix_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            vsix = root / 'fixture.vsix'
            with zipfile.ZipFile(vsix, 'w') as archive:
                archive.writestr('../escape.txt', 'bad')
                archive.writestr(
                    'extension/package.json',
                    json.dumps(
                        {
                            'publisher': 'fixture',
                            'name': 'bad',
                            'version': '1.0.0',
                            'browser': './extension.js',
                        }
                    ),
                )
                archive.writestr('extension/extension.js', '')
            entry = {
                'id': 'fixture.bad',
                'version': '1.0.0',
                'sha256': hashlib.sha256(vsix.read_bytes()).hexdigest(),
                'source': {'type': 'local-vsix', 'path': 'fixture.vsix'},
                'license': None,
            }
            with self.assertRaises(extension_lock.BuildError):
                extension_lock.validate_local_vsix(entry, root=root)

    def test_local_vsix_rejects_absolute_paths_symlinks_and_windows_paths(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            absolute = root / 'absolute.vsix'
            with zipfile.ZipFile(absolute, 'w') as archive:
                archive.writestr('/escape.txt', 'bad')
            entry = {
                'id': 'fixture.absolute',
                'version': '1.0.0',
                'sha256': hashlib.sha256(absolute.read_bytes()).hexdigest(),
                'source': {'type': 'local-vsix', 'path': 'absolute.vsix'},
                'license': None,
            }
            with self.assertRaisesRegex(extension_lock.BuildError, 'absolute path'):
                extension_lock.validate_local_vsix(entry, root=root)

            symlink = root / 'symlink.vsix'
            link = zipfile.ZipInfo('extension/link')
            link.create_system = 3
            link.external_attr = 0o120777 << 16
            with zipfile.ZipFile(symlink, 'w') as archive:
                archive.writestr(link, 'extension.js')
            entry['id'] = 'fixture.symlink'
            entry['sha256'] = hashlib.sha256(symlink.read_bytes()).hexdigest()
            entry['source'] = {'type': 'local-vsix', 'path': 'symlink.vsix'}
            with self.assertRaisesRegex(extension_lock.BuildError, 'symlink'):
                extension_lock.validate_local_vsix(entry, root=root)

            backslash = root / 'backslash.vsix'
            with zipfile.ZipFile(backslash, 'w') as archive:
                archive.writestr('extension\\..\\escape.txt', 'bad')
            entry['id'] = 'fixture.backslash'
            entry['sha256'] = hashlib.sha256(backslash.read_bytes()).hexdigest()
            entry['source'] = {'type': 'local-vsix', 'path': backslash.name}
            with self.assertRaisesRegex(extension_lock.BuildError, 'backslash path'):
                extension_lock.validate_local_vsix(entry, root=root)

            drive = root / 'drive.vsix'
            with zipfile.ZipFile(drive, 'w') as archive:
                archive.writestr('C:/escape.txt', 'bad')
            entry['id'] = 'fixture.drive'
            entry['sha256'] = hashlib.sha256(drive.read_bytes()).hexdigest()
            entry['source'] = {'type': 'local-vsix', 'path': drive.name}
            with self.assertRaisesRegex(extension_lock.BuildError, 'drive path'):
                extension_lock.validate_local_vsix(entry, root=root)

    def test_local_vsix_archive_limits_fail_closed(self):
        manifest = {
            'publisher': 'fixture',
            'name': 'bounded',
            'version': '1.0.0',
            'browser': './extension.js',
        }

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)

            entry_count = root / 'entry-count.vsix'
            with zipfile.ZipFile(entry_count, 'w') as archive:
                archive.writestr('extension/package.json', json.dumps(manifest))
                archive.writestr('extension/extension.js', 'ok')
            entry = {
                'id': 'fixture.bounded',
                'version': '1.0.0',
                'sha256': hashlib.sha256(entry_count.read_bytes()).hexdigest(),
                'source': {'type': 'local-vsix', 'path': entry_count.name},
                'license': None,
            }
            with mock.patch.object(extension_lock, 'MAX_ARCHIVE_ENTRIES', 1):
                with self.assertRaisesRegex(extension_lock.BuildError, 'too many entries'):
                    extension_lock.validate_local_vsix(entry, root=root)

            large_file = root / 'large-file.vsix'
            with zipfile.ZipFile(large_file, 'w') as archive:
                archive.writestr('extension/package.json', json.dumps(manifest))
                archive.writestr('extension/extension.js', 'x' * 1024)
            entry['sha256'] = hashlib.sha256(large_file.read_bytes()).hexdigest()
            entry['source'] = {'type': 'local-vsix', 'path': large_file.name}
            with mock.patch.object(extension_lock, 'MAX_ARCHIVE_FILE_SIZE', 512):
                with self.assertRaisesRegex(extension_lock.BuildError, 'entry is too large'):
                    extension_lock.validate_local_vsix(entry, root=root)

            large_total = root / 'large-total.vsix'
            with zipfile.ZipFile(large_total, 'w') as archive:
                archive.writestr('extension/package.json', json.dumps(manifest))
                archive.writestr('extension/extension.js', 'x' * 256)
            entry['sha256'] = hashlib.sha256(large_total.read_bytes()).hexdigest()
            entry['source'] = {'type': 'local-vsix', 'path': large_total.name}
            with mock.patch.object(extension_lock, 'MAX_ARCHIVE_TOTAL_SIZE', 256):
                with self.assertRaisesRegex(
                    extension_lock.BuildError, 'expanded size exceeds limit'
                ):
                    extension_lock.validate_local_vsix(entry, root=root)

            bomb = root / 'bomb.vsix'
            with zipfile.ZipFile(bomb, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr('extension/package.json', json.dumps(manifest))
                archive.writestr('extension/extension.js', 'A' * 4096)
            entry['sha256'] = hashlib.sha256(bomb.read_bytes()).hexdigest()
            entry['source'] = {'type': 'local-vsix', 'path': bomb.name}
            with (
                mock.patch.object(extension_lock, 'COMPRESSION_RATIO_MIN_FILE_SIZE', 1024),
                mock.patch.object(extension_lock, 'MAX_ARCHIVE_COMPRESSION_RATIO', 2),
            ):
                with self.assertRaisesRegex(extension_lock.BuildError, 'compression ratio'):
                    extension_lock.validate_local_vsix(entry, root=root)

    def test_vsix_digest_is_verified_before_archive_inspection(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            vsix = root / 'not-a-zip.vsix'
            vsix.write_bytes(b'not a zip archive')
            entry = {
                'id': 'fixture.invalid',
                'version': '1.0.0',
                'sha256': '0' * 64,
                'source': {'type': 'local-vsix', 'path': vsix.name},
                'license': None,
            }
            with self.assertRaisesRegex(extension_lock.BuildError, 'SHA-256 mismatch'):
                extension_lock.validate_local_vsix(entry, root=root)

    def test_open_vsx_source_policy_is_explicit_and_redirects_fail_closed(self):
        policy = {
            'schemaVersion': 1,
            'allowedOpenVsxRegistries': ['https://open-vsx.org'],
            'allowedOpenVsxDownloadOrigins': [
                'https://open-vsx.org',
                'https://openvsx.eclipsecontent.org',
            ],
        }
        allowed = {
            'id': 'demo.fixture',
            'version': '1.2.3',
            'sha256': '0' * 64,
            'license': 'MIT',
            'source': {'type': 'open-vsx', 'registry': 'https://open-vsx.org'},
        }
        extension_lock.enforce_source_policy(allowed, policy)

        denied = dict(allowed)
        denied['source'] = {'type': 'open-vsx', 'registry': 'https://registry.example.com'}
        with self.assertRaisesRegex(extension_lock.BuildError, 'not allowed'):
            extension_lock.enforce_source_policy(denied, policy)

        handler = extension_lock._SourcePolicyRedirectHandler(
            {'https://open-vsx.org', 'https://openvsx.eclipsecontent.org'}
        )
        request = extension_lock.urllib.request.Request(
            'https://open-vsx.org/api/demo/fixture/1.2.3/file/demo.fixture-1.2.3.vsix'
        )
        redirected = handler.redirect_request(
            request,
            None,
            302,
            'Found',
            {},
            'https://openvsx.eclipsecontent.org/file/demo.fixture-1.2.3.vsix',
        )
        self.assertIsNotNone(redirected)
        assert redirected is not None
        self.assertEqual(
            extension_lock._url_origin(redirected.full_url, 'test redirect'),
            'https://openvsx.eclipsecontent.org',
        )

        with self.assertRaisesRegex(extension_lock.BuildError, 'redirect target is not allowed'):
            handler.redirect_request(
                request,
                None,
                302,
                'Found',
                {},
                'https://registry.example.com/redirected.vsix',
            )

    def test_open_vsx_download_stream_is_bounded_before_writes(self):
        source = io.BytesIO(b'0123456789')
        destination = io.BytesIO()
        with (
            mock.patch.object(extension_lock, 'MAX_VSIX_ARCHIVE_SIZE', 8),
            mock.patch.object(extension_lock, 'DOWNLOAD_CHUNK_SIZE', 4),
        ):
            with self.assertRaisesRegex(extension_lock.BuildError, 'download exceeds limit'):
                extension_lock._copy_download_bounded(source, destination)
        self.assertEqual(destination.getvalue(), b'01234567')

    def test_open_vsx_registry_rejects_non_origin_urls(self):
        with tempfile.TemporaryDirectory() as td:
            lock_path = Path(td) / 'extensions.lock.json'
            lock_path.write_text(
                json.dumps(
                    {
                        'schemaVersion': 1,
                        'extensions': [
                            {
                                'id': 'demo.fixture',
                                'version': '1.2.3',
                                'sha256': '0' * 64,
                                'source': {
                                    'type': 'open-vsx',
                                    'registry': 'https://user@open-vsx.org/base?x=1',
                                },
                            }
                        ],
                    }
                )
            )
            with self.assertRaises(extension_lock.BuildError):
                extension_lock.load_extension_lock(lock_path)

    def test_open_vsx_source_is_exact_and_license_gated(self):
        entry = {
            'id': 'demo.fixture',
            'version': '1.2.3',
            'sha256': '0' * 64,
            'license': 'MIT',
            'source': {'type': 'open-vsx', 'registry': 'https://open-vsx.org'},
        }
        self.assertEqual(
            extension_lock.open_vsx_download_url(entry),
            'https://open-vsx.org/api/demo/fixture/1.2.3/file/demo.fixture-1.2.3.vsix',
        )
        policy = {
            'schemaVersion': 1,
            'requireDeclared': True,
            'allowed': ['MIT'],
            'denied': ['Proprietary'],
            'overrides': {},
        }
        self.assertEqual(
            extension_lock.enforce_license_policy(entry, {'license': 'MIT'}, policy),
            'MIT',
        )
        denied = dict(entry)
        denied['license'] = 'Proprietary'
        with self.assertRaises(extension_lock.BuildError):
            extension_lock.enforce_license_policy(
                denied,
                {'license': 'Proprietary'},
                policy,
            )

        with tempfile.TemporaryDirectory() as td:
            lock_path = Path(td) / 'extensions.lock.json'
            lock_path.write_text(
                json.dumps(
                    {
                        'schemaVersion': 1,
                        'extensions': [entry],
                    }
                )
            )
            loaded = extension_lock.load_extension_lock(lock_path)
            self.assertEqual(loaded['extensions'][0]['source']['type'], 'open-vsx')
            self.assertEqual(
                loaded['extensions'][0]['source']['registry'],
                'https://open-vsx.org',
            )

    def test_qualification_extension_is_browser_compatible(self):
        fixture = ROOT / 'tests/fixtures/web-extension'
        manifest = json.loads((fixture / 'package.json').read_text())
        self.assertEqual(manifest['browser'], './extension.js')
        self.assertEqual(manifest['engines']['vscode'], '^1.139.0')
        self.assertIn('codeOssStaticWebTest.markReady', manifest['activationEvents'][0])
        self.assertIn('codeOssStaticWebTest.readMarker', manifest['activationEvents'][1])
        self.assertIn('codeOssStaticWebTest.writeStorageFile', manifest['activationEvents'][2])
        self.assertIn('codeOssStaticWebTest.readStorageFile', manifest['activationEvents'][3])
        self.assertIn('codeOssStaticWebTest.probeLanguageService', manifest['activationEvents'][4])
        source = (fixture / 'extension.js').read_text()
        self.assertIn("return context.globalState.get('qualificationMarker', 'missing')", source)
        self.assertIn('vscode.workspace.fs.writeFile', source)
        self.assertIn("'vscode.executeCompletionItemProvider'", source)
        self.assertTrue((fixture / 'extension.js').is_file())

    def test_playwright_suite_uses_subpath_and_blocks_service_workers(self):
        helpers = (ROOT / 'tests/e2e/helpers.cjs').read_text()
        self.assertIn("commands.executeCommand('workbench.action.showCommands')", helpers)
        config = (ROOT / 'tests/e2e/playwright.config.cjs').read_text()
        self.assertIn('/code-oss-web/', config)
        self.assertIn("serviceWorkers: 'block'", config)
        self.assertIn('CODE_OSS_STATIC_WEB_CHROMIUM_EXECUTABLE', config)
        network = (ROOT / 'tests/e2e/network-policy.spec.cjs').read_text()
        self.assertIn('unexpectedRequests', network)
        self.assertIn('webSockets', network)

    def test_action_policy_accepts_digest_pinned_container_actions(self):
        check_policy.check_actions()
        self.assertTrue(
            check_policy.DOCKER_DIGEST.fullmatch(
                'sha256:85462a75c0f8efda09ddd190b92816b70e7662577c8427429e11e1b9f25a992e'
            )
        )
        self.assertIsNone(check_policy.DOCKER_DIGEST.fullmatch('sha256:not-a-digest'))

    def test_toolchain_versions_are_canonical(self):
        manifest = json.loads((ROOT / '.github/toolchain-versions.json').read_text())
        self.assertEqual(manifest['schemaVersion'], 1)
        self.assertRegex(manifest['node'], r'^\d+\.\d+\.\d+$')
        self.assertRegex(manifest['python'], r'^\d+\.\d+\.\d+$')
        check_policy.check_toolchain_versions()

        qualification = (ROOT / '.github/workflows/qualify.yml').read_text()
        release = (ROOT / '.github/workflows/release.yml').read_text()
        package_source = (ROOT / 'scripts/package_release.py').read_text()
        self.assertIn('steps.toolchain.outputs.node-version', qualification)
        self.assertIn('steps.toolchain.outputs.python-version', qualification)
        self.assertIn('toolchain: $toolchain', qualification)
        self.assertIn('.toolchain == $toolchain', release)
        self.assertIn("'toolchainVersions': input_digest", package_source)
        self.assertIn("'toolchain': {", package_source)

    def test_toolchain_policy_rejects_hard_coded_workflow_versions(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            workflows = root / '.github/workflows'
            action_dir = root / '.github/actions/setup-toolchain'
            workflows.mkdir(parents=True)
            action_dir.mkdir(parents=True)
            (root / '.github/toolchain-versions.json').write_text(
                json.dumps({'schemaVersion': 1, 'node': '20.1.0', 'python': '3.12.1'})
            )
            (action_dir / 'action.yml').write_text(
                """manifest="$GITHUB_ACTION_PATH/../../toolchain-versions.json"
node="$(jq -er '.node' "$manifest")"
python="$(jq -er '.python' "$manifest")"
node-version: ${{ steps.versions.outputs.node }}
python-version: ${{ steps.versions.outputs.python }}
"""
            )
            (workflows / 'bad.yaml').write_text(
                'jobs:\n  test:\n    steps:\n'
                '      - uses: ./.github/actions/setup-toolchain\n'
                '      - name: Restore cache\n'
                '        env:\n          CACHE_KEY: python-3.13\n'
                '        run: echo "$CACHE_KEY"\n'
            )
            original_root = check_policy.ROOT
            try:
                check_policy.ROOT = root
                with self.assertRaises(check_policy.BuildError):
                    check_policy.check_toolchain_versions()
            finally:
                check_policy.ROOT = original_root

    def test_yaml_policy_scans_workflows_and_actions(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            workflows = root / '.github/workflows'
            action_dir = root / '.github/actions/example'
            workflows.mkdir(parents=True)
            action_dir.mkdir(parents=True)
            (root / 'build.sh').write_text('')
            (root / 'package.sh').write_text('')

            workflow = workflows / 'example.yaml'
            action = action_dir / 'action.yaml'
            workflow.write_text('jobs:\n  test:\n    steps:\n      - run: npx unsafe-tool\n')
            action.write_text('runs:\n  using: composite\n  steps: []\n')

            original_root = check_policy.ROOT
            try:
                check_policy.ROOT = root
                with self.assertRaises(check_policy.BuildError):
                    check_policy.check_forbidden_execution_patterns()

                workflow.write_text('jobs:\n  test:\n    steps: []\n')
                action.write_text(
                    'runs:\n  using: composite\n  steps:\n    - uses: example/action@main\n'
                )
                with self.assertRaises(check_policy.BuildError):
                    check_policy.check_actions()
            finally:
                check_policy.ROOT = original_root

    def test_build_jobs_are_unprivileged(self):
        check_policy.check_build_job_permissions()
        bad = """jobs:
  build:
    permissions:
      contents: write
      id-token: write
    steps:
      - uses: actions/checkout@0000000000000000000000000000000000000000
        with:
          persist-credentials: true
      - run: ./build.sh
"""
        with self.assertRaises(check_policy.BuildError):
            check_policy.check_build_job_block(ROOT / '.github/workflows/example.yml', 'build', bad)

    def test_attestation_jobs_are_isolated(self):
        check_policy.check_attestation_job_permissions()
        bad = """jobs:
  attest:
    permissions:
      contents: read
      id-token: write
      attestations: write
      artifact-metadata: write
    steps:
      - uses: actions/checkout@0000000000000000000000000000000000000000
      - uses: actions/attest@0000000000000000000000000000000000000000
      - run: ./build.sh
"""
        with self.assertRaises(check_policy.BuildError):
            check_policy.check_attestation_job_block(
                ROOT / '.github/workflows/example.yml',
                'attest',
                bad,
            )

    def test_publication_jobs_depend_on_attestation(self):
        check_policy.check_publication_job_permissions()
        bad = """jobs:
  publish:
    permissions:
      contents: write
    steps:
      - run: echo publish
"""
        with self.assertRaises(check_policy.BuildError):
            check_policy.check_publication_job_block(
                ROOT / '.github/workflows/example.yml',
                'publish',
                bad,
                'attest',
            )

    def test_repository_publication_scan_rejects_environment_bypass(self):
        bypass = """jobs:
  publish:
    needs: attest
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - run: echo publish
"""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            workflows = root / '.github/workflows'
            workflows.mkdir(parents=True)
            (workflows / 'bypass.yml').write_text(bypass)
            original_root = check_policy.ROOT
            try:
                check_policy.ROOT = root
                with self.assertRaises(check_policy.BuildError):
                    check_policy.check_publication_job_permissions()
            finally:
                check_policy.ROOT = original_root

    def test_release_publication_paths_use_protected_environment(self):
        workflow_path = ROOT / '.github/workflows/release.yml'
        check_policy.check_release_publication_boundaries(
            workflow_path,
            workflow_path.read_text(),
        )
        bypass = """jobs:
  github-release:
    needs: attest
    runs-on: ubuntu-latest
    environment: release
    permissions:
      contents: write
  pages:
    needs: attest
    runs-on: ubuntu-latest
    environment:
      name: github-pages
    permissions:
      pages: write
  oci:
    needs: attest
    runs-on: ubuntu-latest
    environment: release
    permissions:
      packages: write
"""
        with self.assertRaises(check_policy.BuildError):
            check_policy.check_release_publication_boundaries(
                ROOT / '.github/workflows/example.yml',
                bypass,
            )

    def test_ci_validates_pr_titles_and_avoids_redundant_branch_work(self):
        ci = (ROOT / '.github/workflows/ci.yml').read_text()
        qualify = (ROOT / '.github/workflows/qualify.yml').read_text()
        tooling = (ROOT / '.github/actions/tooling-checks/action.yml').read_text()

        ci_triggers = ci.split('on:\n', 1)[1].split('\nconcurrency:', 1)[0]
        qualify_triggers = qualify.split('on:\n', 1)[1].split('\nconcurrency:', 1)[0]
        self.assertNotIn('pull_request:', ci_triggers)
        self.assertIn('branches: [master, develop]', ci_triggers)
        self.assertIn('pull_request:', qualify_triggers)
        self.assertIn('types: [opened, synchronize, reopened, edited]', qualify_triggers)

        self.assertIn('uses: ./.github/actions/tooling-checks', ci)
        self.assertIn('uses: ./.github/actions/tooling-checks', qualify)
        self.assertIn('group: ci-', ci)
        self.assertIn('cancel-in-progress: true', ci)

        self.assertIn('name: Pull request title policy', tooling)
        self.assertIn("github.event_name == 'pull_request'", tooling)
        self.assertIn('github.event.pull_request.title', tooling)
        self.assertIn('name: Pull request commit message policy', tooling)
        self.assertIn('pulls/$PR_NUMBER/commits', tooling)
        self.assertIn('@base64', tooling)
        self.assertIn('encoded_messages="$(', tooling)
        self.assertIn('No pull request commits returned by GitHub API', tooling)
        self.assertIn('done <<< "$encoded_messages"', tooling)
        self.assertNotIn('done < <(', tooling)
        self.assertIn("github.event_name == 'push' &&", tooling)
        self.assertIn("startsWith(github.ref, 'refs/heads/')", tooling)
        self.assertIn(
            'github.ref_name != github.event.repository.default_branch',
            tooling,
        )
        self.assertNotIn('style-normalization', tooling)
        self.assertNotIn('Export normalization workspace', tooling)

    def test_github_actions_yaml_checker_covers_actions_and_yaml_extensions(self):
        checker = (ROOT / 'scripts/check_workflow_yaml.rb').read_text()
        self.assertIn("Dir['.github/workflows/*.yml']", checker)
        self.assertIn("Dir['.github/workflows/*.yaml']", checker)
        self.assertIn("Dir['.github/actions/**/action.yml']", checker)
        self.assertIn("Dir['.github/actions/**/action.yaml']", checker)

    def test_workflow_actions_are_commit_pinned(self):
        import re

        definitions = check_policy.action_definition_paths()
        for workflow in definitions:
            for line_number, line in enumerate(workflow.read_text().splitlines(), 1):
                match = re.search(r'uses:\s*[^@\s]+@([^\s#]+)', line)
                if match:
                    reference = match.group(1)
                    if 'uses: docker://' in line:
                        self.assertRegex(
                            reference,
                            r'^sha256:[0-9a-f]{64}$',
                            f'{workflow}:{line_number} must pin an immutable container digest',
                        )
                    else:
                        self.assertRegex(
                            reference,
                            r'^[0-9a-f]{40}$',
                            f'{workflow}:{line_number} must pin an immutable action commit',
                        )

    def test_canonical_distribution_artifacts_preserve_metadata(self):
        qualification = (ROOT / '.github/workflows/qualify.yml').read_text()
        release = (ROOT / '.github/workflows/release.yml').read_text()
        browser_action = (ROOT / '.github/actions/browser-qualification/action.yml').read_text()

        self.assertIn('tar -C dist -cf .work/static-dist.tar .', qualification)
        self.assertIn('path: .work/static-dist.tar', qualification)
        self.assertIn('tar -C dist -cf .work/release-static-dist.tar .', release)
        self.assertIn('path: .work/release-static-dist.tar', release)
        self.assertIn(
            'tar -C reference-dist -xf .work/release-static-dist/release-static-dist.tar',
            release,
        )
        self.assertIn(
            'tar -C dist -xf ".work/browser-dist/${{ inputs.distribution-artifact }}.tar"',
            browser_action,
        )

    def test_build_entrypoint_validates_configuration_before_build_work(self):
        build = (ROOT / 'scripts/build.py').read_text()

        self.assertIn("run([ROOT / 'scripts/validate_config.py'])", build)
        self.assertLess(
            build.index("run([ROOT / 'scripts/validate_config.py'])"),
            build.index("run([ROOT / 'scripts/fetch_upstream.py']"),
        )

    def test_independent_sbom_scan_is_fresh_for_current_distribution(self):
        package = (ROOT / 'package.sh').read_text()
        build = (ROOT / 'scripts/build.py').read_text()

        self.assertNotIn('if [[ ! -f "$independent_sbom" ]]', package)
        self.assertIn(
            'rm -f "$independent_sbom" "$independent_sbom_tmp"',
            package,
        )
        self.assertIn(
            'syft -c "$ROOT/security/syft.yaml" "dir:$ROOT/dist" '
            '-o "cyclonedx-json=$independent_sbom_tmp"',
            package,
        )
        self.assertIn(
            'mv "$independent_sbom_tmp" "$independent_sbom"',
            package,
        )
        self.assertLess(
            package.index('syft -c "$ROOT/security/syft.yaml"'),
            package.index('python3 "$ROOT/scripts/package_release.py"'),
        )

        self.assertIn(
            'independent_sbom.unlink(missing_ok=True)',
            build,
        )
        self.assertIn(
            'independent_sbom_tmp.unlink(missing_ok=True)',
            build,
        )
        self.assertLess(
            build.index('independent_sbom.unlink(missing_ok=True)'),
            build.index("run([ROOT / 'scripts/make_static.py'"),
        )

    def test_qualification_workflow_reuses_browser_action(self):
        workflow = (ROOT / '.github/workflows/qualify.yml').read_text()
        action = (ROOT / '.github/actions/browser-qualification/action.yml').read_text()
        self.assertRegex(
            workflow,
            r'actions/cache@[0-9a-f]{40}\s+# v[0-9]+',
        )
        self.assertIn('name: static-dist', workflow)
        self.assertIn('name: playwright-runtime', workflow)
        self.assertNotIn('name: qualification-harness', workflow)
        self.assertIn('name: playwright-browser-chromium', workflow)
        self.assertIn('browser-plan:', workflow)
        self.assertIn('browsers=\'["chromium"]\'', workflow)
        self.assertIn('browsers=\'["chromium","firefox","webkit"]\'', workflow)
        self.assertIn('scope=smoke', workflow)
        self.assertIn('matrix.browser', workflow)
        self.assertIn('uses: ./.github/actions/browser-qualification', workflow)
        self.assertNotIn('secondary-browsers:', workflow)
        self.assertIn("github.event_name != 'pull_request' ||", workflow)
        self.assertIn("needs.browser-plan.outputs.level == 'artifact' ||", workflow)
        self.assertIn('needs: [browser-plan, build, browser, package, attest]', workflow)
        self.assertIn('needs: package', workflow)
        self.assertIn('actions/attest@1e69f48acb82d1966a394da916b4c1698aa569d6', workflow)
        self.assertIn('subject-checksums: artifacts/SHA256SUMS', workflow)
        self.assertIn('sbom-path: artifacts/sbom.cdx.json', workflow)
        self.assertIn('scripts/run_e2e.py', action)
        self.assertIn('--grep-invert @extension', action)
        self.assertIn('--grep-invert "@extension|@quality"', action)
        self.assertIn('--grep @quality', action)
        self.assertIn('--grep @extension', action)
        self.assertIn('name: Quality baseline', action)
        self.assertIn('CODE_OSS_STATIC_WEB_QUALITY_REPORT', action)
        self.assertIn('.work/quality-metrics.json', action)
        self.assertIn('scripts/add_test_extension.py', action)
        boot_gate = action[
            action.index('    - name: Browser boot gate') : action.index(
                '    - name: Browser qualification'
            )
        ]
        self.assertNotIn("if: inputs.scope == 'smoke'", boot_gate)
        self.assertNotIn("if: inputs.scope == 'full'", boot_gate)
        self.assertIn('--retries=0', boot_gate)
        self.assertIn("if: inputs.scope == 'full'", action)
        self.assertIn('--reuse-upstream-build', workflow)

        extension_test = (ROOT / 'tests/e2e/extension-host.spec.cjs').read_text()
        self.assertIn('codeOssStaticWebTest.markReady', extension_test)
        self.assertIn('codeOssStaticWebTest.readMarker', extension_test)
        self.assertIn('global state persists across workbench reload', extension_test)
        self.assertIn("toBe('ready')", extension_test)
        self.assertIn("commands.executeCommand('workbench.action.reloadWindow')", extension_test)
        self.assertIn('browser filesystem persists across workbench reload', extension_test)
        self.assertIn('JavaScript language service returns completions', extension_test)

        quality_test = (ROOT / 'tests/e2e/quality-baseline.spec.cjs').read_text()
        self.assertIn('@quality performance and accessibility baseline', quality_test)
        self.assertIn('@quality failed-request metric counts HTTP error responses', quality_test)
        self.assertIn('response.status() >= 400', quality_test)
        self.assertIn("page.keyboard.press('F6')", quality_test)
        self.assertIn('staticTransferBytes', quality_test)
        quality_baseline = json.loads((ROOT / 'config/quality-baseline.json').read_text())
        self.assertEqual(quality_baseline['sampling']['samples'], 3)
        self.assertEqual(quality_baseline['source']['qualificationRunId'], 37136030149)
        baselines = [metric['baseline'] for metric in quality_baseline['metrics'].values()]
        self.assertNotIn(None, baselines)
        self.assertNotIn('consoleErrors', quality_baseline['metrics'])
        console_policy = quality_baseline['consoleErrorPolicy']
        self.assertEqual(console_policy['normalization'], 'strip-console-style-prefix')
        self.assertTrue(console_policy['requireAllToleratedObserved'])
        tolerated = console_policy['toleratedFingerprints']
        self.assertEqual(len(tolerated), 10)
        self.assertEqual(len(tolerated), len(set(tolerated)))
        self.assertTrue(all(item and item == item.strip() for item in tolerated))
        quality_console_policy = (ROOT / 'tests/e2e/quality-console-policy.cjs').read_text()
        self.assertIn('validateConsoleErrorPolicy(policy)', quality_console_policy)
        self.assertIn('must be unique', quality_console_policy)
        self.assertIn('unsupported console error normalization', quality_console_policy)
        self.assertEqual(
            quality_baseline['metrics']['distributionBytes']['baseline'],
            190626870,
        )
        self.assertEqual(
            quality_baseline['metrics']['javascriptBytes']['baseline'],
            131365205,
        )

        runner = (ROOT / 'scripts/run_e2e.py').read_text()
        self.assertIn('playwright-runtime', runner)
        self.assertIn('--base-url', runner)
        self.assertIn('CODE_OSS_STATIC_WEB_EXTERNAL_BASE_URL', runner)
        exporter = (ROOT / 'scripts/export_playwright_runtime.py').read_text()
        self.assertIn("Path('@playwright/test')", exporter)

    def test_browser_qualification_topology_is_centralized(self):
        check_policy.check_browser_qualification_topology()
        self.assertFalse((ROOT / '.github/workflows/browser-matrix.yml').exists())

        qualification = (ROOT / '.github/workflows/qualify.yml').read_text()
        release = (ROOT / '.github/workflows/release.yml').read_text()
        promote = (ROOT / '.github/workflows/promote.yml').read_text()
        self.assertEqual(
            qualification.count('uses: ./.github/actions/browser-qualification'),
            2,
        )
        self.assertEqual(release.count('uses: ./.github/actions/browser-qualification'), 1)
        self.assertEqual(promote.count('uses: ./.github/actions/browser-qualification'), 2)
        self.assertIn('browser: [chromium]', release)
        self.assertIn('name: OCI production-serving qualification', qualification)
        self.assertIn('Browser synthetic against live canary', promote)
        self.assertIn('Browser smoke against live Pages deployment', promote)
        for workflow in (qualification, release, promote):
            self.assertNotIn('scripts/install_playwright_browser.py', workflow)
            self.assertNotIn('scripts/run_e2e.py', workflow)
            self.assertNotIn('scripts/add_test_extension.py', workflow)

    def test_production_serving_qualification_is_release_gating(self):
        qualification = (ROOT / '.github/workflows/qualify.yml').read_text()
        promotion = (ROOT / '.github/workflows/promote.yml').read_text()
        release = (ROOT / '.github/workflows/release.yml').read_text()
        nginx = (ROOT / 'deploy/nginx.conf').read_text()

        self.assertIn('name: OCI production-serving qualification', qualification)
        self.assertIn('docker build --tag code-oss-static-web:qualification', qualification)
        self.assertIn('scripts/check_hosting_contract.py', qualification)
        self.assertIn('scope: serving', qualification)
        self.assertIn('SERVING_RESULT: ${{ needs.production-serving.result }}', qualification)
        self.assertIn('"$SERVING_RESULT" != success', qualification)
        self.assertIn('playwright-runtime.tar.gz', promotion)
        self.assertIn('Publish real canary to GitHub Pages', promotion)
        self.assertIn('deployments?environment=github-pages&per_page=100', promotion)
        self.assertIn('legacy-pages-identity.json', promotion)
        self.assertIn('identity-url-path: __canary/', promotion)
        self.assertIn('Browser synthetic against live canary', promotion)
        self.assertIn('Browser smoke against live Pages deployment', promotion)
        self.assertNotIn('playwright-runtime-run-id:', promotion)
        self.assertNotIn('actions/runs/$run_id/artifacts', promotion)
        self.assertIn('CODE_OSS_STATIC_WEB_PLAYWRIGHT_RUNTIME', release)
        self.assertIn('retention-days: 7', release)
        self.assertIn('Cross-Origin-Opener-Policy "same-origin"', nginx)
        self.assertIn('Cache-Control "no-cache"', nginx)
        self.assertIn('default_type application/javascript;', nginx)
        self.assertIn('try_files $uri $uri/ =404;', nginx)

    def test_release_workflow_uses_clean_qualified_artifact(self):
        workflow_path = ROOT / '.github/workflows/release.yml'
        workflow = workflow_path.read_text()
        pages_action = (ROOT / '.github/actions/publish-pages/action.yml').read_text()
        oci_action = (ROOT / '.github/actions/publish-oci/action.yml').read_text()
        release_action = (ROOT / '.github/actions/publish-github-release/action.yml').read_text()
        release_script = (ROOT / 'scripts/publish_github_release.py').read_text()
        check_policy.check_release_publication_boundaries(workflow_path, workflow)
        self.assertIn('./build.sh --clean-upstream', workflow)
        self.assertIn('needs: [build, reproducibility]', workflow)
        self.assertIn('uses: ./.github/actions/browser-qualification', workflow)
        self.assertIn('scripts/compare_dist.py reference-dist dist', workflow)
        self.assertNotIn('actions/cache@', workflow)
        self.assertEqual(workflow.count('environment: release'), 2)
        self.assertRegex(
            pages_action,
            r'actions/deploy-pages@[0-9a-f]{40}\s+# v[0-9]+',
        )
        self.assertRegex(
            oci_action,
            r'docker/build-push-action@[0-9a-f]{40}\s+# v[0-9]+',
        )
        self.assertNotIn('docker/setup-qemu-action@', oci_action)
        self.assertIn(
            'image=moby/buildkit@sha256:28a898719c18a33f4e8000685287fa36fd0dd9560c6440227d3a732d79bb41d8',
            oci_action,
        )
        self.assertIn('platforms: linux/amd64,linux/arm64', oci_action)
        self.assertIn('uses: ./.github/actions/publish-github-release', workflow)
        self.assertNotIn('uses: ./.github/actions/publish-pages', workflow)
        self.assertIn('uses: ./.github/actions/publish-oci', workflow)
        self.assertRegex(release_script, r"'release',\s*'create'")
        self.assertRegex(release_script, r"'release',\s*'upload'")
        self.assertNotIn('--clobber', release_script)
        self.assertIn(
            'published GitHub Release is incomplete; refusing to mutate it',
            release_script,
        )
        self.assertIn("'draft=false'", release_script)
        self.assertIn('scripts/export_release_provenance.py', release_action)
        self.assertIn('pages/deployments/$GITHUB_SHA', pages_action)
        self.assertNotIn('deployments?environment=github-pages', pages_action)
        self.assertNotIn('steps.state.outputs.complete', pages_action)
        self.assertIn('Verify existing GHCR publication', oci_action)
        self.assertIn('inspect_status=$?', oci_action)
        self.assertIn('manifest unknown', oci_action)
        self.assertIn('unable to determine GHCR publication state', oci_action)
        self.assertIn("steps.state.outputs.exists == 'false'", oci_action)
        oci_verifier = (ROOT / 'scripts/verify_oci_image.sh').read_text()
        self.assertIn('for arch in amd64 arm64; do', oci_verifier)
        self.assertIn('child="$image@$digest"', oci_verifier)
        self.assertIn('docker pull --platform "$platform" "$child"', oci_verifier)
        self.assertIn('docker image inspect "$image_id"', oci_verifier)
        self.assertIn('scripts/compare_dist.py "$dist" "$platform_dist"', oci_verifier)
        self.assertIn('served_root=/srv/code-oss-static-web', oci_verifier)
        self.assertIn(
            'COPY dist/ /srv/code-oss-static-web/',
            (ROOT / 'deploy/Dockerfile').read_text(),
        )
        self.assertIn('root /srv/code-oss-static-web;', (ROOT / 'deploy/nginx.conf').read_text())
        self.assertIn('immutable-publication-status:', workflow)
        self.assertIn('needs: immutable-publication-status', workflow)
        self.assertIn('needs: authorize', workflow)
        self.assertIn('qualification_run_id:', workflow)
        self.assertIn('name: Verify release qualification evidence', workflow)
        self.assertIn('release-qualification', workflow)
        self.assertIn('name: Download release qualification evidence', workflow)
        self.assertIn('name: Verify release qualification binding', workflow)
        self.assertIn('Verify qualification provenance', workflow)
        self.assertIn('qualification-provenance.sigstore.json', workflow)
        self.assertIn('qualified-tree-sha256', workflow)
        self.assertIn('scripts/verify_dist_identity.py', workflow)
        self.assertIn('.tag == $tag', workflow)
        self.assertIn('CODE_OSS_STATIC_WEB_RELEASE_TAG: ${{ github.ref_name }}', workflow)
        self.assertIn('name: Verify release commit is on protected default branch', workflow)
        self.assertIn('repos/$GITHUB_REPOSITORY/compare/$GITHUB_SHA...$default_branch', workflow)
        self.assertIn('"$compare_status" != \'ahead\'', workflow)
        self.assertIn('"$compare_status" != \'identical\'', workflow)
        self.assertEqual(workflow.count('name: Verify immutable release ref'), 2)
        self.assertIn('repos/$GITHUB_REPOSITORY/commits/$GITHUB_REF_NAME', workflow)
        self.assertIn("expected_pattern='refs/tags/v*-web.*'", workflow)
        self.assertIn('repos/$GITHUB_REPOSITORY/rulesets', workflow)
        self.assertIn('index("update")', workflow)
        self.assertIn('index("deletion")', workflow)
        self.assertIn('tag_sha_after', workflow)
        self.assertIn('retention-days: 30', workflow)
        ruleset = json.loads((ROOT / '.github/rulesets/immutable-release-tags.json').read_text())
        self.assertEqual(ruleset['target'], 'tag')
        self.assertEqual(ruleset['enforcement'], 'active')
        self.assertEqual(ruleset['bypass_actors'], [])
        self.assertEqual(
            ruleset['conditions']['ref_name']['include'],
            ['refs/tags/v*-web.*'],
        )
        self.assertEqual(
            {rule['type'] for rule in ruleset['rules']},
            {'update', 'deletion'},
        )
        dockerfile = (ROOT / 'deploy/Dockerfile').read_text()
        self.assertRegex(
            dockerfile,
            r'(?m)^FROM nginxinc/nginx-unprivileged:[^\\s@]+@sha256:[0-9a-f]{64}$',
        )
        self.assertNotRegex(dockerfile, r'(?im)^\s*RUN(?:\s|$)')

    def test_distribution_comparison_rejects_extra_served_files(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            reference = root / 'reference'
            candidate = root / 'candidate'
            reference.mkdir()
            candidate.mkdir()
            (reference / 'index.html').write_text('same')
            (candidate / 'index.html').write_text('same')
            (candidate / 'unexpected.txt').write_text('extra')

            with self.assertRaisesRegex(
                compare_dist.BuildError,
                'distribution file count mismatch',
            ):
                compare_dist.compare_distributions(reference, candidate)

    def test_release_publication_recovery_is_artifact_only(self):
        workflow_path = ROOT / '.github/workflows/recover-release-publication.yml'
        workflow = workflow_path.read_text()
        check_policy.check_recovery_publication_boundaries()
        self.assertIn('release_run_id:', workflow)
        self.assertIn('channel:', workflow)
        self.assertIn('.head_branch == $tag', workflow)
        self.assertIn('run-id: ${{ inputs.release_run_id }}', workflow)
        self.assertIn('group: release-${{ github.ref }}', workflow)
        self.assertIn('uses: ./.github/actions/publish-github-release', workflow)
        self.assertNotIn('uses: ./.github/actions/publish-pages', workflow)
        self.assertIn('uses: ./.github/actions/publish-oci', workflow)
        self.assertNotIn('./build.sh', workflow)
        self.assertNotIn('package.sh', workflow)
        self.assertNotIn('actions/attest@', workflow)
        self.assertEqual(workflow.count('name: Verify immutable release ref'), 2)
        self.assertIn('publication-status:', workflow)
        self.assertIn('required preparation job did not succeed exactly once', workflow)

    def test_github_release_asset_reconciliation_is_monotonic(self):
        local = {'a.tar.gz': 'a' * 64, 'SHA256SUMS': 'b' * 64}
        self.assertEqual(
            publish_github_release.pending_asset_uploads(
                local,
                {'a.tar.gz': 'a' * 64},
                draft=True,
            ),
            ['SHA256SUMS'],
        )
        self.assertEqual(
            publish_github_release.pending_asset_uploads(local, local, draft=False),
            [],
        )
        with self.assertRaisesRegex(
            publish_github_release.BuildError,
            'published GitHub Release is incomplete',
        ):
            publish_github_release.pending_asset_uploads(
                local,
                {'a.tar.gz': 'a' * 64},
                draft=False,
            )
        with self.assertRaises(publish_github_release.BuildError):
            publish_github_release.pending_asset_uploads(
                local,
                {'a.tar.gz': 'c' * 64},
                draft=True,
            )
        with self.assertRaises(publish_github_release.BuildError):
            publish_github_release.pending_asset_uploads(
                local,
                {'unexpected.txt': 'd' * 64},
                draft=True,
            )

    def test_product_transform_keeps_chat_contract_fail_closed(self):
        transform = json.loads((ROOT / 'config/policies/product/static.json').read_text())
        default_chat = transform['set']['defaultChatAgent']
        self.assertEqual(default_chat['providerScopes'], [])
        self.assertTrue(default_chat['extensionId'].startswith('code-oss-static-web.disabled'))
        self.assertTrue(default_chat['chatExtensionId'].startswith('code-oss-static-web.disabled'))
        for key in (
            'documentationUrl',
            'termsStatementUrl',
            'privacyStatementUrl',
            'entitlementUrl',
            'tokenEntitlementUrl',
            'mcpRegistryDataUrl',
            'managedSettingsUrl',
        ):
            self.assertIn('disabled.invalid.invalid', default_chat[key])
        self.assertNotIn('defaultChatAgent', transform.get('remove', []))

    def test_standalone_static_bootstrap_uses_web_embedder_api(self):
        self.assertIn('workbench.web.main.internal.css', make_static.INDEX)
        self.assertIn('workbench.web.main.internal.js', make_static.BOOTSTRAP)
        self.assertIn('create(document.body, config)', make_static.BOOTSTRAP)
        self.assertNotIn('vs/code/browser/workbench/workbench.js', make_static.BOOTSTRAP)

    def test_static_bootstrap_registers_only_additional_extensions(self):
        self.assertIn('additional-extensions.json', make_static.BOOTSTRAP)
        self.assertNotIn("fetch(new URL('extensions.json'", make_static.BOOTSTRAP)

    def test_default_static_policy_is_fail_closed(self):
        self.assertIn("connect-src 'self'", make_static.INDEX)
        self.assertNotIn('unsafe-eval', make_static.INDEX)
        self.assertIn('invalid.invalid', make_static.BOOTSTRAP)


if __name__ == '__main__':
    unittest.main()
