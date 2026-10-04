# Internal extension mirror

Bundled company extensions must be admitted through a company-controlled immutable mirror before
they can enter the production extension lock. The public Open VSX service is an intake source, not a
production rebuild dependency.

The intended flow is:

1. Fetch an exact candidate VSIX from an approved source and verify the expected version/digest.
2. Run malware/static scanning outside the build-authority boundary and retain the scan evidence.
3. Review the declared license and browser compatibility.
4. Run `scripts/extension_intake.py` with the reviewer, original source, clean scan result, approval
   date, and configured mirror base URL.
5. Upload the exact candidate bytes to the generated content-addressed mirror URL. The URL contains
   the SHA-256 digest and must be hosted under an origin listed in
   `extensions/source-policy.json`.
6. Add the emitted `lockEntry` to `extensions/extensions.lock.json` only after the mirror object is
   immutable and independently digest-verified.
7. Build and browser-qualify the extension from the mirror-backed lock entry.

The production source policy sets `requireMirrorForLockedExtensions` to true. Therefore a future
non-empty production lock cannot use `open-vsx` or `local-vsix` entries directly. Open VSX remains
available to intake tooling and tests, while released builds consume the approved mirror URL.

A mirrored lock entry records the exact version and SHA-256, the content-addressed mirror URL, the
reviewer, original source, clean scan result, approval date, and reviewed license. Mirror redirects
are constrained to approved mirror origins and downloaded bytes are re-hashed before use.

The repository intentionally does not invent a company storage hostname. Before admitting the first
extension, organization operators must configure `allowedMirrorOrigins` and provision immutable
object retention/access controls for that origin.
