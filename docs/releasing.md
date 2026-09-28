# Releasing

Microsoft Code - OSS updates normally publish automatically. Project-side fixes can publish an
explicit patch revision without waiting for another Microsoft release.

## Version contract

Release tags are immutable and have the form:

```text
v<code-oss-version>-web.N
```

The revision has two meanings:

- `web.0` is reserved for the automatic release of a new Microsoft Code - OSS version.
- `web.1`, `web.2`, and later revisions are project-side patch releases that keep the same
  Microsoft Code - OSS version.

The revision is monotonic for each Microsoft version. Release tags are never moved or reused for a
different commit.

## Automatic Microsoft release

Renovate tracks `microsoft/vscode` and updates the exact upstream tag and tag commit in
`upstream.lock.json`. Renovate dependency PRs use the normal cheap repository checks and are
eligible for auto-merge; ordinary dependency updates do not build or deploy Code - OSS.

When a merged `master` commit actually changes the pinned Microsoft tag or commit, the upstream
qualification trigger dispatches `Full build qualification` with all browsers and
`release_mode=upstream`. Metadata-only lock changes do not trigger that expensive path.

After build, Chromium/Firefox/WebKit qualification, packaging and qualification attestations all
succeed, the workflow creates exactly:

```text
v<code-oss-version>-web.0
```

It then dispatches the independent Release workflow for that immutable tag.

## Project patch release

Use the **Patch release** workflow when a project-owned source, packaging, workflow, container, or
security fix must ship before the next Microsoft release.

The dispatcher is fail-closed:

1. the current Microsoft version must already have a `web.0` tag;
2. current `master` must differ from the latest `web.N` tag for that Microsoft version;
3. the full Chromium/Firefox/WebKit qualification runs again with `release_mode=patch`;
4. after qualification succeeds, the workflow selects one greater than the highest existing
   revision and creates that immutable tag;
5. the independent Release workflow rebuilds and publishes the patch release.

For example, if `v1.140.0-web.0` already exists and a project fix is merged, the next successful
patch release is `v1.140.0-web.1`.

## Retry versus patch

Do **not** increment the revision for a transient publication failure when the source commit has not
changed. Retry the Release workflow for the existing immutable tag using the successful qualification
workflow-run ID.

Increment to the next `web.N` only when a source change was required after the previous tag was
created. The Patch release workflow refuses to create another revision when the latest release tag
already points to current `master`.

## Qualification evidence

The successful all-browser workflow run on the exact release commit is the qualification evidence.
Qualification is not stored as a mutable boolean in source control.

The qualification workflow records the exact commit, selected release tag, release mode and workflow
run ID in a `release-qualification` artifact. The Release workflow downloads that artifact and
verifies all of those bindings before doing any publication work.

The Release workflow then performs an independent clean rebuild, reproducibility comparison,
release-grade Chromium qualification, tag-specific packaging, provenance/SBOM attestation, and
publication to GitHub Releases, GitHub Pages and GHCR.

Final archives, SBOM metadata and the OCI image use the actual immutable `web.N` release tag.

## Failure behavior

If any build, browser, packaging, reproducibility, security or publication gate fails, automation
stops. No mutable tag is moved. A maintainer only needs to intervene when the automated path cannot
prove the revision works or when a project patch release is intentionally requested.

## Release notes

GitHub-generated release notes are published automatically from the merged change history. Security
advisories and other material project notes should be added to the repository before release so they
are part of the immutable release history.

## One-time repository setup

GitHub Pages must be enabled separately from the `github-pages` environment. In repository
**Settings → Pages → Build and deployment**, set **Source** to **GitHub Actions**. The Release
workflow checks this before starting its expensive independent rebuild.

## Verify

After publication:

- verify the GitHub Release archives and `SHA256SUMS`;
- verify artifact attestations with `gh attestation verify`;
- verify the Pages deployment;
- verify the GHCR tag exposes both `linux/amd64` and `linux/arm64` manifests.

Do not publish or move a mutable `latest` tag as part of the immutable release contract.
