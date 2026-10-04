# ADR-0002: Fail closed when secure webview isolation is unavailable

- Status: Accepted
- Date: 2026-10-03

## Context

Code - OSS webviews are designed around stronger isolation than a generic static site can guarantee.
Upstream normally expects a separate webview origin or subdomain together with CSP, sandbox, and
hostname checks. Rewriting those assumptions so a webview can render under the workbench's ordinary
static origin would trade a visible feature failure for a same-origin security failure.

The project must work on deployment-independent static hosting, including path-prefixed hosting,
without requiring a privileged backend or dynamically provisioned subdomains.

## Decision

Secure webviews are unsupported in the generic static deployment and must fail closed.

[scripts/make_static.py](../../scripts/make_static.py) configures the webview endpoint templates under
the reserved <code>invalid.invalid</code> domain, while
[config/policies/runtime/static.json](../../config/policies/runtime/static.json) records webviews as disabled. The project will not
patch out or weaken upstream origin, hostname, CSP, or sandbox checks merely to make webview content
render.

Any future webview enablement requires a deployment-independent isolation design, browser
qualification for that design, an updated threat model, and a superseding ADR or explicit amendment
to this decision.

## Consequences

Features that depend on webviews remain unavailable in the supported static mode. This is an
intentional product limitation.

The failure mode is easy to detect and review: changing the invalid endpoint or runtime mode is a
security-boundary change and is escalated by pull-request classification. The base page CSP also
restricts outbound connections, but CSP is defense in depth; the core decision is not to claim
webview isolation that the deployment cannot provide.

## Enforcement and verification

- [scripts/make_static.py](../../scripts/make_static.py)
- [config/policies/runtime/static.json](../../config/policies/runtime/static.json)
- [scripts/validate_config.py](../../scripts/validate_config.py)
- [scripts/smoke_static.py](../../scripts/smoke_static.py)
- [tests/e2e/security.spec.cjs](../../tests/e2e/security.spec.cjs)
- [SECURITY.md](../../SECURITY.md)
