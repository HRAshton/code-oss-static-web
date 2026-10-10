# Governance

This document defines the repository ownership model, sensitive-path review expectations, target
GitHub settings, and continuity procedure for Code OSS Static Web.

The repository belongs to `Codellei`. During a temporary two-developer phase, `HRAshton` and
`vodyanica` remain the CODEOWNERS for sensitive paths. An author cannot approve their own change;
the other developer supplies the one independent approval required by the branch ruleset.
Organization teams and separate Platform/Security approvals await additional qualified people.
`vodyanica` has repository write access as a collaborator while the organization invitation is
pending. `HRAshton` is currently the sole organization owner, so administration continuity remains
open.

No future organization/account setting change is authorized by this document alone. The repository
owner must approve real team identities, membership, and final settings before they are applied.

## Current operating state

The current protected `master` ruleset requires:

- pull requests for changes to the default branch;
- one approving review;
- dismissal of stale approvals after new pushes;
- approval of the last push by someone other than its author;
- required CODEOWNERS approval when a changed path has an owner;
- required resolution of review threads;
- the `tooling` and `Artifact qualification gate` status checks;
- CodeQL enforcement at the repository's configured threshold.

CODEOWNERS is intentionally scoped to sensitive paths rather than the entire repository. The
Renovate platform-update pair remains outside CODEOWNERS so the routine Microsoft update pipeline
can merge, qualify, publish, and promote without a per-release human gate.

The exact trusted Renovate auto-approval allowlist is:

- `upstream.lock.json`
- `builder-apt-snapshot.json`

Both files must change together, with no additional paths. Approval requires successful
pull-request `Full build qualification` and fail-closed validation of the upstream
version/commit/source-date epoch and APT snapshot transformations. `builder-image.json`,
workflows, and other trust boundaries still require human review.

Release tags are separately protected by the immutable-release-tag ruleset. Release publication
workflows use the protected `release` environment as their shared authorization boundary, while
Pages deployment additionally uses the separate `github-pages` environment.

These settings live in GitHub as repository state, not only in source control. The transfer audit
must compare the live rulesets and environments before and after the ownership change.

## Intended organization ownership

The organization should create durable teams for these responsibilities when qualified people are
available. The names below are role labels, not approved GitHub team slugs.

| Ownership role | Responsibility |
| --- | --- |
| Platform maintainers | Repository administration, build/CI platform, scripts, dependency automation, and general maintenance |
| Security owners | Security policy, trust boundaries, workflow permissions, release integrity, vulnerability response, and security-sensitive configuration |
| Release owners | Release operations and recovery, release-environment policy, Pages/GHCR operation, incident response, and release runbooks |
| Extension-policy owners | Extension admission, source/provenance policy, browser-extension compatibility, proposed API exceptions, and extension supply-chain review |
| Legal/licensing reviewers | License-policy or redistribution review when extension/source changes require it; this may be a service or designated reviewers rather than a permanent repository team |

Each critical capability should have at least two active humans before the original personal owner
is treated as non-essential to operation. A team that contains only one person does not solve the
continuity requirement.

Exact team slugs, members, and repository roles require approval before team-backed policy is
activated. Do not create placeholder identities in repository policy.

## Sensitive paths and human review

The following paths require explicit human review in addition to automated checks. "Platform +
Security", for example, means independent human coverage of both responsibilities when the change
affects the stated trust boundary; a generic approval is not a substitute for the missing role.

| Path or area | Required review responsibility | Rationale |
| --- | --- | --- |
| `.github/**` | Platform + Security | Workflows, actions, rulesets, permissions, automation, and `.github/CODEOWNERS` can change repository or release trust boundaries |
| `GOVERNANCE.md` and `CONTRIBUTING.md` | Platform + Security | These files define repository ownership and review controls; weakening them changes the governance trust boundary |
| `renovate.json` | Platform + Security | Dependency automation can alter what changes are proposed or automatically merged |
| `security/**`, `SECURITY.md`, `docs/release-security.md` | Security | Security model, vulnerability handling, and release-integrity policy |
| `extensions/**` | Platform + Extension Policy; Security for trust/provenance changes; Legal/licensing when license/source policy changes | Extension code and metadata become part of the distributed product and supply chain |
| `deploy/**` | Platform + Release | Runtime/container deployment and publication behavior |
| `scripts/**` | Platform; add Security, Release, or Extension Policy when the script implements those boundaries | Repository scripts implement build, policy, qualification, packaging, and release controls |
| `build.sh`, `package.sh`, `config/**`, `patches/**` | Platform; Security when trust/runtime boundaries change | These inputs materially define generated distribution behavior |
| `upstream.lock.json` and `builder-apt-snapshot.json` (together) | Automated platform-update exception | Only the exact two-file data-only change is eligible for bot approval, after pull-request `Full build qualification` and content validation; neither file alone qualifies |
| Release workflows/actions and `docs/releasing.md` / `OPERATIONS.md` | Release + Platform; Security when publication authority or integrity changes | Controls immutable tag creation, publication, recovery, and operator procedure |

