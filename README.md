# Code OSS Static Web

[![CI](https://github.com/Codellei/code-oss-static-web/actions/workflows/ci.yml/badge.svg)](https://github.com/Codellei/code-oss-static-web/actions/workflows/ci.yml)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/Codellei/code-oss-static-web/badge)](https://scorecard.dev/viewer/?uri=github.com/Codellei/code-oss-static-web)
[![OpenSSF Best Practices](https://www.bestpractices.dev/projects/15349/badge)](https://www.bestpractices.dev/projects/15349)
[![REUSE status](https://api.reuse.software/badge/github.com/Codellei/code-oss-static-web)](https://api.reuse.software/info/github.com/Codellei/code-oss-static-web)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Independent tooling for producing a **zero-backend static browser build** from an immutable
MIT-licensed Code - OSS revision without maintaining a fork of Microsoft's repository.

## Implemented now

- exact upstream tag + 40-character commit lock;
- disposable source fetch by commit, not a maintained fork;
- deterministic `product.json` transform;
- explicit patch manifest for narrowly scoped upstream compatibility fixes;
- upstream `vscode-web-min` build orchestration;
- static `index.html` + runtime bootstrap generation through the upstream web embedder API;
- browser-compatible built-in extension indexing;
- telemetry disabled in the project runtime;
- fail-closed webview mode on generic static hosting;
- self-only default `connect-src` CSP;
- deterministic tar/zip packaging and SHA-256 verification;
- Playwright qualification for static boot, editing, commands, settings, workspace trust, network policy and extension host;
- browser-extension activation plus global-state/filesystem persistence and language-service qualification;
- split build/browser/package/attest jobs using the same canonical `dist/`;
- content-addressed cache for the immutable upstream Code-OSS web bundle;
- exported minimal Playwright runtime for fast browser-only reruns and local debugging;
- deterministic artifact manifest and CycloneDX 1.7 SBOM;
- deterministic license inventory covering every SBOM component;
- isolated GitHub/Sigstore provenance and SBOM attestations;
- reproducibility-gated GitHub Release, Pages and GHCR publication workflows.

## Release outputs

Microsoft Code - OSS updates publish automatically as `web.0`. Project-side fixes can be
published deliberately as monotonic `web.1`, `web.2`, and later patch revisions for the same
Microsoft version.

New immutable `v*-web.*` releases publish the same qualified static distribution as:

- deterministic `.tar.gz` distribution on the GitHub Release;
- a GitHub Pages deployment;
- an OCI image at `ghcr.io/codellei/code-oss-static-web:<tag>` for
  `linux/amd64` and `linux/arm64`.

Releases published before the organization transfer retain their original
`ghcr.io/hrashton/code-oss-static-web:<tag>` images and signed provenance.

Iframe embedding is a hosting decision: the shipped application and OCI image are neutral by
default. Operators can restrict embedding with an HTTP `frame-ancestors` header on the Code
OSS response at their public serving edge. See [static hosting and CSP](COMPATIBILITY.md#static-hosting-and-csp).

Release archives include checksums, an artifact manifest, CycloneDX SBOM, component-level license
inventory, upstream metadata, licenses, notices, and GitHub/Sigstore attestations.

## Deployment profiles

Build policy is selected by the tracked `config/deployment.json` file and resolved through
schema-validated profiles in `config/profiles/`. The default selection is `company-standard`.

| Profile | Proposed API grants | Purpose |
| --- | --- | --- |
| `company-standard` | None | Default secure company deployment starting point. |
| `baseline-static` | None | Exception-free secure baseline. |

Both profiles use the same zero-backend static runtime: telemetry and the gallery are disabled,
network connections default to self-only, and webviews fail closed. The current
`company-standard` policy matches `baseline-static`; company-specific branding, support
settings, extension mirrors, and locked extensions have not yet been provisioned. No extensions
are bundled by default.

Each profile binds runtime, network, product, proposed-API, webview, branding, support, extension
lock, extension license, and extension source policy documents. Builds write
`dist/deployment-profile.json` containing the selected profile ID, a digest over the resolved
configuration closure, and the SHA-256 of every bound input. Release artifact metadata records the
same identity and digest.

Only policy modes implemented and qualified by this repository are schema-valid. New deployment
modes such as isolated webviews must add their implementation, validation, and qualification before
they can be enabled by a profile.

## Build

```bash
./build.sh
python3 scripts/smoke_static.py dist
python3 scripts/serve_static.py --directory dist --base-path /code-oss-web/ --port 8080
```

Package the exact `dist/`:

```bash
./package.sh
```

After the full Code-OSS build, browser qualification can be run with:

```bash
python3 scripts/install_playwright_browser.py --with-deps chromium
python3 scripts/run_e2e.py --project chromium --dist dist --grep-invert @extension
```

See `docs/testing.md` for the extension-host qualification path and browser policy.

## Important current limitation

Secure webviews are intentionally not enabled. Code - OSS normally relies on an isolated webview
origin/subdomain. Until a secure deployment-independent design is qualified, webview content is
configured to fail closed.

## Project links

- [Releases](https://github.com/Codellei/code-oss-static-web/releases) - immutable qualified release artifacts.
- [Issues](https://github.com/Codellei/code-oss-static-web/issues) - bugs and enhancement requests.
- [Contributing](CONTRIBUTING.md) - contribution process, review requirements, and local checks.
- [Governance](GOVERNANCE.md) - ownership, sensitive-path review, migration, and continuity plan.
- [Security](SECURITY.md) - private vulnerability reporting and supported-version policy.
- [Release security](docs/release-security.md) - provenance, SBOM, attestation, and publication boundaries.
- [Compatibility](COMPATIBILITY.md) - supported browser/deployment contract and qualification boundary.
- [Operations](OPERATIONS.md) - release publication recovery and partial-failure procedures.

## Upstream

The exact Code - OSS tag and commit are pinned in `upstream.lock.json`. The tag is resolved
independently (including peeling annotated tags) and must identify the exact pinned commit before a
build can start; the fetched checkout is then separately verified to have that exact `HEAD`.
A changed upstream revision is published only after the automated full-browser qualification
succeeds.

This project is not Microsoft's Visual Studio Code distribution and is not endorsed by Microsoft.

## License

Original project tooling is MIT licensed. Generated artifacts contain Code - OSS and third-party
components under their respective licenses. Release artifacts include the upstream license and
notices, a component-level license inventory, and a CycloneDX SBOM.
