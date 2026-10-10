# Architecture decision records

Architecture decision records capture security- and compatibility-sensitive choices that should not
be changed accidentally while fixing an isolated symptom. The current records describe the
repository's accepted design; a superseding decision should add a new ADR and link the old record to
it rather than rewriting history.

| ADR | Decision | Status |
| --- | --- | --- |
| [0001](0001-no-source-fork.md) | Integrate immutable upstream source without a maintained fork | Accepted |
| [0002](0002-fail-closed-webviews.md) | Fail closed when secure webview isolation is unavailable | Accepted |
| [0003](0003-extension-trust.md) | Treat bundled extensions as explicit trusted release inputs | Accepted |
| [0004](0004-proposed-api-policy.md) | Scope proposed API grants to documented extension IDs | Accepted |
| [0005](0005-release-promotion.md) | Separate qualification, release rebuild, attestation, and promotion | Accepted |
| [0006](0006-gallery-network-policy.md) | Keep gallery and runtime network access disabled in strict baseline | Superseded for company-standard |
| [0007](0007-open-vsx-ready-profile.md) | Open VSX ready-to-use company profile; strict offline baseline remains | Proposed |

See [Architecture](../architecture.md) for the end-to-end data flow and
[Threat model](../../security/threat-model.md) for threats, controls, tests, owners, assumptions, and
residual risks.
