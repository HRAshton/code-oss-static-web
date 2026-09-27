#!/usr/bin/env python3
from __future__ import annotations

import re

from common import ROOT, BuildError, load_json, require

ACTION_REF = re.compile(r"uses:\s*[^@\s]+@([^\s#]+)")
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
FORBIDDEN_PATTERNS = {
    "curl-pipe-shell": re.compile(r"\bcurl\b[^\n|]*\|\s*(?:ba)?sh\b"),
    "wget-pipe-shell": re.compile(r"\bwget\b[^\n|]*\|\s*(?:ba)?sh\b"),
    "npx": re.compile(r"(^|[;&|\s])npx\s+"),
    "pnpm-dlx": re.compile(r"\bpnpm\s+dlx\s+"),
    "npm-exec": re.compile(r"\bnpm\s+exec\s+"),
}


def check_actions() -> None:
    for workflow in sorted((ROOT / ".github/workflows").glob("*.yml")):
        for line_number, line in enumerate(workflow.read_text(encoding="utf-8").splitlines(), 1):
            match = ACTION_REF.search(line)
            if match:
                require(
                    FULL_SHA.fullmatch(match.group(1)) is not None,
                    f"{workflow.relative_to(ROOT)}:{line_number}: action must use a full commit SHA",
                )


def check_shell_scripts() -> None:
    for script in (ROOT / "build.sh", ROOT / "package.sh"):
        lines = script.read_text(encoding="utf-8").splitlines()
        require(lines and lines[0] == "#!/usr/bin/env bash", f"{script.name}: bash shebang required")
        require(
            any(line.strip() == "set -euo pipefail" for line in lines[:5]),
            f"{script.name}: set -euo pipefail required near the top",
        )


def check_forbidden_execution_patterns() -> None:
    paths = [ROOT / "build.sh", ROOT / "package.sh"]
    paths.extend(sorted((ROOT / "scripts").glob("*.py")))
    paths.extend(sorted((ROOT / ".github/workflows").glob("*.yml")))
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for name, pattern in FORBIDDEN_PATTERNS.items():
            require(pattern.search(text) is None, f"{path.relative_to(ROOT)}: forbidden pattern: {name}")


def check_extension_lock() -> None:
    lock = load_json(ROOT / "extensions/extensions.lock.json")
    for extension in lock.get("extensions", []):
        require(extension.get("version") != "latest", "extension lock must not use version=latest")
        require(extension.get("sha256") != "latest", "extension lock must not use mutable hashes")


def main() -> None:
    check_actions()
    check_shell_scripts()
    check_forbidden_execution_patterns()
    check_extension_lock()
    print("repository policy: ok")


if __name__ == "__main__":
    try:
        main()
    except BuildError as exc:
        raise SystemExit(str(exc))
