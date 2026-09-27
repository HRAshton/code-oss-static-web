# Release security

The intended pipeline separates upstream build execution from attestation and publication.
Build/test jobs are read-only and hold no release credentials. Attestation/publish jobs consume
only the completed artifact.

The first implementation provides deterministic tar/zip generation and checksums. SBOM,
attestation, license-inventory, and protected-environment publication remain subsequent gates.
