# ADR-0004: Scope proposed API grants to documented extension IDs

- Status: Accepted
- Date: 2026-10-03

## Context

Code - OSS proposed extension APIs are intentionally unstable. Some separately distributed
extensions may need a narrow host-compatibility grant before an API becomes stable, but enabling
proposed APIs globally or for broad extension classes would silently expand the capability surface
and make upstream upgrades harder to reason about.

The current compatibility case is the separately distributed <code>hrashton.remotish</code>
extension, which needs the <code>scmHistoryProvider</code> and <code>timeline</code> proposals. The
extension is not bundled by this project.

## Decision

Proposed APIs may be enabled only through an explicit extension-ID-to-proposal list in
[config/policies/proposed-api/remotish.json](../../config/policies/proposed-api/remotish.json).

A grant:

- is scoped to a concrete extension ID and an explicit opt-in deployment profile;
- lists individual proposal names rather than enabling all proposals;
- does not imply that the extension is bundled, downloaded, trusted, or added to the release SBOM;
- must have a documented compatibility rationale, reviewer, and expiry;
- must be validated against the pinned upstream revision before build.

[scripts/prepare_upstream.py](../../scripts/prepare_upstream.py) requires every configured proposal to
have a matching <code>src/vscode-dts/vscode.proposed.&lt;name&gt;.d.ts</code> definition in the pinned
Code - OSS source. A removed or renamed proposal therefore fails the build rather than silently
falling back.

The generic `company-standard` profile binds the empty proposed-API policy. Remotish grants are
available only through `remotish-compat`. Configuration validation loads every checked-in
deployment profile, not only the selected one, so an expired dormant compatibility approval fails CI
before it can later be selected.

## Consequences

Compatibility exceptions are visible in source review and cannot accidentally become global product
policy. A separately installed extension receives the grant only when its ID matches the configured
entry.

Filename validation does not prove API semantic compatibility. An upstream revision may retain a
proposal definition while changing behavior. Upstream upgrades that touch a granted API therefore
still require qualification and, when relevant, manual compatibility review.

## Enforcement and verification

- [config/policies/proposed-api/remotish.json](../../config/policies/proposed-api/remotish.json)
- [config/profiles/remotish-compat.json](../../config/profiles/remotish-compat.json)
- [scripts/prepare_upstream.py](../../scripts/prepare_upstream.py)
- [tests/test_proposed_api_grants.py](../../tests/test_proposed_api_grants.py)
- [docs/remotish-compatibility.md](../remotish-compatibility.md)
