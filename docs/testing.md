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
patch manifest/files and the scripts that drive the upstream build. Changes limited to browser tests
can therefore reuse the same upstream bundle while still regenerating the current static wrapper.
Publication/promotion control-plane-only pull requests do not rebuild that bundle at all; they use
the release-metadata qualification lane below. Distribution-dependent packaging, SBOM, and OCI
changes still build a real `dist/` and package that exact artifact.

## Current browser policy

Browser execution is centralized in `.github/actions/browser-qualification`. The pull-request
workflow always runs and classifies changed paths before deciding whether artifact evidence is
required. Documentation-only changes remain on the lightweight tooling path. An explicit allowlist
of release/package/publication-only paths uses a read-only release-metadata lane that runs repository
policy and the Python tooling/unit suite without rebuilding Code - OSS or starting browsers.
Product-affecting changes build the canonical static distribution, run the structural artifact smoke
test, and run the Chromium zero-retry boot gate. Upstream, runtime, qualification-infrastructure, and
other high-risk changes escalate to the full Chromium, Firefox, and WebKit qualification, with the
same zero-retry boot gate before the broader suites. Renames are classified using both the old and
new paths. Mixing release-only paths with runtime/build inputs escalates to the stronger applicable
lane, and unknown paths fail closed to artifact qualification. Artifact/full pull requests also run packaging
against the qualified distribution so distribution-dependent release tooling is exercised, but PR
qualification never runs the downstream attestation job or receives OIDC/attestation write authority.

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

## Performance and accessibility baseline

Chromium qualification runs a dedicated `@quality` pass after the zero-retry boot gate. It uses
three independent browser contexts and reports the median so a single noisy runner sample does not
become a regression gate. Each context performs one cold load and then a second load in the same
context. The second load preserves browser storage but not HTTP response caching: the qualification
server deliberately sends `Cache-Control: no-store`.

The measured timing points are navigation start to visible workbench for cold and warm boot, and
navigation start to a visible untitled editor for editor readiness. Static transfer size is the sum
of same-origin `Content-Length` response headers observed by the time the workbench becomes visible.
The suite also records the complete distribution size, JavaScript size, request failures, page
errors, and every console-error occurrence plus its normalized fingerprint. Request failures include
Playwright transport failures plus HTTP responses with status 400 or higher, so a missing or
server-error static asset cannot pass as a successful startup. All console-error occurrences remain
in the diagnostics artifact. An F6 focus-cycle smoke check requires focus to move to a non-hidden, enabled
element with an accessible name; this adds accessibility coverage without duplicating the existing
editor, settings, command-palette, and workspace-trust functional tests.

Baselines and tolerances live in `config/quality-baseline.json`. For a lower-is-better metric, the
failure limit is `baseline * (1 + relativeTolerance) + absoluteTolerance`. Timing metrics use a
50% relative tolerance plus a small absolute allowance, transfer size uses 5% plus 256 KiB, and
deterministic distribution/JavaScript sizes use 3% plus 1 MiB. Zero-error metrics allow no increase.
Every failure includes the metric name, observed value, baseline, tolerance, and computed limit.
The Chromium diagnostics artifact includes `.work/quality-metrics.json` with every sample and the
raw error lists.

The initial baseline was captured by successful full qualification run 37136030149 at measurement
commit `63afddee4633456de01bb30a2cea5f3479d636bc`. The three timing samples ranged from 2.09–2.15 s
for cold boot, 2.03–2.16 s for warm boot, and 2.17–2.35 s for editor readiness; startup transfer
varied by less than 1%. The recorded medians are 2,096 ms, 2,034 ms, 2,188 ms, and 25,438,689 bytes
respectively. Distribution size is 190,626,870 bytes and JavaScript size is 131,365,205 bytes.
Failed requests and page errors baseline at zero. Ten explicit file-watcher console-error
fingerprints are tolerated from the captured baseline (60 total occurrences across the six sampled
loads). The gate normalizes only the browser console styling prefix, then requires exact membership
in `consoleErrorPolicy.toleratedFingerprints`; no regex, substring, wildcard, or count budget is
accepted. It reports every raw and normalized occurrence. Stale tolerated fingerprints fail as
well, forcing the allowlist to shrink when an upstream error disappears rather than leaving
permanent budget behind.

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

The browser names in this document are Playwright projects and therefore engine-level evidence,
not support claims for branded or managed enterprise deployments. Chrome Enterprise, Edge
Enterprise, and Firefox ESR support requires the additional branded deployment qualification
defined in [Compatibility](../COMPATIBILITY.md); Playwright WebKit does not establish Safari
support.


## Production-serving qualification

The local Python server remains a qualification harness rather than the production hosting contract.
It intentionally sends `Cache-Control: no-store` so the performance baseline measures warm browser
state without HTTP response-cache reuse. It also emits COOP, COEP, and CORP headers as a strict local
test boundary.

Artifact and release-intent qualification additionally require the final `dist/` tree to contain
only real files/directories: the supplied upstream-build and output roots are checked before path
resolution, and symlink entries are rejected during static assembly, cached-build reuse, structural
smoke, distribution-identity calculation, and release packaging. This prevents packaging or identity
calculation from silently dereferencing links to content outside the qualified tree.

Qualification then builds the real `deploy/Dockerfile`, starts the Nginx container, asserts its
HTTP headers and missing-asset 404 behavior, and runs the zero-retry Chromium boot gate against the
container URL. Nginx explicitly serves `Cache-Control: no-cache`, COOP `same-origin`, COEP
`require-corp`, CORP `same-origin`, `X-Content-Type-Options: nosniff`,
`Referrer-Policy: no-referrer`, and the repository Permissions-Policy.

The default OCI image intentionally omits anti-framing response headers, allowing deployers
to choose whether Code OSS may be embedded. The repository's OCI checks cover that neutral
default, not any HTTP security headers injected by the production TLS proxy or CDN. Operators
must verify their chosen `frame-ancestors` policy and HSTS at the real public HTTPS endpoint,
including an iframe allow/deny check appropriate to the customer deployment.

Stable promotion verifies GitHub Pages deployment identity first, then runs the same packaged-workbench
Chromium boot test against the live Pages URL before marking stable successful. The locked Playwright
runtime used for that gate is published as a checksummed and attested immutable GitHub Release asset,
so retries and rollbacks do not depend on Actions artifact retention. Legacy releases that predate
that runtime asset remain rollback-eligible only when prior successful stable deployment history
already proves the release was stable. GitHub Pages response headers and CDN cache policy are
platform-controlled, so the repository asserts successful HTML serving and browser boot without
claiming control over exact Pages cache/security headers.
