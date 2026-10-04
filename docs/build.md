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
  under `artifacts/`.
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
