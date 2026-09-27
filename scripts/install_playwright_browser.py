#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import subprocess
from common import WORK, BuildError, require


def main() -> None:
    parser = argparse.ArgumentParser(description="Install Playwright browsers using the version locked by Code-OSS")
    parser.add_argument("browsers", nargs="+", choices=["chromium", "firefox", "webkit"])
    parser.add_argument("--with-deps", action="store_true")
    args = parser.parse_args()

    cli = WORK / "vscode" / "node_modules" / "playwright" / "cli.js"
    require(cli.is_file(), "Playwright package not found in the qualified Code-OSS checkout; run ./build.sh first")
    node = shutil.which("node")
    require(node is not None, "node executable not found")

    command = [node, str(cli), "install"]
    if args.with_deps:
        command.append("--with-deps")
    command.extend(args.browsers)
    raise SystemExit(subprocess.call(command))


if __name__ == "__main__":
    try:
        main()
    except BuildError as exc:
        raise SystemExit(str(exc))
