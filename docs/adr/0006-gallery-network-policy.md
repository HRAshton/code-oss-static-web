# ADR-0006: Keep gallery and runtime network access disabled by default

- Status: Accepted
- Date: 2026-10-03

## Context

The project is intended to be a zero-backend static browser application. Upstream product metadata
can contain Marketplace/gallery, chat, authentication, telemetry, update, or other service endpoints.
Allowing those endpoints to remain active would make clean startup depend on mutable external
services and could send workspace/product information outside the deployment origin.

A static CSP can constrain browser connections, but product configuration should also avoid creating
network features that merely fail at the CSP layer.

## Decision

The supported base runtime is default-deny for external application network access.

- [config/policies/runtime/static.json](../../config/policies/runtime/static.json) keeps telemetry false and gallery mode disabled.
- [config/policies/product/static.json](../../config/policies/product/static.json) removes upstream
  Marketplace-style built-in extension downloads/auto-updates and replaces unsupported service
  metadata with fail-closed values where needed.
- [config/policies/network/static.json](../../config/policies/network/static.json) allows only <code>self</code>.
- [scripts/make_static.py](../../scripts/make_static.py) emits a CSP with
  <code>connect-src 'self'</code> and no <code>unsafe-eval</code>.
- Clean startup is expected to make zero cross-origin HTTP requests and zero WebSocket connections.

Adding a gallery, registry, telemetry service, authentication endpoint, remote API, or new allowed
origin is a policy change. It requires explicit configuration, threat-model review, tests that prove
the intended origin/method/data flow, and an ADR update or superseding decision.

Extension build-time acquisition is separate from runtime gallery policy. Locked Open VSX downloads
may occur during the build only from origins explicitly allowed by
[extensions/source-policy.json](../../extensions/source-policy.json); those downloads do not enable a
runtime extension gallery.

## Consequences

Features that require arbitrary external services are unavailable by default. The static
distribution is easier to host and audit because normal startup is same-origin.

CSP is defense in depth rather than a complete application firewall. It does not govern every form
of browser navigation or future web platform capability, and separately installed/user-triggered
code may create new behavior that must be reviewed. The policy therefore combines product
configuration, runtime configuration, static CSP, and browser tests.

## Enforcement and verification

- [config/policies/runtime/static.json](../../config/policies/runtime/static.json)
- [config/policies/network/static.json](../../config/policies/network/static.json)
- [config/policies/product/static.json](../../config/policies/product/static.json)
- [scripts/validate_config.py](../../scripts/validate_config.py)
- [scripts/make_static.py](../../scripts/make_static.py)
- [scripts/smoke_static.py](../../scripts/smoke_static.py)
- [tests/e2e/security.spec.cjs](../../tests/e2e/security.spec.cjs)
- [tests/e2e/network-policy.spec.cjs](../../tests/e2e/network-policy.spec.cjs)
