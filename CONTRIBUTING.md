# Contributing

Contributions are welcome through GitHub issues and pull requests.

Before starting a large change, open an issue or discussion in the repository so the design and
scope can be agreed before implementation. Bug fixes and focused maintenance changes can go
directly to a pull request when the expected behavior is clear.

## Pull request process

1. Branch from the current protected default branch.
2. Keep the upstream-specific delta small. Prefer external build or configuration logic over
   patches, and prefer removing patches over adding them.
3. Add or update tests for behavior changes and bug fixes when a practical automated regression is
   possible.
4. Run the local checks described below.
5. Open a pull request that explains the behavior being changed, relevant security or compatibility
   implications, and how the change was tested.

Changes involving webviews, CSP, sandboxing, workspace trust, extension loading, authentication,
URI handlers, provenance, release publication, or other trust boundaries require explicit manual
review. Automated approvals cannot satisfy that requirement.

The trusted Renovate auto-approval workflow is a narrow exception for grouped platform-update
dependency pull requests. The exact trusted Renovate auto-approval allowlist is:

- `upstream.lock.json`
- `builder-apt-snapshot.json`

Both files must change together, with no additional paths. Approval waits for successful
pull-request `Full build qualification` (not the push-only `CI` workflow) and validation
of the upstream version/commit/source-date epoch and APT snapshot transformations.
Changes under `.github/**`, `deploy/**`, `builder-image.json`, or any other release/security
trust boundary are outside that allowlist and require human approval.

Pull requests otherwise require human review and the repository's required checks before merge.
Stale approvals are dismissed when the pull request changes, and the last push must be approved by
someone other than its author.

Repository ownership and sensitive-path review expectations are defined in
[Governance](GOVERNANCE.md). During the temporary two-developer phase, `.github/CODEOWNERS`
requires the other maintainer to approve sensitive-path changes. Distinct organization roles remain
a documented future control until qualified team members and team-backed rules are available.

`upstream.lock.json` and `builder-apt-snapshot.json` are intentionally outside CODEOWNERS,
allowing only the validated two-file platform update to merge without human review. A change to
either file alone is not auto-approved. The immutable image/digest/platform fields in
`builder-image.json` are CODEOWNED, alongside workflows, release policy, deployment, security,
and other trust boundaries.

The protected default-branch ruleset must require the `Artifact qualification gate` job from the
`Full build qualification` workflow. The gate is reported for every pull request: documentation-only
changes pass after path classification without building the static application; explicitly
allowlisted publication/promotion control-plane changes run a read-only release-metadata policy and
unit test lane without rebuilding Code - OSS; distribution-dependent packaging/SBOM/OCI changes build
a real static distribution, run Chromium smoke qualification, and package that exact artifact; and
higher-risk upstream/runtime/qualification-boundary changes require
the broader browser qualification. Mixed or unknown changes fail closed to the stronger applicable
lane.

## Contribution requirements

- Do not commit credentials, private keys, access tokens, or other secrets.
- Keep GitHub Actions and container dependencies pinned according to repository policy.
- Preserve the fail-closed security model; security checks must not be disabled merely to make a
  feature work.
- Keep documentation and tests synchronized with externally visible behavior.
- Follow the existing Python, shell, JavaScript, JSON, and YAML style enforced by CI.

## Commit messages

Every author-controlled commit, including commits created by bots and automation, must use a
single-line Conventional Commit subject. Keep the type and optional scope lowercase, and begin the
description after `: ` with an uppercase letter, for example
`fix(ci): Decouple release tag test from upstream lock`.

The sole history-validation exception is a same-repository `develop` → `master` promotion pull
request: GitHub-generated two-parent `Merge pull request #…` commits already accumulated on
`develop` are accepted there, while their embedded reviewed pull request title must still satisfy
the Conventional Commit subject policy. Other multiline or non-GitHub merge messages remain invalid.

Examples:

```text
feat: Add Open VSX lock support
fix: Preserve extension browser entrypoints
chore: Update qualification policy
```

Pull request titles follow the same policy because merge commits use the reviewed pull request title
as the human-controlled change description.

## Checks

The intended local entrypoint is:

```bash
make check
```

It combines formatting, linting, type checking, ShellCheck, syntax checks, schema/configuration
validation, workflow validation, REUSE licensing checks, unit tests, and repository policy checks.
The REUSE CLI used by CI is pinned to version 6.2.0.

For changes that affect the generated browser distribution, also run the relevant build and
qualification steps documented in [Testing](docs/testing.md). Release-affecting changes should be
checked against [Releasing](docs/releasing.md) and [Release security](docs/release-security.md).

## Reporting problems

Use GitHub Issues for public bugs and enhancement requests. Security vulnerabilities must follow
the private process in [SECURITY.md](SECURITY.md).


When the approved organization teams are staffed, sensitive-path ownership will be generated from
their team mapping. Until then, keep the two real maintainers in CODEOWNERS. See
[organization migration](docs/organization-migration.md).
