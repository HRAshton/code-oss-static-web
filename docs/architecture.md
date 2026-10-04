# Architecture

Code OSS Static Web turns one immutable Code - OSS revision into a browser-only static distribution
and publishes the exact qualified bytes through three independent channels. The project deliberately
does not maintain a source fork: upstream source is fetched into a disposable checkout, transformed
from repository-owned configuration, built, converted into a static distribution, qualified, and
then rebuilt independently for release.

This document describes the components, data flows, trust boundaries, and control ownership. Security
threats and residual risks are analyzed in the [threat model](../security/threat-model.md). Major
design choices are recorded in the [ADR index](adr/README.md).

## Design constraints

- The upstream identity is an exact tag plus 40-character commit recorded in
  [upstream.lock.json](../upstream.lock.json).
- Upstream source is disposable input, not a maintained project branch or fork.
- <code>dist/</code> is the canonical runtime artifact. Browser qualification, packaging, Pages, and
  OCI publication consume that distribution rather than a development server.
- Untrusted build execution is separated from attestation and publication authority.
- Browser capabilities that cannot be made deployment-independent and fail-safe, notably secure
  webviews, remain disabled.
- Default runtime network policy is deny-by-default and same-origin only.
- Release tags are immutable; publication retries reconcile the existing immutable release rather
  than creating different bytes for the same tag.

## Components

