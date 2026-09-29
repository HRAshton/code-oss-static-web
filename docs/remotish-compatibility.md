# Remotish host compatibility

Code OSS Static Web (COSW) grants the separately distributed extension
`hrashton.remotish` permission to use the `scmHistoryProvider` and `timeline` proposed APIs on
qualified COSW releases.

This is a product-level host compatibility grant only. COSW does not bundle, preinstall, download,
or otherwise distribute Remotish, and Remotish is not a runtime dependency of COSW. Users who do
not install Remotish get the normal COSW experience with no additional extension code or providers.

The grant is intentionally scoped to the single extension ID:

```json
{
  "extensionEnabledApiProposals": {
    "hrashton.remotish": [
      "scmHistoryProvider",
      "timeline"
    ]
  }
}
```

Proposed APIs are not enabled globally. During Code-OSS source preparation, COSW verifies that every
proposal named by `extensionEnabledApiProposals` still has a matching
`src/vscode-dts/vscode.proposed.<proposal>.d.ts` definition in the pinned upstream revision. A
removed or renamed proposal therefore fails the qualified build before release.

Because Remotish itself is not shipped in the static distribution, the compatibility grant does not
make Remotish a COSW SBOM or license-inventory component. If Remotish is installed separately, its
distribution and licensing remain outside the COSW release artifact boundary.
