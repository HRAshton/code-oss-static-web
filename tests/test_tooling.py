from __future__ import annotations
import hashlib, json, sys, tempfile, unittest, zipfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import make_static, package_release, extensions_index, extension_lock

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
        self.assertIn('codeOssStaticWebTest.markReady', manifest['activationEvents'][0])
        self.assertTrue((fixture / 'extension.js').is_file())

    def test_playwright_suite_uses_subpath_and_blocks_service_workers(self):
        config = (ROOT / 'tests/e2e/playwright.config.cjs').read_text()
        self.assertIn('/code-oss-web/', config)
        self.assertIn("serviceWorkers: 'block'", config)
        network = (ROOT / 'tests/e2e/network-policy.spec.cjs').read_text()
        self.assertIn('unexpectedRequests', network)
        self.assertIn('webSockets', network)


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
        self.assertIn('scripts/run_e2e.py', workflow)
        self.assertIn('--grep-invert @extension', workflow)
        self.assertIn('--grep @extension', workflow)
        self.assertIn('scripts/add_test_extension.py', workflow)

    def test_default_static_policy_is_fail_closed(self):
        self.assertIn("connect-src 'self'", make_static.INDEX)
        self.assertNotIn('unsafe-eval', make_static.INDEX)
        self.assertIn('invalid.invalid', make_static.BOOTSTRAP)

if __name__ == '__main__': unittest.main()
