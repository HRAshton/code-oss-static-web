# Release security

The pipeline separates upstream build execution from attestation and publication.
Build/test jobs are read-only and hold no release credentials. The attestation job receives only
the completed, verified candidate and has no source checkout or shell/build steps.

Packaging emits deterministic tar/zip archives, `SHA256SUMS`, `artifact-manifest.json`, a
CycloneDX 1.7 `sbom.cdx.json`, and `license-inventory.json`. The artifact manifest binds the
release to the project commit, pinned upstream commit, distribution tree digest,
patch/configuration/extension-lock inputs, runtime component metadata, and exact release-file
digests and sizes.

The SBOM is generated from the final static distribution plus runtime metadata captured from the
pinned upstream package lock. The license inventory uses the same component references and must
cover every SBOM component exactly once. Missing package declarations are represented explicitly as
`NOASSERTION`; they are never silently omitted. Code-OSS's MIT license and upstream third-party
notice file are copied alongside the candidate archives.

After browser qualification and packaging, an isolated OIDC job uses the SHA-pinned
`actions/attest` action to create:

- SLSA build provenance for every file in `SHA256SUMS`;
- an SBOM attestation for the canonical tar.gz and zip archives.

The repository policy rejects attestation jobs that checkout source, execute shell commands, or run
the upstream build. Build jobs are separately prohibited from receiving write/OIDC permissions.

Artifact attestations can be verified with GitHub CLI, for example:

```bash
gh attestation verify code-oss-static-web-1.139.1-web.0.tar.gz \
  --repo HRAshton/code-oss-static-web
```

Development qualification may reuse the content-addressed upstream web-build cache. Cache hits are
an optimization, not provenance. Release publication performs independent clean builds and compares
their normalized distributions before publishing immutable release assets.

Release tags matching `v*-web.*` must be protected by the repository ruleset represented in
`.github/rulesets/immutable-release-tags.json`: active tag targeting, update restriction, deletion
restriction, and no bypass actors. Release authorization also resolves the repository's default
branch and requires the tagged `GITHUB_SHA` to be an ancestor of, or identical to, that branch
before any release build can proceed. This prevents an otherwise-authorized repository writer from
turning an arbitrary off-branch commit into a release merely by creating a matching tag.

All publication paths cross the protected `release` environment boundary after attestation.
The `release` environment is the shared publication authorization boundary and carries the
repository's deployment protection rules. GitHub Release and OCI publication jobs use that
environment directly. Pages first passes through a `pages-release-gate` job on the `release`
environment with no token permissions, then deploys through the separate `github-pages`
environment. The Pages deployment environment does not replace the shared `release` authorization
boundary.

Every GitHub Release, Pages, and OCI publication path additionally checks that the release-tag
ruleset is active and that `GITHUB_REF_NAME` still resolves to the workflow's immutable
`GITHUB_SHA` immediately before publication. Publication fails closed if either invariant is false.
