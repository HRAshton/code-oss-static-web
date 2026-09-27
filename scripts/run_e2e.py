#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path

from common import ROOT, WORK, BuildError, require


def find_playwright_cli() -> Path:
    candidates = [
        WORK / "vscode" / "node_modules" / "@playwright" / "test" / "cli.js",
        WORK / "vscode" / "node_modules" / "playwright" / "cli.js",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise BuildError(
        "Playwright CLI not found in the qualified Code-OSS checkout; run ./build.sh first"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run browser qualification against a built static distribution")
    parser.add_argument("--project", default="chromium")
    parser.add_argument("--dist", type=Path, default=ROOT / "dist")
    parser.add_argument("--headed", action="store_true")
    args, extra = parser.parse_known_args()

    cli = find_playwright_cli()
    node = shutil.which("node")
    require(node is not None, "node executable not found")
    require((args.dist / "index.html").is_file(), f"static distribution missing: {args.dist}")

    env = os.environ.copy()
    env["CODE_OSS_STATIC_WEB_DIST"] = str(args.dist.resolve())
    env["CODE_OSS_STATIC_WEB_BASE_PATH"] = env.get("CODE_OSS_STATIC_WEB_BASE_PATH", "/code-oss-web/")
    upstream_node_modules = str(WORK / "vscode" / "node_modules")
    env["NODE_PATH"] = upstream_node_modules + (os.pathsep + env["NODE_PATH"] if env.get("NODE_PATH") else "")

    command = [
        node,
        str(cli),
        "test",
        "--config",
        str(ROOT / "tests" / "e2e" / "playwright.config.cjs"),
    ]
    if args.project != "all":
        command.extend(["--project", args.project])
    if args.headed:
        command.append("--headed")
    command.extend(extra)
    raise SystemExit(subprocess.call(command, cwd=ROOT, env=env))


if __name__ == "__main__":
    try:
        main()
    except BuildError as exc:
        raise SystemExit(str(exc))
