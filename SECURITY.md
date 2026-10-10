# Security policy

## Supported versions

Only the most recent qualified release is supported for project-specific security fixes. Older
releases and unqualified upstream revisions are not supported. Before the first successful public
release, reports against the current protected default branch are accepted.

This project integrates an immutable Code - OSS revision rather than maintaining a fork. Issues
that reproduce in unmodified Code - OSS should also be reported to the upstream project when
appropriate.

## Reporting a vulnerability

Report suspected vulnerabilities privately through GitHub Private Vulnerability Reporting:

https://github.com/Codellei/code-oss-static-web/security/advisories/new

Do not open a public issue for a vulnerability before coordinated disclosure. Include the affected
release or commit, reproduction steps, expected impact, and any known workarounds. Reports may cover
the build and release pipeline, static runtime configuration, extension loading, trust boundaries,
network policy, artifact integrity, or publication paths.

We aim to acknowledge a report within 7 days and provide an initial assessment within 14 days.
Confirmed medium-or-higher severity vulnerabilities are targeted for remediation within 60 days of
public disclosure; critical issues are prioritized for the earliest practical fix and release.
These are response targets rather than service-level guarantees.

## Disclosure and remediation

Security fixes are developed privately when premature disclosure would increase risk. After a fix is
available, the project will publish an advisory or release note describing the affected versions,
impact, mitigation, and fixed version as appropriate. Reporters are credited unless they request
otherwise.

## Security boundaries

Secure webviews intentionally fail closed in generic static hosting. Code - OSS normally relies on
an isolated webview origin or subdomain, so this project will not bypass origin, CSP, sandbox, or
hostname checks merely to make webviews render.

The release pipeline separates untrusted upstream build execution from attestation and publication.
See [Release security](docs/release-security.md) and the [threat model](security/threat-model.md) for
the trust boundaries and release-security design.


After organization migration, security-sensitive paths are routed to the approved Security team
through generated team-backed CODEOWNERS. Repository transfer and team activation follow
[the organization migration procedure](docs/organization-migration.md).
