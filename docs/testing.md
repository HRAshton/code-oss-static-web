# Browser qualification

The release candidate is tested as a static artifact, not through the Code-OSS development server.

## Test topology

The default qualification URL is intentionally hosted below a path prefix:

```text
http://127.0.0.1:4173/code-oss-web/
```

This catches incorrect absolute URLs before GitHub Pages/CDN deployment.

The canonical `dist/` runs the normal suite. Extension-host qualification uses a copy of `dist/`
with the repository-owned fixture extension injected; the canonical artifact is not modified.

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

```bash
./build.sh
python3 scripts/install_playwright_browser.py --with-deps chromium
python3 scripts/run_e2e.py --project chromium --dist dist --grep-invert @extension

rm -rf .work/qualification-dist
cp -a dist .work/qualification-dist
python3 scripts/add_test_extension.py --dist .work/qualification-dist
python3 scripts/run_e2e.py --project chromium --dist .work/qualification-dist --grep @extension
```

The test runner intentionally uses the Playwright package installed from the upstream Code-OSS
lockfile. A project-owned Playwright dependency may replace this once its own pinned lockfile is
introduced.
