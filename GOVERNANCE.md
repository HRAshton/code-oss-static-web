# Governance

This document defines the repository ownership model, sensitive-path review expectations, target
GitHub settings, and continuity procedure for Code OSS Static Web.

The repository is currently operated from the personal `HRAshton` GitHub account. Organization
migration is intentionally deferred. This document prepares that migration without pretending that
organization teams, CODEOWNERS, or environment-reviewer identities already exist.

No organization/account setting change is authorized by this document alone. The repository owner
must approve the target organization, real team identities, membership, and final settings before
they are applied.

## Current operating state

The current protected `master` ruleset requires:

- pull requests for changes to the default branch;
- one approving review;
- dismissal of stale approvals after new pushes;
- approval of the last push by someone other than its author;
- the `tooling` and `Artifact qualification gate` status checks;
- CodeQL enforcement at the repository's configured threshold.

At the time this plan was written, the ruleset does **not** require review-thread resolution and
does **not** require CODEOWNERS approval.

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
| Release owners | Release authorization, protected release environment approval, publication/recovery, Pages/GHCR operation, and release runbooks |
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
| `.github/**` | Platform + Security | Workflows, actions, rulesets, permissions, and automation can change repository or release trust boundaries |
| `GOVERNANCE.md`, `CONTRIBUTING.md`, and root `CODEOWNERS` | Platform + Security | These files define repository ownership and review controls; weakening them changes the governance trust boundary |
| `security/**`, `SECURITY.md`, `docs/release-security.md` | Security | Security model, vulnerability handling, and release-integrity policy |
| `extensions/**` | Platform + Extension Policy; Security for trust/provenance changes; Legal/licensing when license/source policy changes | Extension code and metadata become part of the distributed product and supply chain |
| `deploy/**` | Platform + Release | Runtime/container deployment and publication behavior |
| `scripts/**` | Platform; add Security, Release, or Extension Policy when the script implements those boundaries | Repository scripts implement build, policy, qualification, packaging, and release controls |
| `build.sh`, `package.sh`, `config/**`, `patches/**` | Platform; Security when trust/runtime boundaries change | These inputs materially define generated distribution behavior |
| `upstream.lock.json` | Platform | Changes the immutable upstream source used by the product |
| Release workflows/actions and `docs/releasing.md` / `OPERATIONS.md` | Release + Platform; Security when publication authority or integrity changes | Controls immutable tag creation, publication, recovery, and operator procedure |

The existing [Contributing](CONTRIBUTING.md) trust-boundary review requirements still apply even
when a path is not explicitly listed above.

### Before organization migration

Role-specific review is procedural because approved GitHub teams do not exist yet. For a sensitive
change, the pull request should identify the applicable review responsibility in its description or
review discussion, and the independent reviewer should explicitly cover that responsibility.

The current branch ruleset still enforces only its configured approval count. This phase therefore
documents the intended control but does not claim team-level enforcement.

### After organization migration

Use GitHub teams and repository settings to enforce the approved ownership model. CODEOWNERS should
route review to real team identities, while branch/ruleset controls should provide the actual merge
gate. Where a change requires two distinct responsibilities, do not assume that listing two owners
on one CODEOWNERS pattern proves both approved it; use the available ruleset/reviewer controls or an
explicit documented dual-review procedure.

## CODEOWNERS policy

No `CODEOWNERS` file is added during the personal-account phase.

Add one only after all of the following are true:

1. the target organization is approved;
2. the real GitHub teams/users that will own each area are created and populated;
3. at least two people cover every critical operational capability;
4. the repository owner reviews the proposed path-to-team mapping;
5. the target branch ruleset is ready to require CODEOWNERS review.

The first CODEOWNERS change must use only concrete, approved GitHub identities. Do not commit fake
organization names, placeholder teams, future usernames, or role labels as CODEOWNERS entries.

The intended mapping is the sensitive-path table above. The migration pull request should translate
those responsibilities into the final approved team slugs and explain any divergence.

## Target repository settings

Organization migration must preserve or strengthen the current protected-branch controls. The
migration settings change should be reviewed as a separate administrative change and recorded in a
migration issue or change record.

For the default-branch ruleset, verify all of the following:

- pull requests remain required;
- the required approval count is not reduced below the current value;
- stale approvals remain dismissed after new pushes;
- last-push approval by someone other than the author remains required;
- **required review-thread resolution is enabled**;
- `tooling` and `Artifact qualification gate` remain required status checks;
- existing CodeQL/code-scanning requirements remain enabled;
- CODEOWNERS review is enabled only after the approved CODEOWNERS file exists;
- any path/team-specific reviewer rules needed for dual-role sensitive changes are configured;
- bypass access is absent or limited to an explicitly reviewed emergency mechanism with audit
  expectations.

For the immutable release-tag ruleset, preserve active update/deletion protection and the existing
no-routine-bypass model. A repository transfer must not create a window in which release tags can be
moved or deleted without the intended protection.

After migration, capture the resulting ruleset IDs and exported/API-visible configuration in the
migration record so the settings are auditable against this document.

## Environment reviewers and release authority

The `release` environment is the authorization boundary for publication. In the target
organization:

- release approval authority should belong to the approved Release Owners, with at least two active
  humans capable of approving;
- self-approval should be prevented where the selected GitHub plan/settings support it;
- environment deployment restrictions should accept only the intended immutable release-tag flow;
- repository administrators who are not Release Owners should not be treated as routine release
  approvers merely because they can administer the repository;
- changes to release-environment reviewers or protection rules require owner review and should be
  recorded in the repository migration/change record.

The `github-pages` environment is a deployment environment, not a replacement for the shared
`release` authorization boundary. Preserve the release gate described in
[Release security](docs/release-security.md).

Release authority includes the ability to approve publication, dispatch the intended release or
recovery workflow, inspect failed publication state, and follow [Operations](OPERATIONS.md). It does
not include permission to move immutable release tags or overwrite conflicting published artifacts.

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
6. Add the reviewed CODEOWNERS file using only the final organization/team identities.
7. Apply the target default-branch settings, including review-thread resolution and CODEOWNERS
   review, without weakening the existing required checks or last-push approval.
8. Reapply/verify immutable release-tag protection.
9. Configure the `release` environment reviewers and deployment restrictions, then verify the
   `github-pages` environment remains separate from release authorization.
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
- two humans able to authorize and operate the `release` environment;
- two humans able to inspect/recover GitHub Release, Pages, and GHCR publication state.

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
