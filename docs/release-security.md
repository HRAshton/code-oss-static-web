# Release security

The pipeline separates upstream build execution from attestation and publication.
Build/test jobs are read-only and hold no release credentials. The attestation job receives only
the completed, verified candidate and has no source checkout or shell/build steps.

Packaging emits deterministic tar/zip archives, `SHA256SUMS`, `artifact-manifest.json`, a
CycloneDX 1.7 `sbom.cdx.json`, and `license-inventory.json`. The artifact manifest binds the
release to the project commit, pinned upstream commit, canonical Node/Python toolchain versions and toolchain-manifest digest,
distribution tree digest, patch/configuration/extension-lock inputs, runtime component metadata, and exact release-file
digests and sizes.

The native SBOM is generated from the final static distribution plus runtime metadata captured from
the pinned upstream package lock. Because that generator and its internal consistency checks share a
discovery model, release qualification also scans the final <code>dist/</code> independently with
Syft 1.48.0 through a full-commit-pinned Anchore action. The reviewed scanner configuration
explicitly adds Syft's `javascript-package-cataloger` for directory scans so shipped npm and
extension package manifests are independently discoverable. Packaging normalizes Syft's package findings
into <code>independent-component-inventory.json</code> and compares them with the native SBOM in
<code>sbom-comparison.json</code>. Package identity and installed location must agree; unexplained
components missing from either side fail closed.

Expected representation differences are not hidden in code. They live in
<code>security/sbom-comparison-policy.json</code>, are JSON-schema validated, and must be used by the
comparison or packaging fails as a stale exception. Current exceptions are exact purl+path entries
for optimized runtime package directories whose final release bytes omit <code>package.json</code>;
the native inventory still binds those components to the pinned upstream package lock. The root
<code>Code - OSS</code> package is normalized directly to the native upstream application record.
Syft file components are excluded because they are file evidence rather than software packages,
while extensions are normalized to Syft's npm-style representation and compared rather than
blanket-exempted. Nested extension language-server package manifests discovered by Syft are also
included by the native generator.

Independent scan evidence is never reused across distribution changes. `scripts/build.py` deletes
any prior independent-SBOM output before regenerating `dist/`, and `package.sh` always performs a
fresh Syft scan of the current `dist/` into a temporary file and atomically replaces the scan used
for comparison. A stale `.work/independent-sbom.cdx.json` therefore cannot satisfy packaging after
the distribution changes.

The license inventory uses the native SBOM component references and must cover every native component
exactly once. Missing package declarations are represented explicitly as <code>NOASSERTION</code>;
they are never silently omitted. Code-OSS's MIT license and upstream third-party notice file are
copied alongside the candidate archives. The normalized independent inventory and comparison report
are release files covered by <code>SHA256SUMS</code>, the artifact manifest, and provenance
attestation.

There is no repository vulnerability-admission severity gate yet. If one is added, repository policy
requires it to consume the same raw Syft SBOM produced by the independent final-distribution scan
rather than rescanning from the native SBOM, preserving discovery independence.

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

Development qualification may reuse the content-addressed upstream web-build cache. Cold builds may
also reuse an npm package-download cache; `npm ci` still selects dependencies from the lockfile in
the pinned upstream revision, so cached package tarballs are a transport optimization only. Cache
hits are an optimization, not provenance. Immutable release publication performs independent clean
builds without development caches and compares their normalized distributions before publishing
release assets. Promotion consumes those already-published immutable assets and never rebuilds or
re-attests them.

Release tags matching `v*-web.*` must be protected by the repository ruleset represented in
`.github/rulesets/immutable-release-tags.json`: active tag targeting, update restriction, deletion
restriction, and no bypass actors. Release authorization also resolves the repository's default
branch and requires the tagged `GITHUB_SHA` to be an ancestor of, or identical to, that branch
before any release build can proceed. This prevents an otherwise-authorized repository writer from
turning an arbitrary off-branch commit into a release merely by creating a matching tag.

Immutable publication and mutable deployment are separate trust transitions. After attestation,
the GitHub Release and release-tagged GHCR image cross the protected `release` environment boundary.
They retain the immutable `v*-web.*` identity and never serve as mutable canary/stable aliases.

The automated upstream and patch dispatchers bind qualification to the exact source commit they
inspected. Qualification checks the dispatched `expected_source_sha` against its checked-out
`GITHUB_SHA` before qualification planning proceeds, and release qualification evidence preserves
that expected SHA. The independent Release workflow requires the preserved expectation to equal the
immutable release commit.

The qualification release job crosses the same `release` boundary before creating the immutable
release tag and dispatching Release. Every immutable GitHub Release/GHCR publication path checks that
the release-tag ruleset is active and that the release tag still resolves to the workflow's immutable
commit immediately before publication.

After both immutable publication channels succeed, Release dispatches
`.github/workflows/promote.yml` on the same immutable release tag, so normal Pages deployment records
carry the promoted release SHA. Manual recovery or rollback may run the current workflow from
`master` while naming an older immutable release. Promotion independently resolves the
immutable GitHub Release, verifies the protected release ref, downloads the published
`artifact-manifest.json`, `SHA256SUMS`, and canonical tar archive, verifies GitHub attestations and
checksums, and constructs a promotion identity containing the release tag/commit/Release ID,
distribution tree digest/file count, archive digest, and promotion profile/policy digest.

Canary and stable are GitHub Deployment environments. Each attempt records the complete promotion
identity in its deployment payload and records success/failure as deployment status. Stable
promotion additionally crosses a no-token `release` environment gate and deploys the verified
archive through the separate `github-pages` environment. The current stable pointer is therefore
the latest successful `stable` deployment, not a mutable release tag.

