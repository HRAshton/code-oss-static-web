# Contributing

Keep the upstream-specific delta small. Prefer external build/configuration logic over patches,
and prefer removing patches over adding them. Changes involving webviews, CSP, sandboxing,
workspace trust, extension loading, auth, URI handlers, or provenance require manual review.

## Commit messages

Commits use Conventional Commits, must be a single line, and the description after `:` must begin
with an uppercase letter.

Examples:

```text
feat: Add Open VSX lock support
fix: Preserve extension browser entrypoints
chore: Update qualification policy
```

## Checks

The intended local entrypoint is:

```bash
make check
```

It combines formatting, linting, type checking, ShellCheck, syntax checks, unit tests, and repository
policy checks. Tool versions used by CI are pinned in the workflow.
