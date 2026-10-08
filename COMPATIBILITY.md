# Compatibility

This document defines the browser and deployment environments supported by Code OSS Static Web.
It applies to the currently supported project release described in [Support](SUPPORT.md).

A browser engine passing Playwright is not, by itself, a support promise for a branded browser
deployment. Company support depends on the complete deployment tuple: release artifact, browser
brand/version, operating-system image, managed-browser policy, proxy/network path, storage mode,
and static-hosting configuration.

## Evidence levels

- **Tested Playwright engine** means the canonical static artifact passed the repository's automated
  Playwright suite using a Playwright-managed browser build. This is engine-level compatibility
  evidence only.
- **Supported browser deployment** means the exact branded deployment is inside the version window
  below and has a successful deployment-qualification record for the exact company environment.
- **Unsupported** means the project makes no support promise, even when a related Playwright engine
  happens to pass.

Full qualification exercises the Playwright Chromium, Firefox, and WebKit projects on Linux.
Release validation reuses the same browser qualification implementation for Chromium. Neither run
claims that Google Chrome, Microsoft Edge, Firefox ESR, or Safari has been tested as a branded,
managed enterprise deployment.

## Current deployment shape

The repository currently has one supportable deployment shape: the zero-backend static runtime
produced in `dist/`. This document calls it the **baseline static deployment** for clarity; there
is not yet a selectable deployment-profile system.

The baseline static deployment has these fixed boundaries:

- all application assets are static files served from one origin, optionally below a path prefix;
- telemetry is disabled;
- the extension gallery is disabled;
- secure webviews are disabled and fail closed;
- runtime network policy is default-deny with only `self` allowed;
- no service-worker offline cache is part of the product;
- additional extensions are admitted at build time from the immutable extension lock.

A deployment that changes those boundaries is a different product profile and is unsupported until
it has its own reviewed policy and qualification contract.

## Branded browser support

Browser-version names are evaluated on the date of deployment qualification. The qualification
record must include the exact browser version; channel names alone are not sufficient.

| Browser deployment | Support status | Version window | Required evidence |
| --- | --- | --- | --- |
| Google Chrome Enterprise desktop | Supported after deployment qualification | Current Stable | Playwright Chromium evidence plus the manual deployment qualification below |
| Google Chrome Enterprise desktop | Supported after deployment qualification | Immediately previous Stable | Playwright Chromium evidence plus the manual deployment qualification below |
| Microsoft Edge Enterprise desktop | Supported after deployment qualification | Current Stable | Playwright Chromium evidence plus the manual deployment qualification below |
| Mozilla Firefox desktop | Supported after deployment qualification | Current ESR | Playwright Firefox evidence plus the manual deployment qualification below |
| Apple Safari desktop | Unsupported | Any | Playwright WebKit is not a Safari support claim |
| Mobile Chrome, Firefox, Safari, and other mobile browsers | Unsupported | Any | No mobile qualification |
| Embedded WebViews, WKWebView, Android WebView, Teams/Slack-style hosts, and similar containers | Unsupported | Any | No embedded-host qualification |

Support attaches to the qualified operating-system image as well as the browser. Passing on one
Windows, macOS, or Linux image does not establish support for every OS image that can run the same
browser.

When a supported browser moves outside the recorded version window, the new browser version needs a
new deployment-qualification record before company support is claimed for it.

## Manual deployment qualification

The enterprise browser rows above require a manual qualification because the automated matrix uses
Playwright-managed engines rather than the company's branded browser, OS image, policy set, proxy,
and identity/network stack.

For every supported deployment tuple, record at least:

- Code OSS Static Web release tag and canonical distribution digest or other immutable artifact
  identity;
- browser brand, full version, and release channel;
- OS edition/version/build or managed image identifier;
- managed-browser policy set identifier or revision;
- proxy/network path used by the deployment;
- static-hosting URL and base path;
- normal persistent-storage mode;
- qualification date and operator/reviewer.

Use the [enterprise browser qualification record template](docs/enterprise-browser-qualification-record.md)
to capture the full tuple, per-check outcomes, extension-specific results, evidence references,
and an independent approval. Store completed records in the company's private
deployment/promotion or change-management system. Do not commit enterprise policy exports,
proxy credentials, authentication material, or other internal secrets to this public repository.

