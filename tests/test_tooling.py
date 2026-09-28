from __future__ import annotations
import hashlib, json, sys, tempfile, unittest, zipfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import check_policy, make_static, package_release, extensions_index, extension_lock, generate_license_inventory, generate_runtime_metadata, generate_sbom

class ToolingTests(unittest.TestCase):
    def test_upstream_lock_is_exact_commit_and_unqualified(self):
        lock = json.loads((ROOT / 'upstream.lock.json').read_text())
        self.assertRegex(lock['commit'], r'^[0-9a-f]{40}$')
        self.assertFalse(lock['qualified'])

    def test_archives_are_deterministic(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td); src = base / 'src'; src.mkdir()
            (src / 'a.txt').write_text('a\n')
            (src / 'b').mkdir(); (src / 'b/x.txt').write_text('x\n')
            a, b = base / 'a.tar.gz', base / 'b.tar.gz'
            za, zb = base / 'a.zip', base / 'b.zip'
            package_release.build_tar(src, a, 1790307657)
            package_release.build_tar(src, b, 1790307657)
            package_release.build_zip(src, za, 1790307657)
            package_release.build_zip(src, zb, 1790307657)
            self.assertEqual(hashlib.sha256(a.read_bytes()).digest(), hashlib.sha256(b.read_bytes()).digest())
            self.assertEqual(hashlib.sha256(za.read_bytes()).digest(), hashlib.sha256(zb.read_bytes()).digest())

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
            (extension / 'package.json').write_text(json.dumps({
                'publisher': 'demo',
                'name': 'fixture',
                'version': '1.2.3',
                'license': 'MIT',
                'browser': './extension.js',
            }))
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
                {bom['metadata']['component']['bom-ref']} |
                {component['bom-ref'] for component in bom['components']},
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
            web = d / 'extensions/web'; web.mkdir(parents=True)
            (web / 'package.json').write_text(json.dumps({'publisher':'p','name':'web','version':'1','browser':'dist/web.js'}))
            node = d / 'extensions/node'; node.mkdir()
            (node / 'package.json').write_text(json.dumps({'publisher':'p','name':'node','version':'1','main':'dist/node.js'}))
            values = {x['id']: x['browserCompatible'] for x in extensions_index.build_extension_index(d)['extensions']}
            self.assertEqual(values, {'p.node': False, 'p.web': True})



    def test_local_vsix_lock_validation_and_installation(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            vendor = root / 'vendor'; vendor.mkdir()
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
            lock_path.write_text(json.dumps({
                'schemaVersion': 1,
                'extensions': [{
                    'id': 'fixture.browser',
                    'version': '1.2.3',
                    'sha256': digest,
                    'license': 'MIT',
                    'source': {'type': 'local-vsix', 'path': 'vendor/fixture.vsix'},
                }],
            }))
            dist = root / 'dist'; dist.mkdir()
            installed = extension_lock.install_locked_extensions(dist, lock_path, root=root)
            self.assertEqual(installed[0]['id'], 'fixture.browser')
            self.assertTrue((dist / 'extensions/fixture.browser/extension.js').is_file())
            index = extensions_index.build_extension_index(dist)
            self.assertTrue(index['extensions'][0]['browserCompatible'])

    def test_local_vsix_rejects_digest_mismatch_and_node_only_extension(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            vsix = root / 'fixture.vsix'
            manifest = {'publisher': 'fixture', 'name': 'node', 'version': '1.0.0', 'main': './extension.js'}
            with zipfile.ZipFile(vsix, 'w') as archive:
                archive.writestr('extension/package.json', json.dumps(manifest))
                archive.writestr('extension/extension.js', 'module.exports = {};\n')
            digest = hashlib.sha256(vsix.read_bytes()).hexdigest()
            entry = {
                'id': 'fixture.node', 'version': '1.0.0', 'sha256': digest,
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
                archive.writestr('extension/package.json', json.dumps({
                    'publisher': 'fixture', 'name': 'bad', 'version': '1.0.0', 'browser': './extension.js'
                }))
                archive.writestr('extension/extension.js', '')
            entry = {
                'id': 'fixture.bad', 'version': '1.0.0',
                'sha256': hashlib.sha256(vsix.read_bytes()).hexdigest(),
                'source': {'type': 'local-vsix', 'path': 'fixture.vsix'},
                'license': None,
            }
            with self.assertRaises(extension_lock.BuildError):
                extension_lock.validate_local_vsix(entry, root=root)

    def test_qualification_extension_is_browser_compatible(self):
        fixture = ROOT / 'tests/fixtures/web-extension'
        manifest = json.loads((fixture / 'package.json').read_text())
        self.assertEqual(manifest['browser'], './extension.js')
        self.assertEqual(manifest['engines']['vscode'], '^1.139.0')
        self.assertIn('codeOssStaticWebTest.markReady', manifest['activationEvents'][0])
        self.assertIn('codeOssStaticWebTest.readMarker', manifest['activationEvents'][1])
        source = (fixture / 'extension.js').read_text()
        self.assertIn("return context.globalState.get('qualificationMarker', 'missing')", source)
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

    def test_workflow_actions_are_commit_pinned(self):
        import re
        for workflow in (ROOT / '.github/workflows').glob('*.yml'):
            for line_number, line in enumerate(workflow.read_text().splitlines(), 1):
                match = re.search(r'uses:\s*[^@\s]+@([^\s#]+)', line)
                if match:
                    self.assertRegex(
                        match.group(1),
                        r'^[0-9a-f]{40}$',
                        f'{workflow}:{line_number} must pin an immutable action commit',
                    )

    def test_qualification_workflow_runs_browser_and_extension_suites(self):
        workflow = (ROOT / '.github/workflows/qualify.yml').read_text()
        self.assertIn('actions/cache@caa296126883cff596d87d8935842f9db880ef25', workflow)
        self.assertIn('name: static-dist', workflow)
        self.assertIn('name: playwright-runtime', workflow)
        self.assertIn('name: qualification-harness', workflow)
        self.assertIn('name: playwright-browser-chromium', workflow)
        self.assertIn('PLAYWRIGHT_BROWSERS_PATH: .work/playwright-browsers', workflow)
        self.assertIn("github.event_name == 'workflow_dispatch'", workflow)
        self.assertIn('needs: build', workflow)
        self.assertIn('needs: browser', workflow)
        self.assertIn('needs: package', workflow)
        self.assertIn('actions/attest@1e69f48acb82d1966a394da916b4c1698aa569d6', workflow)
        self.assertIn('subject-checksums: artifacts/SHA256SUMS', workflow)
        self.assertIn('sbom-path: artifacts/sbom.cdx.json', workflow)
        package_source = (ROOT / 'scripts/package_release.py').read_text()
        self.assertIn("license-inventory.json", package_source)
        self.assertIn('actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c', workflow)
        self.assertIn('scripts/run_e2e.py', workflow)
        self.assertIn('--grep-invert @extension', workflow)
        self.assertIn('--grep @extension', workflow)
        self.assertIn('scripts/add_test_extension.py', workflow)
        self.assertIn('--reuse-upstream-build', workflow)

        extension_test = (ROOT / 'tests/e2e/extension-host.spec.cjs').read_text()
        self.assertIn("codeOssStaticWebTest.markReady", extension_test)
        self.assertIn("codeOssStaticWebTest.readMarker", extension_test)
        self.assertIn('global state persists across workbench reload', extension_test)
        self.assertIn("toBe('ready')", extension_test)
        self.assertIn("commands.executeCommand('workbench.action.reloadWindow')", extension_test)

        runner = (ROOT / 'scripts/run_e2e.py').read_text()
        self.assertIn("playwright-runtime", runner)
        exporter = (ROOT / 'scripts/export_playwright_runtime.py').read_text()
        self.assertIn("Path('@playwright/test')", exporter)

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

if __name__ == '__main__': unittest.main()
