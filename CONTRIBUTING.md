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
review.

Pull requests require human review and the repository's required checks before merge. Stale
approvals are dismissed when the pull request changes, and the last push must be approved by someone
other than its author.

## Contribution requirements

- Do not commit credentials, private keys, access tokens, or other secrets.
- Keep GitHub Actions and container dependencies pinned according to repository policy.
- Preserve the fail-closed security model; security checks must not be disabled merely to make a
  feature work.
- Keep documentation and tests synchronized with externally visible behavior.
- Follow the existing Python, shell, JavaScript, JSON, and YAML style enforced by CI.

## Commit messages

Every commit, including commits created by bots and automation, must use a
single-line Conventional Commit subject. Keep the type and optional scope lowercase, and begin the
description after `: ` with an uppercase letter, for example
`fix(ci): Decouple release tag test from upstream lock`.

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
