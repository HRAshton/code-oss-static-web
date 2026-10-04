# Threat model

This threat model covers repository-controlled build/release tooling and the supported browser-only
static deployment of Code OSS Static Web. It complements the component and data-flow description in
[docs/architecture.md](../docs/architecture.md) and the release-specific design in
[docs/release-security.md](../docs/release-security.md).

The goal is not to claim that upstream Code - OSS, third-party dependencies, GitHub, browsers, or
static hosts are trusted absolutely. The design reduces where those parties can influence release
identity, publication authority, and browser behavior, and makes important failures observable and
fail closed.

## Assets

- **Release identity and integrity:** the mapping from project commit and pinned upstream commit to
  the exact distributed static files.
- **Qualification evidence:** proof that the distribution released is the distribution that passed
  the required browser/security checks.
- **Provenance and metadata:** checksums, artifact manifest, SBOM, license inventory, and attestations.
- **Release immutability and promotion state:** immutable release tags, GitHub Release assets, and GHCR images, plus auditable canary/stable deployment pointers selecting an immutable release.
- **Repository/release authority:** maintainer accounts, protected environments, workflow tokens,
  OIDC identities, and repository settings.
- **Browser-origin authority:** JavaScript served by the deployment origin and the capabilities
  available to the workbench and web extension host.
- **Workspace/user data:** opened workspace content, editor state, extension global state, and browser
  filesystem/storage persisted by the origin.
- **Extension trust decisions:** exact bundled extension bytes, source origins, declared licenses, and
  any extension-specific proposed API grants.

## Threat actors and failure sources

- A compromised or malicious upstream repository/release.
- A compromised npm/runtime dependency or dependency download path.
- A malicious contributor attempting to alter build, workflow, configuration, or release policy.
- A compromised maintainer or GitHub account with repository write or settings authority.
- A compromised third-party GitHub Action or hosted runner.
- An attacker able to poison caches or substitute workflow artifacts.
- A malicious or compromised extension publisher, registry, mirror, CDN, or VSIX file.
- A malicious workspace attempting to trigger code execution or abuse extension behavior.
- A publication-service failure or attacker presenting conflicting Release/Pages/registry state.
- A compromised static host/CDN account or sibling application sharing the deployment origin.
- Normal browser/storage failures such as quota eviction, site-data clearing, or origin migration.

## Security assumptions

1. GitHub's repository, Actions, environment, OIDC, attestation, artifact, Release, Pages, and GHCR
   services enforce their documented identity/permission boundaries.
2. SHA-256 is collision resistant for the project use cases.
3. The protected default branch and <code>release</code> environment are configured to require the
   intended human review/deployment protections. Repository files document and test expected policy,
   but cannot by themselves force every GitHub setting.
4. The browser correctly enforces HTTPS origin semantics, CSP, sandboxing, and storage isolation.
5. Release users obtain artifacts from the intended GitHub/Pages/GHCR endpoints and validate
   attestations/checksums when their threat model requires it.
6. A maintainer who deliberately changes policy can change future releases. The design makes policy
   changes reviewable and separates duties during automation; it is not a defense against every
   authorized administrator acting maliciously.
7. Workspace trust and extension policy reduce exposure but do not turn arbitrary extension code into
   a strong sandbox.

## Threats, controls, tests, and residual risk