| Component | Responsibility | Important implementation paths |
| --- | --- | --- |
| Upstream identity | Pins the Microsoft repository, release tag, exact commit, and source date epoch. | [upstream.lock.json](../upstream.lock.json), [scripts/validate_config.py](../scripts/validate_config.py), [scripts/fetch_upstream.py](../scripts/fetch_upstream.py) |
| Disposable upstream checkout | Resolves the remote tag, fetches the exact commit into <code>.work/vscode</code>, and verifies <code>HEAD</code>. | [scripts/fetch_upstream.py](../scripts/fetch_upstream.py) |
| Product preparation | Applies deterministic product metadata changes and validates any extension-specific proposed API grants against the pinned upstream definitions. | [config/product-transform.json](../config/product-transform.json), [scripts/prepare_upstream.py](../scripts/prepare_upstream.py), [patches/manifest.json](../patches/manifest.json) |
| Upstream build | Runs the Code - OSS install/build in the disposable checkout and exports only the browser build plus the minimal Playwright runtime needed for qualification. | [scripts/build.py](../scripts/build.py), [build.sh](../build.sh), [scripts/export_playwright_runtime.py](../scripts/export_playwright_runtime.py) |
| Static assembler | Copies the optimized upstream web build, writes the static bootstrap and CSP, applies fail-closed runtime defaults, and adds locked browser extensions. | [scripts/make_static.py](../scripts/make_static.py), [config/runtime.json](../config/runtime.json), [config/network-policy.json](../config/network-policy.json) |
| Extension ingestion | Acquires only exact locked VSIX bytes, verifies hashes/source/license/archive policy, and installs browser-compatible extensions into the distribution. | [scripts/extension_lock.py](../scripts/extension_lock.py), [extensions/README.md](../extensions/README.md), [extensions/extensions.lock.json](../extensions/extensions.lock.json), [extensions/source-policy.json](../extensions/source-policy.json), [extensions/license-policy.json](../extensions/license-policy.json) |
| Qualification | Classifies pull-request risk, runs a read-only release/tooling lane for publication/promotion control-plane changes, requires real <code>dist/</code> plus packaging integration for distribution-dependent release changes, boots artifact changes as a static site, and for high-risk runtime changes runs multi-browser behavioral/security qualification. | [.github/workflows/qualify.yml](../.github/workflows/qualify.yml), [.github/actions/release-metadata-qualification/action.yml](../.github/actions/release-metadata-qualification/action.yml), [.github/actions/browser-qualification/action.yml](../.github/actions/browser-qualification/action.yml), [scripts/classify_pr.py](../scripts/classify_pr.py), [tests/e2e](../tests/e2e) |
| Packaging and metadata | Produces deterministic archives, checksums, artifact manifest, native SBOM, independent Syft component inventory/comparison, license inventory, and distribution tree identity. | [scripts/package_release.py](../scripts/package_release.py), [scripts/generate_sbom.py](../scripts/generate_sbom.py), [scripts/compare_sbom_inventory.py](../scripts/compare_sbom_inventory.py), [security/sbom-comparison-policy.json](../security/sbom-comparison-policy.json), [scripts/generate_license_inventory.py](../scripts/generate_license_inventory.py), [scripts/verify_release.py](../scripts/verify_release.py) |
| Attestation | Consumes the verified release candidate in an isolated job with OIDC/attestation permission and no source build. | [.github/workflows/release.yml](../.github/workflows/release.yml), [scripts/check_policy.py](../scripts/check_policy.py), [docs/release-security.md](release-security.md) |
| Immutable publication | After attestation, publishes the immutable GitHub Release and immutable GHCR image. GitHub Release consumes `release-candidate` plus attestation evidence; GHCR consumes the canonical `release-static-dist`. | [.github/workflows/release.yml](../.github/workflows/release.yml), [.github/actions/publish-github-release/action.yml](../.github/actions/publish-github-release/action.yml), [.github/actions/publish-oci/action.yml](../.github/actions/publish-oci/action.yml) |
| Promotion | Resolves a published immutable release, verifies its attestations and policy-bound identity, records canary/stable state as GitHub Deployments, and deploys stable Pages without rebuilding. | [.github/workflows/promote.yml](../.github/workflows/promote.yml), [config/promotion-policy.json](../config/promotion-policy.json), [scripts/promotion.py](../scripts/promotion.py), [.github/actions/publish-pages/action.yml](../.github/actions/publish-pages/action.yml) |
| Publication recovery | Reuses retained artifacts from a completed pre-publication release run for immutable GitHub Release/GHCR recovery; promotion recovery resolves durable immutable release assets and moves channel state without rebuilding. | [.github/workflows/recover-release-publication.yml](../.github/workflows/recover-release-publication.yml), [.github/workflows/promote.yml](../.github/workflows/promote.yml), [OPERATIONS.md](../OPERATIONS.md) |
| Browser runtime | Loads only static same-origin assets, enables workspace trust, keeps gallery/webviews disabled, and persists browser/workbench state in origin-scoped browser storage. | [scripts/make_static.py](../scripts/make_static.py), [tests/e2e/security.spec.cjs](../tests/e2e/security.spec.cjs), [tests/e2e/network-policy.spec.cjs](../tests/e2e/network-policy.spec.cjs), [tests/e2e/workbench.spec.cjs](../tests/e2e/workbench.spec.cjs) |

## End-to-end build and release data flow

