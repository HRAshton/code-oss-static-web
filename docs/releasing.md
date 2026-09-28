# Releasing

Stable releases are automated immutable publications driven only by Microsoft Code - OSS revision
changes.

## Upstream integration

Renovate tracks `microsoft/vscode` and updates the exact upstream tag and tag commit in
`upstream.lock.json`. Renovate dependency PRs use the normal cheap repository checks and are
eligible for auto-merge; they do not build or deploy Code - OSS.

When a merged `master` commit actually changes the pinned Microsoft tag or commit, the upstream
qualification trigger dispatches `Full build qualification` with `browser=all`. Metadata-only
changes to the lock do not trigger that expensive path.

## Qualification and publication

The successful all-browser workflow run on the exact `master` commit is the qualification evidence.
Qualification is intentionally not stored as a mutable boolean in source control.

After build, Chromium/Firefox/WebKit qualification, packaging and qualification attestations all
succeed, the workflow creates exactly one immutable tag:

```text
v<code-oss-version>-web.0
```

There are no routine `web.1` or later project releases. Project, dependency, workflow and container
updates merge into `master` and ship with the next Microsoft-driven `web.0` release.

The qualification workflow explicitly dispatches the release workflow using the immutable tag and
its own workflow-run ID. The release workflow verifies that the referenced qualification run
succeeded for the same commit and has the release-qualification evidence artifact before it performs
an independent clean rebuild, reproducibility comparison, Chromium qualification, packaging,
provenance/SBOM attestation, and publication to GitHub Releases, GitHub Pages and GHCR.

## Failure behavior

If any build, browser, packaging, reproducibility, security or publication gate fails, automation
stops. No later release tag is invented and no mutable tag is moved. A maintainer only needs to
intervene when the automated path cannot prove the new Microsoft revision works.

A failed publication for an already-created immutable tag is retried by manually dispatching the
Release workflow with the successful qualification workflow-run ID; the tag itself is never moved.

## Release notes

GitHub-generated release notes are published automatically from the merged change history. Security
advisories and other material project notes should be added to the repository before the next
Microsoft-driven release so they are part of the immutable release history.

## Verify

After publication:

- verify the GitHub Release archives and `SHA256SUMS`;
- verify artifact attestations with `gh attestation verify`;
- verify the Pages deployment;
- verify the GHCR tag exposes both `linux/amd64` and `linux/arm64` manifests.

Do not publish or move a mutable `latest` tag as part of the immutable release contract.
