# Code OSS Static Web

Experimental independent tooling for producing a **zero-backend static browser build** from an
immutable MIT-licensed Code - OSS revision without maintaining a fork of Microsoft's repository.

> **Status:** Phase 0 implementation. The current upstream target is pinned but not yet qualified.

## Implemented now

- exact upstream tag + 40-character commit lock;
- disposable source fetch by commit, not a maintained fork;
- deterministic `product.json` transform;
- explicit patch manifest (currently empty);
- upstream `vscode-web-min` build orchestration;
- static `index.html` + runtime bootstrap generation;
- browser-compatible built-in extension indexing;
- telemetry disabled in the project runtime;
- fail-closed webview mode on generic static hosting;
- self-only default `connect-src` CSP;
- deterministic tar/zip packaging and SHA-256 verification;
- initial threat model and CI structure;
- Playwright qualification scaffold for Chromium/Firefox/WebKit;
- network/WebSocket policy tests under a non-root static base path;
- repository-owned browser-extension qualification fixture;
- split build/browser/package qualification jobs using the same canonical `dist/`;
- content-addressed cache for the immutable upstream Code-OSS web bundle;
- exported minimal Playwright runtime for fast browser-only reruns and local debugging.

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

## Important initial limitation

Secure webviews are intentionally not enabled. Code - OSS normally relies on an isolated webview
origin/subdomain. Until a secure deployment-independent design is qualified, webview content is
configured to fail closed.

## Upstream

Initial target: Code - OSS `1.139.1`, commit
`04c0d99f4fb0d8afe6ce4f0c58e31e183ac3e4b1`.

This project is not Microsoft's Visual Studio Code distribution and is not endorsed by Microsoft.

## License

Original project tooling is MIT licensed. Generated artifacts contain Code - OSS and third-party
components under their respective licenses and must ship the corresponding notices/SBOM.
