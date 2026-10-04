# Operations

## Promotion model

Immutable release creation and organizational deployment are separate operations:

```text
immutable v*-web.* release
        |
        v
      canary
        |
        v
      stable
```

The immutable release contains the GitHub Release assets, attestations, and the release-tagged GHCR
image. Promotion never rebuilds, repackages, re-attests, or changes that release. The
`Promote immutable release` workflow downloads the published GitHub Release archive, verifies the
published checksums and GitHub attestations, and binds the promotion to:

- immutable release tag and commit;
- GitHub Release ID;
- canonical distribution tree SHA-256 and file count;
- release archive SHA-256;
- promotion profile and SHA-256 of `config/promotion-policy.json`.

Successful canary and stable promotions are recorded as GitHub Deployments. The latest successful
deployment in each environment is the channel pointer; previous successful deployments are the audit
history. GitHub additionally records the actor, workflow run, timestamps, and deployment statuses.

The default promotion policy is fully automatic. A successful immutable release dispatches
`target=auto`, which verifies canary and then promotes the same immutable identity to stable without
human action. Automatic promotion refuses to move canary or stable behind the currently successful
stable release.

### Audit channel state

List recent promotion records:

```bash
gh api "repos/HRAshton/code-oss-static-web/deployments?environment=canary&per_page=20"
gh api "repos/HRAshton/code-oss-static-web/deployments?environment=stable&per_page=20"
```

For a deployment ID, inspect both the recorded immutable identity and its latest status:

```bash
DEPLOYMENT_ID=123456
gh api "repos/HRAshton/code-oss-static-web/deployments/$DEPLOYMENT_ID"
gh api "repos/HRAshton/code-oss-static-web/deployments/$DEPLOYMENT_ID/statuses?per_page=1"
```

The deployment payload is authoritative for the promoted release/artifact/policy identity. A channel
is changed only by a new successful deployment record; immutable release tags and release assets are
never moved or replaced.

### Manual canary promotion

Manual canary promotion is useful for replaying a failed automatic promotion or deliberately
re-evaluating an immutable release:

```bash
TAG=v1.140.0-web.0

gh workflow run promote.yml \
  --ref master \
  -f release_tag="$TAG" \
  -f target=canary
```

The workflow executes from current protected `master`, but all deployed bytes and release identity
come from the immutable GitHub Release named by `TAG`.

### Stable promotion

A new release may move to stable only after the same release/artifact identity has a successful canary
record. The normal `target=auto` path satisfies that requirement in one promotion run.

To finish a release whose canary succeeded but stable failed:

```bash
TAG=v1.140.0-web.0

gh workflow run promote.yml \
  --ref master \
  -f release_tag="$TAG" \
  -f target=stable
```

Stable promotion deploys GitHub Pages from the verified immutable release archive. It does not use a
source checkout as release content and does not invoke `build.sh`, `package.sh`, or
`actions/attest`. Before upload, the workflow adds `deployment-identity.json` containing the
selected immutable release tag and commit, canonical distribution tree digest, and deployment-profile
ID and digest for profiled releases. Legacy releases that predate deployment-profile metadata retain
`deploymentProfile: null`; rollback verifies that null exactly rather than inventing profile
metadata. After deployment, the shared Pages action fetches that file from the returned live
Pages URL with a cache-busting query and fails unless it exactly matches the expected promotion
identity. A successful Pages workflow status alone is not treated as proof that the intended release
is live.

Forward stable promotion requires a canary recorded with the same complete promotion identity,
including the promotion policy/profile digest. If the policy changes after canary, rerun canary under
the current policy before promoting forward to stable.

### Roll back stable

Rollback is another stable promotion to an older immutable release that previously succeeded in the
stable environment. During migration to this model, a successful historical `github-pages`
deployment also counts as prior stable evidence, so the first post-migration rollback can return to
the production release that existed before `stable` deployment records were introduced. Rollback
creates a new deployment record; it does not move or recreate a release tag.

First identify a previous successful stable deployment and its `payload.release.tag`, then run:

```bash
PREVIOUS_TAG=v1.139.1-web.2

gh workflow run promote.yml \
  --ref master \
  -f release_tag="$PREVIOUS_TAG" \
  -f target=stable
```