Using the exact release artifact and the actual company deployment path, perform these checks from a
clean, non-private browser profile without development flags:

1. Load the workbench from its production base path and confirm the packaged workbench reaches the
   ready state without a fatal page error.
2. Edit text, open and close the command palette with the normal keyboard shortcut, open Settings,
   and confirm workspace trust is enabled.
3. Reload the workbench, then fully restart the browser and confirm ordinary workbench settings or
   other expected browser-backed state persists.
4. Exercise each company-supported locked extension's activation and primary supported workflow.
   Extensions are supported separately; a passing workbench does not qualify every extension.
5. Confirm the actual managed policy and proxy path do not cause fatal CSP, module, worker, storage,
   or asset-loading failures.
6. Confirm application assets are served from the intended origin/base path and are not rewritten to
   an HTML fallback, blocked, substituted, or redirected to an unqualified cross-origin asset host.
7. Record any browser policy exceptions or known deployment limitations in the same qualification
   record.

A missing or stale manual record means the branded deployment has Playwright engine evidence only,
not a company browser support promise.

## Managed browser policies

Managed browsers are supported only as the exact policy set represented by a successful deployment
qualification. Policies that disable or interfere with capabilities exercised by qualification are
unsupported. Examples include policies that block module or worker execution, disable required
browser storage, force site-data clearing that removes required persistence, or inject security
controls that prevent the static assets from executing.

Enterprise extension injection is not automatically incompatible, but any injected browser
extension that changes page behavior, networking, storage, or CSP is part of the deployment tuple
and must be present during qualification.

## Corporate proxies and network controls

A corporate forward proxy, reverse proxy, authentication gateway, or TLS-inspection path is
supported only when the exact production path passes deployment qualification.

The baseline product does not require an application backend, WebSocket service, or cross-origin API.
Clean startup is automatically qualified for zero cross-origin HTTP requests and zero WebSockets.
Proxy or gateway behavior that rewrites the application bytes, changes the application origin,
substitutes asset responses, blocks required same-origin requests, or prevents the built-in CSP from
executing the application is unsupported.

## Storage and private browsing

Normal browser mode with persistent site storage is part of the supported deployment contract.
Automated extension-host qualification verifies extension global state and browser-filesystem state
across workbench reloads.

Clearing browser site data is expected to remove browser-backed settings, extension state, and
browser filesystem data. Browser profile roaming or cross-device synchronization is not a support
promise.

Private/incognito browsing and managed profiles configured to clear site data on exit are
unsupported because persistence is intentionally not guaranteed in those modes.

## Automated hosting targets

The OCI image is an explicitly qualified hosting target: qualification builds the shipped Nginx
image, checks its response-header contract, and boots the workbench through Chromium against the
running container. GitHub Pages is qualified after stable publication through live
deployment-identity verification and a Chromium browser boot. Pages CDN/cache headers remain
controlled by GitHub rather than this repository.

## Static hosting and CSP

Company deployments must use HTTPS except for loopback-only development/qualification servers. The
release may be hosted at the origin root or below a path prefix.

The deployment must:

- serve the canonical release files without modifying their bytes;
- serve JavaScript modules and other assets with browser-acceptable content types;
- preserve the configured base path and relative asset URLs;
- avoid rewriting missing asset requests to `index.html`;
- keep application assets on the application origin.

The generated page includes a restrictive CSP. In particular, runtime connections are restricted to
`self`; scripts and workers require the repository's self/blob allowances; styles require the
repository's inline-style allowance. A hosting platform or gateway may add a CSP header only when
the combined policy still permits the baseline application to run. A deployment cannot rely on a
proxy or response header to broaden the generated meta policy.

The generated application and shipped OCI Nginx configuration are **iframe-neutral by default**:
they do not impose an HTTP anti-framing policy. This allows embedding, but provides no
clickjacking protection. Each deployment operator must decide whether to prohibit framing,
permit only same-origin framing, or allow explicitly approved embedding origins.

When anti-framing protection is required, send an HTTP `Content-Security-Policy` header on
the **Code OSS document response** at the actual public serving edge. For example:

- Prohibit embedding: `Content-Security-Policy: frame-ancestors 'none'`
- Allow an approved portal: `Content-Security-Policy: frame-ancestors 'self' https://portal.example.com`

