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
be supplied with `source.registry`. The exact versioned VSIX is downloaded into
`.work/extensions-cache/`, then its SHA-256 is checked before the archive is inspected or copied.
Release builds never request an extension alias such as `latest`.

For every locked extension the build fails unless all of the following hold:

- the VSIX SHA-256 exactly matches the lock;
- `extension/package.json` exists;
- manifest publisher/name matches the locked extension ID;
- manifest version matches the locked version;
- a non-empty `browser` entry point exists and is present in the archive;
- the declared license satisfies `extensions/license-policy.json`;
- the extension ID is not already present in the upstream distribution;
- the archive contains no absolute paths, parent traversal, or symlink entries.

The default license policy requires a declared license and allows a conservative set of
redistribution-friendly SPDX identifiers. Project maintainers may add an extension-specific
`overrides` entry after reviewing its license obligations.

Installed lockfile extensions are copied into `dist/extensions/` and recorded in
`dist/locked-extensions.json`. The generated `additional-extensions.json` exposes only those
post-build additions to the static workbench.
