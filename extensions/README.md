# Extensions

The canonical distribution can include additional browser-compatible extensions through
`extensions.lock.json`. Every release input is pinned by exact version and SHA-256; `latest`
resolution is rejected.

## Local VSIX source

```json
{
  "id": "example.browser-extension",
  "version": "1.2.3",
  "sha256": "<64 lowercase hex characters>",
  "license": "MIT",
  "source": {
    "type": "local-vsix",
    "path": "vendor/example.browser-extension-1.2.3.vsix"
  }
}
```

Paths are resolved relative to the repository root.

## Open VSX source

```json
{
  "id": "example.browser-extension",
  "version": "1.2.3",
  "sha256": "<64 lowercase hex characters>",
  "license": "MIT",
  "source": {
    "type": "open-vsx"
  }
}
```

The default registry is `https://open-vsx.org`. A custom HTTPS Open VSX-compatible registry can
be supplied with `source.registry` only when its origin is explicitly listed in
`extensions/source-policy.json`. Registry values must be HTTPS origins without credentials,
paths, queries, or fragments. Download redirects are separately restricted to
`allowedOpenVsxDownloadOrigins`; the production policy allows the Open VSX registry plus its
`openvsx.eclipsecontent.org` file-delivery origin. The exact versioned VSIX is downloaded into
`.work/extensions-cache/` with a hard 272 MiB raw-archive cap, then its SHA-256 is checked before
the archive is inspected or copied. Release builds never request an extension alias such as
`latest`.

For every locked extension the build fails unless all of the following hold:

- the VSIX SHA-256 exactly matches the lock;
- `extension/package.json` exists;
- manifest publisher/name matches the locked extension ID;
- manifest version matches the locked version;
- a non-empty `browser` entry point exists and is present in the archive;
- the declared license satisfies `extensions/license-policy.json`;
- the extension ID is not already present in the upstream distribution;
- the archive contains no absolute paths, parent traversal, Windows-style paths, or symlink entries;
- the raw VSIX archive does not exceed 272 MiB, including while a remote response is streaming;
- the archive contains at most 4,096 entries;
- no expanded file exceeds 64 MiB and total expanded content does not exceed 256 MiB;
- files of at least 1 MiB do not exceed a 200:1 uncompressed-to-compressed size ratio.

The default license policy requires a declared license and allows a conservative set of
redistribution-friendly SPDX identifiers. Project maintainers may add an extension-specific
`overrides` entry after reviewing its license obligations.

Installed lockfile extensions are copied into `dist/extensions/` and recorded in
`dist/locked-extensions.json`. The generated `additional-extensions.json` exposes only those
post-build additions to the static workbench.

## Archive ingestion policy

Archive metadata is validated before any member is read or extracted, and extraction re-counts the
actual emitted bytes against the same per-file and total expanded-size limits. This provides a
second fail-closed boundary if archive metadata is inconsistent. Digest verification remains the
outer trust boundary: locked local and downloaded VSIX bytes must match their SHA-256 before ZIP
metadata or contents are inspected.

Production Open VSX sources are default-deny. `extensions/source-policy.json` separately lists
registry origins and file-download origins. A registry must be explicitly approved, while its
reviewed CDN/file host may be approved only for redirects and final responses. Adding a mirror,
registry, or delivery origin is therefore an explicit repository policy change.
