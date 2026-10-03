# Release security

The pipeline separates upstream build execution from attestation and publication.
Build/test jobs are read-only and hold no release credentials. The attestation job receives only
the completed, verified candidate and has no source checkout or shell/build steps.

Packaging emits deterministic tar/zip archives, `SHA256SUMS`, `artifact-manifest.json`, a
CycloneDX 1.7 `sbom.cdx.json`, and `license-inventory.json`. The artifact manifest binds the
release to the project commit, pinned upstream commit, canonical Node/Python toolchain versions and toolchain-manifest digest,
distribution tree digest, patch/configuration/extension-lock inputs, runtime component metadata, and exact release-file
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
repository's deployment protection rules. The qualification release job crosses that boundary
before creating the immutable release tag and dispatching publication. GitHub Release and OCI
publication jobs use the environment directly. Pages first passes through a `pages-release-gate`
job on the `release` environment with no token permissions, then deploys through the separate
`github-pages` environment. The Pages deployment environment does not replace the shared
`release` authorization boundary.

Every GitHub Release, Pages, and OCI publication path additionally checks that the release-tag
ruleset is active and that `GITHUB_REF_NAME` still resolves to the workflow's immutable
`GITHUB_SHA` immediately before publication. Publication fails closed if either invariant is false.

Publication is retry-safe per channel. The normal Release workflow and the recovery workflow share
the same channel implementations and the same `release-${ref}` concurrency group. GitHub Release
publication reconciles assets monotonically: matching published assets are verification-only, and
only an interrupted draft may add missing expected assets before publication. Conflicting,
unexpected, or incomplete published asset sets fail closed. Pages treats a successful deployment
for the immutable release commit as complete before creating another deployment. GHCR verifies the
existing release tag, release labels, multi-platform manifest, and every canonical static file; it
publishes only after the registry explicitly reports that the tag is absent, while indeterminate
registry failures abort without pushing.

`Recover release publication` accepts the completed source Release workflow-run ID, verifies that
all pre-publication preparation jobs succeeded, and downloads retained `release-static-dist`,
`release-candidate`, and/or `release-attestation` artifacts as required by the selected channel. It
contains no upstream build, package, or attestation step. GitHub Release existence is therefore not
used as a proxy for Pages or GHCR completion; each channel is verified independently.
