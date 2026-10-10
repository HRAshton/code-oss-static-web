# ADR-0004: Scope proposed API grants to reviewed extension IDs

- Status: Accepted
- Date: 2026-10-03

## Decision

The shipped `company-standard` and `baseline-static` profiles grant **no**
proposed APIs. Any future exception requires a separately reviewed opt-in
profile and an explicit extension-ID-to-proposal mapping. The grant must carry
a concrete compatibility reason, reviewer, expiry, and validation against the
pinned upstream `src/vscode-dts/vscode.proposed.<name>.d.ts` definitions.

The extension must be admitted and qualified independently. A grant must not
implicitly bundle, download or trust third-party code. Configuration validation
checks every defined profile, even when it is not selected. Filename existence
is not proof of API semantic compatibility.

## Enforcement

- [config/policies/proposed-api/none.json](../../config/policies/proposed-api/none.json)
- [scripts/prepare_upstream.py](../../scripts/prepare_upstream.py)
- [scripts/validate_config.py](../../scripts/validate_config.py)
- [tests/test_proposed_api_grants.py](../../tests/test_proposed_api_grants.py)
