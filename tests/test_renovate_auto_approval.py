from __future__ import annotations

import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

MOCK_GH = """#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

args = sys.argv[1:]
endpoint = next((arg for arg in args if arg.startswith('repos/')), '')
if '--method' in args:
    Path(os.environ['APPROVAL_MARKER']).write_text('approved', encoding='utf-8')
elif endpoint.endswith('/files'):
    mode = os.environ['FILE_LIST_MODE']
    if mode in ('allowed', 'mixed', 'partial_error'):
        print('upstream.lock.json')
    if mode in ('denied', 'mixed'):
        print('deploy/Dockerfile')
    if mode in ('api_error', 'partial_error'):
        print('Simulated GitHub API failure', file=sys.stderr)
        sys.exit(1)
elif endpoint.endswith('/reviews'):
    print('0')
elif endpoint.endswith('/pulls'):
    print(json.dumps([{
        'number': 42,
        'state': 'open',
        'user': {'login': 'renovate[bot]'},
        'head': {
            'sha': os.environ['SOURCE_SHA'],
            'repo': {'full_name': os.environ['GITHUB_REPOSITORY']},
        },
    }]))
else:
    print('Unexpected gh invocation: ' + str(args), file=sys.stderr)
    sys.exit(2)
"""


class RenovateAutoApprovalTests(unittest.TestCase):
    def test_file_list_must_be_successful_nonempty_and_allowlisted(self) -> None:
        workflow = (ROOT / '.github/workflows/renovate-auto-approve.yml').read_text(
            encoding='utf-8'
        )
        approve_step = workflow.split('      - name: Approve trusted Renovate update\n', 1)[1]
        run = approve_step.split('        run: |\n', 1)[1].split('\n      - name:', 1)[0]
        script = textwrap.dedent(run)

        cases = {
            'allowed': True,
            'api_error': False,
            'partial_error': False,
            'empty': False,
            'denied': False,
            'mixed': False,
        }
        with tempfile.TemporaryDirectory() as tmp:
            tools = Path(tmp)
            gh = tools / 'gh'
            gh.write_text(MOCK_GH, encoding='utf-8')
            gh.chmod(0o755)
            for mode, should_approve in cases.items():
                with self.subTest(mode=mode):
                    marker = tools / f'{mode}-approved'
                    env = os.environ.copy()
                    env.update(
                        {
                            'PATH': os.pathsep.join((str(tools), env['PATH'])),
                            'GITHUB_REPOSITORY': 'HRAshton/code-oss-static-web',
                            'SOURCE_SHA': 'a' * 40,
                            'GH_TOKEN': 'test-token',
                            'FILE_LIST_MODE': mode,
                            'APPROVAL_MARKER': str(marker),
                        }
                    )
                    result = subprocess.run(
                        ['bash', '-c', script],
                        cwd=ROOT,
                        env=env,
                        text=True,
                        capture_output=True,
                        check=False,
                    )
                    self.assertEqual(
                        result.returncode == 0,
                        should_approve,
                        f'{mode}: stdout={result.stdout!r} stderr={result.stderr!r}',
                    )
                    self.assertEqual(marker.exists(), should_approve)


if __name__ == '__main__':
    unittest.main()