The existing [Contributing](CONTRIBUTING.md) trust-boundary review requirements still apply even
when a path is not explicitly listed above.

### Temporary two-developer review

The branch ruleset requires CODEOWNERS review and review-thread resolution. Sensitive paths in
`.github/CODEOWNERS` are currently assigned to `@HRAshton` and `@vodyanica`, so a matching
change requires approval from one of those designated owners in addition to satisfying the branch
ruleset.

Those two identities are an interim routing and enforcement mechanism. With only two developers,
one author leaves one eligible independent reviewer. The owner approved this temporary exception to
the separate Platform/Security approval goal for sensitive changes; it does not lower the branch
ruleset, CODEOWNERS, CodeQL, or required checks. Record the exception in migration evidence and
remove it when qualified team coverage is available.

`upstream.lock.json` and `builder-apt-snapshot.json` are deliberately not CODEOWNED. The
Renovate auto-approval workflow accepts only that exact pair after pull-request
`Full build qualification` and content validation; either file alone is insufficient.
Changes to the approval automation and immutable `builder-image.json` identity are CODEOWNED.

### Future team-backed review

Use GitHub teams and repository settings to enforce the approved ownership model. CODEOWNERS should
route review to real team identities, while branch/ruleset controls should provide the actual merge
gate. Where a change requires two distinct responsibilities, do not assume that listing two owners
on one CODEOWNERS pattern proves both approved it; use the available ruleset/reviewer controls or an
explicit documented dual-review procedure.

## CODEOWNERS policy

`.github/CODEOWNERS` is active during the two-developer phase and uses only the two real current
maintainers. It is intentionally limited to sensitive paths. There is no repository-wide catch-all,
because ordinary pull requests are already subject to the branch review rule and the narrowly
validated Renovate platform-update pair must remain humanless.

The CODEOWNERS file itself is protected by its `.github/` rule. Repository policy tests pin the
interim owner set and sensitive-path coverage so a pull request cannot silently expand automation,
remove ownership, or put either platform-update lock behind a human CODEOWNER gate.

When the team-backed model is staffed and approved:

1. replace the individual owners with approved real team slugs/users;
2. keep at least two people capable of covering each critical operational responsibility;
3. preserve the sensitive-path mapping or document and review any divergence;
4. keep CODEOWNERS review enabled in the target branch ruleset; and
5. use organization ruleset reviewer controls where distinct Platform/Security/Release approvals
   must be enforced independently.

Do not commit fake organization names, placeholder teams, future usernames, or role labels as
CODEOWNERS entries.

## Target repository settings

The native transfer preserved the protected-branch controls. Any later settings change must be
reviewed as a separate administrative change and recorded in a migration issue or change record.

For the default-branch ruleset, verify all of the following:

- pull requests remain required;
- the required approval count is not reduced below the current value;
- stale approvals remain dismissed after new pushes;
- last-push approval by someone other than the author remains required;
- **required review-thread resolution remains enabled**;
- `tooling` and `Artifact qualification gate` remain required status checks;
- existing CodeQL/code-scanning requirements remain enabled;
- required CODEOWNERS review remains enabled;
- any path/team-specific reviewer rules needed for future dual-role sensitive changes are configured
  when that model is staffed;
- bypass access is absent or limited to an explicitly reviewed emergency mechanism with audit
  expectations.

For the immutable release-tag ruleset, preserve active update/deletion protection and the existing
no-routine-bypass model. A repository transfer must not create a window in which release tags can be
moved or deleted without the intended protection.

For this migration, capture the resulting ruleset IDs and exported/API-visible configuration in the
migration record so the settings are auditable against this document.

## Environment protection and release authority

The `release` environment is the authorization boundary for publication, but the routine Microsoft
update path is intentionally non-interactive. A normal
Renovate → qualification → immutable release → canary → stable/Pages run must not require a human
environment approval.

In Codellei:

- do **not** add required human reviewers to the `release` environment while the automatic upstream
  release workflows use it;
- at least two approved Release Owners must be capable of operating, diagnosing, and recovering the
  release flow when automation cannot prove a safe transition;