~~~text
Repository inputs
  upstream.lock.json
  config/*
  patches/*
  extensions/*
  project scripts/workflows
        |
        | TB1: repository-controlled configuration -> external upstream identity
        v
Resolve upstream tag independently and verify exact commit
        |
        | TB2: network-fetched upstream Git objects -> disposable checkout
        v
.work/vscode @ exact detached commit
        |
        +--> deterministic product transform
        +--> explicit patch manifest
        +--> npm ci / upstream gulp vscode-web-min
        |
        | TB3: untrusted upstream/dependency execution -> project-owned static assembly
        v
.work/vscode-web
        |
        +--> strict static index/CSP/bootstrap
        +--> runtime defaults
        +--> locked extension ingestion
        |
        v
canonical dist/
        |
        | TB4: build output -> qualification evidence
        +--------------------------+
        |                          |
        v                          v
structural smoke              browser qualification
and tree identity             static host + Playwright
        |                          |
        +------------+-------------+
                     |
                     v
qualified distribution identity
(tree SHA-256 + file count + provenance)
                     |
                     | TB5: qualification run -> independent release rebuild
                     v
Release workflow on immutable v*-web.* tag
                     |
        clean build #1 + verify qualified identity
                     |
                     +--> release-static-dist
                     |       |
                     |       +--> clean build #2 + normalized distribution comparison
                     |       +--> release browser qualification
                     |       |
                     |       +--> package archives + metadata
                     |               |
                     |               | TB6: qualified static dist -> packaged release candidate
                     |               v
                     |         release-candidate
                     |         archives + checksums + manifest + native SBOM
                     |         + independent inventory/comparison + license inventory
                     |               |
                     |               | TB7: untrusted build/package jobs -> isolated attestation authority
                     |               v
                     |         OIDC provenance/SBOM attestations
                     |               |
                     +---------------+ TB8: attestation completion -> immutable publication
                                     |
                              +------+------+
                              |             |
                              v             v
                        GitHub Release     GHCR
                        release-candidate  release-static-dist
                        + attestation      immutable image
                              |             |
                              +------+------+
                                     |
                                     v
                           immutable release identity
                       tag + commit + artifact/tree digest
                                     |
                                     | TB9: immutable release -> mutable promotion state
                                     v
                                  canary
                                     |
                          policy/identity verification
                                     |
                                     v
                                  stable
                                     |
                                     v
                              GitHub Pages
                                     |
                                     v
                              static browsers
~~~

### 1. Repository inputs to upstream identity

[scripts/validate_config.py](../scripts/validate_config.py) validates the upstream repository and the
shape of the lock. [scripts/fetch_upstream.py](../scripts/fetch_upstream.py) resolves the configured
tag with <code>git ls-remote</code>, peels annotated tags, requires the resolved object to equal the
pinned commit, fetches that commit directly, checks out detached <code>HEAD</code>, and verifies the
checkout SHA again.

The control prevents a moved or mismatched tag from silently changing the source selected by the
lock. It does not make the pinned upstream commit trustworthy by itself; upstream source remains
untrusted build input.

### 2. Upstream checkout to browser build

[scripts/build.py](../scripts/build.py) hard-resets and cleans the disposable checkout before applying
the deterministic product transform, explicit patch manifest, <code>npm ci</code>, and the upstream
<code>vscode-web-min</code> build. Repository policy requires jobs that execute this build to be
read-only and without OIDC/release credentials; [scripts/check_policy.py](../scripts/check_policy.py)
enforces those workflow invariants.

Development qualification may restore the upstream web-build cache keyed by immutable build inputs in
[.github/workflows/qualify.yml](../.github/workflows/qualify.yml). The release workflow does not use
that cache and performs independent clean builds, so a cache hit is an optimization rather than
release provenance.

### 3. Browser build to canonical static distribution

[scripts/make_static.py](../scripts/make_static.py) copies the optimized upstream output into a fresh
<code>dist/</code>, writes the project-owned HTML/bootstrap, copies runtime policy, installs locked
extensions, and writes extension indexes. The generated bootstrap uses a relative base URL so the
same bytes work at an origin root or below a path prefix.

The base page CSP restricts <code>connect-src</code> to <code>'self'</code>, disables object content,
and does not include <code>unsafe-eval</code>. Webview endpoints are configured under the reserved
<code>invalid.invalid</code> domain. These defaults are statically checked by
[scripts/smoke_static.py](../scripts/smoke_static.py) and exercised by
[tests/e2e/security.spec.cjs](../tests/e2e/security.spec.cjs).

### 4. Canonical distribution to qualification evidence

The pull-request workflow classifies changed paths with
[scripts/classify_pr.py](../scripts/classify_pr.py). Documentation-only changes take the lightweight
path; product-affecting changes require a static build and Chromium boot; upstream/runtime/security
boundary changes require broader browser qualification. Unknown paths fail closed to artifact
qualification.

Browser qualification serves the artifact as a static site under a non-root prefix and verifies boot,
editor behavior, workspace trust, extension-host behavior, network policy, and fail-closed runtime
defaults. Automated upstream and patch dispatchers pass the exact project commit they inspected as
<code>expected_source_sha</code>. Workflow-dispatch qualification verifies that the checked-out
<code>GITHUB_SHA</code> equals that immutable expectation before planning or build work; branch
movement therefore fails closed instead of silently qualifying a newer source revision.
Release-intent qualification records that expected source SHA together with the normalized
distribution tree digest and file count for the exact <code>static-dist</code> artifact consumed by
the browser jobs.

### 5. Qualification evidence to independent release rebuild

The release workflow runs on an immutable release tag. It verifies qualification provenance, performs
a clean build without the development cache, and uses
[scripts/verify_dist_identity.py](../scripts/verify_dist_identity.py) to require the rebuilt
distribution to have the same tree digest and file count as the qualified artifact. A second clean
build is compared file-for-file through [scripts/compare_dist.py](../scripts/compare_dist.py).

These are separate gates: qualification binding proves the release bytes match what was tested;
reproducibility proves two clean release builds normalize to the same distribution.

### 6. Release candidate to attestations

Packaging creates deterministic archives and metadata from the rebuilt <code>dist/</code>. Before
packaging is accepted, a SHA-pinned Anchore action runs Syft against that final distribution with an
explicit JavaScript package cataloger selected by <code>security/syft.yaml</code>.
[scripts/compare_sbom_inventory.py](../scripts/compare_sbom_inventory.py) normalizes the scanner
findings and compares package identity plus artifact location with the project-generated CycloneDX
SBOM. VS Code extensions are matched to Syft's npm-style package representation by their installed
path/name/version rather than ignored. CycloneDX file components are scanner evidence rather than
software components and are excluded from the set comparison. Syft's root
<code>Code - OSS</code> npm package is normalized to the native upstream application identity rather
than excepted. Nested <code>extensions/*/server/package.json</code> components discovered by Syft are
included in the native runtime metadata and SBOM.

