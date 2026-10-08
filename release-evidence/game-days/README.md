# Release game-day evidence

Completed controlled release/recovery game days are recorded here as JSON indexes of durable
workflow, GitHub Release, artifact, OCI, and deployment identities. See
[the game-day runbook](../../docs/release-game-day.md).

A record is evidence only after the real workflows and deployments have completed. Do not add
placeholder or synthetic records to satisfy the control. Each record must identify distinct
executor/reviewer GitHub accounts by login and numeric user ID and link to the reviewer's durable
GitHub sign-off permalink.

Use the filename `YYYY-MM-DD-<release-tag>.json`. Validate a record with:

```bash
python3 scripts/verify_game_day_record.py release-evidence/game-days/<record>.json
```

The repository unit suite validates every committed JSON record in this directory.

To check that at least one validated game-day record has actually been committed, run
`make release-recovery-readiness` or dispatch the manual **Release recovery readiness**
GitHub Actions workflow. The check fails while this directory has no JSON records.
It verifies record structure, not the authenticity of the referenced GitHub runs or deployments;
that remains the independent reviewer's responsibility.
