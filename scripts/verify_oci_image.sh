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
served_root=/srv/code-oss-static-web
rm -rf "$work"
mkdir -p "$work"

docker buildx imagetools inspect "$image" --format '{{json .Manifest}}' > "$work/manifest.json"
jq -e '
  ([.manifests[] | select(.platform.os == "linux" and .platform.architecture == "amd64")] | length) == 1 and
  ([.manifests[] | select(.platform.os == "linux" and .platform.architecture == "arm64")] | length) == 1
' "$work/manifest.json" >/dev/null

containers=()
cleanup() {
  local container
  for container in "${containers[@]}"; do
    docker rm -f "$container" >/dev/null 2>&1 || true
  done
}
trap cleanup EXIT

for arch in amd64 arm64; do
  platform="linux/$arch"
  digest="$(
    jq -er --arg arch "$arch" '
      [.manifests[]
        | select(.platform.os == "linux" and .platform.architecture == $arch)
        | .digest]
      | if length == 1 then .[0] else error("expected exactly one platform child") end
    ' "$work/manifest.json"
  )"
  child="$image@$digest"

  docker pull --platform "$platform" "$child" >/dev/null
  image_id="$(docker image inspect "$child" --format '{{.Id}}')"
  labels="$(docker image inspect "$image_id" --format '{{json .Config.Labels}}')"
  jq -e --arg commit "$commit" --arg tag "$tag" '
    .["org.opencontainers.image.revision"] == $commit and
    .["org.opencontainers.image.version"] == $tag
  ' <<<"$labels" >/dev/null

  platform_dist="$work/$arch/image-dist"
  mkdir -p "$platform_dist"
  container="$(docker create --platform "$platform" "$image_id")"
  containers+=("$container")
  docker cp "$container:$served_root/." "$platform_dist/"

  python3 scripts/compare_dist.py "$dist" "$platform_dist"
done

echo "GHCR publication complete: $image"
