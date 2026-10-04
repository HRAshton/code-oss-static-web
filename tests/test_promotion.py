from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import promotion
from common import BuildError


class PromotionIdentityTests(unittest.TestCase):
    def write_fixture(self, root: Path) -> tuple[Path, Path, Path, Path]:
        policy = root / 'promotion-policy.json'
        policy.write_text(
            json.dumps(
                {
                    'schemaVersion': 1,
                    'profile': 'automatic-default-v1',
                    'automatic': {'enabled': True, 'order': ['canary', 'stable']},
                    'channels': {
                        'canary': {'environment': 'canary'},
                        'stable': {
                            'environment': 'stable',
                            'requiresCanary': True,
                            'deployPages': True,
                        },
                    },
                }
            )
            + '\n',
            encoding='utf-8',
        )

        archive = root / 'code-oss-static-web-1.140.0-web.0.tar.gz'
        archive.write_bytes(b'immutable release bytes')
        archive_digest = hashlib.sha256(archive.read_bytes()).hexdigest()

        manifest = root / 'artifact-manifest.json'
        manifest.write_text(
            json.dumps(
                {
                    'schemaVersion': 1,
                    'version': '1.140.0-web.0',
                    'project': {'commit': 'a' * 40},
                    'distribution': {'treeSha256': 'b' * 64, 'fileCount': 17},
                    'deploymentProfile': {
                        'schemaVersion': 1,
                        'id': 'company-standard',
                        'configSha256': 'c' * 64,
                        'bindings': {},
                    },
                    'artifacts': [
                        {
                            'name': archive.name,
                            'sha256': archive_digest,
                            'size': archive.stat().st_size,
                        },
                        {
                            'name': 'playwright-runtime.tar.gz',
                            'sha256': 'd' * 64,
                            'size': 123,
                        },
                    ],
                }
            )
            + '\n',
            encoding='utf-8',
        )

        checksums = root / 'SHA256SUMS'
        checksums.write_text(
            f'{hashlib.sha256(manifest.read_bytes()).hexdigest()}  {manifest.name}\n'
            f'{archive_digest}  {archive.name}\n',
            encoding='utf-8',
        )
        return policy, manifest, checksums, archive

    def test_build_identity_binds_release_artifact_and_policy(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            policy, manifest, checksums, archive = self.write_fixture(Path(td))
            identity = promotion.build_identity(
                release_tag='v1.140.0-web.0',
                release_commit='a' * 40,
                release_id=42,
                manifest_path=manifest,
                checksums_path=checksums,
                archive_path=archive,
                policy_path=policy,
            )

            self.assertEqual(identity['release']['tag'], 'v1.140.0-web.0')
            self.assertEqual(identity['release']['githubReleaseId'], 42)
            self.assertEqual(identity['artifact']['distribution']['treeSha256'], 'b' * 64)
            self.assertEqual(identity['artifact']['deploymentProfile']['id'], 'company-standard')
            self.assertEqual(identity['artifact']['deploymentProfile']['configSha256'], 'c' * 64)
            self.assertEqual(identity['policy']['profile'], 'automatic-default-v1')
            self.assertRegex(identity['policy']['sha256'], r'^[0-9a-f]{64}$')

    def test_release_archive_ignores_playwright_runtime_tarball(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            _, manifest, _, archive = self.write_fixture(Path(td))
            data = json.loads(manifest.read_text(encoding='utf-8'))
            selected = promotion.release_archive(data)
            self.assertEqual(selected['name'], archive.name)

    def test_build_identity_records_legacy_unprofiled_release(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            policy, manifest, checksums, archive = self.write_fixture(Path(td))
            data = json.loads(manifest.read_text(encoding='utf-8'))
            del data['deploymentProfile']
            manifest.write_text(json.dumps(data) + '\n', encoding='utf-8')
            checksums.write_text(
                f'{hashlib.sha256(manifest.read_bytes()).hexdigest()}  {manifest.name}\n'
                f'{hashlib.sha256(archive.read_bytes()).hexdigest()}  {archive.name}\n',
                encoding='utf-8',
            )
            identity = promotion.build_identity(
                release_tag='v1.140.0-web.0',
                release_commit='a' * 40,
                release_id=42,
                manifest_path=manifest,
                checksums_path=checksums,
                archive_path=archive,
                policy_path=policy,
            )
            self.assertIsNone(identity['artifact']['deploymentProfile'])

    def test_pages_deployment_identity_preserves_legacy_unprofiled_release(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            policy, manifest, checksums, archive = self.write_fixture(Path(td))
            data = json.loads(manifest.read_text(encoding='utf-8'))
            del data['deploymentProfile']
            manifest.write_text(json.dumps(data) + '\n', encoding='utf-8')
            checksums.write_text(
                f'{hashlib.sha256(manifest.read_bytes()).hexdigest()}  {manifest.name}\n'
                f'{hashlib.sha256(archive.read_bytes()).hexdigest()}  {archive.name}\n',
                encoding='utf-8',
            )
            identity = promotion.build_identity(
                release_tag='v1.140.0-web.0',
                release_commit='a' * 40,
                release_id=42,
                manifest_path=manifest,
                checksums_path=checksums,
                archive_path=archive,
                policy_path=policy,
            )

            pages_identity = promotion.build_pages_deployment_identity(identity)

            self.assertIsNone(identity['artifact']['deploymentProfile'])
            self.assertIsNone(pages_identity['deploymentProfile'])

    def test_pages_deployment_identity_binds_release_tree_and_profile(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            policy, manifest, checksums, archive = self.write_fixture(Path(td))
            identity = promotion.build_identity(
                release_tag='v1.140.0-web.0',
                release_commit='a' * 40,
                release_id=42,
                manifest_path=manifest,
                checksums_path=checksums,
                archive_path=archive,
                policy_path=policy,
            )
            pages_identity = promotion.build_pages_deployment_identity(identity)

            self.assertEqual(
                pages_identity,
                {
                    'schemaVersion': 1,
                    'release': {
                        'tag': 'v1.140.0-web.0',
                        'commit': 'a' * 40,
                    },
                    'distribution': {'treeSha256': 'b' * 64},
                    'deploymentProfile': {
                        'id': 'company-standard',
                        'configSha256': 'c' * 64,
                    },
                },
            )

    def test_pages_deployment_identity_rejects_release_and_artifact_mismatches(self) -> None:
        expected: dict[str, Any] = {
            'schemaVersion': 1,
            'release': {
                'tag': 'v1.140.0-web.0',
                'commit': 'a' * 40,
            },
            'distribution': {'treeSha256': 'b' * 64},
            'deploymentProfile': {
                'id': 'company-standard',
                'configSha256': 'c' * 64,
            },
        }
        mismatches = {
            'release tag': ('release', 'tag', 'v1.140.0-web.1'),
            'release commit': ('release', 'commit', 'd' * 40),
            'tree digest': ('distribution', 'treeSha256', 'e' * 64),
            'profile digest': ('deploymentProfile', 'configSha256', 'f' * 64),
        }
        for label, (section, field, replacement) in mismatches.items():
            with self.subTest(label=label):
                actual = copy.deepcopy(expected)
                actual[section][field] = replacement
                with self.assertRaisesRegex(
                    BuildError,
                    'does not match expected promotion identity',
                ):
                    promotion.verify_pages_deployment_identity(expected, actual)

    def test_pages_deployment_identity_rollback_is_bound_to_release_commit(self) -> None:
        workflow_sha = 'f' * 40
        expected = {
            'schemaVersion': 1,
            'release': {
                'tag': 'v1.139.1-web.2',
                'commit': 'a' * 40,
            },
            'distribution': {'treeSha256': 'b' * 64},
            'deploymentProfile': {
                'id': 'company-standard',
                'configSha256': 'c' * 64,
            },
        }
        live = copy.deepcopy(expected)

        self.assertNotEqual(workflow_sha, expected['release']['commit'])
        promotion.verify_pages_deployment_identity(expected, live)

    def test_pages_deployment_identity_legacy_rollback_preserves_null_profile(self) -> None:
        workflow_sha = 'f' * 40
        expected: dict[str, Any] = {
            'schemaVersion': 1,
            'release': {
                'tag': 'v1.139.1-web.2',
                'commit': 'a' * 40,
            },
            'distribution': {'treeSha256': 'b' * 64},
            'deploymentProfile': None,
        }
        live = copy.deepcopy(expected)

        self.assertNotEqual(workflow_sha, expected['release']['commit'])
        promotion.verify_pages_deployment_identity(expected, live)

    def test_pages_deployment_identity_rejects_profile_presence_mismatch(self) -> None:
        legacy: dict[str, Any] = {
            'schemaVersion': 1,
            'release': {
                'tag': 'v1.139.1-web.2',
                'commit': 'a' * 40,
            },
            'distribution': {'treeSha256': 'b' * 64},
            'deploymentProfile': None,
        }
        profiled = copy.deepcopy(legacy)
        profiled['deploymentProfile'] = {
            'id': 'company-standard',
            'configSha256': 'c' * 64,
        }

        with self.assertRaisesRegex(
            BuildError,
            'does not match expected promotion identity',
        ):
            promotion.verify_pages_deployment_identity(legacy, profiled)
        with self.assertRaisesRegex(
            BuildError,
            'does not match expected promotion identity',
        ):
            promotion.verify_pages_deployment_identity(profiled, legacy)

    def test_build_identity_rejects_tag_manifest_version_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            policy, manifest, checksums, archive = self.write_fixture(Path(td))
            with self.assertRaisesRegex(BuildError, 'version does not match'):
                promotion.build_identity(
                    release_tag='v1.141.0-web.0',
                    release_commit='a' * 40,
                    release_id=42,
                    manifest_path=manifest,
                    checksums_path=checksums,
                    archive_path=archive,
                    policy_path=policy,
                )

    def test_policy_requires_automatic_canary_then_stable(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            policy, _, _, _ = self.write_fixture(Path(td))
            data = json.loads(policy.read_text(encoding='utf-8'))
            data['automatic']['enabled'] = False
            policy.write_text(json.dumps(data), encoding='utf-8')
            with self.assertRaisesRegex(BuildError, 'must remain automatic'):
                promotion.load_promotion_policy(policy)


class PromotionWorkflowTests(unittest.TestCase):
    def test_promotion_workflow_preserves_immutable_release_boundary(self) -> None:
        workflow = (ROOT / '.github/workflows/promote.yml').read_text(encoding='utf-8')
        release = (ROOT / '.github/workflows/release.yml').read_text(encoding='utf-8')
        recovery = (ROOT / '.github/workflows/recover-release-publication.yml').read_text(
            encoding='utf-8'
        )
        pages_action = (ROOT / '.github/actions/publish-pages/action.yml').read_text(
            encoding='utf-8'
        )

        self.assertNotIn('./build.sh', workflow)
        self.assertNotIn('package.sh', workflow)
        self.assertNotIn('actions/attest@', workflow)
        self.assertIn('gh release download', workflow)
        self.assertIn('gh attestation verify', workflow)
        self.assertIn('scripts/promotion.py', workflow)
        self.assertIn('--argjson identity "$target_identity"', workflow)
        self.assertIn('--argjson releaseArtifact "$target_release_artifact"', workflow)
        self.assertIn('[.[] | select(.state == "success")] | length', workflow)
        self.assertIn('environment: "canary"', workflow)
        self.assertIn('environment: "stable"', workflow)
        self.assertIn('automatic promotion refuses to move stable backward', workflow)
        self.assertIn('previous stable deployment history', workflow)
        self.assertIn('environment=github-pages&ref=$RELEASE_COMMIT', workflow)
        self.assertIn('uses: ./.github/actions/publish-pages', workflow)
        self.assertIn('scripts/pages_identity.py write', workflow)
        self.assertIn(
            'cp .work/promotion/pages-deployment-identity.json dist/deployment-identity.json',
            workflow,
        )
        self.assertIn(
            'identity-path: .work/promotion/pages-deployment-identity.json',
            workflow,
        )
        self.assertIn('commit: ${{ needs.authorize.outputs.release-commit }}', workflow)

        self.assertNotIn('uses: ./.github/actions/publish-pages', release)
        self.assertIn('immutable-publication-status:', release)
        self.assertIn('gh workflow run promote.yml', release)
        self.assertIn('--ref "$GITHUB_REF_NAME"', release)
        self.assertIn('-f target=auto', release)

        self.assertNotIn('uses: ./.github/actions/publish-pages', recovery)
        self.assertIn('pages/deployments/$GITHUB_SHA', pages_action)
        self.assertIn('DEPLOYED_URL: ${{ steps.deployment.outputs.page_url }}', pages_action)
        self.assertIn('deployment-identity.json?promotion_run=$GITHUB_RUN_ID', pages_action)
        self.assertIn('Cache-Control: no-cache', pages_action)
        self.assertIn('scripts/pages_identity.py verify', pages_action)
        self.assertNotIn('deployments?environment=github-pages', pages_action)
        self.assertNotIn('steps.state.outputs.complete', pages_action)

        import check_policy

        check_policy.check_promotion_boundaries()


if __name__ == '__main__':
    unittest.main()
