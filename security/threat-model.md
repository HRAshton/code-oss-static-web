# Threat model

## Assets

Release integrity, the exact upstream-to-artifact mapping, workspace data, browser storage,
extension execution, and release provenance.

## Threat actors

Compromised upstream/dependency, malicious extension/workspace, malicious contributor,
compromised CI action, and artifact-substitution attacker.

## Boundaries

1. Pinned upstream source -> disposable build checkout.
2. Checkout -> optimized web build.
3. Web build -> static bootstrap transformation.
4. Workbench -> web extensions.
5. Workbench -> webviews (disabled until isolation is qualified).
6. Build/test jobs -> attestation/publish jobs.

## Initial controls

- `connect-src` is self-only in the static page CSP.
- Telemetry is disabled by project runtime configuration.
- upstream Marketplace-style `builtInExtensions` downloads are removed before building.
- default chat/auth shortcut product metadata is removed from the disposable checkout.
- webview URLs use the reserved `invalid.invalid` domain and are additionally blocked by CSP.
