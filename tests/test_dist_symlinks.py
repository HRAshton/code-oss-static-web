from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import common  # noqa: E402
import package_release  # noqa: E402


class DistributionSymlinkTests(unittest.TestCase):
    def test_distribution_identity_rejects_internal_and_escaping_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dist = root / 'dist'
            dist.mkdir()
            (dist / 'index.html').write_text('ok\n')
            target = dist / 'target.txt'
            target.write_text('inside\n')

            internal = dist / 'internal-link'
            internal.symlink_to(target.name)
            with self.assertRaisesRegex(common.BuildError, 'contains symlink entries'):
                package_release.distribution_tree_digest(dist)
            internal.unlink()

            outside = root / 'outside.txt'
            outside.write_text('outside\n')
            escaping = dist / 'escaping-link'
            escaping.symlink_to(outside)
            with self.assertRaisesRegex(common.BuildError, 'contains symlink entries'):
                package_release.distribution_tree_digest(dist)

    def test_symlink_guard_rejects_broken_and_root_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dist = root / 'dist'
            dist.mkdir()

            broken = dist / 'broken-link'
            broken.symlink_to('missing.txt')
            with self.assertRaisesRegex(common.BuildError, 'contains symlink entries'):
                common.assert_no_symlinks(dist)
            broken.unlink()

            root_link = root / 'dist-link'
            root_link.symlink_to(dist, target_is_directory=True)
            with self.assertRaisesRegex(
                common.BuildError,
                'root must not be a symlink',
            ):
                common.assert_no_symlinks(root_link)

    def test_upstream_build_root_is_checked_before_resolution(self) -> None:
        make_static = (ROOT / 'scripts/make_static.py').read_text()
        source_guard = make_static.index(
            "assert_no_symlinks(source_arg, label='upstream web build')"
        )
        source_resolve = make_static.index('source = source_arg.resolve()')
        self.assertLess(source_guard, source_resolve)
        self.assertNotIn(
            "assert_no_symlinks(source, label='upstream web build')",
            make_static,
        )

        build = (ROOT / 'scripts/build.py').read_text()
        reuse_branch = build.split('if args.reuse_upstream_build:', 1)[1]
        reuse_branch = reuse_branch.split('else:', 1)[0]
        self.assertIn(
            "assert_no_symlinks(built, label='cached upstream web build')",
            reuse_branch,
        )
        self.assertNotIn(
            "require(built.is_dir(), f'cached upstream web build missing: {built}')",
            reuse_branch,
        )

    def test_symlink_free_distribution_identity_still_hashes_files(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            dist = Path(td)
            (dist / 'index.html').write_text('ok\n')
            (dist / 'target.txt').write_text('inside\n')

            digest, count = package_release.distribution_tree_digest(dist)
            self.assertRegex(digest, r'^[0-9a-f]{64}$')
            self.assertEqual(count, 2)

    def test_final_distribution_boundaries_apply_symlink_guard(self) -> None:
        make_static = (ROOT / 'scripts/make_static.py').read_text()
        self.assertIn(
            "assert_no_symlinks(source_arg, label='upstream web build')",
            make_static,
        )
        self.assertIn(
            'final static distribution root must not be a symlink',
            make_static,
        )
        self.assertIn(
            "assert_no_symlinks(output, label='final static distribution')",
            make_static,
        )
        self.assertIn('shutil.copytree(source, output, symlinks=False)', make_static)

        smoke = (ROOT / 'scripts/smoke_static.py').read_text()
        self.assertIn("assert_no_symlinks(root, label='static distribution')", smoke)

        package = (ROOT / 'scripts/package_release.py').read_text()
        self.assertIn("assert_no_symlinks(DIST, label='release distribution')", package)
        self.assertIn(
            "assert_no_symlinks(root, label='distribution identity')",
            package,
        )
        self.assertNotIn(
            "assert_no_symlinks(root, label='release distribution')",
            package,
        )


if __name__ == '__main__':
    unittest.main()