Automatic promotion is serialized across releases and fails closed if a stale release would move
canary or stable behind the current stable commit. A forward stable transition requires successful
canary with the same complete release/artifact/policy identity. A backward stable transition is
accepted only when the target immutable release/artifact identity has previous successful stable
history; the new rollback event records the current policy/profile identity. Rollback is therefore a
new audited promotion event rather than release mutation.

Stable Pages publication carries a release-bound <code>deployment-identity.json</code> alongside the
immutable release bytes. The identity contains the immutable release tag and commit, normalized
distribution tree SHA-256, and deployment-profile ID and digest for profiled releases. A legacy
release without deployment-profile metadata is represented explicitly with
<code>deploymentProfile: null</code>; the live verifier requires that absence to match exactly, which
preserves legacy rollback without inventing a profile digest. After Pages deployment reports success,
the publication action fetches that identity from the returned live Pages URL with a
cache-busting query and requires an exact match to the expected promotion identity projection. The
workflow-SHA Pages status is therefore not sufficient authorization evidence by itself; rollback and
recovery remain bound to the selected immutable release even when they execute from newer
<code>master</code>.

Immutable publication is retry-safe per channel. The normal Release workflow and immutable recovery
workflow share the same GitHub Release/GHCR implementations and the same `release-${ref}` concurrency
group. GitHub Release publication reconciles assets monotonically: matching published assets are
verification-only, and only an interrupted draft may add missing expected assets before publication.
Conflicting, unexpected, or incomplete published asset sets fail closed. GHCR verifies the existing
release tag, multi-platform manifest, release labels on both amd64 and arm64 children, and the exact
served static file tree for both platform images; it publishes only after the registry explicitly
reports that the tag is absent, while indeterminate registry failures abort without pushing.

`Recover immutable release publication` accepts the source Release workflow-run ID, verifies that all
pre-publication preparation jobs succeeded, and downloads retained `release-static-dist`,
`release-candidate`, and/or `release-attestation` artifacts as required for GitHub Release/GHCR
repair. It contains no upstream build, package, or attestation step. Promotion recovery is separate:
it re-resolves durable GitHub Release assets, so stable rollback is not bounded by workflow-artifact
retention and never reconstructs release content from source.

Vulnerability admission reuses the independently generated final-distribution SBOM as input to pinned
Grype. High/Critical and unknown-severity findings fail by default; exact package/vulnerability
exceptions are owned, reasoned, and expiring. Automatic upstream releases also enforce the configured
observation window measured from the pinned upstream GitHub release publication time. See
[`docs/vulnerability-admission.md`](vulnerability-admission.md) and
[`config/vulnerability-policy.json`](../config/vulnerability-policy.json).

## Recovery assurance exercise

Operational recovery assurance is exercised through the controlled
[release recovery game day](release-game-day.md). Its committed evidence record binds workflow runs,
immutable artifact/OCI identities, durable Playwright-runtime digest, rollback target, and the
canary/stable deployment identities before and after rollback. It also binds distinct executor and
reviewer GitHub identities and the reviewer's durable GitHub sign-off permalink. The record is an
index into GitHub's durable audit trail, not a substitute for workflow/release/deployment evidence.

## Builder identity

Release builds do not rely solely on the mutable `ubuntu-latest` filesystem. Release-authorizing
qualification and both Release rebuilds execute inside the digest-pinned builder recorded in
[`builder-image.json`](../builder-image.json). The qualification cache is bound to the image
and snapshot locks; the artifact manifest records the combined identity and both input digests.
Release authorization rejects qualification evidence whose builder identity does not match the
immutable release commit.

The separate, Renovate-managed [`builder-apt-snapshot.json`](../builder-apt-snapshot.json)
records the Ubuntu APT snapshot timestamp (`aptSnapshot`); image, digest and platform remain
in the CODEOWNED identity lock. All three build jobs install bootstrap and native prerequisites
from that same snapshot before checkout, verify that APT selected the snapshot archive, and
check the timestamp against the checked-out snapshot lock. The snapshot is part of the qualified
artifact's builder identity and independently checked before release authorization, including
its input digest. Cache keys include both locks, so snapshot rotation triggers full qualification.

The digest-pinned minimal Ubuntu image initially lacks CA certificates. To authenticate the HTTPS
snapshot endpoint without installing mutable packages, the build jobs mount the GitHub-hosted
runner's CA bundle read-only for APT transport only. Ubuntu archive signatures are still verified,
and all installed system packages (including `ca-certificates`) come from the locked snapshot.
The host CA bundle is an explicit external trust/availability assumption, not an artifact input.

The Ubuntu Snapshot Service remains an external availability dependency. Canonical currently intends to retain snapshots for
at least two years, not indefinitely; very old historical
rebuilds may eventually fail closed if the snapshot disappears. A separately digest-pinned
builder OCI image with preinstalled prerequisites remains the archival alternative.

Renovate couples the snapshot refresh to the VS Code release. Its custom datasource
uses the GitHub release publication timestamp minus 48 hours, rounded down to UTC
midnight; the `minimumGroupSize: 3` grouped update requires the upstream tag/commit,
its derived source date epoch, and the snapshot-only root lock. The trusted
approval guard compares the actual base and PR-head bytes and permits only the
expected tag, commit, source date epoch, and snapshot replacements. No workflow code
or CODEOWNED path is edited in routine Renovate PRs; qualification and release jobs read the
source-bound timestamp from trusted planner/authorizer outputs. Full qualification must pass.
A failed candidate leaves the previously qualified builder inputs and immutable release unchanged.
