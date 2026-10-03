#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 4 ]]; then
  echo "usage: verify_oci_image.sh <image> <commit> <tag> <dist>" >&2
  exit 2
fi

image="$1"
commit="$2"
tag="$3"
dist="$4"
work=.work/oci-verify
rm -rf "$work"
mkdir -p "$work/image-dist"

docker buildx imagetools inspect "$image" --format '{{json .Manifest}}' > "$work/manifest.json"
jq -e '
  ([.manifests[] | select(.platform.os == "linux" and .platform.architecture == "amd64")] | length) == 1 and
  ([.manifests[] | select(.platform.os == "linux" and .platform.architecture == "arm64")] | length) == 1
' "$work/manifest.json" >/dev/null

docker pull --platform linux/amd64 "$image" >/dev/null
labels="$(docker image inspect "$image" --format '{{json .Config.Labels}}')"
jq -e --arg commit "$commit" --arg tag "$tag" '
  .["org.opencontainers.image.revision"] == $commit and
  .["org.opencontainers.image.version"] == $tag
' <<<"$labels" >/dev/null

container="$(docker create --platform linux/amd64 "$image")"
trap 'docker rm -f "$container" >/dev/null 2>&1 || true' EXIT
docker cp "$container:/usr/share/nginx/html/." "$work/image-dist/"
PYTHONPATH=scripts python3 - "$dist" "$work/image-dist" <<'PY'
from __future__ import annotations

import os
import sys
from pathlib import Path

from common import sha256_file
from package_release import iter_files

expected = Path(sys.argv[1])
image_root = Path(sys.argv[2])
for source in iter_files(expected):
    relative = source.relative_to(expected)
    target = image_root / relative
    if not target.is_file():
        raise SystemExit(f'OCI image is missing static file: {relative.as_posix()}')
    if sha256_file(source) != sha256_file(target):
        raise SystemExit(f'OCI static file digest mismatch: {relative.as_posix()}')
    expected_executable = bool(source.stat().st_mode & 0o111)
    actual_executable = bool(target.stat().st_mode & 0o111)
    if actual_executable != expected_executable:
        raise SystemExit(f'OCI static file mode mismatch: {relative.as_posix()}')
PY
echo "GHCR publication complete: $image"
