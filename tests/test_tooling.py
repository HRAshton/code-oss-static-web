from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import check_policy
import extension_lock
import extensions_index
import generate_license_inventory
import generate_runtime_metadata
import generate_sbom
import make_static
import package_release
import validate_config


class ToolingTests(unittest.TestCase):
    def test_upstream_lock_is_exact_commit(self):
        lock = json.loads((ROOT / 'upstream.lock.json').read_text())
        self.assertRegex(lock['commit'], r'^[0-9a-f]{40}$')
        self.assertNotIn('qualified', lock)
        self.assertNotIn('qualificationNote', lock)

    def test_renovate_updates_auto_merge_without_human_reviewer(self):
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

    def test_full_qualification_supports_upstream_and_patch_release_modes(self):
        workflow = (ROOT / '.github/workflows/qualify.yml').read_text()
        self.assertIn('release_mode:', workflow)
        self.assertIn('default: none', workflow)
        self.assertIn("inputs.browser == 'all'", workflow)
        self.assertIn("inputs.release_mode != 'none'", workflow)
        self.assertIn('upstream)', workflow)
        self.assertIn('patch)', workflow)
        self.assertIn('matching-refs/tags/v${version}-web.', workflow)
        self.assertIn('already points to this qualification commit', workflow)
        self.assertIn('name: release-qualification', workflow)
        self.assertIn('releaseMode: $releaseMode', workflow)
        self.assertIn('gh workflow run release.yml', workflow)
        self.assertIn('qualification_run_id="$GITHUB_RUN_ID"', workflow)

        patch = (ROOT / '.github/workflows/patch-release.yml').read_text()
        self.assertIn('name: Patch release', patch)
        self.assertIn('No v${version}-web.0 exists', patch)
        self.assertIn('already points to current master', patch)
        self.assertIn('-f browser=all', patch)
        self.assertIn('-f release_mode=patch', patch)

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
        workflow = (ROOT / '.github/workflows/ci.yml').read_text()
        self.assertNotIn("pip install --disable-pip-version-check 'reuse==", workflow)
        self.assertIn(
            'docker://fsfe/reuse:6.2.0@sha256:'
            '85462a75c0f8efda09ddd190b92816b70e7662577c8427429e11e1b9f25a992e',
            workflow,
        )

    def test_repository_configuration_is_valid(self):
        validate_config.validate_all()

    def test_release_tag_contract_supports_patch_revisions(self):
        import check_release_tag

        lock = json.loads((ROOT / 'upstream.lock.json').read_text())
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
            self.assertEqual(metadata['npm'][0]['name'], '@scope/pkg')
            self.assertEqual(metadata['npm'][0]['version'], '4.5.6')
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
            dist = root / 'dist'
            dist.mkdir()
            installed = extension_lock.install_locked_extensions(dist, lock_path, root=root)
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
            )

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

    def test_ci_validates_pr_titles_and_skips_default_branch_merge_messages(self):
        workflow = (ROOT / '.github/workflows/ci.yml').read_text()
        self.assertIn('name: Pull request title policy', workflow)
        self.assertIn('types: [opened, synchronize, reopened, edited]', workflow)
        self.assertIn("github.event_name == 'pull_request'", workflow)
        self.assertIn('github.event.pull_request.title', workflow)
        self.assertIn("github.event_name == 'push' &&", workflow)
        self.assertIn("startsWith(github.ref, 'refs/heads/')", workflow)
        self.assertIn(
            'github.ref_name != github.event.repository.default_branch',
            workflow,
        )

    def test_workflow_actions_are_commit_pinned(self):
        import re

        for workflow in (ROOT / '.github/workflows').glob('*.yml'):
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
        browser_matrix = (ROOT / '.github/workflows/browser-matrix.yml').read_text()

        self.assertIn('tar -C dist -cf .work/static-dist.tar .', qualification)
        self.assertIn('path: .work/static-dist.tar', qualification)
        self.assertIn('tar -C dist -cf .work/release-static-dist.tar .', release)
        self.assertIn('path: .work/release-static-dist.tar', release)
        self.assertIn(
            'tar -C reference-dist -xf .work/release-static-dist/release-static-dist.tar',
            release,
        )
        self.assertIn('tar -C dist -xf .work/static-dist/static-dist.tar', qualification)
        self.assertIn('tar -C dist -xf .work/static-dist/static-dist.tar', browser_matrix)

    def test_qualification_workflow_runs_browser_and_extension_suites(self):
        workflow = (ROOT / '.github/workflows/qualify.yml').read_text()
        self.assertRegex(
            workflow,
            r'actions/cache@[0-9a-f]{40}\s+# v[0-9]+',
        )
        self.assertIn('name: static-dist', workflow)
        self.assertIn('name: playwright-runtime', workflow)
        self.assertIn('name: qualification-harness', workflow)
        self.assertIn('name: playwright-browser-chromium', workflow)
        self.assertIn('PLAYWRIGHT_BROWSERS_PATH: .work/playwright-browsers', workflow)
        self.assertIn("github.event_name == 'workflow_dispatch'", workflow)
        self.assertIn('needs: build', workflow)
        self.assertIn('secondary-browsers', workflow)
        self.assertIn('browser: [firefox, webkit]', workflow)
        self.assertIn('needs: [browser, secondary-browsers]', workflow)
        self.assertIn('needs: package', workflow)
        self.assertIn('actions/attest@1e69f48acb82d1966a394da916b4c1698aa569d6', workflow)
        self.assertIn('subject-checksums: artifacts/SHA256SUMS', workflow)
        self.assertIn('sbom-path: artifacts/sbom.cdx.json', workflow)
        package_source = (ROOT / 'scripts/package_release.py').read_text()
        self.assertIn('license-inventory.json', package_source)
        self.assertIn('extensionLicensePolicy', package_source)
        self.assertIn(
            'actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c', workflow
        )
        self.assertIn('scripts/run_e2e.py', workflow)
        self.assertIn('--grep-invert @extension', workflow)
        self.assertIn('--grep @extension', workflow)
        self.assertIn('scripts/add_test_extension.py', workflow)
        self.assertIn('--reuse-upstream-build', workflow)

        extension_test = (ROOT / 'tests/e2e/extension-host.spec.cjs').read_text()
        self.assertIn('codeOssStaticWebTest.markReady', extension_test)
        self.assertIn('codeOssStaticWebTest.readMarker', extension_test)
        self.assertIn('global state persists across workbench reload', extension_test)
        self.assertIn("toBe('ready')", extension_test)
        self.assertIn("commands.executeCommand('workbench.action.reloadWindow')", extension_test)
        self.assertIn('browser filesystem persists across workbench reload', extension_test)
        self.assertIn('JavaScript language service returns completions', extension_test)

        runner = (ROOT / 'scripts/run_e2e.py').read_text()
        self.assertIn('playwright-runtime', runner)
        exporter = (ROOT / 'scripts/export_playwright_runtime.py').read_text()
        self.assertIn("Path('@playwright/test')", exporter)

    def test_browser_matrix_reuses_qualified_artifacts(self):
        workflow = (ROOT / '.github/workflows/browser-matrix.yml').read_text()
        self.assertIn("workflows: ['Full build qualification']", workflow)
        self.assertIn('browser: [firefox, webkit]', workflow)
        self.assertIn('run-id: ${{ env.SOURCE_RUN_ID }}', workflow)
        self.assertNotIn('./build.sh', workflow)

    def test_release_workflow_uses_clean_qualified_artifact(self):
        workflow_path = ROOT / '.github/workflows/release.yml'
        workflow = workflow_path.read_text()
        check_policy.check_release_publication_boundaries(workflow_path, workflow)
        self.assertIn('./build.sh --clean-upstream', workflow)
        self.assertIn('needs: [build, reproducibility]', workflow)
        self.assertIn('scripts/compare_dist.py reference-dist dist', workflow)
        self.assertNotIn('actions/cache@', workflow)
        self.assertEqual(workflow.count('environment: release'), 3)
        self.assertRegex(
            workflow,
            r'actions/deploy-pages@[0-9a-f]{40}\s+# v[0-9]+',
        )
        self.assertRegex(
            workflow,
            r'docker/build-push-action@[0-9a-f]{40}\s+# v[0-9]+',
        )
        self.assertNotIn('docker/setup-qemu-action@', workflow)
        self.assertIn(
            'image=moby/buildkit@sha256:28a898719c18a33f4e8000685287fa36fd0dd9560c6440227d3a732d79bb41d8',
            workflow,
        )
        self.assertIn('platforms: linux/amd64,linux/arm64', workflow)
        self.assertIn('pages-release-gate:', workflow)
        self.assertIn('needs: [attest, pages-release-gate]', workflow)
        self.assertIn('permissions: {}', workflow)
        self.assertIn('gh release create', workflow)
        self.assertIn('needs: authorize', workflow)
        self.assertIn('qualification_run_id:', workflow)
        self.assertIn('name: Verify release qualification evidence', workflow)
        self.assertIn('name: Verify GitHub Pages is enabled', workflow)
        self.assertIn('repos/$GITHUB_REPOSITORY/pages', workflow)
        self.assertIn('release-qualification', workflow)
        self.assertIn('name: Download release qualification evidence', workflow)
        self.assertIn('name: Verify release qualification binding', workflow)
        self.assertIn('.tag == $tag', workflow)
        self.assertIn('CODE_OSS_STATIC_WEB_RELEASE_TAG: ${{ github.ref_name }}', workflow)
        self.assertIn('name: Verify release commit is on protected default branch', workflow)
        self.assertIn('repos/$GITHUB_REPOSITORY/compare/$GITHUB_SHA...$default_branch', workflow)
        self.assertIn('"$compare_status" != \'ahead\'', workflow)
        self.assertIn('"$compare_status" != \'identical\'', workflow)
        self.assertEqual(workflow.count('name: Verify immutable release ref'), 3)
        self.assertIn('repos/$GITHUB_REPOSITORY/commits/$GITHUB_REF_NAME', workflow)
        self.assertIn("expected_pattern='refs/tags/v*-web.*'", workflow)
        self.assertIn('repos/$GITHUB_REPOSITORY/rulesets', workflow)
        self.assertIn('index("update")', workflow)
        self.assertIn('index("deletion")', workflow)
        self.assertIn('tag_sha_after', workflow)
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

    def test_product_transform_keeps_chat_contract_fail_closed(self):
        transform = json.loads((ROOT / 'config/product-transform.json').read_text())
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
