# Contributing

Keep the upstream-specific delta small. Prefer external build/configuration logic over patches,
and prefer removing patches over adding them. Changes involving webviews, CSP, sandboxing,
workspace trust, extension loading, auth, URI handlers, or provenance require manual review.

Run:

```bash
python3 -m unittest discover -s tests -v
```
