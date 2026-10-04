from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('classify_pr', ROOT / 'scripts/classify_pr.py')
assert SPEC is not None and SPEC.loader is not None
classify_pr = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(classify_pr)


class PullRequestQualificationTests(unittest.TestCase):
    def test_documentation_only_changes_stay_lightweight(self):
        self.assertEqual(
            classify_pr.classify_paths(
                [
                    'README.md',
                    'OPERATIONS.md',
                    'docs/testing.md',
                    '.github/ISSUE_TEMPLATE/bug.md',
                ]
            ),
            'lightweight',
        )

    def test_release_only_changes_use_release_qualification(self):
        paths = (
            'scripts/promotion.py',
            'scripts/pages_identity.py',
            'scripts/publish_github_release.py',
            '.github/workflows/promote.yml',
            '.github/workflows/recover-release-publication.yml',
            '.github/actions/publish-pages/action.yml',
            '.github/actions/publish-github-release/action.yml',
        )
        for path in paths:
            with self.subTest(path=path):
                self.assertEqual(classify_pr.classify_paths([path]), 'release')

    def test_distribution_dependent_release_paths_require_artifact_integration(self):
        paths = (
            'package.sh',
            'pyproject.toml',
            'scripts/package_release.py',
            'scripts/generate_sbom.py',
            'scripts/generate_license_inventory.py',
            'scripts/generate_runtime_metadata.py',
            'scripts/compare_sbom_inventory.py',
            'scripts/verify_release.py',
            'scripts/verify_oci_image.sh',
            '.github/actions/independent-sbom/action.yml',
            '.github/actions/publish-oci/action.yml',
            'security/sbom-comparison-policy.json',
            'schemas/sbom-comparison-policy.schema.json',
            'tests/test_independent_sbom.py',
        )
        for path in paths:
            with self.subTest(path=path):
                self.assertEqual(classify_pr.classify_paths([path]), 'artifact')

    def test_release_workflow_keeps_full_qualification(self):
        self.assertEqual(classify_pr.classify_paths(['.github/workflows/release.yml']), 'full')

    def test_release_and_documentation_changes_stay_release_only(self):
        self.assertEqual(
            classify_pr.classify_paths(['scripts/promotion.py', 'docs/release-security.md']),
            'release',
        )

    def test_release_changes_mixed_with_runtime_changes_escalate(self):
        self.assertEqual(
            classify_pr.classify_paths(['scripts/promotion.py', 'scripts/make_static.py']),
            'full',
        )
        self.assertEqual(
            classify_pr.classify_paths(['scripts/promotion.py', 'deploy/nginx.conf']),
            'artifact',
        )

    def test_product_affecting_paths_require_artifact_evidence(self):
        paths = (
            'scripts/check_policy.py',
            'config/product-transform.json',
            'extensions/extensions.lock.json',
            'patches/runtime.patch',
            'deploy/Dockerfile',
            'build.sh',
            'package.sh',
            '.github/workflows/ci.yml',
        )
        for path in paths:
            with self.subTest(path=path):
                self.assertNotEqual(classify_pr.classify_paths([path]), 'lightweight')

    def test_runtime_and_security_boundaries_get_full_qualification(self):
        paths = (
            'upstream.lock.json',
            'config/product-transform.json',
            'extensions/extensions.lock.json',
            'patches/runtime.patch',
            'security/network-policy.json',
            'scripts/make_static.py',
            'scripts/deployment_profile.py',
            'scripts/run_e2e.py',
            'scripts/verify_dist_identity.py',
            '.github/workflows/qualify.yml',
            '.github/actions/browser-qualification/action.yml',
        )
        for path in paths:
            with self.subTest(path=path):
                self.assertEqual(classify_pr.classify_paths([path]), 'full')

    def test_unknown_paths_fail_closed_to_artifact_qualification(self):
        self.assertEqual(classify_pr.classify_paths(['new-product-input.toml']), 'artifact')

    def test_mixed_documentation_and_product_change_is_not_lightweight(self):
        self.assertEqual(
            classify_pr.classify_paths(['docs/testing.md', 'deploy/nginx.conf']),
            'artifact',
        )

    def test_empty_file_list_is_rejected(self):
        with self.assertRaises(ValueError):
            classify_pr.classify_paths([])

    def test_workflow_reports_one_stable_artifact_gate_for_every_pull_request(self):
        workflow = (ROOT / '.github/workflows/qualify.yml').read_text(encoding='utf-8')
        pull_request = workflow.split('  pull_request:\n', 1)[1].split(
            '  workflow_dispatch:\n',
            1,
        )[0]

        self.assertNotIn('paths:', pull_request)
        self.assertIn('python3 scripts/classify_pr.py', workflow)
        self.assertIn('.previous_filename // empty', workflow)
        self.assertIn("release)\n                  browsers='[]'", workflow)
        self.assertIn('browsers=\'["chromium"]\'', workflow)
        self.assertIn('browsers=\'["chromium","firefox","webkit"]\'', workflow)
        self.assertIn("needs.browser-plan.outputs.level == 'artifact' ||", workflow)
        self.assertIn('name: Release metadata qualification', workflow)
        self.assertIn('uses: ./.github/actions/release-metadata-qualification', workflow)
        self.assertIn('name: Artifact qualification gate', workflow)
        self.assertIn(
            'needs: [browser-plan, release-metadata, build, browser, package]',
            workflow,
        )
        self.assertIn('required release metadata evidence missing', workflow)
        self.assertIn('PACKAGE_RESULT: ${{ needs.package.result }}', workflow)
        self.assertIn("github.event_name == 'pull_request'", workflow)
        self.assertIn("needs.browser-plan.outputs.level == 'artifact'", workflow)
        self.assertIn('required artifact evidence missing', workflow)
        self.assertIn('uses: ./.github/actions/independent-sbom', workflow)
        self.assertIn('output-file: .work/independent-sbom.cdx.json', workflow)

        attest_block = workflow.split('  attest:\n', 1)[1].split('  release:\n', 1)[0]
        self.assertIn("if: github.event_name != 'pull_request'", attest_block)

    def test_qualification_caches_separate_build_outputs_from_package_downloads(self):
        workflow = (ROOT / '.github/workflows/qualify.yml').read_text(encoding='utf-8')
        cache_key = workflow.split('key: code-oss-web-', 1)[1].split('\n\n      - name:', 1)[0]

        for required in (
            "'upstream.lock.json'",
            "'scripts/prepare_upstream.py'",
            "'scripts/deployment_profile.py'",
            "'scripts/apply_patches.py'",
            "'config/**'",
            "'patches/**'",
        ):
            self.assertIn(required, cache_key)
        self.assertNotIn("'extensions/**'", cache_key)
        self.assertIn('name: Restore npm download cache', workflow)
        self.assertIn('path: ~/.npm', workflow)
        self.assertIn("hashFiles('upstream.lock.json')", workflow)
        self.assertIn('code-oss-npm-', workflow)

    def test_ruleset_documentation_names_the_required_artifact_gate(self):
        contributing = (ROOT / 'CONTRIBUTING.md').read_text(encoding='utf-8')
        self.assertIn('Artifact qualification gate', contributing)
        self.assertIn('protected default-branch ruleset', contributing)


if __name__ == '__main__':
    unittest.main()
