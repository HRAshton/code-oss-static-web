# ADR-0007: Select an explicit Open VSX ready-to-use profile

- Status: Proposed (requires network and install-flow qualification)
- Date: 2026-10-10
- Supersedes: [ADR-0006](0006-gallery-network-policy.md) for `company-standard` only

## Context

A browser-only deployment is useful with a discovery gallery. A gallery
requires third-party network access and does not fit the strict self-only
contract. The unmodified public gallery cannot be made safe merely by
overwriting `runtime.json`.

## Decision

- `baseline-static`: no gallery, default-deny/self-only CSP.
- `company-standard`: Open VSX `extensionsGallery` in the **web embedder
  configuration**, and a fixed registry/CDN CSP allowlist. Host telemetry stays
  disabled, webviews stay fail-closed.
- No proposed APIs are enabled automatically. No extension is bundled except
  the exact-version, SHA-256-checked mirror entries approved in the extension
  lock. Experimental extensions remain outside the release.
- GitHub Pages and the Docker image consume the *identical qualified
  distribution tarball*; no promotion-time byte rewriting.
- A new gallery provider or network origin requires a reviewed policy update,
  browser tests and new qualified immutable release.

## Risks and verification

Gallery metadata and downloads leak request metadata to the registry/CDN;
extensions can execute with web-extension-host permissions. CSP is not an
extension sandbox; installing an extension is a separate trust decision.
Nginx's COEP policy and live registry CORS/redirect behavior must be checked
with a browser install test, not inferred from a successful static boot.
Tests must enforce host telemetry off, explicit gallery URLs, no arbitrary
origins, and strict baseline behavior.

## Enforcement

- [config/profiles/company-standard.json](../../config/profiles/company-standard.json)
- [config/profiles/baseline-static.json](../../config/profiles/baseline-static.json)
- [scripts/make_static.py](../../scripts/make_static.py)
- [tests/e2e/security.spec.cjs](../../tests/e2e/security.spec.cjs)
- [tests/e2e/network-policy.spec.cjs](../../tests/e2e/network-policy.spec.cjs)
- [ready-to-use documentation](../ready-to-use.md)
