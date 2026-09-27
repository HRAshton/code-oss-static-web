# Extensions

The canonical distribution can include additional browser-compatible extensions through `extensions.lock.json`.

## Local VSIX source

The first supported source is a local VSIX with an exact SHA-256 digest:

```json
{
  "schemaVersion": 1,
  "extensions": [
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
  ]
}
```

Paths are resolved relative to the repository root. Release builds do not resolve `latest` or download an extension implicitly.

For every locked local VSIX the build fails unless all of the following hold:

- the file exists and is a `.vsix` ZIP archive;
- its SHA-256 exactly matches the lock;
- `extension/package.json` exists;
- the manifest publisher/name matches the locked extension ID;
- the manifest version matches the locked version;
- a non-empty `browser` entry point exists;
- the referenced browser entry point is present inside the VSIX;
- a declared lockfile license does not contradict the manifest license;
- the extension ID is not already present in the upstream distribution;
- the archive contains no absolute paths, parent traversal, or symlink entries.

Installed lockfile extensions are copied into `dist/extensions/` and recorded in `dist/locked-extensions.json`. The generated `extensions.json` then exposes them to the static workbench as built-in browser extensions.

Open VSX acquisition is intentionally not implemented yet. When added, it must pin exact versions and hashes before an artifact can become a release input.
