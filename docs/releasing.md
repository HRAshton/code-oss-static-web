# Releasing

Microsoft Code - OSS updates normally create, verify, publish, and promote automatically. Project-side
fixes can publish an explicit patch revision without waiting for another Microsoft release. Immutable
release creation is separate from mutable canary/stable deployment state.

## Version contract

Release tags are immutable and have the form:

```text
v<code-oss-version>-web.N
```

The revision has two meanings:

- `web.0` is reserved for the automatic release of a new Microsoft Code - OSS version.
- `web.1`, `web.2`, and later revisions are project-side patch releases that keep the same
  Microsoft Code - OSS version.

The revision is monotonic for each Microsoft version. Release tags are never moved or reused for a
different commit.

## Automatic Microsoft release

Renovate tracks `microsoft/vscode` and updates the exact upstream tag and tag commit in
`upstream.lock.json`. Renovate dependency PRs use the normal cheap repository checks and are
eligible for auto-merge; ordinary dependency updates do not build or deploy Code - OSS.

When a merged `master` commit actually changes the pinned Microsoft tag or commit, the upstream
qualification trigger re-resolves current protected `master`, inspects the lock at that immutable
commit, and dispatches `Full build qualification` with all browsers, `release_mode=upstream`, and
that current commit as `expected_source_sha`. If `master` moves again before qualification starts,
qualification fails before planning; re-running the upstream trigger resolves and binds the new
current `master` instead of reusing the original push SHA. Metadata-only lock changes do not trigger
that expensive path.

After build, Chromium/Firefox/WebKit qualification, packaging and qualification attestations all
succeed, the workflow creates exactly:

```text
v<code-oss-version>-web.0
```

The terminal release-intent gate rejects a successful workflow when tooling, planning, build,
browser, OCI serving, packaging, attestation, or release dispatch was skipped or failed.
An already-existing immutable tag instead requires successful artifact-only publication recovery,
with new-build and tag-creation jobs skipped. Both automatic and operator-triggered release intent
use this gate.

It then dispatches the independent Release workflow for that immutable tag. After immutable GitHub
Release and release-tagged GHCR publication succeeds, Release automatically dispatches the promotion
workflow. The default policy verifies canary and promotes the same immutable identity to stable,
including GitHub Pages, without human action.

## Emergency upstream soak bypass

Normal qualification and the unattended Microsoft update path always enforce the upstream
publication observation window. An approved Release/Security operator may use
**Upstream soak break-glass** (`.github/workflows/upstream-soak-break-glass.yml`) on `master`
with the exact current source SHA and an emergency reason. The dedicated caller requires a distinct
`upstream-soak-break-glass` environment approval before invoking qualification, and the called
workflow independently authorizes both the original dispatcher and re-running actor before full
three-browser qualification. Configure the environment and
approved operators as specified in [vulnerability admission](vulnerability-admission.md).
The override does not relax the Grype vulnerability admission threshold.

## Project patch release

Use the **Patch release** workflow when a project-owned source, packaging, workflow, container, or
security fix must ship before the next Microsoft release.

The dispatcher is fail-closed. It resolves one exact default-branch commit, reads the upstream lock
from that immutable commit, and passes the same commit as `expected_source_sha` to qualification.

1. the current Microsoft version must already have a `web.0` tag;
2. if current `master` already matches the latest `web.N` tag, the request is treated as a retry
   of that immutable release and routes directly to artifact-only publication recovery;
3. otherwise, full Chromium/Firefox/WebKit qualification runs with `release_mode=patch`;
4. after qualification succeeds, the workflow selects one greater than the highest existing
   revision and creates that immutable tag;
5. the independent Release workflow rebuilds and publishes the new immutable patch release;
6. automatic promotion verifies canary and advances stable to that same immutable release.

For example, if `v1.140.0-web.0` exists on an older commit and a project fix is merged, the next
successful patch release is `v1.140.0-web.1`. Re-running Patch release without changing `master`
keeps the existing `web.N` tag and enters recovery instead of allocating another revision.

## Retry versus patch

