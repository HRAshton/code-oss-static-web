# Build

Prerequisites: Git, Python 3.11+, and a Node/npm version compatible with the pinned Code - OSS
revision. The first full qualification workflow uses Node 24.

```bash
./build.sh
python3 scripts/smoke_static.py dist
./package.sh
```

The disposable checkout is `.work/vscode`. `npm ci` executes upstream scripts, therefore the CI
build job must not possess release credentials or OIDC attestation permission.
