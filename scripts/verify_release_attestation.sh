#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" != 3 ]]; then
  echo 'usage: verify_release_attestation.sh ASSET RELEASE_TAG REPOSITORY' >&2
  exit 2
fi

asset="$1"
tag="$2"
repository="$3"
if [[ "$repository" != Codellei/code-oss-static-web ]]; then
  echo 'untrusted release repository' >&2
  exit 1
fi

if [[ "$tag" == v1.140.0-web.0 ]]; then
  # This is the Pages root carried through the native repository transfer.
  # Its original signer remains HRAshton; GitHub no longer indexes that attestation online.
  release_id="$(gh api "repos/$repository/releases/tags/$tag" --jq .id)"
  commit="$(gh api "repos/$repository/commits/$tag" --jq .sha)"
  if [[ "$release_id" != 402435131 ||
        "$commit" != f9a2f279e7ec81ecacb7d9705d534c86b3129674 ]]; then
    echo 'legacy Pages release identity changed' >&2
    exit 1
  fi

  case "$(basename "$asset")" in
    artifact-manifest.json)
      expected=e47ac77660fd1d29194efc5e7ce830b611f37b2e47bf3b445ca608de14a00c53
      ;;
    code-oss-static-web-1.140.0-web.0.tar.gz)
      expected=69ca20c182823e9cbf8241a9d5f019daf7b42a93f68542bc9d63d15a2c5041c4
      ;;
    *)
      echo 'legacy attestation is allowed only for the existing Pages root assets' >&2
      exit 1
      ;;
  esac
  actual="$(sha256sum "$asset" | awk '{print $1}')"
  if [[ "$actual" != "$expected" ]]; then
    echo 'legacy Pages release asset digest changed' >&2
    exit 1
  fi

  bundle="$(dirname "$asset")/release-provenance.sigstore.json"
  if [[ ! -f "$bundle" ]]; then
    gh release download "$tag" --repo "$repository" \
      --dir "$(dirname "$asset")" --pattern release-provenance.sigstore.json
  fi
  bundle_digest="$(sha256sum "$bundle" | awk '{print $1}')"
  if [[ "$bundle_digest" != 5bccb650cda56e11234640026c3a4649d2ed7f5b7c2d19617923b0f0d0b8896b ]]; then
    echo 'legacy Pages release bundle digest changed' >&2
    exit 1
  fi
  gh attestation verify "$asset" \
    --bundle "$bundle" \
    --repo HRAshton/code-oss-static-web \
    --cert-identity "https://github.com/HRAshton/code-oss-static-web/.github/workflows/release.yml@refs/tags/$tag" \
    >/dev/null
  exit 0
fi

gh attestation verify "$asset" \
  --repo "$repository" \
  --cert-identity "https://github.com/$repository/.github/workflows/release.yml@refs/tags/$tag" \
  >/dev/null