The workflow permits a backward stable transition only when that exact immutable release/artifact
identity has successful stable history or the target commit has a successful legacy
`github-pages` deployment. Historical rollback eligibility intentionally does not require the old
promotion-policy digest to match: the new rollback attempt is evaluated under, and records, the
current promotion policy/profile. GitHub Pages is redeployed when its currently served successful
deployment does not match the rollback commit, even if that older commit was deployed in the past.

Canary is not implicitly rolled back when stable is rolled back. Move canary separately if the
operational intent is for both channel pointers to reference the same previous release.

### Canary failure handling

A successful `canary` deployment means the immutable candidate was actually served by GitHub Pages
under `__canary/<release-tag>/`, its release-bound identity converged at that URL, and the live
Chromium synthetic booted. While publishing canary, the workflow reconstructs the previous stable
root from its immutable release asset, verifies its digest and attestation, and restores its root
deployment identity before adding the candidate subpath. During migration, if no `stable`
deployment record exists yet, the workflow recovers the exact legacy production identity from the
live root `deployment-identity.json`, binds it to the successful legacy `github-pages` deployment,
and reconstructs that immutable release instead of replacing production with an empty placeholder.

If canary publication, identity verification, or browser boot fails, the canary deployment is marked
failed and automatic stable promotion does not run. Re-run promotion for the same immutable release
after correcting promotion infrastructure; do not move or rebuild the release tag.

### Recover a failed promotion

Promotion is retry-safe because it always re-resolves immutable GitHub Release assets and records a
new deployment attempt.

- If authorization, checksum, attestation, or canary verification fails, stable is untouched.
- If stable fails before Pages succeeds, fix the external/configuration problem and rerun
  `target=stable`; no new release is created.
- If Pages deployment reports success but live `deployment-identity.json` is missing, stale, or
  mismatched, stable remains failed. Rerunning `target=stable` re-resolves the same immutable release
  identity, redeploys the verified bytes, and repeats live identity verification before stable success
  is recorded; it never rebuilds release content.
- If an automatic promotion is stale relative to a newer stable release, it fails closed instead of
  rolling stable backward.
- If the requested backward target has neither stable history nor a successful legacy Pages
  deployment, the workflow refuses the rollback.
- Promotion uses durable GitHub Release assets rather than expiring workflow artifacts, so rollback
  does not depend on the original release run's artifact-retention window.

Human intervention is required only when the automated checks cannot prove a safe transition, for an
explicit rollback, or for a deliberate promotion-policy change. Routine Microsoft upstream release
promotion remains automatic.

## Independent SBOM cross-check failures

Release-intent qualification and the independent Release workflow both scan the extracted final
distribution with pinned Syft before `package.sh` accepts a candidate. Successful candidates contain
`independent-component-inventory.json` and `sbom-comparison.json` alongside the native
`sbom.cdx.json`.

If packaging reports a component missing from the native SBOM, treat it as a release blocker: either
fix native component discovery or add a narrowly matched exception to
`security/sbom-comparison-policy.json` with a reviewable reason. Do not add broad path/ecosystem
ignores. Components missing from Syft are also blockers unless the representation difference is
explicitly documented. Unused exceptions fail packaging, so remove an exception when the scanner and
native model converge.

The baseline exceptions are exact purl+path entries for runtime package directories whose optimized
release form omits `package.json`; Syft cannot recover their package identity from those final bytes.
They remain represented by the native inventory using the pinned upstream package lock. Any version
or path change makes an exception stale and blocks packaging until reviewed. The root
`Code - OSS` package is normalized to the native upstream application identity rather than
excepted. Syft file records are not software components and are ignored by the comparison. Extensions
are not ignored: the comparison maps their native `vscode-extension:` identity to Syft's npm package
identity at the installed extension path, and nested extension language-server manifests are included
in the native component inventory.

For local `./package.sh`, install the Syft version recorded in
`security/sbom-comparison-policy.json`. CI installs the reviewed version automatically. A scanner
version change is a security-policy change and must update the policy and regression baseline
together.

## Qualification source binding

Automated upstream and patch release dispatches first resolve the exact project commit they inspect,
then pass that commit to `Full build qualification` as `expected_source_sha`. The upstream trigger
re-resolves the protected default branch on every run, including a GitHub workflow retry; the original
push event is used only to identify the pre-change lock revision. The patch path also reads
`upstream.lock.json` by its resolved immutable commit rather than by the moving default-branch name.

