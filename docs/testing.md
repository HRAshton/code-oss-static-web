# Browser qualification

The release candidate is tested as a static artifact, not through the Code-OSS development server.

## Test topology

The default qualification URL is intentionally hosted below a path prefix:

```text
http://127.0.0.1:4173/code-oss-web/
```

This catches incorrect absolute URLs before GitHub Pages/CDN deployment.

The canonical `dist/` is built once and uploaded as the `static-dist` workflow artifact. Browser
qualification and packaging download that exact artifact in separate read-only jobs. Extension-host
qualification uses a copy of `dist/` with the repository-owned fixture extension injected; the
canonical artifact is not modified.

The expensive upstream Code-OSS web bundle is cached by immutable build inputs: upstream lock,
Node version, product transform, patch manifest/files and the scripts that drive the upstream build.
Changes limited to browser tests or packaging can therefore reuse the same upstream bundle while
still regenerating the current static wrapper.

## Current browser policy

Chromium is the default qualification target. Firefox and WebKit are available in the manual
qualification workflow but are not claimed as supported until the first real Code-OSS static build
has passed them.

## Current Playwright coverage

- static workbench boot;
- workbench configuration security defaults;
- static assets under a non-root base path;
- editor text input;
- command palette operation;
- zero cross-origin HTTP requests during clean startup;
- zero WebSocket connections during clean startup;
- CSP rejection of arbitrary cross-origin fetches;
- telemetry/gallery/webview fail-closed runtime policy;
- browser extension-host activation using the repository qualification extension.

Service workers are blocked in the browser test context so they cannot hide network requests from
qualification.

## Running after a real build

A fresh local build exports only the Playwright packages required by the qualification harness:

```bash
./build.sh
python3 scripts/install_playwright_browser.py --with-deps chromium
python3 scripts/run_e2e.py --project chromium --dist dist --grep-invert @extension

rm -rf .work/qualification-dist
cp -a dist .work/qualification-dist
python3 scripts/add_test_extension.py --dist .work/qualification-dist
python3 scripts/run_e2e.py --project chromium --dist .work/qualification-dist --grep @extension
```

The test runner uses the Playwright version installed by the pinned Code-OSS dependency graph, but
copies only `@playwright/test`, `playwright` and `playwright-core` into
`.work/playwright-runtime`. CI publishes that runtime separately from `static-dist`, allowing
browser tests to run without the upstream checkout or its complete `node_modules`.

For fast local debugging, download `static-dist`, `playwright-runtime`,
`qualification-harness`, and `playwright-browser-chromium` from the same qualification run.
Place the browser bundle at `.work/playwright-browsers/` and run:

```bash
PLAYWRIGHT_BROWSERS_PATH=.work/playwright-browsers \
  python3 scripts/run_e2e.py --project chromium --dist dist --grep-invert @extension
```

This uses the same unmanaged Chromium and ffmpeg revision that CI qualified, so it also works on
machines whose system browser is managed by restrictive enterprise policy. An explicit
`CODE_OSS_STATIC_WEB_CHROMIUM_EXECUTABLE` override remains available for unmanaged local browsers.
GitHub Actions remains the authoritative release qualification environment.
