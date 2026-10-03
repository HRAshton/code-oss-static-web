# ADR-0005: Separate qualification, release rebuild, attestation, and promotion

- Status: Accepted
- Date: 2026-10-03

## Context

A static distribution passes through build runners, workflow artifacts, browser qualification,
packaging, attestation, and three publication systems. Reusing a single privileged job for all of
those activities would let upstream/dependency execution reach release credentials and would make it
difficult to prove that published bytes are the bytes that were tested.

Caching and workflow artifacts improve CI efficiency but must not become implicit release provenance.

## Decision

Release promotion is a sequence of independently checked boundaries:

1. Full qualification builds the canonical <code>dist/</code>, runs the required browser suites, and
   records its normalized tree SHA-256 and file count as qualification evidence.
2. An immutable <code>v&lt;code-oss-version&gt;-web.N</code> tag identifies the release revision.
3. The independent Release workflow verifies qualification provenance and performs a clean rebuild
   without the development build cache.
4. [scripts/verify_dist_identity.py](../../scripts/verify_dist_identity.py) requires that rebuild to
   match the qualified distribution identity.
5. A second clean build is compared with
   [scripts/compare_dist.py](../../scripts/compare_dist.py) as an independent reproducibility gate.
6. Packaging creates deterministic archives and release metadata from the verified distribution.
7. Attestation runs in a downstream job that has OIDC/attestation authority but no source checkout or
   upstream build.
8. Immutable publication crosses the protected <code>release</code> environment and re-checks
   immutable-tag invariants before publishing GitHub Release assets and the immutable GHCR image.
9. After immutable publication succeeds, a separate promotion workflow resolves the durable release,
   verifies attestations/checksums, and records a policy-bound identity containing the release tag,
   commit, artifact/distribution digests, and promotion profile/policy digest.
10. Routine upstream releases automatically progress through <code>canary</code> and then
    <code>stable</code>. The exact canary identity must succeed before automatic stable promotion.
    Stable owns the Pages deployment.
11. Rollback creates a new stable deployment pointing at a previously stable immutable release; it
    never moves a release tag or rebuilds/re-attests content.
12. Immutable publication recovery may reuse retained source-run artifacts; promotion recovery uses
    durable GitHub Release assets. Neither path rebuilds the immutable release.

Release tags are never moved, and no mutable <code>latest</code> tag is part of the release contract.
The mutable state is explicitly the canary/stable deployment pointer recorded in GitHub Deployments.
A transient publication or promotion failure is recovered against the existing immutable release
rather than producing a different <code>web.N</code> revision with unchanged source.

## Consequences

The design costs additional clean builds and can prefer unavailability over mutation when registry or
artifact state is ambiguous. That cost is intentional: cache hits, existing registry state, or a
successful publication channel never substitute for explicit release evidence.

GitHub remains a substantial trust dependency. Separation reduces the authority available to any one
job, but a compromise of the platform control plane or enough repository administrators can still
affect future releases.

## Enforcement and verification

- [.github/workflows/qualify.yml](../../.github/workflows/qualify.yml)
- [.github/workflows/release.yml](../../.github/workflows/release.yml)
- [.github/workflows/recover-release-publication.yml](../../.github/workflows/recover-release-publication.yml)
- [.github/workflows/promote.yml](../../.github/workflows/promote.yml)
- [config/promotion-policy.json](../../config/promotion-policy.json)
- [scripts/promotion.py](../../scripts/promotion.py)
- [.github/rulesets/immutable-release-tags.json](../../.github/rulesets/immutable-release-tags.json)
- [scripts/check_policy.py](../../scripts/check_policy.py)
- [scripts/verify_dist_identity.py](../../scripts/verify_dist_identity.py)
- [scripts/compare_dist.py](../../scripts/compare_dist.py)
- [docs/release-security.md](../release-security.md)
- [docs/releasing.md](../releasing.md)
- [OPERATIONS.md](../../OPERATIONS.md)
