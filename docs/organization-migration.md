# Organization team migration

This is the activation procedure for the governance model in [GOVERNANCE.md](../GOVERNANCE.md).
It does not authorize a repository transfer or invent team identities.

## Before transfer

1. Approve the target organization and create real teams for Platform, Security, Release,
   Extension Policy, and Legal/licensing responsibilities.
2. Put at least two qualified humans in each critical operational team where applicable.
3. Export or record the current branch/tag rulesets, Actions policy, environments, Pages settings,
   GHCR package access, security features, and repository visibility.
4. Confirm the destination organization permits the Actions used by this repository and does not
   weaken immutable-tag, CODEOWNERS, code-scanning, or environment controls.

## Render team-backed CODEOWNERS

After the repository belongs to the organization and the final team slugs exist, run:

    python3 scripts/render_codeowners.py \
      --organization <org-slug> \
      --platform-team <platform-team> \
      --security-team <security-team> \
      --release-team <release-team> \
      --extension-policy-team <extension-policy-team> \
      --legal-team <legal-team>

This writes both `.github/CODEOWNERS` and `.github/governance-teams.json`. Repository policy then
switches from the interim personal-owner contract to an exact generated team contract. Do not edit
team-mode CODEOWNERS manually.

## After transfer

Verify the effective default-branch and immutable-tag rulesets, required checks, CODEOWNERS review,
Actions permissions, release and github-pages environments, Pages source/deployment state, GHCR
ownership/access, Private Vulnerability Reporting, and security scanning. Open a sample sensitive
change and confirm the intended team receives the review request.

A second Release operator must execute or recover a documented release procedure successfully before
the original personal owner is considered non-essential. Record the organization, team slugs,
ruleset IDs, environment settings, operator identities, date, and any exception in the migration
change record.
