from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import builder_environment  # noqa: E402
from common import BuildError  # noqa: E402


class BuilderEnvironmentTests(unittest.TestCase):
    def test_builder_manifest_requires_digest_and_platform(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'builder.json'
            path.write_text(
                json.dumps(
                    {
                        'schemaVersion': 1,
                        'image': 'docker.io/library/ubuntu',
                        'digest': 'sha256:' + 'a' * 64,
                        'platform': 'linux/amd64',
                    }
                ),
                encoding='utf-8',
            )
            builder = builder_environment.load_builder(path)
            self.assertEqual(
                builder_environment.image_reference(builder),
                'docker.io/library/ubuntu@sha256:' + 'a' * 64,
            )

    def test_builder_manifest_rejects_mutable_or_malformed_identity(self) -> None:
        cases = [
            {
                'schemaVersion': 1,
                'image': 'docker.io/library/ubuntu@latest',
                'digest': 'sha256:' + 'a' * 64,
                'platform': 'linux/amd64',
            },
            {
                'schemaVersion': 1,
                'image': 'docker.io/library/ubuntu',
                'digest': 'latest',
                'platform': 'linux/amd64',
            },
            {
                'schemaVersion': 1,
                'image': 'docker.io/library/ubuntu',
                'digest': 'sha256:' + 'a' * 64,
                'platform': 'linux/arm64',
            },
        ]
        for value in cases:
            with self.subTest(value=value):
                with tempfile.TemporaryDirectory() as td:
                    path = Path(td) / 'builder.json'
                    path.write_text(json.dumps(value), encoding='utf-8')
                    with self.assertRaises(BuildError):
                        builder_environment.load_builder(path)

    def test_job_block_parser_is_job_scoped(self) -> None:
        blocks = builder_environment.job_blocks(
            'jobs:\n  build:\n    runs-on: ubuntu-latest\n  release:\n    runs-on: ubuntu-latest\n'
        )
        self.assertIn('runs-on: ubuntu-latest', blocks['build'])
        self.assertNotIn('  release:', blocks['build'])
        self.assertIn('runs-on: ubuntu-latest', blocks['release'])


if __name__ == '__main__':
    unittest.main()
