# Build

Prerequisites: Git, Python 3.11+, and a Node/npm version compatible with the pinned Code - OSS
revision. The first full qualification workflow uses Node 24.

```bash
./build.sh
python3 scripts/smoke_static.py dist
./package.sh
```

The disposable checkout is `.work/vscode`. `npm ci` executes upstream scripts, therefore the CI
build job must not possess release credentials or OIDC attestation permission.


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
