from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import deployment_profile  # noqa: E402
import validate_config  # noqa: E402
import validate_json_schema  # noqa: E402
from common import BuildError  # noqa: E402


class DeploymentProfileTests(unittest.TestCase):
    def test_selected_profile_preserves_current_company_policy(self):
        profile = deployment_profile.load_selected_profile()
        self.assertEqual(profile['id'], 'company-standard')
        self.assertEqual(profile['documents']['runtime']['telemetry'], False)
        self.assertEqual(profile['documents']['network']['allowedOrigins'], ['self'])
        self.assertEqual(profile['documents']['webview']['mode'], 'disabled')
        self.assertEqual(
            profile['documents']['proposedApi']['grants'],
            {'hrashton.remotish': ['scmHistoryProvider', 'timeline']},
        )

    def test_baseline_static_has_no_proposed_api_exceptions(self):
        profile = deployment_profile.load_profile('baseline-static')
        self.assertEqual(profile['documents']['proposedApi']['grants'], {})
        self.assertEqual(profile['documents']['network']['default'], 'deny')
        self.assertEqual(profile['documents']['network']['allowedOrigins'], ['self'])
        self.assertEqual(profile['documents']['webview']['mode'], 'disabled')

    def test_profile_digest_is_stable_and_covers_referenced_inputs(self):
        first = deployment_profile.load_selected_profile()
        second = deployment_profile.load_selected_profile()
        self.assertEqual(first['configSha256'], second['configSha256'])

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for relative in (
                'config/deployment.json',
                'config/profiles/company-standard.json',
                'config/policies/runtime/static.json',
                'config/policies/network/static.json',
                'config/policies/product/static.json',
                'config/policies/proposed-api/company-standard.json',
                'config/policies/webview/disabled.json',
                'config/policies/branding/default.json',
                'config/policies/support/default.json',
                'extensions/extensions.lock.json',
                'extensions/license-policy.json',
                'extensions/source-policy.json',
            ):
                source = ROOT / relative
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            before = deployment_profile.load_selected_profile(root=root)['configSha256']
            runtime = root / 'config/policies/runtime/static.json'
            data = json.loads(runtime.read_text())
            data['productName'] = 'Changed'
            runtime.write_text(json.dumps(data) + '\n')
            after = deployment_profile.load_selected_profile(root=root)['configSha256']
            self.assertNotEqual(before, after)

    def test_disabled_webview_url_requires_reserved_hostname(self):
        good = {
            'schemaVersion': 1,
            'mode': 'disabled',
            'externalBaseUrlTemplate': (
                'https://{{uuid}}.invalid.invalid/out/vs/workbench/contrib/webview/browser/pre/'
            ),
        }
        validate_config.validate_webview_policy(good)

        schema = json.loads((ROOT / 'schemas/webview-policy.schema.json').read_text())
        for template in (
            'https://example.com/invalid.invalid/out/',
            'https://invalid.invalid.example.com/out/',
            'http://uuid.invalid.invalid/out/',
        ):
            policy = dict(good)
            policy['externalBaseUrlTemplate'] = template
            with self.assertRaises(BuildError):
                validate_config.validate_webview_policy(policy)
            with self.assertRaises(BuildError):
                validate_json_schema._validate(policy, schema, 'webview policy')

    def test_unknown_profile_and_path_escape_fail_closed(self):
        with self.assertRaisesRegex(BuildError, 'unknown deployment profile'):
            deployment_profile.load_profile('does-not-exist')

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / 'config/profiles').mkdir(parents=True)
            profile = json.loads((ROOT / 'config/profiles/baseline-static.json').read_text())
            profile['id'] = 'escape'
            profile['bindings']['branding'] = '../outside.json'
            (root / 'config/profiles/escape.json').write_text(json.dumps(profile))
            with self.assertRaisesRegex(BuildError, 'must not traverse parents'):
                deployment_profile.load_profile('escape', root=root)


if __name__ == '__main__':
    unittest.main()