The comparison emits <code>independent-component-inventory.json</code> and
<code>sbom-comparison.json</code>. Any independent package not represented by the native SBOM, any
native package not represented independently, or an empty independent software inventory fails
packaging unless a narrow reviewed exception in
[security/sbom-comparison-policy.json](../security/sbom-comparison-policy.json) explains the
representation difference. Current exceptions are exact purl+path identities for optimized runtime
package directories that omit <code>package.json</code> from the final distribution; their native
records remain bound to the pinned upstream package lock. The comparison rejects stale exceptions,
so version/path drift requires review.

The attestation job is intentionally downstream of build/package work. Repository policy requires the
attestation job to have the required OIDC/attestation permissions while prohibiting source checkout,
shell build steps, or upstream build execution. Pull-request composition validation runs in the
read-only package job; attestation remains disabled for pull requests. The security design is
documented in [docs/release-security.md](release-security.md).

### 7. Attestation to immutable publication

Attestation completion gates immutable publication. GitHub Release consumes the packaged
<code>release-candidate</code> plus attestation evidence, while GHCR consumes the canonical
<code>release-static-dist</code>. Both cross the protected <code>release</code> environment and
re-check immutable-tag invariants immediately before publication.

Immutable publication is retry-safe and fail-closed. GitHub Release assets are reconciled
monotonically; conflicting or incomplete published content is never overwritten. GHCR distinguishes a
confirmed missing tag from indeterminate registry state, verifies existing images, and re-verifies
newly published images.

### 8. Immutable release to canary and stable

Deployment state is deliberately separate from release creation. After immutable GitHub Release and
GHCR publication succeed, the Release workflow automatically dispatches
[.github/workflows/promote.yml](../.github/workflows/promote.yml) on the immutable release ref.

