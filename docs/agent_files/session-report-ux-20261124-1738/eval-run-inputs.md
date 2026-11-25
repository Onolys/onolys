---
status: done
summary: Do smaller — pin goal/speaker/language/span/transcript-hash on RunDoc at start_run, worker reads only RunDoc; drop lineage, requested-vs-actual, provenance extras; keep speaker-fix-after-failure.
date: 2026-11-24
---

# Eval: run input receipt

## Verdict

**Do smaller.** The full receipt is mostly protecting against changes the API already blocks. Two real gaps exist (goal race, worker reads live session). Fix them with a copy-at-start snapshot on `RunDoc` plus a transcript hash. Roughly 1 commit, ~150 LOC plus tests. Do NOT build lineage, requested-vs-actual, engine-provenance matrix.

One brainstorm statement is wrong and must change: "retry uses same pinned inputs". Today `POST /speakers/confirm` is deliberately allowed in `failed` ("applies to the next run only") — pinning retry to the old speaker would remove an existing, sensible feature (fix the wrong speaker, retry).

## What problem it really solves (evidence)

Write paths and when they are allowed:

| Input | Writer | Allowed states | Can change after run start? |
|---|---|---|---|
| transcript | `routes/transcript.py:77` via `transition_plan(only_from=("created",))`; `jobs/transcribe.py:267` put_transcript | `created`, or transcribe step (failed→transcribing) | **No.** Both occur before any run exists; transcribe retry needs `step=="transcribe"`, runs only start after `transcript_ready`. Overwrite at `firestore.py:652` is unreachable once a run exists. |
| language | session create (`sessions.py:317`), transcript PUT (`transcript.py:78`) | pre-run | **No** after run start. |
| stt | `transcribe.py:~259` (`stt.run`), reset `stt: None` at PUT | pre-run | **No.** |
| clinician_speaker | `speakers.py:124` -> `firestore.py:398` txn, `CONFIRM_STATES=("awaiting_input","failed")` (`speakers.py:27`) | awaiting_input, failed | **Not mid-run** (state-gated in txn). **Yes between failed run and retry — by design.** |
| change_goal | `routes/rating.py:143` final submit, `extra_fields={"change_goal":...}` | every state except deleting/cancelled; one-shot (`rating_submitted`, `_not_final` guard) and blocked after a report | **Yes, narrow race.** `start_run` (`firestore.py:1173-1179`) does not require `rating_submitted`, so `POST /runs` can start with goal unset; a final rating submitted while running (or while failed) changes the goal the worker reads at `jobs/run.py:155`. One-shot, so it can change at most once. |

Other evidence:
- Worker reads session live: `jobs/run.py:148-164` (goal, speaker, `stt_run`, language = transcript.language or session.language).
- `RunDoc.stt/rating_id/code_version` exist (`models.py:298-322`) but worker ignores stt; `code_version` is used.
- Missing transcript is `PermanentError("internal_error")` (`run.py:150-153`); with an immutable transcript this is unreachable except deletion races.
- Hash: no hash on TranscriptDoc (`models.py:265-268`); transcript is effectively write-once after run start, so a hash guards only against future edit features, not today's bugs.

Honest answer: today only the **goal** can drift (late final-rating during run/failed). Speaker drift mid-run is impossible; between failed->retry it is a feature. Transcript/language/STT drift: basically never. Value is mainly (a) closing the goal race, (b) making the report self-describing for traceability/UI, (c) future-proofing for transcript editing.

## Recommended design (minimal)

