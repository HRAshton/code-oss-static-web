# Organization team activation

The repository was transferred to `Codellei` without rewriting Git history or release tags. This
procedure activates the future team-backed model in [GOVERNANCE.md](../GOVERNANCE.md). It does not
authorize settings changes or invent team identities.

## Current two-developer phase

`HRAshton` and `vodyanica` are the real CODEOWNERS. One independent review is required for an
author's sensitive-path change. The owner approved a temporary exception to separate
Platform/Security approvals because a two-person project cannot supply both when one person is the
author. Keep the required checks, CodeQL, CODEOWNERS review, and immutable-tag ruleset active.
Record the exception and organization settings in restricted migration evidence, not the public
repository. `vodyanica` retains repository write access as a collaborator while the Codellei
membership invitation is pending.

Before team activation, approve actual people and slugs for Platform, Security, Release, Extension
Policy, and Legal/licensing responsibilities. Establish backup release and organization administration
capability. Do not create fictional teams to satisfy policy tests.

## Render team-backed CODEOWNERS

After the approved final team slugs exist, run:

    python3 scripts/render_codeowners.py \
      --organization <org-slug> \
      --platform-team <platform-team> \
      --security-team <security-team> \
      --release-team <release-team> \
      --extension-policy-team <extension-policy-team> \
      --legal-team <legal-team>

This writes both `.github/CODEOWNERS` and `.github/governance-teams.json`. Repository policy then
switches from the interim two-developer contract to an exact generated team contract. Do not edit
team-mode CODEOWNERS manually.

## Verify team activation

Verify the effective default-branch and immutable-tag rulesets, required checks, CODEOWNERS review,
Actions permissions, release and github-pages environments, Pages source/deployment state, GHCR
ownership/access, Private Vulnerability Reporting, and security scanning. Open a sample sensitive
change and confirm the intended team receives the review request.

A second Release operator must execute or recover a documented release procedure successfully before
the original personal owner is considered non-essential. Record the organization, team slugs,
ruleset IDs, environment settings, operator identities, date, and any exception in the migration
change record.