Promotion downloads durable GitHub Release assets, verifies their attestations and checksums, and
builds a promotion identity containing the immutable release tag/commit, GitHub Release ID, archive
digest, distribution tree digest/file count, and promotion policy/profile digest. It never executes
the upstream build, packaging, or attestation.

The happy path is automatic: the immutable release is recorded as a successful <code>canary</code>
deployment after artifact verification, then the exact same release/artifact/policy identity is
promoted to <code>stable</code> and deployed to GitHub Pages. Before upload, promotion derives a
machine-readable <code>deployment-identity.json</code> from the verified immutable release identity.
It records the release tag and commit, canonical distribution tree SHA-256, and deployment-profile ID
and digest when that immutable release contains profile metadata. Legacy releases preserve
<code>deploymentProfile: null</code> in the Pages identity so the migration-era rollback contract
remains representable without manufacturing provenance that did not exist. The file is Pages
promotion metadata added after the canonical distribution digest is established, so it does not
create a self-referential tree digest.

After <code>actions/deploy-pages</code> completes, the shared Pages action resolves the returned Pages
URL, fetches <code>deployment-identity.json</code> with a cache-busting query, and requires exact
equality with the expected promotion identity projection. The Pages deployment status keyed to the
workflow SHA remains a transport-status check only; the live identity check independently proves the
served site is the intended immutable release, including rollback runs whose workflow SHA differs
from the release commit. GitHub Deployments provide the auditable channel history.

Automatic promotion refuses to move stable backward. An explicit rollback is a new stable promotion
to an identity that has previously been successful in stable (or a legacy successful Pages
deployment during migration). Release tags, GitHub Release assets, and immutable GHCR tags never move.

### Canary serving model

A canary promotion is a real Pages deployment, not an artifact-only deployment record. The workflow
reconstructs the previously successful stable release at the Pages root from its immutable,
attested GitHub Release archive, preserves that release's root deployment identity, and publishes the
candidate below `__canary/<release-tag>/`. During migration, a successful legacy `github-pages`
deployment plus the live root deployment identity is used to recover and verify the exact immutable
production release when no `stable` record exists yet. The candidate carries the same promotion
identity later required by stable promotion. A live identity fetch and Chromium boot synthetic must
succeed before
the repository records the `canary` deployment as successful.

Automatic stable promotion depends on that successful canary identity. Stable publication then
replaces the Pages root with the exact same immutable candidate release. A failed or indeterminate
canary therefore cannot advance the stable channel.

Immutable publication recovery remains artifact-only through
[.github/workflows/recover-release-publication.yml](../.github/workflows/recover-release-publication.yml).
Promotion recovery uses the durable immutable GitHub Release as its source and changes only deployment
state; it does not rebuild or re-attest release content.

## Runtime data flows

### Static host to browser

The supported deployment is a normal static HTTPS origin. The browser loads <code>index.html</code>,
<code>static-bootstrap.mjs</code>, <code>runtime.json</code>, extension metadata, and Code - OSS assets
from the same origin. Clean startup is expected to make no cross-origin HTTP requests and no
WebSocket connections; [tests/e2e/network-policy.spec.cjs](../tests/e2e/network-policy.spec.cjs)
checks both behavior and CSP rejection of an arbitrary cross-origin fetch.

A static host or CDN is therefore part of the runtime trust base: anyone able to replace served
JavaScript can execute with the application's browser-origin authority. TLS, host/CDN account
security, immutable deployment provenance, and cache invalidation are deployment responsibilities
outside the repository's build-time controls.

### Workbench to extensions and workspace content

Workspace trust is enabled in the generated workbench and checked by
[tests/e2e/workbench.spec.cjs](../tests/e2e/workbench.spec.cjs). Additional bundled extensions are
explicit release inputs governed by the extension lock/source/license/archive policies. Qualification
checks that the browser extension host activates and that extension state/filesystem persistence
works in [tests/e2e/extension-host.spec.cjs](../tests/e2e/extension-host.spec.cjs).

