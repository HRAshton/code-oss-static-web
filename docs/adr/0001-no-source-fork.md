# ADR-0001: Integrate immutable upstream source without a maintained fork

- Status: Accepted
- Date: 2026-10-03

## Context

The project needs to produce a static browser distribution from Code - OSS while keeping the
project-owned delta reviewable and minimizing long-lived divergence from upstream. Maintaining a
source fork would make it easier for security or compatibility changes to become implicit in a
large branch history and would increase the cost of evaluating every upstream update.

At the same time, fetching a named upstream release without binding it to an immutable object would
allow tag movement or resolution differences to change the source selected by an unchanged project
revision.

## Decision

The project does not maintain a Code - OSS source fork.

Instead:

1. [upstream.lock.json](../../upstream.lock.json) records the expected Microsoft repository, release
   tag, exact 40-character commit, and source date epoch.
2. [scripts/fetch_upstream.py](../../scripts/fetch_upstream.py) independently resolves the tag,
   including annotated-tag peeling, requires it to identify the pinned commit, fetches the commit
   directly into a disposable checkout, and verifies detached <code>HEAD</code>.
3. Project behavior is expressed through deterministic repository-owned configuration and tooling,
   principally [config/product-transform.json](../../config/product-transform.json),
   [scripts/prepare_upstream.py](../../scripts/prepare_upstream.py), and the explicit
   [patch manifest](../../patches/manifest.json).
4. The disposable checkout is reset and cleaned before the product transform and patch set are
   applied by [scripts/build.py](../../scripts/build.py).
5. Patches are an explicit exception mechanism. The preferred design is configuration/external
   tooling, and the patch set may legitimately remain empty.

## Consequences

Upstream updates are visible as lock changes rather than merges from a fork. The exact source
identity is reviewable and automation can fail before building when the tag and commit disagree.
Project-owned behavior remains concentrated in comparatively small configuration/tooling surfaces.

The design does not make upstream trustworthy. The pinned commit and its dependency graph remain
untrusted inputs that execute during the build, so build jobs are denied release credentials and
OIDC authority. A malicious upstream commit can still produce malicious output; qualification,
reproducibility, review, and downstream privilege separation are additional controls rather than a
substitute for source review.

## Enforcement and verification

- [scripts/validate_config.py](../../scripts/validate_config.py)
- [scripts/fetch_upstream.py](../../scripts/fetch_upstream.py)
- [scripts/build.py](../../scripts/build.py)
- [docs/build.md](../build.md)
- [scripts/check_policy.py](../../scripts/check_policy.py)
- [tests/test_tooling.py](../../tests/test_tooling.py)
