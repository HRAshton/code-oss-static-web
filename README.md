# Code OSS Static Web

Independent tooling for producing a **zero-backend static browser build** from an immutable
MIT-licensed Code - OSS revision without maintaining a fork of Microsoft's repository.

> **Status:** Release-candidate track. Code - OSS `1.139.1` is qualified in Chromium, Firefox and
> WebKit. Secure webviews remain intentionally disabled/fail-closed in the generic static mode.

## Implemented now

- exact upstream tag + 40-character commit lock;
- disposable source fetch by commit, not a maintained fork;
- deterministic `product.json` transform;
- explicit patch manifest (currently empty);
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

## Upstream

Qualified target: Code - OSS `1.139.1`, commit
`04c0d99f4fb0d8afe6ce4f0c58e31e183ac3e4b1`.

This project is not Microsoft's Visual Studio Code distribution and is not endorsed by Microsoft.

## License

Original project tooling is MIT licensed. Generated artifacts contain Code - OSS and third-party
components under their respective licenses. Release candidates include the upstream license and
notices, a component-level license inventory, and a CycloneDX SBOM.