At workflow start, qualification checks the checked-out `GITHUB_SHA` against the expected SHA before
planning, build, packaging, or release-tag work. A default-branch move between inspection and workflow
start therefore fails closed. The expected SHA is shown in the workflow summary, stored in the
`release-qualification` evidence, and independently rechecked by the Release workflow.

A source-SHA mismatch is not a retryable publication failure. Re-run the upstream or patch dispatcher
so it inspects the current branch state and creates a new qualification request bound to that exact
commit.

## Recovering a partial immutable release publication

Immutable release publication has two independent channels: GitHub Release assets and the immutable
release-tagged GHCR image. Completion of one channel is not evidence that the other completed.
GitHub Pages is stable promotion state and is recovered through the promotion workflow above, not
through immutable release publication recovery.

Use publication recovery only after the source `Release` workflow reached and successfully completed
its preparation boundary: authorization, clean build, reproducibility comparison, Chromium release
qualification, packaging, and attestation. The recovery workflow verifies those jobs and consumes
their retained artifacts. It never runs `build.sh`, `package.sh`, or `actions/attest`.

### Identify the immutable inputs

Record both the immutable release tag and the workflow-run ID of the failed or partially failed
`Release` run. The recovery workflow must be dispatched on that exact tag, and the source run must
have the same `head_sha`. Do not create a new `web.N` revision for a transient publication
failure.

Example:

```bash
TAG=v1.140.0-web.0
RELEASE_RUN_ID=123456789
```

### Inspect immutable publication state

| Channel | Complete state | Retry behavior | Conflict behavior |
| --- | --- | --- | --- |
| GitHub Release | Published release has exactly the expected assets with matching SHA-256 digests | Matching published releases are verification-only; an interrupted draft may upload only its missing expected assets and is published only after the complete set verifies | Missing assets on an already-published release, unexpected assets, or mismatching bytes fail closed; published assets are never changed |
| GHCR | Both amd64 and arm64 child images have the expected release labels and their complete served file trees exactly match `release-static-dist` | A matching existing tag is reused; a confirmed-missing tag is rebuilt only as channel packaging from retained `release-static-dist` and then verified | An existing tag with missing, changed, or extra served files on either platform, or an indeterminate registry lookup, fails closed and is not overwritten |

### Recover one immutable publication channel

Use the retained artifacts from the original Release run:

```bash
gh workflow run recover-release-publication.yml \
  --ref "$TAG" \
  -f release_run_id="$RELEASE_RUN_ID" \
  -f channel=github-release

gh workflow run recover-release-publication.yml \
  --ref "$TAG" \
  -f release_run_id="$RELEASE_RUN_ID" \
  -f channel=ghcr
```

Use `channel=all` when both channels need verification or recovery. The workflow uses the same
`release-${ref}` concurrency group as normal immutable publication, so recovery cannot race another
publication attempt for the same immutable tag.

### Immutable publication failure states

- If `authorize`, `build`, `reproducibility`, `browser (chromium)`, `package`, or `attest`
  did not succeed in the source Release run, publication recovery refuses to proceed.
- If a required retained artifact has expired, automated immutable publication recovery refuses to
  reconstruct release content from source. This limitation applies to repairing GitHub Release/GHCR
  publication; promotion and rollback use durable published GitHub Release assets once publication
  succeeded.
- If GitHub Release or GHCR already contains conflicting immutable content, recovery fails closed.
  Investigate the repository audit trail and registry/release state; do not use clobber or move the
  release tag.

### Post-recovery verification

After recovery, confirm the selected channel job and `publication-status` job are successful. Once
both immutable channels are complete, run or rerun automatic promotion if necessary:

```bash
gh workflow run promote.yml \
  --ref master \
  -f release_tag="$TAG" \
  -f source_release_run_id="$RELEASE_RUN_ID" \
  -f target=auto
```

## Release recovery game day

The controlled end-to-end recovery exercise is defined in
[the release game-day runbook](docs/release-game-day.md). The exercise covers immutable-publication
retry/recovery, real canary qualification, stable rollback, and forward promotion without moving or
rebuilding release identities. Completed evidence belongs under
[`release-evidence/game-days/`](release-evidence/game-days/README.md) and is structurally validated
by the repository test suite.


Organization ownership changes must follow [the organization migration procedure](docs/organization-migration.md).
At least two approved Release operators must be able to execute the recovery procedures in this
document before a personal maintainer is removed from operational coverage.