- environment deployment restrictions should accept only the intended immutable release-tag flow;
- repository administrators who are not Release Owners should not be treated as routine release
  operators merely because they can administer the repository;
- changes to release-environment protection or release authority require owner review and should be
  recorded in the repository migration/change record.

If policy later requires mandatory human approval for exceptional release operations, use a separate
manual/break-glass environment or workflow boundary rather than inserting a reviewer gate into the
routine automatic path.

The `github-pages` environment is a deployment environment, not a replacement for the shared
`release` authorization boundary. Preserve the release gate described in
[Release security](docs/release-security.md).

Release authority includes the ability to dispatch approved manual/recovery workflows, inspect
failed publication state, and follow [Operations](OPERATIONS.md). It does not include permission to
move immutable release tags or overwrite conflicting published artifacts.

## Organization transition follow-up

The native transfer retained the repository ID, refs, releases, collaborators, and active branch and
tag rulesets. Keep publication frozen until the remaining cutover checks are complete:

1. Merge reviewed Codellei identity and release-path changes after required CI and independent review.
2. Confirm Renovate installation and the narrow automated approval path in Codellei.
3. Verify new GHCR package access and public visibility on the first approved new release.
4. Verify Pages canary and stable identities after separately approved deployment.
5. Have `vodyanica` accept the organization invitation and demonstrate backup release operation at a
   normal release opportunity. Add a second organization administration path.
6. Staff and approve distinct Platform, Security, Release, Extension Policy, and Legal coverage, then
   render team-backed CODEOWNERS and remove the temporary review exception.

Any migration step that cannot be verified should remain open in the migration record rather than
being treated as implicitly complete.

## Continuity and bus-factor procedure

Repository operation must remain possible when any one maintainer is unavailable.

Maintain at least the following independent capabilities:

- two humans able to administer repository membership/settings or an organization-owner escalation
  path that can restore that capability;
- two humans able to review/merge ordinary platform changes;
- two humans able to access and coordinate private vulnerability reports;
- two humans able to operate and recover the `release` environment when automation needs
  intervention;
- two humans able to inspect/recover GitHub Release, Pages, and GHCR publication state.

Routine upstream releases remain zero-touch: backup human capability is a continuity property, not a
per-release approval requirement.

At least quarterly, or after a material ownership change, review the team/member list and confirm
that no critical capability has silently returned to a single person. This review can be recorded in
an issue, audit/change record, or organization governance system.

For release continuity, a backup operator must be able to locate the immutable release tag and
workflow-run evidence, inspect the independent publication channels, and execute the documented
recovery workflow without credentials or knowledge held only by the original maintainer. The
recovery procedure is defined in [Operations](OPERATIONS.md).

When a maintainer leaves or loses access:

1. remove or adjust their organization/team/environment membership;
2. verify each critical capability still has the required backup coverage;
3. rotate any maintainer-specific credentials that existed outside GitHub's repository-scoped
   automation;
4. verify required rulesets and environment protections were not weakened by the membership change;
5. assign any open security/release responsibilities to another approved owner;
6. record completion in the applicable access/change-management audit trail.

The project should not depend on a private local checkout, personal token, undocumented secret,
personal package ownership, or sole knowledge of the release process to remain maintainable.

## Audit evidence

For organization migration and later governance changes, retain enough evidence to reconstruct what
was approved and applied:

- target organization and approved team slugs;
- reviewers/owner approval for CODEOWNERS and settings changes;
- effective branch and tag ruleset configuration;
- environment reviewer/protection configuration;
- date and responsible operator for migration or governance changes;
- any temporary exception, its rationale, owner, and expiry/removal condition.

Source-controlled policy documents describe intent; GitHub's effective repository settings are the
enforcement state. Review both when auditing governance.


## Prepared team migration tooling

The source tree includes [`scripts/render_codeowners.py`](scripts/render_codeowners.py) so the
final organization/team slugs can be applied without hand-editing sensitive-path ownership. The
script refuses collapsed role slugs and produces an exact `.github/governance-teams.json` mapping
that repository policy validates against CODEOWNERS. Until that mapping exists, the existing
two-person interim ownership remains authoritative. Follow
[the organization migration procedure](docs/organization-migration.md) for activation.

## Extension mirror governance

Extension Policy owns candidate approval and mirror admission; Legal owns license review where
required; Platform owns the build-side mirror client and fail-closed source policy. A mirrored
extension approval records reviewer, original source, digest, license, clean scan result, and
approval date. The mirror storage service and retention policy are organization controls and must be
audited before the first production extension is locked. See
[the internal extension mirror procedure](docs/extension-mirror.md).
