# Upstream upgrades

A candidate update changes `upstream.lock.json` to an exact commit, obtains a clean checkout,
applies the same transform and patch set, then runs the full qualification suite. Compilation
alone is never sufficient to publish a release.
