# ADR-0003: Treat bundled extensions as explicit trusted release inputs

- Status: Accepted
- Date: 2026-10-03

## Context

Browser-compatible extensions can add important functionality, but an extension executes code in the
workbench/web extension-host environment and may process workspace and persisted user state.
Extension registries and VSIX archives also introduce supply-chain and archive-ingestion risk.

Treating a gallery result, mutable alias, or publisher identity as sufficient trust would make the
release contents depend on mutable external state.

## Decision

Bundled extensions are explicit, immutable release inputs rather than dynamically resolved runtime
dependencies.

Every bundled extension must be listed in
[extensions/extensions.lock.json](../../extensions/extensions.lock.json) with an exact ID, version,
SHA-256, license, and approved source type. Open VSX acquisition is default-deny by origin through
[extensions/source-policy.json](../../extensions/source-policy.json). License acceptance is explicit
through [extensions/license-policy.json](../../extensions/license-policy.json).

[scripts/extension_lock.py](../../scripts/extension_lock.py) must verify the digest before inspecting
the archive, require a matching manifest/browser entrypoint, reject duplicate upstream IDs, and
enforce archive path, symlink, file-count, expanded-size, download-size, and compression-ratio
limits. Installed extensions are copied into the canonical distribution and recorded in generated
lock/index metadata.

Workspace trust remains enabled, but it is not considered a sandbox for an extension that is
deliberately bundled or separately installed.

## Consequences

Adding or changing a bundled extension is a security and redistribution decision that receives full
qualification. The release is reproducible with respect to the exact locked bytes and does not rely
on a <code>latest</code> alias.

The controls establish what code is shipped; they do not prove that the approved code is benign.
Maintainers remain responsible for reviewing extension behavior and license obligations, and users
remain responsible for separately installed extensions.

The production extension lock may be empty. Supporting a locked-extension mechanism does not imply
that any third-party extension is trusted by default.

## Enforcement and verification

- [extensions/README.md](../../extensions/README.md)
- [scripts/extension_lock.py](../../scripts/extension_lock.py)
- [scripts/validate_config.py](../../scripts/validate_config.py)
- [scripts/make_static.py](../../scripts/make_static.py)
- [tests/test_tooling.py](../../tests/test_tooling.py)
- [tests/e2e/extension-host.spec.cjs](../../tests/e2e/extension-host.spec.cjs)
- [tests/e2e/workbench.spec.cjs](../../tests/e2e/workbench.spec.cjs)
