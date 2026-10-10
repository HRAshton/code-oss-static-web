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
        self.assertEqual(workflow.count('scripts/verify_release_attestation.sh'), 3)
        verifier = (ROOT / 'scripts/verify_release_attestation.sh').read_text(encoding='utf-8')
        self.assertIn('gh attestation verify', verifier)
        self.assertIn('--bundle "$bundle"', verifier)
        self.assertIn('--cert-identity', verifier)
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
        self.assertIn('identity-url-path: __canary/${{ inputs.release_tag }}', workflow)
        self.assertIn('needs: [authorize, pages-release-gate]', workflow)
        self.assertIn('Build real canary Pages bundle', workflow)
        self.assertIn('deployments?environment=github-pages&per_page=100', workflow)
        self.assertIn('legacy-pages-identity.json', workflow)
        self.assertIn('pages_identity.py verify', workflow)
        self.assertIn('legacy Pages release tag no longer resolves to deployed commit', workflow)
        self.assertNotIn('deployment_commit="$(jq -r', workflow)
        self.assertIn('for asset in artifact-manifest.json "$stable_archive"', workflow)
        self.assertIn('Browser synthetic against live canary', workflow)
        self.assertIn('commit: ${{ needs.authorize.outputs.release-commit }}', workflow)

        self.assertNotIn('uses: ./.github/actions/publish-pages', release)
        self.assertIn('immutable-publication-status:', release)
        self.assertIn('gh workflow run promote.yml', release)
        self.assertIn('--ref "$GITHUB_REF_NAME"', release)
        self.assertIn('-f target=auto', release)

        self.assertNotIn('uses: ./.github/actions/publish-pages', recovery)
        self.assertIn('pages/deployments/$GITHUB_SHA', pages_action)
        self.assertIn('DEPLOYED_URL: ${{ steps.deployment.outputs.page_url }}', pages_action)
        self.assertIn('identity-url-path:', pages_action)
        self.assertIn('${identity_path#/}?promotion_run=$GITHUB_RUN_ID', pages_action)
        self.assertIn('Cache-Control: no-cache', pages_action)
        # The auto canary and stable jobs share a workflow run, so their Pages
        # artifact names must be distinct and selected explicitly by deploy-pages.
        self.assertEqual(workflow.count('artifact-name: github-pages-canary'), 1)
        self.assertEqual(workflow.count('artifact-name: github-pages-stable'), 1)
        self.assertIn('default: github-pages', pages_action)
        self.assertIn('name: ${{ inputs.artifact-name }}', pages_action)
        self.assertIn('artifact_name: ${{ inputs.artifact-name }}', pages_action)
        # A reported Pages deployment can precede CDN identity convergence.
        self.assertIn('for verify_attempt in $(seq 1 24); do', pages_action)
        self.assertIn('if [[ "$verify_attempt" -lt 24 ]]; then', pages_action)
        self.assertIn('sleep 5', pages_action)
        self.assertIn('live Pages deployment identity did not converge', pages_action)
        self.assertIn('scripts/pages_identity.py verify', pages_action)
        self.assertNotIn('deployments?environment=github-pages', pages_action)
        self.assertNotIn('steps.state.outputs.complete', pages_action)

        import check_policy

        check_policy.check_promotion_boundaries()

    def test_canary_bootstraps_from_successful_legacy_pages_without_identity(self) -> None:
        import io
        import os
        import shutil
        import subprocess
        import tarfile
        import textwrap

        workflow = (ROOT / '.github/workflows/promote.yml').read_text(encoding='utf-8')
        step = workflow.split('      - name: Build real canary Pages bundle\n', 1)[1]
        script = textwrap.dedent(
            step.split('        run: |\n', 1)[1].split('\n      - name:', 1)[0]
        )

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            shutil.copytree(ROOT / 'scripts', root / 'scripts')
            # This test exercises Pages root reconstruction; signer verification is separate.
            (root / 'scripts/verify_release_attestation.sh').write_text(
                '#!/usr/bin/env bash\nexit 0\n', encoding='utf-8'
            )
            (root / 'config').mkdir()
            release_dir = root / 'release-source'
            release_dir.mkdir()
            policy, manifest, checksums, archive = PromotionIdentityTests().write_fixture(
                release_dir
            )
            shutil.copy2(policy, root / 'config/promotion-policy.json')

            # An actual immutable release archive, representing the previous live root.
            with tarfile.open(archive, 'w:gz') as tar:
                content = b'legacy homepage'
                entry = tarfile.TarInfo('index.html')
                entry.size = len(content)
                tar.addfile(entry, io.BytesIO(content))
            manifest_data = json.loads(manifest.read_text(encoding='utf-8'))
            archive_sha256 = hashlib.sha256(archive.read_bytes()).hexdigest()
            manifest_data['artifacts'][0]['sha256'] = archive_sha256
            manifest_data['artifacts'][0]['size'] = archive.stat().st_size
            manifest.write_text(json.dumps(manifest_data) + '\n', encoding='utf-8')
            checksums.write_text(
                f'{hashlib.sha256(manifest.read_bytes()).hexdigest()}  artifact-manifest.json\n'
                f'{archive_sha256}  {archive.name}\n',
                encoding='utf-8',
            )
            legacy = promotion.build_identity(
                release_tag='v1.140.0-web.0',
                release_commit='a' * 40,
                release_id=42,
                manifest_path=manifest,
                checksums_path=checksums,
                archive_path=archive,
                policy_path=policy,
            )
            identity_file = root / 'live-identity.json'
            identity_file.write_text(
                json.dumps(promotion.build_pages_deployment_identity(legacy)),
                encoding='utf-8',
            )
            live_index = root / 'live-index.html'
            live_index.write_bytes(b'legacy homepage')

            bin_dir = root / 'bin'
            bin_dir.mkdir()
            stubs = {
                'gh': """#!/usr/bin/env bash
set -euo pipefail
if [[ "$1" == api ]]; then
  case "$2" in
    'repos/Codellei/code-oss-static-web/deployments?environment=stable&per_page=100') exit 0 ;;
    'repos/Codellei/code-oss-static-web/deployments?environment=github-pages&per_page=100') echo 101 ;;
    'repos/Codellei/code-oss-static-web/deployments/101/statuses?per_page=100') echo 1 ;;
    'repos/Codellei/code-oss-static-web/deployments/101')
      printf '{"id":101,"sha":"%s"}\n' "$MOCK_LEGACY_SHA" ;;
    'repos/Codellei/code-oss-static-web/pages') echo 'https://example.invalid/repo/' ;;
    --paginate) printf '%s' "$MOCK_TAGS" ;;
    repos/Codellei/code-oss-static-web/commits/v*-web.*) echo "$MOCK_LEGACY_SHA" ;;
    repos/Codellei/code-oss-static-web/releases/tags/v*-web.*)
      echo '{"id":42,"tag_name":"v1.140.0-web.0","draft":false,"prerelease":false}' ;;
    *) echo "unexpected gh api: $*" >&2; exit 1 ;;
  esac
elif [[ "$1" == release && "$2" == download ]]; then
  shift 3
  dir=''
  while [[ "$#" -gt 0 ]]; do
    case "$1" in
      --dir) dir="$2"; mkdir -p "$dir"; shift 2 ;;
      --pattern) cp "$MOCK_RELEASE_DIR/$2" "$dir/$2"; shift 2 ;;
      *) shift ;;
    esac
  done
elif [[ "$1" == attestation && "$2" == verify ]]; then
  exit 0
else
  echo "unexpected gh invocation: $*" >&2
  exit 1
fi
""",
                'curl': """#!/usr/bin/env bash
output=''
url=''
while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --output) output="$2"; shift 2 ;;
    http*) url="$1"; shift ;;
    *) shift ;;
  esac
done
if [[ "$url" == *'/index.html?'* ]]; then
  cp "$MOCK_LIVE_INDEX" "$output"
else
  if [[ "$MOCK_HTTP_CODE" == 200 ]]; then
    cp "$MOCK_IDENTITY_FILE" "$output"
  else
    printf 'not a deployment identity\n' > "$output"
  fi
  printf '%s' "$MOCK_HTTP_CODE"
fi
""",
                'python3': """#!/usr/bin/env bash
if [[ "$1" == "scripts/smoke_static.py" ]]; then
  exit 0
fi
exec "$SYSTEM_PYTHON" "$@"
""",
            }
            for name, source in stubs.items():
                stub = bin_dir / name
                stub.write_text(source, encoding='utf-8')
                stub.chmod(0o755)

            promotion_input = root / '.work/promotion'
            promotion_input.mkdir(parents=True)
            (promotion_input / 'pages-deployment-identity.json').write_text(
                '{"release":"candidate"}\n', encoding='utf-8'
            )
            with tarfile.open(promotion_input / 'candidate.tar.gz', 'w:gz') as tar:
                candidate = b'candidate homepage'
                entry = tarfile.TarInfo('index.html')
                entry.size = len(candidate)
                tar.addfile(entry, io.BytesIO(candidate))

            env = os.environ.copy()
            env.update(
                {
                    'PATH': f'{bin_dir}:{env["PATH"]}',
                    'SYSTEM_PYTHON': sys.executable,
                    'GITHUB_REPOSITORY': 'Codellei/code-oss-static-web',
                    'GITHUB_RUN_ID': '42',
                    'ARCHIVE_NAME': 'candidate.tar.gz',
                    'RELEASE_TAG': 'v1.141.0-web.0',
                    'MOCK_HTTP_CODE': '404',
                    'MOCK_TAGS': 'v1.140.0-web.0\n',
                    'MOCK_LEGACY_SHA': 'a' * 40,
                    'MOCK_RELEASE_DIR': str(release_dir),
                    'MOCK_LIVE_INDEX': str(live_index),
                    'MOCK_IDENTITY_FILE': str(identity_file),
                }
            )

            def run() -> subprocess.CompletedProcess[str]:
                return subprocess.run(
                    ['bash', '-c', script],
                    cwd=root,
                    env=env,
                    capture_output=True,
                    text=True,
                )

            # The same production root is retained if checks after publication fail.
            result = run()
            self.assertEqual(result.returncode, 0, result.stderr)
            pages = root / '.work/pages-dist'
            self.assertEqual((pages / 'index.html').read_bytes(), live_index.read_bytes())
            self.assertEqual(
                json.loads((pages / 'deployment-identity.json').read_text(encoding='utf-8')),
                json.loads(identity_file.read_text(encoding='utf-8')),
            )
            canary = pages / '__canary/v1.141.0-web.0'
            self.assertEqual((canary / 'index.html').read_bytes(), b'candidate homepage')
            self.assertTrue((canary / 'deployment-identity.json').is_file())
            self.assertNotIn('No stable release', (pages / 'index.html').read_text())

            # Unknown release, ambiguous release or divergent root: refuse to publish.
            for tags, live_bytes, error in (
                ('', b'legacy homepage', 'no immutable release matches'),
                (
                    'v1.140.0-web.0\nv1.139.1-web.1\n',
                    b'legacy homepage',
                    'multiple immutable releases match',
                ),
                ('v1.140.0-web.0\n', b'different production root', 'root does not match'),
            ):
                with self.subTest(error=error):
                    env['MOCK_TAGS'] = tags
                    live_index.write_bytes(live_bytes)
                    result = run()
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(error, result.stderr)
                    self.assertFalse((pages / '__canary').exists())

            env['MOCK_TAGS'] = 'v1.140.0-web.0\n'
            live_index.write_bytes(b'legacy homepage')
            env['MOCK_HTTP_CODE'] = '500'
            result = run()
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('HTTP 500', result.stderr)

            # Valid identities use the existing exact verification; malformed 200 fails.
            env['MOCK_HTTP_CODE'] = '200'
            result = run()
            self.assertEqual(result.returncode, 0, result.stderr)
            identity_file.write_text('not json', encoding='utf-8')
            result = run()
            self.assertNotEqual(result.returncode, 0)


if __name__ == '__main__':
    unittest.main()