Do **not** increment the revision for a transient immutable-publication or promotion failure when the
source commit has not changed.

GitHub Release and release-tagged GHCR are immutable publication channels. For a partial failure in
those channels, run **Recover immutable release publication** on the existing tag and provide the
original Release workflow-run ID. Recovery consumes retained release artifacts and never rebuilds,
repackages, or re-attests content.

Canary, stable, and GitHub Pages are promotion state. For a failed promotion, rerun
`promote.yml` against the same immutable release. Promotion downloads durable published GitHub
Release assets, verifies their attestations and digests, and never executes the release build.
Stable remains on the previous successful immutable release until the new stable promotion succeeds.

Rollback also uses `promote.yml`: promoting a previously successful stable release creates a new
stable deployment record pointing to that older immutable identity. Release tags and assets are not
moved.

### Canary deployment

The canary stage publishes a reachable candidate under the repository Pages site at
`__canary/<release-tag>/` while retaining the previous stable release at the root. It reconstructs
that stable root only from its verified immutable release archive; during migration it can recover
the exact prior production release from a successful legacy `github-pages` deployment plus the
live root deployment identity. It then verifies the candidate's release-bound identity at the
canary path and runs a Chromium boot synthetic against the served URL.
Only that successful canary deployment record is accepted by automatic stable promotion. A
canary-only dispatch leaves the candidate reachable for operator inspection without advancing the
stable channel.

See [Operations](../OPERATIONS.md) for promotion, rollback, audit, and both recovery procedures.

## Qualification evidence

The successful all-browser workflow run on the exact release commit is the qualification evidence.
Qualification is not stored as a mutable boolean in source control.

The qualification workflow records the exact commit, dispatched expected source SHA, selected
release tag, release mode, workflow run ID, and canonical Node/Python toolchain versions in a
`release-qualification` artifact. The Release workflow downloads that artifact and requires both
the recorded commit and expected source SHA to equal the immutable release commit before doing any
publication work.

The Release workflow then performs an independent clean rebuild, reproducibility comparison,
release-grade Chromium qualification, tag-specific packaging, provenance/SBOM attestation, and
immutable publication to GitHub Releases and the release-tagged GHCR image. A separate promotion
workflow consumes that immutable identity and advances canary then stable; stable owns GitHub Pages.

Final archives, SBOM metadata and the OCI image use the actual immutable `web.N` release tag.

## Failure behavior

If any build, browser, packaging, reproducibility, security, immutable-publication, or promotion gate
fails, automation stops. No immutable tag is moved, and failed promotion leaves the previous stable
release authoritative. A maintainer only needs to intervene when the automated path cannot prove the
revision works, for an explicit rollback/policy change, or when a project patch release is
intentionally requested.

## Release notes

GitHub-generated release notes are published automatically from the merged change history. Security
advisories and other material project notes should be added to the repository before release so they
are part of the immutable release history.

## One-time repository setup

GitHub Pages must be enabled separately from the `github-pages` environment. In repository
**Settings → Pages → Build and deployment**, set **Source** to **GitHub Actions**. The stable promotion job checks this before attempting a Pages deployment.

## Verify

After publication:

- verify the GitHub Release archives and `SHA256SUMS`;
- verify artifact attestations with `gh attestation verify`;
- verify the release-tagged GHCR image exposes both `linux/amd64` and `linux/arm64` manifests;
- verify the latest successful `canary` and `stable` GitHub Deployment payloads reference the expected
  immutable release/artifact/policy identity;
- verify GitHub Pages serves `deployment-identity.json` for the expected immutable release tag,
  commit, distribution tree digest, and deployment-profile digest.

Do not publish or move a mutable `latest` tag as part of the immutable release contract.

## Recovery game day

For the controlled release/recovery exercise, follow
[the release game-day runbook](release-game-day.md). The exercise deliberately distinguishes the
short-lived retained-artifact publication-recovery path from durable rollback/promotion, which
re-resolves immutable GitHub Release assets. Commit a validated game-day evidence record only after
the real workflows and deployments have completed and a distinct reviewer has published the durable
GitHub sign-off permalink recorded in that evidence.
