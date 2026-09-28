#!/usr/bin/env bash
set -euo pipefail
python3 "$(dirname "$0")/scripts/package_release.py"
python3 "$(dirname "$0")/scripts/verify_release.py" "$(dirname "$0")/artifacts"
