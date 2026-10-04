#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
independent_sbom="$ROOT/.work/independent-sbom.cdx.json"
if [[ ! -f "$independent_sbom" ]]; then
  if ! command -v syft >/dev/null 2>&1; then
    echo "Syft is required to package release composition evidence; expected version is recorded in security/sbom-comparison-policy.json" >&2
    exit 1
  fi
  mkdir -p "$ROOT/.work"
  syft -c "$ROOT/security/syft.yaml" "dir:$ROOT/dist" -o "cyclonedx-json=$independent_sbom"
fi

python3 "$ROOT/scripts/package_release.py"
python3 "$ROOT/scripts/verify_release.py" "$ROOT/artifacts"
