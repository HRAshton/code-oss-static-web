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
                        'schemaVersion': 3,
                        'image': 'docker.io/library/ubuntu',
                        'digest': 'sha256:' + 'a' * 64,
                        'platform': 'linux/amd64',
                    }
                ),
                encoding='utf-8',
            )
            snapshot = path.with_name('builder-apt-snapshot.json')
            snapshot.write_text(
                json.dumps({'schemaVersion': 1, 'aptSnapshot': '20261001T000000Z'}),
                encoding='utf-8',
            )
            builder = builder_environment.load_builder(path)
            self.assertEqual(builder['aptSnapshot'], '20261001T000000Z')
            self.assertEqual(
                builder_environment.image_reference(builder),
                'docker.io/library/ubuntu@sha256:' + 'a' * 64,
            )

            snapshot.write_text(
                json.dumps({'schemaVersion': 1, 'aptSnapshot': '20261005T000000Z'}),
                encoding='utf-8',
            )
            self.assertEqual(
                builder_environment.load_builder(path)['aptSnapshot'], '20261005T000000Z'
            )

    def test_builder_manifest_rejects_mutable_or_malformed_identity(self) -> None:
        identity = {
            'schemaVersion': 3,
            'image': 'docker.io/library/ubuntu',
            'digest': 'sha256:' + 'a' * 64,
            'platform': 'linux/amd64',
        }
        cases = [
            {**identity, 'aptSnapshot': '20261001T000000Z'},
            {**identity, 'schemaVersion': 2},
            {**identity, 'image': 'docker.io/library/ubuntu@latest'},
            {**identity, 'digest': 'latest'},
            {**identity, 'platform': 'linux/arm64'},
        ]
        for value in cases:
            with self.subTest(value=value):
                with tempfile.TemporaryDirectory() as td:
                    path = Path(td) / 'builder.json'
                    path.write_text(json.dumps(value), encoding='utf-8')
                    path.with_name('builder-apt-snapshot.json').write_text(
                        json.dumps({'schemaVersion': 1, 'aptSnapshot': '20261001T000000Z'}),
                        encoding='utf-8',
                    )
                    with self.assertRaises(BuildError):
                        builder_environment.load_builder(path)

    def test_builder_snapshot_rejects_unsupported_fields_and_formats(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'builder.json'
            path.write_text(
                json.dumps(
                    {
                        'schemaVersion': 3,
                        'image': 'docker.io/library/ubuntu',
                        'digest': 'sha256:' + 'a' * 64,
                        'platform': 'linux/amd64',
                    }
                ),
                encoding='utf-8',
            )
            snapshot = path.with_name('builder-apt-snapshot.json')
            for invalid in (
                {'schemaVersion': 2, 'aptSnapshot': '20261001T000000Z'},
                {'schemaVersion': 1, 'aptSnapshot': 'latest'},
                {'schemaVersion': 1, 'aptSnapshot': '20261001T000000Z', 'digest': 'malicious'},
            ):
                with self.subTest(invalid=invalid):
                    snapshot.write_text(json.dumps(invalid), encoding='utf-8')
                    with self.assertRaises(BuildError):
                        builder_environment.load_builder(path)

    def test_job_rejects_mutable_apt_or_mismatched_snapshot(self) -> None:
        builder = builder_environment.load_builder(ROOT / 'builder-image.json')
        reference = builder_environment.image_reference(builder)
        block = builder_environment.job_blocks(
            (ROOT / '.github/workflows/qualify.yml').read_text()
        )['build']
        builder_environment.validate_build_job(
            'qualification', block, reference, builder['aptSnapshot']
        )
        with self.assertRaisesRegex(BuildError, 'locked APT snapshot'):
            builder_environment.validate_build_job(
                'qualification',
                block.replace(
                    'needs.browser-plan.outputs.apt_snapshot',
                    'needs.invalid.outputs.apt_snapshot',
                ),
                reference,
                builder['aptSnapshot'],
            )
        with self.assertRaisesRegex(BuildError, 'snapshot-locked prerequisite'):
            builder_environment.validate_build_job(
                'qualification',
                block.replace('apt-get update --snapshot', 'apt-get update'),
                reference,
                builder['aptSnapshot'],
            )
        with self.assertRaisesRegex(BuildError, 'trusted TLS'):
            builder_environment.validate_build_job(
                'qualification',
                block.replace(
                    'Acquire::https::CaInfo=/tmp/runner-ca-bundle.pem',
                    'Acquire::https::CaInfo=',
                    1,
                ),
                reference,
                builder['aptSnapshot'],
            )
        with self.assertRaisesRegex(BuildError, 'snapshot-locked prerequisite'):
            builder_environment.validate_build_job(
                'qualification',
                block.replace(
                    '/etc/ssl/certs/ca-certificates.crt:/tmp/runner-ca-bundle.pem:ro',
                    '',
                ),
                reference,
                builder['aptSnapshot'],
            )
        with self.assertRaisesRegex(BuildError, 'extra mutable APT'):
            builder_environment.validate_build_job(
                'qualification',
                block + '\n      - run: apt-get update\n',
                reference,
                builder['aptSnapshot'],
            )

    def test_parallel_release_builds_enforce_identical_locked_environment(self) -> None:
        builder = builder_environment.load_builder(ROOT / 'builder-image.json')
        reference = builder_environment.image_reference(builder)
        jobs = builder_environment.job_blocks(
            (ROOT / '.github/workflows/release.yml').read_text(encoding='utf-8')
        )
        for job_name in ('build', 'rebuild'):
            with self.subTest(job=job_name):
                block = jobs[job_name]
                builder_environment.validate_build_job(
                    f'release {job_name}', block, reference, builder['aptSnapshot']
                )
                with self.assertRaisesRegex(BuildError, 'locked builder digest'):
                    builder_environment.validate_build_job(
                        f'release {job_name}',
                        block.replace(reference, 'docker.io/library/ubuntu:latest'),
                        reference,
                        builder['aptSnapshot'],
                    )
                with self.assertRaisesRegex(BuildError, 'locked APT snapshot'):
                    builder_environment.validate_build_job(
                        f'release {job_name}',
                        block.replace(
                            'needs.authorize.outputs.apt_snapshot',
                            'needs.invalid.outputs.apt_snapshot',
                        ),
                        reference,
                        builder['aptSnapshot'],
                    )

        self.assertIn('needs: [build, rebuild]', jobs['reproducibility'])
        self.assertIn(
            'scripts/compare_dist.py reference-dist rebuild-dist',
            jobs['reproducibility'],
        )
        self.assertIn('needs: [browser, reproducibility]', jobs['package'])

    def test_job_block_parser_is_job_scoped(self) -> None:
        blocks = builder_environment.job_blocks(
            'jobs:\n  build:\n    runs-on: ubuntu-latest\n  release:\n    runs-on: ubuntu-latest\n'
        )
        self.assertIn('runs-on: ubuntu-latest', blocks['build'])
        self.assertNotIn('  release:', blocks['build'])
        self.assertIn('runs-on: ubuntu-latest', blocks['release'])


if __name__ == '__main__':
    unittest.main()
