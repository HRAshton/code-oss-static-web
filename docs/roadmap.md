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

Strict codestyle/repository policy remains to be implemented as a blocking `check` target, including:

- deterministic formatter;
- strict linting;
- strict type checking for typed tooling;
- ShellCheck for shell scripts;
- Ruff plus Pyright/mypy for Python if Python remains in the final toolchain;
- schema validation for JSON/YAML configuration;
- release-contract/policy tests that reject unpinned tools, mutable inputs and unsafe fallbacks.