1. **Snapshot at start.** In `start_run` and `start_first_run` txns (`firestore.py` ~1155-1230, mirror in `repo/fake.py` ~871), the session doc is already read; copy into the new RunDoc: `change_goal`, `clinician_speaker`, `language` (effective), `stt` (session.stt.run), `transcript_sha256`. Add the fields to `RunDoc` (`models.py:298`); `rating_id` can stay optional/unset unless the UI wants it.
2. **Worker reads RunDoc only** (`jobs/run.py:148-164`): goal/speaker/language/stt from `run_doc`. Automatic worker retry then reuses the same run doc, so it is pinned for free; no extra mechanism.
3. **Transcript hash.** Compute sha256 once at `routes/transcript.py` PUT and `jobs/transcribe.py:267` over canonical JSON (data already in memory; no extra reads), store on `TranscriptDoc.sha256`. start_run copies it. Worker, which already loads the transcript, recomputes only if cheap (or compares stored `TranscriptDoc.sha256` to run's) — mismatch -> `PermanentError("internal_error")` before any model call. Skip recompute if it costs a second full read; compare stored values.
4. **Manual retry** (`runs.py:172-178`): keep copying preset/n_runs/span from prior run. Take goal/speaker from the *current session* (so speaker-fix-after-failure keeps working) via the normal start_run snapshot. Transcript hash must equal prior's (guaranteed today; assert as a guard).
5. **Goal race alternative (even smaller):** instead of/in addition to snapshot, make `start_run` require `rating_submitted` (goal final) — but that changes product (run without rating allowed today). Snapshot is safer; also have `put_rating` accept the late goal without affecting the running run (it will, since worker reads RunDoc).

## Drop from brainstorm

- Requested-vs-actual settings capture (no divergence source today; preset resolve is deterministic).
- Engine provenance beyond existing `code_version`.
- Previous-run reference / lineage (brainstorm itself says only if a consumer needs it).
- "Pinned run never falls back" machinery and structured-failure-reason taxonomy: one `internal_error` check suffices.
- Rating-revision pinning (contextual only; leave).
- Compatibility handling for legacy runs: owner said break fine. Old runs without snapshot fields: worker may just fail them; no unknown-provenance UI.
- Claim "retry keeps pinned inputs incl. speaker" — drop for speaker.

## Edge cases

| Case | Behavior |
|---|---|
| Quota/retry cap | Unchanged: manual retry still reserves a unit and increments `retry_count` in `start_run` txn (`retry_allowed`). Snapshot adds no counters. |
| Earlier-step retry (`/retry` for transcribe/validate, `sessions.py:474-504`) | Only reachable with no run (failure pre-transcript). If a run failed, step is `run`. No invalidation case today; if re-transcription is ever allowed post-run, the new hash simply differs and a manual retry creates a run with the new transcript (retry must then not claim same inputs). Guard: assert in retry that hash unchanged else treat as fresh start. |
| Speaker fixed after failure | New run snapshots new speaker; old failed run keeps old value in history (good, shows why it failed). |
| Goal submitted late | Running run unaffected (RunDoc); failed->retry picks up the goal as newly final. Accept. |
| Cancel | Run doc keeps snapshot; no effect. |
| Delete | RunDoc is a session child; deletion path already removes children — verify no new top-level collections added (none proposed). |
| Success final | `has_final_report` blocks retry; unchanged. |
| Seed = sid | Same inputs != same output; do not promise reproducibility in UI/copy. |
| Worker redelivery | Same run doc, same snapshot; publish_report txn (`run.py:~245`) already idempotent. |

## Tests

1. start_run copies goal/speaker/language/stt/hash onto RunDoc (firestore + fake repo parity).
2. Worker uses RunDoc: mutate session goal after start (final rating while running) -> report/adapter params use original goal.
3. Worker redelivery keeps same snapshot.
4. Manual retry: goal late-submitted while failed -> new run has new goal; failed run keeps old.
5. Speaker confirm in `failed` -> retry run snapshots new speaker; confirm while `running` -> 409.
6. Transcript hash set on PUT and on STT path; stable for same content; hash mismatch run-vs-stored -> `internal_error`, no adapter call.
7. Legacy run without snapshot fields -> fails cleanly (or documented), no crash.
8. Retry cap/quota unchanged (existing tests stay green); cancel/delete during run with snapshot.

## Open questions for owner

| Question | Recommended default |
|---|---|
| Should retry after failure use the session's current goal/speaker (allowing fixes) or the failed run's? | Current session values for speaker and goal; pin only transcript hash, span, preset, n_runs. |
| Require rating_submitted (final goal) before a run can start? | No; keep snapshot approach, less product change. |
| Store `rating_id` on RunDoc? | Skip unless UI shows it. |
| Surface the receipt in API/UI? | Backend-only now; expose later if a consumer exists. |
| Hash over canonical JSON vs blob bytes? | Canonical transcript JSON at write time, one place. |