| Threat | Controls and enforcement | Verification | Control owner | Residual risk |
| --- | --- | --- | --- | --- |
| **T1. Upstream tag is moved or does not identify the reviewed commit.** | [scripts/fetch_upstream.py](../scripts/fetch_upstream.py) independently resolves and peels the tag, requires it to equal the 40-character lock commit, fetches the commit directly, and verifies detached <code>HEAD</code>. [scripts/validate_config.py](../scripts/validate_config.py) restricts the upstream repository and lock shape. | CI config validation; <code>fetch_upstream.py --verify-tag-only</code>; tooling tests in [tests/test_tooling.py](../tests/test_tooling.py). | Maintainers + CI | A correctly pinned upstream commit can itself contain malicious code. |
| **T2. Upstream/dependency code compromises the build job.** | Upstream source lives in disposable <code>.work/vscode</code>; [scripts/build.py](../scripts/build.py) resets/cleans it before preparation. Jobs that execute upstream install/build code are required to be read-only, without release credentials or OIDC; [scripts/check_policy.py](../scripts/check_policy.py) enforces workflow policy. | Repository policy checks in <code>make check</code>/CI; release workflow tests in [tests/test_tooling.py](../tests/test_tooling.py). | CI policy + GitHub Actions | A compromised runner can corrupt that job's outputs or logs. Later identity/reproducibility gates reduce release substitution risk but do not make the runner trustworthy for secrets it legitimately receives. |
| **T3. A contributor changes a security boundary without adequate qualification.** | [scripts/classify_pr.py](../scripts/classify_pr.py) keeps runtime/build and qualification-infrastructure changes on artifact/full qualification, while an explicit release-only allowlist uses a read-only policy/unit-test lane; mixed or unknown paths fail closed to the stronger applicable qualification. The protected branch requires the Artifact qualification gate and human review per [CONTRIBUTING.md](../CONTRIBUTING.md). | [tests/test_pr_qualification.py](../tests/test_pr_qualification.py), [.github/workflows/qualify.yml](../.github/workflows/qualify.yml), [.github/actions/release-metadata-qualification/action.yml](../.github/actions/release-metadata-qualification/action.yml). | Maintainers + branch protection | Repository settings can drift from the checked-in expectation; classification depends on maintaining the explicit allowlists as new trust-boundary files are added. |
| **T4. Maintainer/account compromise creates an unauthorized release from an arbitrary commit.** | Release authorization requires the tagged commit to be on the repository default-branch history; release tags are protected by [.github/rulesets/immutable-release-tags.json](../.github/rulesets/immutable-release-tags.json); publication crosses the protected <code>release</code> environment. | Policy checks plus authorization jobs in [.github/workflows/release.yml](../.github/workflows/release.yml); release design tests in [tests/test_tooling.py](../tests/test_tooling.py). | Repository administrators + GitHub | An attacker controlling enough administrator/reviewer accounts or repository settings can still authorize malicious future releases. Existing immutable external copies/attestations aid detection, not prevention of all admin abuse. |
| **T5. A compromised third-party Action gains release authority.** | Actions are SHA-pinned by repository policy. Build jobs do not receive release/OIDC authority. Attestation and publication authority is confined to downstream jobs/actions with explicit permissions. | [scripts/check_policy.py](../scripts/check_policy.py), CI policy tests. | Maintainers + GitHub Actions | SHA pinning protects against tag movement, not compromise already present in the pinned action commit or GitHub runtime. |
| **T6. Development cache poisoning substitutes release bytes.** | The upstream build-output cache key includes the upstream lock, toolchain versions, build/preparation scripts, product transform, and patches. A separate npm download cache only supplies package tarballs to `npm ci`; dependency selection remains bound to the lockfile in the pinned upstream revision. Release publication performs clean builds without <code>actions/cache</code>, verifies the qualified tree identity, and compares a second clean distribution. | [.github/workflows/qualify.yml](../.github/workflows/qualify.yml), [.github/workflows/release.yml](../.github/workflows/release.yml), [scripts/verify_dist_identity.py](../scripts/verify_dist_identity.py), [scripts/compare_dist.py](../scripts/compare_dist.py), [tests/test_tooling.py](../tests/test_tooling.py). | CI/release workflow | A cache can still waste CI time or corrupt non-release qualification. If the same compromise controls qualification and release infrastructure consistently, reproducibility alone may not detect it. |
| **T7. Workflow artifact substitution or poisoning breaks the tested-to-released binding.** | Browser qualification consumes the canonical <code>static-dist</code>; release-intent qualification records its tree digest/file count and provenance. Release independently rebuilds and requires exact distribution identity before packaging. Attestation is performed only after candidate verification. | Qualification/release workflow checks, [scripts/verify_dist_identity.py](../scripts/verify_dist_identity.py), [scripts/compare_dist.py](../scripts/compare_dist.py). | GitHub Actions + maintainers | The design depends on GitHub artifact/provenance identity and on the correctness of the tree-digest implementation. |
| **T8. Malicious or compromised VSIX input abuses acquisition or archive extraction.** | Extensions require exact ID/version/SHA-256, approved source origins, browser entrypoint, allowed license, no duplicate upstream ID, bounded archive/download sizes, entry counts, path validation, symlink rejection, and expansion-ratio limits. Digest verification occurs before archive inspection. | [scripts/extension_lock.py](../scripts/extension_lock.py), [scripts/validate_config.py](../scripts/validate_config.py), [extensions/README.md](../extensions/README.md), extension tests in [tests/test_tooling.py](../tests/test_tooling.py). | Maintainers | A byte-for-byte approved extension may still contain malicious logic or later-discovered vulnerabilities. |
| **T9. Bundled or user-installed extension abuses workbench privileges or user data.** | Bundled extensions are explicit locked release inputs; workspace trust remains enabled; qualification verifies the browser extension host and persistence behavior. No extension is bundled by default today. | [extensions/extensions.lock.json](../extensions/extensions.lock.json), [tests/e2e/extension-host.spec.cjs](../tests/e2e/extension-host.spec.cjs), [tests/e2e/workbench.spec.cjs](../tests/e2e/workbench.spec.cjs). | Maintainers for bundled extensions; users for separately installed extensions | Workspace trust is not a security sandbox for an extension that is allowed to execute. Extension code can act with the capabilities exposed by the web extension host and may access workspace/state available to it. |
| **T10. Malicious workspace triggers execution before trust is established.** | Generated workbench configuration sets <code>enableWorkspaceTrust: true</code>. Security-sensitive changes receive full qualification. | [scripts/make_static.py](../scripts/make_static.py), [tests/e2e/workbench.spec.cjs](../tests/e2e/workbench.spec.cjs). | Upstream Code - OSS + maintainers | Enforcement semantics are inherited from upstream Code - OSS. Bugs in upstream trust handling or extensions that ignore trust can remain exploitable. |
| **T11. Proposed API access expands silently or drifts from upstream.** | Grants live in [config/product-transform.json](../config/product-transform.json), are extension-ID scoped, and [scripts/prepare_upstream.py](../scripts/prepare_upstream.py) fails if a named proposal definition is absent. Current Remotish compatibility does not bundle the extension. | [tests/test_proposed_api_grants.py](../tests/test_proposed_api_grants.py), [docs/remotish-compatibility.md](../docs/remotish-compatibility.md). | Maintainers | Proposed APIs are unstable by definition; an upstream semantic change can preserve a definition filename while changing behavior. |
| **T12. Unexpected runtime network/gallery traffic leaks data.** | Runtime gallery mode is disabled; upstream Marketplace-style built-in downloads and auto-updates are removed; [config/network-policy.json](../config/network-policy.json) is default-deny/self-only; generated CSP uses <code>connect-src 'self'</code>. | [scripts/validate_config.py](../scripts/validate_config.py), [scripts/smoke_static.py](../scripts/smoke_static.py), [tests/e2e/security.spec.cjs](../tests/e2e/security.spec.cjs), [tests/e2e/network-policy.spec.cjs](../tests/e2e/network-policy.spec.cjs). | Maintainers + browser | CSP is not a universal application firewall and does not by itself govern every possible navigation or future browser primitive. User actions or separately installed code may introduce additional network behavior that requires review. |
| **T13. Webview content gains same-origin authority because generic static hosting lacks isolated webview origins.** | Webview endpoint templates use <code>invalid.invalid</code>, runtime webviews are disabled, and the project refuses to bypass upstream origin/CSP/sandbox assumptions. | [scripts/make_static.py](../scripts/make_static.py), [scripts/validate_config.py](../scripts/validate_config.py), [scripts/smoke_static.py](../scripts/smoke_static.py), [tests/e2e/security.spec.cjs](../tests/e2e/security.spec.cjs). | Maintainers | Webview-dependent features remain unavailable. Re-enabling them requires a qualified isolation design; changing only the blocked hostname is not sufficient. |
| **T14. Shared static-host origin exposes browser storage or lets sibling applications influence state.** | Documentation requires treating the host origin as a trust boundary; no service-worker offline cache is supported; dedicated origins are recommended where cross-application isolation matters. | [tests/e2e/workbench.spec.cjs](../tests/e2e/workbench.spec.cjs) verifies persistent extension/browser storage and absence of service-worker registrations. | Static-host operator + browser + user | IndexedDB/local storage and similar browser state are origin-scoped, not path-scoped. A sibling application served from the same origin is not isolated merely because it uses a different URL path. Site-data clearing/quota eviction can cause data loss. |
| **T15. GitHub Release publication overwrites or completes an inconsistent immutable release.** | Publication reconciles expected assets monotonically: matching published assets are verification-only; only an interrupted draft may add missing expected assets; conflicts/unexpected content fail closed. | [.github/actions/publish-github-release/action.yml](../.github/actions/publish-github-release/action.yml), [scripts/publish_github_release.py](../scripts/publish_github_release.py), [OPERATIONS.md](../OPERATIONS.md). | Release workflow + GitHub Releases | GitHub service compromise is outside repository controls. Expired recovery artifacts can require manual incident handling. |
| **T16. Registry failure is mistaken for a missing GHCR tag and causes an overwrite.** | OCI publication distinguishes confirmed not-found from indeterminate lookup errors. Existing images are verified; a new image is pushed only after confirmed absence and verified again afterward. | [.github/actions/publish-oci/action.yml](../.github/actions/publish-oci/action.yml), [scripts/verify_oci_image.sh](../scripts/verify_oci_image.sh). | Release workflow + GHCR | Registry compromise or incorrect registry responses can defeat client-side checks. Publication may be unavailable during ambiguous failures by design. |
| **T17. Immutable publication or promotion partially fails after earlier stages succeed.** | GitHub Release and GHCR are verified independently before automatic promotion begins. Canary/stable promotion is globally serialized; failed or indeterminate promotion leaves the previous successful stable deployment authoritative. Immutable publication recovery is artifact-only, while promotion recovery resolves durable release assets without rebuilding. | [.github/workflows/release.yml](../.github/workflows/release.yml), [.github/workflows/recover-release-publication.yml](../.github/workflows/recover-release-publication.yml), [.github/workflows/promote.yml](../.github/workflows/promote.yml), [OPERATIONS.md](../OPERATIONS.md). | Release/promotion workflows + GitHub services | A new immutable release can exist without becoming stable. Availability may remain on the prior stable release until promotion can be proven safe. |
| **T18. Static host/CDN serves modified JavaScript after promotion.** | Stable Pages is deployed from a verified immutable release archive, and the successful stable deployment records the release/artifact/policy identity; consumers can independently verify GitHub Release artifacts and attestations. The runtime itself has no backend that can repair a compromised host. | [.github/workflows/promote.yml](../.github/workflows/promote.yml), [docs/release-security.md](../docs/release-security.md), [docs/releasing.md](../docs/releasing.md). | Host/CDN operator + consumers | Anyone who can replace same-origin JavaScript can act with that origin's browser authority. Use dedicated, protected hosting and independent artifact verification when this threat matters. |
| **T19. Promotion state is forged, stale, or rolled backward unintentionally.** | Promotion binds release tag/commit, GitHub Release ID, archive and distribution digests, and policy/profile digest; stable requires matching successful canary identity on the automatic path; automatic promotion refuses backward movement; rollback requires previous stable history and records a new deployment event. | [.github/workflows/promote.yml](../.github/workflows/promote.yml), [config/promotion-policy.json](../config/promotion-policy.json), [scripts/promotion.py](../scripts/promotion.py), [tests/test_promotion.py](../tests/test_promotion.py). | Maintainers + promotion workflow + GitHub Deployments | A sufficiently privileged administrator can alter deployment/environment policy or GitHub deployment records; external audit copies may still be needed for stronger tamper evidence. |

