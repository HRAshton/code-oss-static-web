from __future__ import annotations

import json
import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

MOCK_GH = """#!/usr/bin/env python3
import base64
import json
import os
import sys
from pathlib import Path

args = sys.argv[1:]
endpoint = next((arg for arg in args if arg.startswith('repos/')), '')
mode = os.environ['FILE_LIST_MODE']
paths = (
    'upstream.lock.json',
    'builder-image.json',
)
if '--method' in args:
    Path(os.environ['APPROVAL_MARKER']).write_text('approved', encoding='utf-8')
elif endpoint.endswith('/files'):
    if mode != 'empty':
        print('\\n'.join(paths if mode != 'denied' else ('deploy/Dockerfile',)))
    if mode == 'unexpected':
        print('.github/workflows/ci.yml')
    if mode in ('api_error', 'partial_error'):
        print('Simulated GitHub API failure', file=sys.stderr)
        sys.exit(1)
elif '/contents/' in endpoint:
    path, ref = endpoint.split('/contents/', 1)[1].split('?ref=', 1)
    root = os.environ['BASE_FIXTURE'] if ref == 'b' * 40 else os.environ['HEAD_FIXTURE']
    print(base64.b64encode((Path(root) / path).read_bytes()).decode('ascii'))
elif endpoint.endswith('/pulls/42'):
    print(os.environ['SOURCE_SHA'])
elif endpoint.endswith('/reviews'):
    print('0')
elif endpoint.endswith('/pulls'):
    print(json.dumps([{
        'number': 42,
        'state': 'open',
        'user': {'login': 'renovate[bot]'},
        'base': {'ref': 'master', 'sha': 'b' * 40},
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
    def make_fixtures(self, tmp: Path) -> tuple[Path, Path]:
        base, head = tmp / 'base', tmp / 'head'
        for folder in (base, head):
            (folder / '.github/workflows').mkdir(parents=True)

        upstream = {
            'schemaVersion': 1,
            'tag': '1.141.0',
            'commit': 'a' * 40,
            'sourceDateEpoch': 1790307657,
        }
        for folder, new in ((base, False), (head, True)):
            lock = {**upstream}
            if new:
                lock.update(tag='1.142.0', commit='b' * 40)
            (folder / 'upstream.lock.json').write_text(json.dumps(lock, indent=2) + '\n')
            builder = {
                'schemaVersion': 2,
                'image': 'docker.io/library/ubuntu',
                'digest': 'sha256:' + 'f' * 64,
                'platform': 'linux/amd64',
                'aptSnapshot': '20260105T000000Z' if new else '20260101T000000Z',
            }
            (folder / 'builder-image.json').write_text(json.dumps(builder, indent=2) + '\n')
            stamp = builder['aptSnapshot']
            (folder / '.github/workflows/qualify.yml').write_text(
                f"env:\n  APT_SNAPSHOT: '{stamp}'\n"
            )
            (folder / '.github/workflows/release.yml').write_text(
                f"build:\n  APT_SNAPSHOT: '{stamp}'\nrepro:\n  APT_SNAPSHOT: '{stamp}'\n"
            )
        return base, head

    def test_auto_approval_checks_exact_content_and_api_failures(self) -> None:
        workflow = (ROOT / '.github/workflows/renovate-auto-approve.yml').read_text()
        marker = '      - name: Approve trusted Renovate update\n'
        approve_step = workflow.split(marker, 1)[1]
        run = approve_step.split('        run: |\n', 1)[1].split('\n      - name:', 1)[0]
        script = textwrap.dedent(run)

        cases = {
            'allowed': True,
            'empty': False,
            'denied': False,
            'unexpected': False,
            'api_error': False,
            'partial_error': False,
            'malicious_upstream': False,
            'malicious_builder': False,
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gh = root / 'gh'
            gh.write_text(MOCK_GH)
            gh.chmod(0o755)
            for mode, should_approve in cases.items():
                with self.subTest(mode=mode):
                    base, head = self.make_fixtures(root / mode)
                    if mode == 'malicious_upstream':
                        upstream = head / 'upstream.lock.json'
                        upstream.write_text(
                            upstream.read_text().replace('"schemaVersion": 1', '"schemaVersion": 2')
                        )
                    if mode == 'malicious_builder':
                        builder = head / 'builder-image.json'
                        builder.write_text(
                            builder.read_text().replace('linux/amd64', 'linux/arm64')
                        )
                    marker = root / f'{mode}-approved'
                    env = os.environ.copy()
                    env.update(
                        {
                            'PATH': os.pathsep.join((str(root), env['PATH'])),
                            'GITHUB_REPOSITORY': 'HRAshton/code-oss-static-web',
                            'SOURCE_SHA': 'a' * 40,
                            'GH_TOKEN': 'test-token',
                            'FILE_LIST_MODE': mode,
                            'APPROVAL_MARKER': str(marker),
                            'BASE_FIXTURE': str(base),
                            'HEAD_FIXTURE': str(head),
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
