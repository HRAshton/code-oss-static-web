# Browser qualification

The release is tested as a static artifact, not through the Code-OSS development server.

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
the canonical Node and Python versions from `.github/toolchain-versions.json`, product transform,
patch manifest/files and the scripts that drive the upstream build.
Changes limited to browser tests or packaging can therefore reuse the same upstream bundle while
still regenerating the current static wrapper.

## Current browser policy

Browser execution is centralized in `.github/actions/browser-qualification`. The pull-request
workflow always runs and classifies changed paths before deciding whether artifact evidence is
required. Documentation-only changes remain on the lightweight tooling path. Product-affecting
changes build the canonical static distribution, run the structural artifact smoke test, and run the
Chromium zero-retry boot gate. Upstream, runtime, qualification-infrastructure, and security-boundary
changes escalate to the full Chromium, Firefox, and WebKit qualification, with the same zero-retry
boot gate before the broader suites. Renames are classified using both the old and new paths, and
unknown paths fail closed to artifact qualification.

The protected default-branch ruleset must require the `Artifact qualification gate` job from
`Full build qualification`. That job is reported for every pull request, including documentation-only
changes where the expensive build and browser jobs are intentionally skipped. Full qualification
also runs on `develop` and for manual `all` dispatches. Release-intent qualification records the
normalized distribution-tree SHA-256 and file count from the exact `static-dist` consumed by the
browser jobs, and preserves the attested artifact manifest plus its provenance bundle with the
qualification evidence. The release workflow verifies that provenance, independently rebuilds the
tagged revision, and requires its normalized distribution identity to exactly match the qualified
identity before archiving, packaging, attesting, or publishing it. The existing second clean rebuild
still compares normalized distributions independently, so qualification binding and reproducibility
remain separate release gates.

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
- browser extension-host activation using the repository qualification extension;
- extension global-state and browser-filesystem persistence across workbench reload;
- JavaScript language-service completion initialization;
- keyboard command-palette shortcut behavior;
- Settings UI opening;
- workspace-trust enablement;
- explicit absence of a service-worker offline cache in the supported static mode.

Service workers are blocked in the browser test context so they cannot hide network requests from
qualification. Offline caching is not a release feature: the supported static mode requires the
hosted assets to remain reachable. Secure webviews are likewise not a supported deployment mode in
this release and remain fail-closed.

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

For fast local debugging with the exact unmanaged Chromium used by CI, manually dispatch the
qualification workflow with the `chromium` target. Manual Chromium runs additionally publish the
large, short-lived `playwright-browser-chromium` artifact; normal push qualification intentionally
does not upload that browser bundle.

Download `static-dist`, `playwright-runtime`, and `playwright-browser-chromium` from that manual run. Place the browser bundle at
`.work/playwright-browsers/` and run:

```bash
PLAYWRIGHT_BROWSERS_PATH=.work/playwright-browsers \
  python3 scripts/run_e2e.py --project chromium --dist dist --grep-invert @extension
```

This uses the same unmanaged Chromium and ffmpeg revision that CI qualified, so it also works on
machines whose system browser is managed by restrictive enterprise policy. An explicit
`CODE_OSS_STATIC_WEB_CHROMIUM_EXECUTABLE` override remains available for unmanaged local browsers.
GitHub Actions remains the authoritative release qualification environment.
