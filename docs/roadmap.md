# Roadmap

## Immediate

- qualify the complete Code-OSS 1.139.1 build;
- fix any static ESM/bootstrap incompatibilities with the smallest possible delta;
- run Chromium Playwright qualification;
- record the first real clean-start network trace;
- determine whether any upstream patches are required.

## Browser qualification

- stabilize selectors against the first real artifact;
- add filesystem/persistence tests;
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
- add extension license inventory and SBOM integration.

## Supply chain/release

- artifact-level CycloneDX SBOM;
- provenance attestation;
- release verification command;
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
- [x] enforce that jobs executing upstream builds have read-only permissions, no OIDC and no persisted checkout credentials;\n- add further release-contract checks for attest/publish job separation and immutable release inputs.