## Control ownership summary

| Owner | Controls |
| --- | --- |
| Repository maintainers | Upstream/config/extension locks, ADRs, workflow definitions, review, release policy, incident response |
| Repository administrators | Branch/ruleset/environment settings, reviewer/deployment protections, account access |
| GitHub Actions/platform | Hosted runners, artifacts, OIDC, attestations, environments, Releases, Pages, GHCR |
| Upstream Code - OSS and dependencies | Correctness of the pinned source and dependency graph consumed by unprivileged build jobs |
| Static-host/CDN operator | Served-byte integrity, TLS, account security, origin isolation, caching behavior |
| Browser | CSP, same-origin policy, sandboxing, storage semantics and quotas |
| User | Trust decisions for workspaces and separately installed extensions; browser/site-data lifecycle |

## Explicit residual risks

### Upstream and dependency compromise

Exact pinning and tag binding make the selected source auditable; they do not assert that the selected
source is benign. The upstream build executes dependency lifecycle/build scripts. Those jobs are
therefore treated as hostile-capable and denied release authority. A sophisticated compromise that
produces deterministic malicious output can pass reproducibility unless behavioral qualification or
review detects it.

### Maintainer and account compromise

Review requirements, immutable tags, default-branch ancestry, and protected release environments
raise the authorization threshold and preserve audit evidence. They cannot prevent a sufficiently
privileged administrator or coordinated set of compromised approvers from changing policy for a
future release. Account security and repository settings remain part of the trust base.

