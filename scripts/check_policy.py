#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

from common import ROOT, BuildError, load_json, require

ACTION_REF = re.compile(r"uses:\s*[^@\s]+@([^\s#]+)")
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
JOB_HEADER = re.compile(r"^  ([A-Za-z0-9_-]+):\s*$")
WRITE_PERMISSION = re.compile(r"^\s{6}[A-Za-z0-9-]+:\s*write\s*$", re.MULTILINE)
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
        require(bool(lines) and lines[0] == "#!/usr/bin/env bash", f"{script.name}: bash shebang required")
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


def workflow_job_blocks(text: str) -> list[tuple[str, str]]:
    lines = text.splitlines()
    try:
        jobs_index = lines.index("jobs:")
    except ValueError:
        return []

    blocks: list[tuple[str, str]] = []
    current_name: str | None = None
    current_start = 0

    for index in range(jobs_index + 1, len(lines)):
        match = JOB_HEADER.fullmatch(lines[index])
        if match is None:
            continue
        if current_name is not None:
            blocks.append((current_name, "\n".join(lines[current_start:index])))
        current_name = match.group(1)
        current_start = index

    if current_name is not None:
        blocks.append((current_name, "\n".join(lines[current_start:])))

    return blocks


def check_build_job_block(workflow: Path, job_name: str, block: str) -> None:
    if "./build.sh" not in block:
        return

    display = f"{workflow.relative_to(ROOT)}:{job_name}"
    require(
        re.search(r"^    permissions:\s*$", block, re.MULTILINE) is not None,
        f"{display}: build job must declare explicit permissions",
    )
    require(
        re.search(r"^      contents:\s*read\s*$", block, re.MULTILINE) is not None,
        f"{display}: build job must use contents: read",
    )
    require(
        WRITE_PERMISSION.search(block) is None,
        f"{display}: build job must not receive write permissions",
    )
    require(
        "persist-credentials: false" in block,
        f"{display}: checkout in build job must disable persisted credentials",
    )


def check_build_job_permissions() -> None:
    for workflow in sorted((ROOT / ".github/workflows").glob("*.yml")):
        text = workflow.read_text(encoding="utf-8")
        for job_name, block in workflow_job_blocks(text):
            check_build_job_block(workflow, job_name, block)



def check_attestation_job_block(workflow: Path, job_name: str, block: str) -> None:
    if "actions/attest@" not in block:
        return

    display = f"{workflow.relative_to(ROOT)}:{job_name}"
    require(
        re.search(r"^    permissions:\s*$", block, re.MULTILINE) is not None,
        f"{display}: attestation job must declare explicit permissions",
    )
    require(
        re.search(r"^      contents:\s*read\s*$", block, re.MULTILINE) is not None,
        f"{display}: attestation job must use contents: read",
    )
    require(
        re.search(r"^      id-token:\s*write\s*$", block, re.MULTILINE) is not None,
        f"{display}: attestation job must use id-token: write",
    )
    require(
        re.search(r"^      attestations:\s*write\s*$", block, re.MULTILINE) is not None,
        f"{display}: attestation job must use attestations: write",
    )
    require(
        re.search(r"^      artifact-metadata:\s*write\s*$", block, re.MULTILINE) is not None,
        f"{display}: attestation job must use artifact-metadata: write",
    )
    require("actions/checkout@" not in block, f"{display}: attestation job must not checkout source")
    require("./build.sh" not in block, f"{display}: attestation job must not execute upstream builds")
    require(
        re.search(r"^\s+-?\s*run:\s*", block, re.MULTILINE) is None,
        f"{display}: attestation job must not execute shell commands",
    )


def check_attestation_job_permissions() -> None:
    for workflow in sorted((ROOT / ".github/workflows").glob("*.yml")):
        text = workflow.read_text(encoding="utf-8")
        for job_name, block in workflow_job_blocks(text):
            check_attestation_job_block(workflow, job_name, block)

def main() -> None:
    check_actions()
    check_shell_scripts()
    check_forbidden_execution_patterns()
    check_extension_lock()
    check_build_job_permissions()
    check_attestation_job_permissions()
    print("repository policy: ok")


if __name__ == "__main__":
    try:
        main()
    except BuildError as exc:
        raise SystemExit(str(exc))
