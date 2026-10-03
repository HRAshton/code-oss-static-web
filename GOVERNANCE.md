# Governance

This document defines the repository ownership model, sensitive-path review expectations, target
GitHub settings, and continuity procedure for Code OSS Static Web.

The repository is currently operated from the personal `HRAshton` GitHub account. Organization
migration is intentionally deferred. Sensitive paths use interim CODEOWNERS backed by the two
current maintainers; organization teams and team-backed role enforcement do not exist yet.

No organization/account setting change is authorized by this document alone. The repository owner
must approve the target organization, real team identities, membership, and final settings before
they are applied.

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

CODEOWNERS is intentionally scoped to sensitive paths rather than the entire repository. The narrow
Renovate-only `upstream.lock.json` path remains outside CODEOWNERS so the routine Microsoft update
pipeline can merge, qualify, publish, and promote without a per-release human gate.

Release tags are separately protected by the immutable-release-tag ruleset. Release publication
workflows use the protected `release` environment as their shared authorization boundary, while
Pages deployment additionally uses the separate `github-pages` environment.

These settings live in GitHub as repository state, not only in source control. Before an ownership
migration, export or otherwise record the live ruleset/environment configuration and compare it with
this plan so no protection is silently lost during transfer.

## Intended organization ownership

The target organization should create durable teams for these responsibilities. The names below are
role labels, not approved GitHub team slugs.

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

Exact organization name, team slugs, members, and repository roles must be approved during the
migration review. Do not create placeholder identities in repository policy.

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
| `upstream.lock.json` | Automated upstream exception | The exact tag/commit pin is the only bot-auto-approved path; CI plus full release qualification provide the gate without per-update human approval |
| Release workflows/actions and `docs/releasing.md` / `OPERATIONS.md` | Release + Platform; Security when publication authority or integrity changes | Controls immutable tag creation, publication, recovery, and operator procedure |

The existing [Contributing](CONTRIBUTING.md) trust-boundary review requirements still apply even
when a path is not explicitly listed above.

### Before organization migration

The branch ruleset requires CODEOWNERS review and review-thread resolution. Sensitive paths in
`.github/CODEOWNERS` are currently assigned to `@HRAshton` and `@vodyanica`, so a matching
change requires approval from one of those designated owners in addition to satisfying the branch
ruleset.

Those two identities are an interim routing/enforcement mechanism, not a claim that one person can
represent multiple future organization roles. Where this document calls for two distinct
responsibilities, the pull request should still record that coverage explicitly until organization
teams and role-specific rules can enforce it.

`upstream.lock.json` is deliberately not CODEOWNED. The Renovate auto-approval workflow accepts
only that exact path, while the merged revision still has to pass the full browser qualification,
immutable publication, and promotion pipeline. Changes to the automation itself are CODEOWNED.

### After organization migration

Use GitHub teams and repository settings to enforce the approved ownership model. CODEOWNERS should
route review to real team identities, while branch/ruleset controls should provide the actual merge
gate. Where a change requires two distinct responsibilities, do not assume that listing two owners
on one CODEOWNERS pattern proves both approved it; use the available ruleset/reviewer controls or an
explicit documented dual-review procedure.

## CODEOWNERS policy

`.github/CODEOWNERS` is active during the personal-account phase and uses only the two real current
maintainers. It is intentionally limited to sensitive paths. There is no repository-wide catch-all,
because ordinary pull requests are already subject to the branch review rule and the routine
`upstream.lock.json` automation must remain humanless.

The CODEOWNERS file itself is protected by its `.github/` rule. Repository policy tests pin the
interim owner set and sensitive-path coverage so a pull request cannot silently expand automation,
remove ownership, or put `upstream.lock.json` behind a human CODEOWNER gate.

After organization migration:

1. replace the individual owners with approved real team slugs/users;
2. keep at least two people capable of covering each critical operational responsibility;
3. preserve the sensitive-path mapping or document and review any divergence;
4. keep CODEOWNERS review enabled in the target branch ruleset; and
5. use organization ruleset reviewer controls where distinct Platform/Security/Release approvals
   must be enforced independently.

Do not commit fake organization names, placeholder teams, future usernames, or role labels as
CODEOWNERS entries.

## Target repository settings

Organization migration must preserve or strengthen the current protected-branch controls. The
migration settings change should be reviewed as a separate administrative change and recorded in a
migration issue or change record.

For the default-branch ruleset, verify all of the following:

- pull requests remain required;
- the required approval count is not reduced below the current value;
- stale approvals remain dismissed after new pushes;
- last-push approval by someone other than the author remains required;
- **required review-thread resolution remains enabled**;
- `tooling` and `Artifact qualification gate` remain required status checks;
- existing CodeQL/code-scanning requirements remain enabled;
- required CODEOWNERS review remains enabled;
- any path/team-specific reviewer rules needed for dual-role sensitive changes are configured;
- bypass access is absent or limited to an explicitly reviewed emergency mechanism with audit
  expectations.

For the immutable release-tag ruleset, preserve active update/deletion protection and the existing
no-routine-bypass model. A repository transfer must not create a window in which release tags can be
moved or deleted without the intended protection.

After migration, capture the resulting ruleset IDs and exported/API-visible configuration in the
migration record so the settings are auditable against this document.

## Environment protection and release authority

The `release` environment is the authorization boundary for publication, but the routine Microsoft
update path is intentionally non-interactive. A normal
Renovate → qualification → immutable release → canary → stable/Pages run must not require a human
environment approval.

In the target organization:

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

## Migration checklist

Perform organization migration as a deliberate owner-reviewed change, not as an incidental transfer.

1. Select and approve the target organization and the real Platform, Security, Release, and
   Extension Policy team identities.
2. Populate each critical team with at least two active people where practical, and confirm each
   person's repository role uses least privilege.
3. Record the current repository settings before transfer: default-branch ruleset, release-tag
   ruleset, Actions permissions, environments/reviewers, Pages configuration, security features,
   and package access.
4. Transfer/adopt the repository into the organization without rewriting history or release tags.
5. Verify Actions, Pages, Releases, GHCR package ownership/access, Private Vulnerability Reporting,
   and repository links still point to the intended project.
6. Replace the interim individual CODEOWNERS entries with the final approved organization/team
   identities and review any path-mapping changes.
7. Verify the target default-branch settings preserve review-thread resolution, CODEOWNERS review,
   required checks, stale-review dismissal, and last-push approval.
8. Reapply/verify immutable release-tag protection.
9. Configure `release` environment deployment restrictions and Release Owner access without adding
   a routine human-review gate, then verify the `github-pages` environment remains separate from
   release authorization.
10. Re-run repository policy/CI checks and inspect the effective rulesets through the GitHub API or
    settings UI.
11. At the next ordinary release opportunity, have a backup Release Owner perform or approve the
    release flow so continuity is demonstrated without creating a test release solely for the
    migration.
12. Only after the checks above pass should the original personal owner be considered removable
    from day-to-day administration.

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