`frame-ancestors` cannot be enforced through the generated meta CSP. Setting a policy on
the parent portal alone does not restrict who else may frame Code OSS. Avoid conflicting
`X-Frame-Options: DENY` or `SAMEORIGIN` headers if cross-origin embedding is intended.
Multiple HTTP CSP policies are enforced together, so adding a permissive policy cannot
override an existing restrictive one. Qualify the resulting embedding behavior in the
customer's actual browser and hosting environment.

The OCI image also serves `Cross-Origin-Resource-Policy: same-origin`. A cross-origin
portal using `Cross-Origin-Embedder-Policy: require-corp` cannot assume that an
allowing `frame-ancestors` policy is sufficient: the portal's COEP may still block
the frame. For a qualified cross-origin portal deployment, the operator may need to
**replace the CORP header on the Code OSS HTML document response** with
`Cross-Origin-Resource-Policy: cross-origin` while preserving the document's
`Cross-Origin-Embedder-Policy: require-corp` and setting the appropriate
`frame-ancestors` allowlist. Keep the existing `same-origin` CORP on static assets
unless separately reviewed. Unlike `frame-ancestors`, CORP has no arbitrary-origin
allowlist: `cross-origin` is a broad opt-in to cross-origin no-CORS loading. Test
the exact iframe, browser, and authentication/storage behavior at the public edge;
do not change the default OCI image to relax these headers globally.

GitHub Pages does not expose arbitrary response-header configuration to this repository.
Clients needing an enforced anti-framing policy for Pages-hosted artifacts must serve the
application behind a controlled HTTP edge or host it themselves; changing only the
embedding page cannot set the required header. HSTS likewise belongs at the
TLS-terminating production edge, not in the static HTML or the HTTP-only OCI server.

Cross-origin asset CDNs and extensions that require arbitrary cross-origin network access are not
supported by the baseline static deployment.

## Offline behavior

Offline operation is unsupported. The baseline deployment deliberately does not register a
service-worker cache, and the hosted assets must remain reachable. A browser or intermediary cache
may improve repeat loads, but cache presence is not an offline availability contract.

## Webviews and embedded hosts

Secure Code OSS webviews are unsupported in the baseline static deployment and are configured to
fail closed. Supporting webviews requires an isolated webview origin/subdomain architecture,
separate threat modelling, and separate qualification.

No `company-webview` or equivalent deployment profile exists yet. Embedded browser/webview
containers are likewise unsupported even when their rendering engine resembles a tested Playwright
engine.

## Extension API limitations

Only browser-compatible extensions are candidates for support. Locked extensions must have a
non-empty `browser` entry point, exact version and digest, and must pass the repository's extension
ingestion policy.

The baseline static deployment does not support extensions that require:

- a Node.js-only extension host or a `main` entry point without a browser entry point;
- native modules, local process execution, or direct host-OS filesystem access;
- secure Code OSS webviews;
- runtime installation from a public extension gallery;
- arbitrary cross-origin network access blocked by the baseline CSP/network policy.

Proposed APIs are not a general compatibility promise. An extension that depends on a proposed API
needs explicit policy review and extension-specific qualification.

The repository's automated extension fixture proves browser extension-host activation, global-state
persistence, browser-filesystem persistence, and JavaScript language-service initialization. It does
not prove compatibility for every third-party extension.

## Qualification map

| Support claim | Qualification evidence |
| --- | --- |
| Static boot, editing, commands, Settings, workspace trust | Automated Playwright suite |
| Default network/CSP/telemetry/gallery/webview policy | Automated Playwright security coverage |
| Browser extension-host activation and persistence | Automated Playwright extension-host coverage |
| No supported offline cache | Automated service-worker absence check |
| Chrome Enterprise Stable and previous Stable | Playwright Chromium plus manual branded deployment record |
| Edge Enterprise Stable | Playwright Chromium plus manual branded deployment record |
| Firefox ESR | Playwright Firefox plus manual branded deployment record |
| Managed browser policy, proxy, OS image, and hosting tuple | Manual branded deployment record |
| Safari, mobile browsers, private browsing, embedded WebViews, secure webviews | Unsupported; no support evidence is claimed |

See [Browser qualification](docs/testing.md) for the automated engine topology and
[Extensions](extensions/README.md) for extension admission rules.
