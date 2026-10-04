from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import compare_sbom_inventory
from common import BuildError


class IndependentSbomComparisonTests(unittest.TestCase):
    def policy(self) -> dict[str, Any]:
        return {
            'schemaVersion': 1,
            'scanner': {'name': 'syft', 'version': '1.48.0'},
            'exceptions': [],
        }

    def native_sbom(self, *, include_beta: bool = True) -> dict[str, Any]:
        components: list[dict[str, Any]] = [
            {
                'type': 'application',
                'bom-ref': 'code-oss:' + '0' * 40,
                'name': 'Code - OSS',
                'version': '1.140.0',
            },
            {
                'type': 'library',
                'bom-ref': 'pkg:npm/alpha@1.0.0',
                'name': 'alpha',
                'version': '1.0.0',
                'purl': 'pkg:npm/alpha@1.0.0',
                'properties': [
                    {
                        'name': 'code-oss-static-web:artifactPath',
                        'value': 'node_modules/alpha',
                    }
                ],
            },
            {
                'type': 'library',
                'bom-ref': 'vscode-extension:demo.fixture@1.2.3',
                'group': 'demo',
                'name': 'fixture',
                'version': '1.2.3',
                'properties': [
                    {
                        'name': 'code-oss-static-web:extensionId',
                        'value': 'demo.fixture',
                    },
                    {
                        'name': 'code-oss-static-web:artifactPath',
                        'value': 'extensions/demo.fixture',
                    },
                ],
            },
        ]
        if include_beta:
            components.append(
                {
                    'type': 'library',
                    'bom-ref': 'pkg:npm/beta@2.0.0',
                    'name': 'beta',
                    'version': '2.0.0',
                    'purl': 'pkg:npm/beta@2.0.0',
                    'properties': [
                        {
                            'name': 'code-oss-static-web:artifactPath',
                            'value': 'node_modules/beta',
                        }
                    ],
                }
            )
        return {
            'bomFormat': 'CycloneDX',
            'specVersion': '1.7',
            'components': components,
        }

    def independent_sbom(self) -> dict[str, Any]:
        return {
            'bomFormat': 'CycloneDX',
            'specVersion': '1.6',
            'metadata': {
                'tools': {
                    'components': [
                        {
                            'type': 'application',
                            'name': 'syft',
                            'version': '1.48.0',
                        }
                    ]
                }
            },
            'components': [
                {
                    'type': 'application',
                    'bom-ref': 'pkg:npm/Code%20-%20OSS@1.140.0?package-id=code-oss',
                    'name': 'Code - OSS',
                    'version': '1.140.0',
                    'purl': 'pkg:npm/Code%20-%20OSS@1.140.0',
                    'properties': [
                        {'name': 'syft:package:foundBy', 'value': 'javascript-package-cataloger'},
                        {'name': 'syft:location:0:path', 'value': '/package.json'},
                    ],
                },
                {
                    'type': 'library',
                    'bom-ref': 'pkg:npm/alpha@1.0.0?package-id=alpha',
                    'name': 'alpha',
                    'version': '1.0.0',
                    'purl': 'pkg:npm/alpha@1.0.0',
                    'properties': [
                        {'name': 'syft:package:foundBy', 'value': 'javascript-package-cataloger'},
                        {
                            'name': 'syft:location:0:path',
                            'value': '/node_modules/alpha/package.json',
                        },
                    ],
                },
                {
                    'type': 'library',
                    'bom-ref': 'pkg:npm/beta@2.0.0?package-id=beta',
                    'name': 'beta',
                    'version': '2.0.0',
                    'purl': 'pkg:npm/beta@2.0.0',
                    'properties': [
                        {'name': 'syft:package:foundBy', 'value': 'javascript-package-cataloger'},
                        {
                            'name': 'syft:location:0:path',
                            'value': '/node_modules/beta/package.json',
                        },
                    ],
                },
                {
                    'type': 'library',
                    'bom-ref': 'pkg:npm/fixture@1.2.3?package-id=fixture',
                    'name': 'fixture',
                    'version': '1.2.3',
                    'purl': 'pkg:npm/fixture@1.2.3',
                    'properties': [
                        {'name': 'syft:package:foundBy', 'value': 'javascript-package-cataloger'},
                        {
                            'name': 'syft:location:0:path',
                            'value': '/extensions/demo.fixture/package.json',
                        },
                    ],
                },
                {
                    'type': 'file',
                    'bom-ref': 'file:ignored',
                    'name': '/index.html',
                },
            ],
        }

    def test_baseline_component_sets_match_with_explicit_synthetic_exception(self) -> None:
        inventory, report = compare_sbom_inventory.compare_documents(
            self.native_sbom(),
            self.independent_sbom(),
            self.policy(),
        )

        self.assertEqual(report['status'], 'pass')
        self.assertEqual(report['summary']['matchedComponents'], 4)
        self.assertEqual(report['summary']['appliedExceptions'], 0)
        self.assertEqual(report['unexplainedMissingFromNative'], [])
        self.assertEqual(report['unexplainedMissingFromIndependent'], [])
        self.assertEqual(len(inventory['components']), 4)

    def test_independent_scanner_catches_component_omitted_by_native_generator(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            native = root / 'native.json'
            independent = root / 'independent.json'
            policy = root / 'policy.json'
            inventory = root / 'inventory.json'
            comparison = root / 'comparison.json'
            native.write_text(json.dumps(self.native_sbom(include_beta=False)), encoding='utf-8')
            independent.write_text(json.dumps(self.independent_sbom()), encoding='utf-8')
            policy.write_text(json.dumps(self.policy()), encoding='utf-8')

            with self.assertRaisesRegex(BuildError, 'missing from native SBOM'):
                compare_sbom_inventory.compare_files(
                    native,
                    independent,
                    policy,
                    inventory,
                    comparison,
                )

            report = json.loads(comparison.read_text(encoding='utf-8'))
            self.assertEqual(report['status'], 'fail')
            self.assertEqual(report['summary']['unexplainedMissingFromNative'], 1)
            missing = report['unexplainedMissingFromNative'][0]
            self.assertEqual(missing['purl'], 'pkg:npm/beta@2.0.0')
            self.assertEqual(missing['path'], 'node_modules/beta')

    def test_empty_independent_scan_fails_closed(self) -> None:
        independent = self.independent_sbom()
        independent.pop('components')

        with self.assertRaisesRegex(
            BuildError,
            'independent SBOM discovered no software components',
        ):
            compare_sbom_inventory.compare_documents(
                self.native_sbom(),
                independent,
                self.policy(),
            )

    def test_scanner_version_must_match_reviewed_policy(self) -> None:
        independent = self.independent_sbom()
        metadata = independent['metadata']
        self.assertIsInstance(metadata, dict)
        tools = metadata['tools']
        self.assertIsInstance(tools, dict)
        components = tools['components']
        self.assertIsInstance(components, list)
        tool = components[0]
        self.assertIsInstance(tool, dict)
        tool['version'] = '1.49.0'
        with self.assertRaisesRegex(BuildError, 'independent scanner mismatch'):
            compare_sbom_inventory.compare_documents(
                self.native_sbom(),
                independent,
                self.policy(),
            )


if __name__ == '__main__':
    unittest.main()
