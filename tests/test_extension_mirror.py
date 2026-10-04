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

import extension_intake  # noqa: E402
import extension_lock  # noqa: E402


def mirror_policy(origin: str = 'https://extensions.example.invalid') -> dict[str, object]:
    return {
        'schemaVersion': 2,
        'allowedOpenVsxRegistries': ['https://open-vsx.org'],
        'allowedOpenVsxDownloadOrigins': [
            'https://open-vsx.org',
            'https://openvsx.eclipsecontent.org',
        ],
        'allowedMirrorOrigins': [origin],
        'requireMirrorForLockedExtensions': True,
    }


class ExtensionMirrorTests(unittest.TestCase):
    def _write_vsix(self, path: Path) -> None:
        manifest = {
            'publisher': 'demo',
            'name': 'fixture',
            'version': '1.2.3',
            'license': 'MIT',
            'browser': './extension.js',
        }
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('extension/package.json', json.dumps(manifest))
            archive.writestr('extension/extension.js', 'exports.activate = () => {};\n')

    def test_production_policy_requires_internal_mirror(self) -> None:
        entry = {
            'id': 'demo.fixture',
            'version': '1.2.3',
            'sha256': '0' * 64,
            'license': 'MIT',
            'source': {'type': 'open-vsx', 'registry': 'https://open-vsx.org'},
        }
        with self.assertRaisesRegex(extension_lock.BuildError, 'must use the internal mirror'):
            extension_lock.enforce_source_policy(entry, mirror_policy())

    def test_mirror_lock_requires_content_address_and_approval(self) -> None:
        digest = 'a' * 64
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
                                'sha256': digest,
                                'license': 'MIT',
                                'source': {
                                    'type': 'mirror-vsix',
                                    'url': (
                                        'https://extensions.example.invalid/sha256/'
                                        f'{digest}/demo.fixture-1.2.3.vsix'
                                    ),
                                },
                                'approval': {
                                    'reviewer': 'extension-policy',
                                    'source': 'https://open-vsx.org/extension/demo/fixture',
                                    'scanResult': 'clean',
                                    'approvedAt': '2026-10-04',
                                },
                            }
                        ],
                    }
                )
            )
            loaded = extension_lock.load_extension_lock(lock_path)
        self.assertEqual(loaded['extensions'][0]['source']['type'], 'mirror-vsix')
        self.assertEqual(loaded['extensions'][0]['approval']['scanResult'], 'clean')

    def test_dirty_scan_is_not_admissible(self) -> None:
        digest = 'b' * 64
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
                                'sha256': digest,
                                'license': 'MIT',
                                'source': {
                                    'type': 'mirror-vsix',
                                    'url': (
                                        'https://extensions.example.invalid/sha256/'
                                        f'{digest}/demo.fixture-1.2.3.vsix'
                                    ),
                                },
                                'approval': {
                                    'reviewer': 'extension-policy',
                                    'source': 'candidate',
                                    'scanResult': 'malicious',
                                    'approvedAt': '2026-10-04',
                                },
                            }
                        ],
                    }
                )
            )
            with self.assertRaisesRegex(extension_lock.BuildError, 'scanResult must be clean'):
                extension_lock.load_extension_lock(lock_path)

    def test_intake_record_binds_mirror_url_to_candidate_digest(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            vsix = Path(td) / 'demo.fixture-1.2.3.vsix'
            self._write_vsix(vsix)
            digest = hashlib.sha256(vsix.read_bytes()).hexdigest()
            record = extension_intake.build_intake_record(
                vsix=vsix,
                extension_id='demo.fixture',
                version='1.2.3',
                license_name='MIT',
                original_source='https://open-vsx.org/extension/demo/fixture',
                reviewer='extension-policy',
                scan_result='clean',
                approved_at='2026-10-04',
                mirror_base_url='https://extensions.example.invalid/code-oss',
                source_policy=mirror_policy(),
                license_policy={
                    'schemaVersion': 1,
                    'requireDeclared': True,
                    'allowed': ['MIT'],
                    'denied': [],
                    'overrides': {},
                },
            )
        self.assertEqual(record['candidate']['sha256'], digest)
        self.assertIn(digest, record['mirror']['url'])
        self.assertEqual(record['lockEntry']['source']['type'], 'mirror-vsix')


if __name__ == '__main__':
    unittest.main()
