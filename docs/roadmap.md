# Roadmap

## Immediate

- [x] qualify the complete Code-OSS 1.139.1 static build in Chromium;
- [x] resolve current upstream web embedder/bootstrap compatibility without source patches;
- [x] run Chromium Playwright qualification against the real static artifact;
- record the first explicit clean-start network trace artifact;
- [x] determine whether upstream source patches are required for 1.139.1: none.

## Browser qualification

- [x] stabilize selectors against the real artifact;
- [x] add browser-extension activation and global-state persistence qualification;
- add filesystem/workspace persistence tests;
- add worker/language-service tests;
- qualify Firefox;
- qualify WebKit where upstream behavior permits;
- add explicit offline-mode tests if offline caching becomes a supported feature.

## Extensions

- [x] implement the production `extensions.lock.json` schema and validator;
- [x] add pinned local VSIX ingestion;
- [x] add digest verification;
- [x] add browser-entrypoint compatibility checks;
- add Open VSX acquisition with exact versions/hashes;
- [x] add extension and shipped npm runtime components to the release SBOM;
- add extension license inventory.

## Supply chain/release

- [x] deterministic release archives and checksums;
- [x] deterministic artifact manifest bound to project/upstream/build inputs;
- [x] artifact-level CycloneDX 1.7 SBOM;
- [x] release verification command for checksums, manifest and SBOM;
- provenance attestation;
- artifact-level license inventory;
- canonical GitHub Release;
- Pages deployment from the exact canonical `dist/`;
- OCI image built from that same `dist/`;
- reproducible full-build comparison.

## Engineering policy

- [x] EditorConfig and LF normalization;
- [x] repository policy checks for immutable Action refs and unsafe execution patterns;
- [x] Conventional Commit validation for direct pushes;
- [x] pinned Ruff, Pyright and ShellCheck in CI;
- [x] single local `make check` entrypoint;
- expand Ruff from critical correctness rules to the configured full lint ruleset;
- make Ruff formatting a blocking CI gate after the existing Python files are normalized;
- tighten Pyright from `basic` to `strict`;
- add schema validation for all JSON/YAML configuration;
- [x] enforce that jobs executing upstream builds have read-only permissions, no OIDC and no persisted checkout credentials;
- add further release-contract checks for attest/publish job separation and immutable release inputs.
