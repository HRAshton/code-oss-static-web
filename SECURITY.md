# Security policy

Use GitHub private vulnerability reporting once the repository is published. Do not report a
suspected vulnerability in a public issue.

The project is pre-release. Only upstream revisions explicitly marked qualified are intended for
deployment.

Webviews deliberately fail closed during Phase 0. A generic static host does not automatically
provide the isolated per-webview origin model Code - OSS expects, so this project will not bypass
origin, CSP, sandbox, or hostname checks merely to make webviews render.