Workspace trust reduces accidental execution against untrusted workspaces; it is not a sandbox for an
extension that a maintainer deliberately bundles or a user deliberately installs.

### Workbench to webviews

Secure Code - OSS webviews normally depend on an isolated origin/subdomain. Generic static hosting
cannot guarantee that isolation portably, so the product intentionally points webview endpoints at
<code>invalid.invalid</code> and keeps runtime webviews disabled. The project does not weaken upstream
origin, CSP, sandbox, or hostname assumptions merely to render webviews.

### Browser storage

Extension global state and the browser filesystem persist across workbench reloads. Browser storage
is origin-scoped, not path-scoped: hosting this application at <code>/code-oss-web/</code> on an origin
shared with unrelated applications does not create a storage security boundary between those paths.

Deployments that require isolation from sibling applications should use a dedicated origin. Users and
operators should also treat site-data clearing, private browsing, browser policy, quota eviction, and
origin migration as possible data-loss events. The supported static mode intentionally does not add a
service-worker offline cache, so runtime availability depends on the host continuing to serve the
static assets.

## Trust boundaries

| Boundary | Crossing | Main controls | Owner |
| --- | --- | --- | --- |
| TB1 | Repository config -> upstream identity | Lock schema, exact tag/commit binding | Maintainers + CI |
| TB2 | Upstream network -> disposable checkout | Direct commit fetch, detached HEAD verification | CI |
| TB3 | Upstream/dependencies -> project assembly | Disposable checkout, read-only build jobs, no release/OIDC credentials | CI policy |
| TB4 | Build output -> qualification | Canonical <code>dist/</code>, artifact smoke/browser tests, tree identity | CI |
| TB5 | Qualification -> release rebuild | Provenance verification, qualified tree digest/file count | Release workflow |
| TB6 | Rebuild -> release candidate | Second clean build and normalized distribution comparison | Release workflow |
| TB7 | Candidate -> attestation authority | Source-free/build-free attestation job, minimal write permissions | GitHub Actions + maintainers |
| TB8 | Attestation -> immutable publication | Protected <code>release</code> environment, immutable tag checks, channel-specific artifact verification | Repository settings + maintainers |
| TB9 | Immutable release -> canary/stable -> browser | Policy-bound promotion identity, serialized GitHub Deployments, stable Pages deployment, rollback by pointer movement | Release workflow + GitHub/host operator + browser |

## Control ownership

Repository maintainers own configuration, locks, ADRs, review policy, workflow definitions, release
environment policy, and response to conflicts. GitHub Actions supplies hosted runners, OIDC,
attestation, artifact transport, protected environments, Releases, Pages, and GHCR services. The
static-host operator owns the final serving origin, TLS, CDN/account security, caching behavior, and
whether the application has a dedicated origin. Browsers enforce same-origin policy, CSP, storage
semantics, and user-controlled site-data lifecycle. Users decide which workspaces and separately
installed extensions they trust.

No single owner eliminates all risk. The control split is intentional so release authority is not
present in the jobs that execute upstream build code.

## Architectural decisions

- [ADR-0001: Integrate immutable upstream source without a maintained fork](adr/0001-no-source-fork.md)
- [ADR-0002: Fail closed when secure webview isolation is unavailable](adr/0002-fail-closed-webviews.md)
- [ADR-0003: Treat bundled extensions as explicit trusted release inputs](adr/0003-extension-trust.md)
- [ADR-0004: Scope proposed API grants to documented extension IDs](adr/0004-proposed-api-policy.md)
- [ADR-0005: Separate qualification, release rebuild, attestation, and promotion](adr/0005-release-promotion.md)
- [ADR-0006: Keep gallery and runtime network access disabled by default](adr/0006-gallery-network-policy.md)
