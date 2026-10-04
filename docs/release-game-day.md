# Release recovery game day

This runbook is an execution plan, not evidence that a recovery exercise has happened. A completed
record is created only after the real workflows and deployments below have finished.

## Scope and safety

Run the exercise from the current protected default branch after the release/promotion changes are
merged. Schedule it as a production change because the exercise intentionally advances stable,
rolls stable back to a previously successful immutable release, and forward-promotes the candidate
again.

Use two operators: one executes and one independently checks the recorded identities. Record each
operator's GitHub login and immutable numeric GitHub user ID. The reviewer must publish the
independent sign-off as a durable GitHub issue comment or pull-request review/comment permalink;
that URL is part of the evidence record. Freeze promotion-policy/profile changes for the duration
of the exercise. Choose:

- a new immutable release produced by the normal qualification/Release path as the candidate;
- a different immutable release that already has successful stable history as the rollback target.

Do not move either release tag, rebuild release content to make the exercise pass, or use a rollback
target that lacks the workflow's required historical stable evidence.

## Exercise

1. **Qualification.** Run release-intent qualification for the candidate source commit and record the
   successful Full build qualification run ID. Confirm the resulting immutable tag is bound to that
   exact commit.
2. **Immutable publication.** Run/observe the independent Release workflow for the immutable tag and
   record its run ID. Confirm `immutable-publication-status` succeeds.
3. **Independent identity check.** From the published GitHub Release, verify `SHA256SUMS`, the
   canonical distribution archive, `artifact-manifest.json`, `playwright-runtime.tar.gz`, their
   GitHub attestations, the distribution-tree SHA-256 in the manifest, and the immutable GHCR digest.
   Record those durable identities in the evidence record.
4. **Idempotent publication retry.** Dispatch `release.yml` again on the same immutable tag using
   the original qualification run ID. Record the retry run ID and confirm GitHub Release assets,
   release tag, archive digest, runtime digest, and GHCR digest do not move.
5. **Artifact-only publication recovery.** While the original Release run's recovery artifacts are
   still retained, dispatch `recover-release-publication.yml` on the same immutable tag with
   `release_run_id=<original Release run>` and `channel=all`. Record the recovery run ID and
   confirm it converges without building, packaging, attesting, or retagging. This step exercises the
   retained-artifact publication repair path; it is not the long-term rollback mechanism.
6. **Canary to stable.** Dispatch `promote.yml` for the candidate with `target=auto` (and the
   source Release run ID for audit). Confirm the real Pages canary identity and Chromium synthetic
   succeed, then stable Pages converges to the exact same immutable release. Record the successful
   canary and stable deployment IDs and identities.
7. **Rollback.** Dispatch `promote.yml` with the previously successful rollback tag and
   `target=stable`. Confirm the candidate GitHub Release/GHCR identities remain unchanged and live
   stable Pages now reports the rollback target identity. Record the new stable deployment.
8. **Forward promotion.** Dispatch `promote.yml` for the candidate with `target=stable`. If the
   promotion policy/profile changed despite the freeze, rerun canary first. Confirm the final stable
   identity exactly matches the candidate identity recorded before rollback.
9. **Independent review and close-out.** The reviewer independently re-resolves the recorded
   workflow, GitHub Release, artifact, OCI, and deployment identities and confirms the executor did
   not substitute or move any immutable identity. The reviewer posts that sign-off as a GitHub issue
   comment or pull-request review/comment permalink. Record that permalink, then add operator
   observations and create follow-up issues for every unexpected failure, manual workaround,
   ambiguous signal, or undocumented recovery step.

## Evidence record

Create:

`release-evidence/game-days/YYYY-MM-DD-<release-tag>.json`

The record is an index of durable, auditable identities. It must include:

- candidate tag and commit;
- distinct executor/reviewer GitHub logins and immutable numeric GitHub user IDs;
- the reviewer's durable GitHub sign-off permalink;
- qualification, Release, publication-retry, publication-recovery, promotion, rollback, and
  forward-promotion workflow run IDs;
- GitHub Release ID;
- archive, distribution-tree, Playwright-runtime, and GHCR digests;
- rollback target tag/commit/distribution-tree digest;
- canary/stable deployment IDs with their release tag, commit, and distribution-tree digest;
- non-empty operator notes and any follow-up issue URLs.

Validate it before committing:

```bash
python3 scripts/verify_game_day_record.py \
  release-evidence/game-days/YYYY-MM-DD-<release-tag>.json
```

Repository tests also validate every committed `release-evidence/game-days/*.json` record.

Do not commit secrets, tokens, environment credentials, browser traces containing private data, or
raw private logs. The JSON record does not replace the GitHub workflow/release/deployment audit
trail; it links the exercise to those immutable records.
