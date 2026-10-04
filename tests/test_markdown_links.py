from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import check_markdown_links  # noqa: E402
from common import BuildError  # noqa: E402


class MarkdownLinkTests(unittest.TestCase):
    def test_relative_file_and_directory_links_resolve(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            docs = root / 'docs'
            docs.mkdir()
            (root / 'README.md').write_text('[docs](docs/)\n')
            (docs / 'guide.md').write_text('[root](../README.md#section)\n')
            self.assertEqual(
                check_markdown_links.find_broken_links(
                    [root / 'README.md', docs / 'guide.md'],
                    root=root,
                ),
                [],
            )

    def test_broken_relative_link_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            markdown = root / 'README.md'
            markdown.write_text('[missing](docs/missing.md)\n')
            broken = check_markdown_links.find_broken_links([markdown], root=root)
            self.assertEqual(
                broken,
                ['README.md -> docs/missing.md (missing docs/missing.md)'],
            )

    def test_external_anchor_and_fenced_examples_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            markdown = root / 'README.md'
            markdown.write_text(
                '[anchor](#local)\n'
                '[external](https://example.com/missing)\n'
                '~~~md\n[example](not-real.md)\n~~~\n'
            )
            self.assertEqual(
                check_markdown_links.find_broken_links([markdown], root=root),
                [],
            )

    def test_reference_and_root_relative_links_are_checked(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            docs = root / 'docs'
            docs.mkdir()
            target = docs / 'guide.md'
            target.write_text('# Guide\n', encoding='utf-8')
            markdown = root / 'README.md'
            content = '[guide][g]\n[root](/docs/guide.md)\n[g]: docs/guide.md "Guide"\n'
            markdown.write_text(content, encoding='utf-8')
            self.assertEqual(
                check_markdown_links.find_broken_links([markdown], root=root),
                [],
            )

    def test_balanced_parentheses_and_angle_destinations_with_spaces(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            docs = root / 'docs'
            docs.mkdir()
            (docs / 'Guide_(local).md').write_text('# Balanced\n', encoding='utf-8')
            (docs / 'Guide (local).md').write_text('# Spaced\n', encoding='utf-8')
            markdown = root / 'README.md'
            content = (
                '[balanced](docs/Guide_(local).md)\n'
                '[angle](<docs/Guide (local).md>)\n'
                '[balanced-ref][br]\n'
                '[spaced-ref][sr]\n'
                '[br]: docs/Guide_(local).md "Balanced"\n'
                '[sr]: <docs/Guide (local).md> "Spaced"\n'
            )
            markdown.write_text(content, encoding='utf-8')

            self.assertEqual(
                check_markdown_links.find_broken_links([markdown], root=root),
                [],
            )

    def test_balanced_parentheses_preserve_full_broken_target(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            markdown = root / 'README.md'
            markdown.write_text(
                '[missing](docs/Missing_(local).md)\n',
                encoding='utf-8',
            )
            expected = 'README.md -> docs/Missing_(local).md (missing docs/Missing_(local).md)'
            self.assertEqual(
                check_markdown_links.find_broken_links([markdown], root=root),
                [expected],
            )

    def test_repository_escape_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / 'repo'
            root.mkdir()
            markdown = root / 'README.md'
            markdown.write_text('[escape](../outside.md)\n')
            with self.assertRaisesRegex(BuildError, 'escapes repository'):
                check_markdown_links.find_broken_links([markdown], root=root)

    def test_repository_markdown_links_are_clean(self) -> None:
        paths = check_markdown_links.tracked_markdown(ROOT)
        self.assertEqual(
            check_markdown_links.find_broken_links(paths, root=ROOT),
            [],
        )

    def test_shared_tooling_gate_runs_markdown_validation(self) -> None:
        action = (ROOT / '.github/actions/tooling-checks/action.yml').read_text()
        self.assertIn('name: Repository Markdown links', action)
        self.assertIn('python3 scripts/check_markdown_links.py', action)


if __name__ == '__main__':
    unittest.main()
