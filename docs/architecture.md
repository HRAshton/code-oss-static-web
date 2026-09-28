# Architecture

```text
upstream.lock.json
       |
       v
immutable Code - OSS commit
       |
       +--> deterministic product transform
       +--> explicit patch set (currently empty)
       v
upstream vscode-web-min build
       v
static transformer
  index.html + static-bootstrap.mjs + runtime.json + extensions.json
       v
browser-only dist/
```

The bootstrap computes its base URL at runtime so the same `dist/` can be hosted at `/` or a
static subpath. It injects the workbench configuration before importing upstream's web workbench.
