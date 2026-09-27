# Release security

The intended pipeline separates upstream build execution from attestation and publication.
Build/test jobs are read-only and hold no release credentials. Attestation/publish jobs consume
only the completed artifact.

Packaging emits deterministic tar/zip archives, `SHA256SUMS`, and
`artifact-manifest.json`. The artifact manifest binds the release to the project commit,
pinned upstream commit, distribution tree digest, patch/configuration/extension-lock inputs,
and the exact archive digests and sizes.

SBOM, provenance attestation, license-inventory, and protected-environment publication remain
subsequent gates.
