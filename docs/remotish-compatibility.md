# Remotish host compatibility

The generic `company-standard` deployment profile grants no proposed APIs. Remotish compatibility is
an explicit opt-in through the `remotish-compat` deployment profile.

That profile grants the separately distributed extension `hrashton.remotish` permission to use only
the `scmHistoryProvider` and `timeline` proposed APIs. The grant remains host compatibility only:
COSW does not bundle, preinstall, download, or otherwise distribute Remotish.

The exception lives in `config/policies/proposed-api/remotish.json` and carries review metadata:
extension ID, reviewer role, reason, and expiry. Because the extension is not present in the extension
lock, there is no approved VSIX version or digest to bind yet. If Remotish is ever bundled, its
proposed-API approval must be revised to bind the admitted extension artifact metadata before release.

During Code-OSS source preparation, COSW verifies that every proposal named by the selected profile
still has a matching `src/vscode-dts/vscode.proposed.<proposal>.d.ts` definition in the pinned
upstream revision. A removed or renamed proposal therefore fails the qualified build.

Select `remotish-compat` only for deployments that explicitly need this unstable compatibility
surface. Normal company deployments continue to select `company-standard`.


To opt in for a qualified deployment, change the deployment selector to:

```json
{
  "schemaVersion": 1,
  "profile": "remotish-compat"
}
```

That selector change is itself a release input and changes the deployment-profile digest recorded in
qualification, release metadata, and promotion identity. Switching profiles therefore requires the
normal qualification/release path; it is not a runtime toggle.
