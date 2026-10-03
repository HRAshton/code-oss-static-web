# Operations

## Recovering a partial release publication

Release publication has three independent channels: GitHub Release assets, GitHub Pages, and the
GHCR image. Completion of one channel is not evidence that either of the other channels completed.
The authoritative record for an automated attempt is the job result for each publication channel in
the `Release` or `Recover release publication` workflow.

Use publication recovery only after the source `Release` workflow reached and successfully completed
its preparation boundary: authorization, clean build, reproducibility comparison, Chromium release
qualification, packaging, and attestation. The recovery workflow verifies those jobs and consumes
their retained artifacts. It never runs `build.sh`, `package.sh`, or `actions/attest`.

### Identify the immutable inputs

Record both the immutable release tag and the workflow-run ID of the failed or partially failed
`Release` run. The recovery workflow must be dispatched on that exact tag, and the source run must
have the same `head_sha`; the recovery run itself is dispatched on the immutable tag. Do not create
a new `web.N` revision for a transient publication failure.

Example:

```bash
TAG=v1.140.0-web.0
RELEASE_RUN_ID=123456789
```

### Inspect channel state

| Channel | Complete state | Retry behavior | Conflict behavior |
| --- | --- | --- | --- |
| GitHub Release | Published release has exactly the expected assets with matching SHA-256 digests | Matching published releases are verification-only; an interrupted draft may upload only its missing expected assets and is published only after the complete set verifies | Missing assets on an already-published release, unexpected assets, or mismatching bytes fail closed; published assets are never changed |
| GitHub Pages | Pages deployment for the release commit reports `succeed` | Already-successful deployment is reused; otherwise the retained `release-static-dist` is deployed | A failed deployment can be retried independently without rebuilding the distribution |
| GHCR | The release tag has amd64 and arm64 manifests, expected release labels, and every canonical static file matches `release-static-dist` | A matching existing tag is reused; a confirmed-missing tag is rebuilt only as channel packaging from retained `release-static-dist` and then verified | An existing tag that does not verify, or an indeterminate registry lookup, fails closed and is not overwritten |

### Recover one channel

Use the retained artifacts from the original Release run:

```bash
gh workflow run recover-release-publication.yml \
  --ref "$TAG" \
  -f release_run_id="$RELEASE_RUN_ID" \
  -f channel=github-release

gh workflow run recover-release-publication.yml \
  --ref "$TAG" \
  -f release_run_id="$RELEASE_RUN_ID" \
  -f channel=pages

gh workflow run recover-release-publication.yml \
  --ref "$TAG" \
  -f release_run_id="$RELEASE_RUN_ID" \
  -f channel=ghcr
```

Use `channel=all` when more than one channel needs verification or recovery. The workflow uses the
same `release-${ref}` concurrency group as normal publication, so recovery cannot race another
publication attempt for the same immutable tag.

### Failure states

- If `authorize`, `build`, `reproducibility`, `browser (chromium)`, `package`, or `attest` did not
  succeed in the source Release run, publication recovery refuses to proceed. That is a
  pre-publication failure, not a partial-publication failure.
- If a required retained artifact has expired, automated publication recovery refuses to reconstruct
  release content from source. Escalate for a deliberate maintainer decision rather than silently
  rebuilding or changing an immutable publication.
- If GitHub Release or GHCR already contains conflicting immutable content, recovery fails closed.
  Investigate the repository audit trail and registry/release state; do not use clobber or move the
  release tag.
- A successful GitHub Release by itself does not imply Pages or GHCR success. Verify the individual
  channel jobs or run recovery with `channel=all`.

### Post-recovery verification

After recovery, confirm the selected channel job and the `publication-status` job are successful.
For a complete release, verify all three publication channels independently as described in
[Releasing](docs/releasing.md).