### Runner, workflow, cache, and artifact compromise

Caches are never release provenance, and release rebuilds do not consume the development build cache.
Qualification-to-release identity checks and a second clean build reduce artifact substitution risk.
The project still depends on GitHub's runner/artifact/attestation control plane and on the integrity of
the checked-in workflow-policy checker.

### Extensions and workspaces

Archive/source/hash/license controls establish exactly what extension bytes are bundled and prevent
several ingestion classes; they do not prove an extension is non-malicious. Workspace trust limits
automatic behavior for untrusted workspaces but is inherited from upstream and is not equivalent to
isolating extensions from user data.

### Publication and registry failures

The design prefers unavailability over silent mutation. Ambiguous GHCR state, conflicting immutable
Release assets, invalid promotion identity, or an unsafe/stale automatic transition fail closed. A
new immutable release may therefore remain unpromoted while the prior stable release continues to
serve. Immutable publication recovery can depend on retained workflow artifacts; promotion rollback
instead resolves durable GitHub Release assets and moves only auditable channel state.

### Browser storage and static hosting

A static subpath is a deployment convenience, not an origin isolation boundary. Browser state may
contain user/workspace/extension data and is available according to browser-origin rules. Deploy on a
dedicated origin when sibling applications are not equally trusted. The static host itself can replace
application code and is therefore in the runtime trust base. No service-worker offline cache is
supported, so host outages directly affect availability.

## Decision records

The decisions behind the principal controls are documented in
[docs/adr/README.md](../docs/adr/README.md). Any change that weakens a fail-closed boundary, introduces
a new network/gallery origin, bundles a new extension trust source, broadens proposed APIs, changes
release promotion, or enables webviews should update the relevant ADR and this threat model together.
