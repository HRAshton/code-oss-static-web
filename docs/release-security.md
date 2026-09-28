# Release security

The pipeline separates upstream build execution from attestation and publication.
Build/test jobs are read-only and hold no release credentials. Attestation/publish jobs will
consume only completed, verified artifacts.

Packaging emits deterministic tar/zip archives, `SHA256SUMS`, `artifact-manifest.json`, and a
CycloneDX 1.7 `sbom.cdx.json`. The artifact manifest binds the release to the project commit,
pinned upstream commit, distribution tree digest, patch/configuration/extension-lock inputs,
runtime component metadata, and the exact archive/SBOM digests and sizes.

The SBOM is generated from the final static distribution plus runtime metadata captured from the
pinned upstream package lock. It covers shipped npm packages and packaged extensions and is
validated by `scripts/verify_release.py`.

Development qualification may reuse the content-addressed upstream web-build cache. A future
attested release workflow must use a clean build path before provenance generation; cache hits are
an optimization and are not release provenance.

Remaining release-security gates are provenance attestation/signing, artifact-level license
inventory, protected-environment publication, and the canonical GitHub Release/Pages/OCI publish
flow.
