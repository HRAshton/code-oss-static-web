# Releasing

Stable releases are immutable tag-triggered publications from the protected default branch.

## Upstream integration

Microsoft Code - OSS updates are integration changes, not releases. Renovate tracks
`microsoft/vscode` and opens an update PR that pins both the upstream version and its exact tag
commit. Every upstream update resets `qualified` to `false` and records a pending qualification
note.

The upstream PR requests `vodyanica` and is eligible for GitHub auto-merge after the normal
protected-branch checks and required review. Once the unqualified update reaches `master`, the
upstream qualification trigger dispatches the existing full qualification workflow with
`browser=all`.

Compatibility fixes may then land on `master` while the upstream lock remains unqualified.
Publication stays blocked because the release tag contract requires `qualified: true`. Promote the
lock to qualified only after the full browser/release qualification succeeds; at that point refresh
the qualification note and the release timestamp metadata before creating the immutable release tag.

## Preflight

1. Confirm the target commit is on `master` and CI, CodeQL, and required repository checks are green.
2. Confirm `upstream.lock.json` has `"qualified": true`.
3. Confirm the protected `release` environment is configured for publication approval.
4. Confirm the `github-pages` environment and repository Pages deployment are configured for GitHub Actions.
5. Verify the exact release tag contract with `scripts/check_release_tag.py`.

For the current qualified upstream, the tag is `v1.139.1-web.0`.

## Publish

Create the immutable release tag on the verified `master` commit and push only that tag:

```bash
git fetch origin master
git tag v1.139.1-web.0 <verified-master-sha>
git push origin refs/tags/v1.139.1-web.0
```

The release workflow performs branch-lineage authorization, independent reproducible builds,
browser qualification, deterministic packaging, provenance/SBOM attestation, and publication to
GitHub Releases, GitHub Pages, and GHCR.

## Release notes

Every user-facing release must include human-readable release notes that summarize the important
changes and upgrade impact. GitHub-generated notes may be used as a starting point, but they must be
reviewed and supplemented when the generated text does not explain material behavior changes.

Any project vulnerability fixed by the release that already has a CVE or equivalent public
identifier must be called out explicitly with the affected and fixed versions. Dependency-only
vulnerabilities are documented when they materially affect the generated distribution.

## Verify

After publication:

- verify the GitHub Release archives and `SHA256SUMS`;
- verify artifact attestations with `gh attestation verify`;
- verify the Pages deployment;
- verify the GHCR tag exposes both `linux/amd64` and `linux/arm64` manifests;
- make the newly created GHCR package public if anonymous pulls are part of the release policy.

Do not publish or move a mutable `latest` tag as part of the immutable release contract.
