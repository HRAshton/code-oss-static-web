# Build

Prerequisites: Git and Python 3.11+. CI, qualification, and release jobs install the canonical
Node and Python versions from `.github/toolchain-versions.json`; use those same versions when
reproducing CI or release behavior locally.

```bash
./build.sh
python3 scripts/smoke_static.py dist
./package.sh
```

The disposable checkout is `.work/vscode`. `npm ci` executes upstream scripts, therefore the CI
build job must not possess release credentials or OIDC attestation permission.

The upstream lock has a two-part identity invariant: the configured release `tag` must resolve to
the exact 40-character `commit`. Validation resolves the tag independently with `git ls-remote`;
when the tag is annotated, the peeled `^{}` target is compared with the pinned commit. A mismatch
fails before any product build starts. The source fetch then still checks out the commit directly and
verifies that the disposable checkout's `HEAD` is exactly the same SHA.

To verify only the remote tag-to-commit binding without building:

```bash
python3 scripts/fetch_upstream.py --verify-tag-only
```


## Build interface

The project intentionally keeps its external build interface small:

- `./build.sh` produces a fresh static distribution in `dist/`.
- `./build.sh --clean-upstream` removes and refetches the disposable upstream checkout before
  building. Release qualification uses this mode.
- `./build.sh --reuse-upstream-build` reuses the already-built immutable upstream web bundle and
  regenerates only the project-owned static distribution.
- `./package.sh` packages the current `dist/` into deterministic release archives and metadata
  under `artifacts/`. Packaging also requires the Syft version recorded in
  `security/sbom-comparison-policy.json` and uses `security/syft.yaml` to enable independent
  JavaScript package discovery. CI supplies the pinned scanner automatically; local packaging uses a
  matching `syft` executable from `PATH`.
- `python3 scripts/serve_static.py --directory dist --base-path <path> --port <port>` serves the
  generated distribution for local browser testing.

Configuration inputs are `upstream.lock.json`, files under `config/`, the patch manifest under
`patches/`, and the extension lock/policy under `extensions/`. Their schemas live under
`schemas/`. The generated `dist/` directory is the canonical runtime input to qualification,
packaging, Pages, and OCI publication.


## Pull-request qualification cost

Pull requests are path-classified before expensive artifact work. Documentation-only changes use the
lightweight gate. Publication/promotion control-plane-only changes use the read-only release-metadata
qualification lane, which runs repository policy and unit/tooling tests without rebuilding Code - OSS
or starting the browser matrix. Distribution-dependent packaging/SBOM/OCI changes remain artifact
qualification: they build the canonical static distribution, run Chromium smoke qualification, and
run packaging against that exact `dist/`. The fast-lane allowlist is explicit; mixed changes that
touch runtime/build inputs escalate to artifact or full qualification, and unknown paths fail closed
to artifact qualification.

Full changes continue to run Chromium, Firefox, and WebKit qualification.

## Pinned release builder

Qualification builds that can authorize a release, the independent release rebuild, and the second
reproducibility rebuild run inside the immutable OCI image recorded in
[`builder-image.json`](../builder-image.json). Workflows reference the image by
digest rather than by a mutable tag. The immutable image/digest/platform fields are CODEOWNED;
[`builder-apt-snapshot.json`](../builder-apt-snapshot.json) holds only Renovate's mutable APT
snapshot timestamp. The qualification cache key includes both locks and the qualification
workflow itself, which binds its bootstrap and native-package prerequisite
definition. A builder or prerequisite change therefore cannot reuse an upstream web bundle built
under an older environment.

Release `artifact-manifest.json` records the combined builder identity (including `aptSnapshot`)
and the SHA-256 of each lock alongside the canonical Node/Python toolchain. Qualification
evidence records the same builder identity; `release.yml` re-fetches both locks from the
immutable release commit and requires evidence, identity, and both manifest input digests
to match before a clean rebuild starts.

The hosted runner still provides the outer GitHub Actions executor, and Ubuntu package repositories
used by the prerequisite bootstrap remain external mutable infrastructure. Those are explicit
residual rebuild dependencies, not hidden guarantees. If a historical rebuild can no longer resolve
those dependencies, treat that as a rebuildability incident rather than silently substituting newer
inputs.

## Historical rebuild exercise

For an older immutable release, check out its release tag, inspect the tag's
`builder-image.json` and `builder-apt-snapshot.json`. Run the build inside the recorded image
digest using the tag's canonical toolchain, upstream lock, patch set, deployment profiles,
and extension lock. Compare the normalized
distribution tree with the release's `artifact-manifest.json`. The manifest's `builder` (including `aptSnapshot`) and
`inputs.builderImage` and `inputs.builderAptSnapshot` fields record the identity and both
input digests for that exercise.
Use the recorded snapshot timestamp for both `apt-get update` and `apt-get install` rather
than the current Ubuntu repositories. Historical snapshots have finite retention; the exercise
may eventually fail closed for an older release without an archived builder image.

### Renovate-managed builder snapshot rotation

The same Renovate PR that updates the pinned VS Code release also updates the Ubuntu
APT snapshot timestamp. Renovate's custom datasource derives the candidate from VS
Code's published GitHub release time, minus 48 hours and rounded down to midnight
UTC. The `minimumGroupSize: 3` requirement groups the upstream tag/commit, source date
epoch, and snapshot-only lock updates. The qualification planner and release authorizer
resolve the pinned timestamp from this lock at the exact source commit; container jobs
consume those immutable job outputs rather than duplicating the timestamp in YAML.

Renovate derives `sourceDateEpoch` from the upstream GitHub release's `created_at`
(commit date) as Unix seconds, and groups that change with the VS Code tag/commit
and builder snapshot. The pinned epoch must equal the pinned commit's UTC committer
timestamp; when changing the pin manually, derive it with
`git show -s --format=%ct <commit>` in the fetched upstream checkout.

The trusted auto-approval job accepts only the exact two-file diff: an advancing
VS Code tag, commit, and source date epoch plus a timestamp-only snapshot lock change.
It independently obtains the commit timestamp from GitHub's Git commit API and rejects
stale, regressed, or mismatching epochs.
It downloads both revisions from GitHub and executes the guard from trusted
master, never the PR branch. Full qualification must succeed before automated
approval and merge. All other changes fail closed. The snapshot lock is a narrowly
scoped, non-CODEOWNED data input like the upstream lock; the image identity and workflows
are CODEOWNED. If the release has no publication timestamp, the group is not generated.
