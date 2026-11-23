---
status: draft
summary: Processing screen shows a 6-step list with a clear spinner/"In progress" current step, one progress bar + % + Elapsed from upload start (server owns base %, web interpolates within long stages, freezes while waiting for the user), and a per-phase "can I leave?" hint.
date: 2026-11-23
---
# PRD: SP05 Processing screen clarity

Repo/branch: Onolys/onolys (local `iaudit`) / `feat/session-ux-logging-claude-email` · Depends on: SP04 (file order only: 03 → 04 → 05 all edit `SessionPage.tsx`; SP05 lands last), SP03 (failed card), SP01 (rating timings for calibration) · Owns: `web/src/features/session/{timeline.ts, progress.ts (new), useSessionStatus.ts, SessionPage.tsx (steps/progress/hint region only), timeline.test.ts, progress.test.ts (new), SessionPage.test.tsx}`, `web/src/features/upload/UploadSlot.tsx` (report byte fraction only), `web/src/mocks/**` (progress fields), `web/src/api/schema.d.ts` (regen), `api/src/onolys_api/{jobs/machine.py, jobs/validate.py, jobs/run.py, repo/models.py, routes/sessions.py}` (status-doc fields only), `docs/reference/` status-doc note · Shared regen: `api/openapi.json`, `docs/contracts/public` (new `SessionDetail` fields; SP03, SP04, SP07 also regenerate; last merged wins)

## TL;DR
Today the current step is only bold + a left border, and Elapsed, the bar and "you can close this tab" show only in `running` [verified: SessionPage.tsx:140-179, timeline.ts:175 `showRunCopy: state === "running"`]. This SP gives the current step a spinner + "In progress" + accent colour, shows one bar/%/Elapsed from upload start, and swaps a phase hint (keep tab open / can close / we'll wait). The server already owns a base `progress`; it also needs to expose start time, audio length and the current stage's expected duration so the web can interpolate honestly.

## Problem
- 7 rows incl. "Check audio" and, with the rating flag off, "Session setup" [verified: timeline.ts LABELS, `label: ... "Session setup"`].
- Progress is silent until `running`, and jumps in 3 hops (20 → 40, then 45/85/93/…) [verified: machine.py STATE_PROGRESS, STAGE_WEIGHTS = 40/8/3].
- Elapsed starts at the first status doc seen in `running` (`runStartedAt` = `updated_at`), so a reload resets it [verified: useSessionStatus.ts `runStartedAt`].
- Fallback poll sets `updated_at: new Date()` in `detailToDoc` [verified: useSessionStatus.ts:30], so any timestamp-based UI is wrong there.
- Web cannot know audio length or upload start: `session_status` allowlist is `uid,state,step,progress,error_code,latest_report_version,updated_at` + 4 flags [verified: machine.py STATUS_FIELDS]; `duration_ms` is on the recording doc, `stage_started_at`/`created_at` on the session doc only [verified: models.py:118-143].

## Goals / Non-Goals
**Goals:** steps per brainstorm A; unmistakable current step; continuous honest % and Elapsed from upload start; correct leave/stay hint per phase; reduced-motion + screen-reader safe; light/dark via tokens.
**Non-goals:** streaming transcription (dropped); cancel behaviour (SP04); failure copy/retry (SP03); changing stage order; ETA text ("2 min left").

## Requirements
**R1 Steps** (`timeline.ts`). Visible keys: `upload, transcribe, speaker, rating (only if ratingEnabled()), run, report`. `validate` and the "Session setup" row are removed.

| State | Upload | Transcribe | Notes |
|---|---|---|---|
| created / uploading / upload_incomplete | current | pending | |
| validating | done | current, sub-label "Checking audio" | folded |
| transcribing | done | current | |
| awaiting_input+ | done | done | speaker/rating current per flags (unchanged logic) |
| failed, bad-file codes (`VALIDATE_CODES`) | failed | pending | "upload a different file" fits Upload |
| failed, `TRANSCRIBE_CODES` / other pre-transcript | done | failed | |
| failed after transcript | done | done | `run` failed |
| cancelled / deleting | all pending, no progress | | SP04 shows its own message |

Rating-off: no rating row; awaiting-input line reads "Waiting for your change goal" (goal-only fallback form still shows [verified: slots.tsx `SetupFallback`]). `run` sub-labels unchanged (`code/tips/assemble`).
**R2 Progress contract.** Add to `session_status` (and `SessionDetail`, for the fallback poll), all PHI-free numbers/timestamps:

| Field | Meaning | Written by |
|---|---|---|
| `started_at` | first entry to `uploading` (re-run: run start) | `advance` on `to="uploading"` / re-run |
| `stage_started_at` | entered the current state (already on session doc) | `advance` (mirror) |
| `waited_ms` | total ms spent in `awaiting_input` | `advance` leaving that state |
| `audio_s` | recording duration | `validate` (from `duration_ms`) |
| `progress_next` | base % of the next stage (cap 99 on last stage) | `advance` / `progress_cb` |
| `stage_expected_s` | typical duration of the current stage | server (stage table + f(audio_s)) |

Base `progress` stays server-owned (`STATE_PROGRESS`, `STAGE_WEIGHTS`); values unchanged until calibrated (R6). `detailToDoc` uses the real `updated_at`.
**R3 Interpolation** (`progress.ts`, pure): `deriveProgress(doc, now, uploadFraction?) → {pct, elapsedMs, frozen, hidden}`.
- Upload: `pct = base + (next−base) × uploadFraction` from the uploader's byte counter; after a reload (no counter) just base.
- Timed stage (`validating`, `transcribing`, each `run` stage): `x = 1 − exp(−t / stage_expected_s)`, `t = now − stage_started_at`; `pct = floor(base + (progress_next − 1 − base) × x)`. Asymptotic: never reaches the next base, never stalls visibly.
- Frozen: `awaiting_input` → `pct = progress` (40), no interpolation; `report_ready` = 100. `failed`/`cancelled`: the bar, % and Elapsed are hidden (R4, AC3; resolved owner-default 2026-11-23), `deriveProgress` returns `hidden: true` instead of a frozen value. Elapsed = `now − started_at − waited_ms` (− current wait while `awaiting_input`, so it freezes too).
- Invariants: integer; `pct ≤ 99` unless `report_ready`; never below server `progress`; the hook keeps the max shown within one state so a late doc cannot move the bar back (a re-run restarts at 45, as today).
**R4 Visual** (`SessionPage.tsx`). Step row: `done` = check + `text-score-good`; `current` = spinner + visible text "In progress" + `text-primary`/`border-primary`; `pending` = `text-muted-foreground`; `failed` = `text-destructive`. Bar, "N%" and Elapsed render in every non-terminal state from `created`, above the step list; one "Cancel" slot (R7). Spinner and bar: `Spinner` and `Progress` components from `@onolys/ui`. v0.2.0 exports neither [verified 2026-11-23: local clone `/root/projects/onolys/onolys-ui`, `git show v0.2.0:src/index.ts` has no Spinner/Progress, no such file under `src/components`], so this SP depends on a cross-repo change (see Cross-repo dependency); no inline SVG fallback. `Spinner` uses `motion-safe:animate-spin`; `Progress` renders a native `<progress>` (R8).
**R5 Hint** (one line under the bar, in the live region's sibling, not the live region):

| Phase | States | Copy |
|---|---|---|
| upload | created, uploading, upload_incomplete | Keep this tab open until upload finishes |
| background | validating, transcribing, running | You can close this tab — we'll keep working |
| waiting | awaiting_input (incl. held Start) | We'll wait here for your choice |
| none | report_ready, failed, cancelled, deleting | — |

"Usually under 5 minutes" is dropped (unverified claim with a Claude run now in play). The "Your rating" step and any rating-related waiting copy apply only when `ratingEnabled()`; the default flow (flag off) has no rating step and no rating input during processing, so the background hint holds from upload-complete (speaker pick excepted).
**R9 Docs.** SP05 updates project docs: `docs/concepts/user-rating.md` (created 2026-11-23; states self-rating is not offered today, flag off; dormant card behaviour) is kept consistent with the hint copy; the `docs/reference/` status-doc note covers the new progress fields (R2).
**R6 Calibration.** `stage_expected_s` and the `STATE_PROGRESS` weights are placeholders until real timings exist: transcription expected = `clamp(20 + 0.2 × audio_s, 30, 600)`; rating stages from `miti.done` stage durations on staging after SP01/SP02 land. Constants live in one server table.
**R7 Cancel slot.** SP05 reserves `<div data-slot="cancel">` directly under the hint, right-aligned, rendered iff SP04's `isCancellable(state)` (the seven in-progress states) is true. SP04 owns the link, dialog, "Cancelling…" and `cancelled` message; SP05 only requires that "Cancelling…" replaces the slot's content, not the step list.
**R8 A11y.** Status lines stay in the existing `role="status" aria-live="polite"` block and change only on state/step change (not per tick). The bar is a native `<progress>` with `aria-label="Overall progress"` and `aria-valuetext`, outside any live region; Elapsed also outside it. Spinner `aria-hidden`; meaning always also in text ("In progress"), never colour alone. Reduced motion: no spin (static ring), no bar transition. 1 s tick runs only while a timed state is active [verified: existing `useNow(active)`].

## Cross-repo dependency (owner 2026-11-23)
Add `Spinner` and `Progress` to the UI library repo `github.com/Onolys/onolys-ui` (local clone `/root/projects/onolys/onolys-ui`, components in `src/components/ui/`, exports in `src/index.ts`; follow its tests, stories and CHANGELOG conventions), release a new tag (v0.3.0 or next, per that repo's release process), then bump `web/package.json` `"@onolys/ui": "git+https://github.com/Onolys/onolys-ui.git#v0.2.0"` to the new tag and refresh `web/package-lock.json`. This is a separate repo/PR and gates the web tasks of this SP. No inline SVG fallback.

## Architecture
```
advance()/validate/progress_cb ─► session_status {progress, progress_next, stage_expected_s,
                                   stage_started_at, started_at, waited_ms, audio_s}
useSessionStatus (live | fallback via SessionDetail) ─► doc
timeline.ts: deriveTimeline(doc, {ratingEnabled}) → steps, lines, hint
progress.ts: deriveProgress(doc, now, uploadFraction) → pct, elapsedMs, frozen
SessionPage: Steps · Bar+%+Elapsed · Hint · [cancel slot] · gates/cards
```
Shared files: `SessionPage.tsx`, `timeline.ts` (SP03 failure copy, SP04 `cancelled` + slot), `machine.py` + `repo/models.py` + `routes/sessions.py` (SP04 `cancelled` state), `chips.ts` is SP04's (`cancelled` chip only; SP05 leaves it).

## Decisions
| # | Decision | Choice | Alternatives | Why |
|---|---|---|---|---|
| D1 | Where timing logic lives | Server sends `progress_next` + `stage_expected_s`; web only interpolates | Mirror tables in web | One tunable place, no drift |
| D2 | Curve | `1 − exp(−t/expected)` capped below next base | Linear then stall | Never overshoots, never freezes if slow |
| D3 | Elapsed | Pauses while waiting for the user | Wall clock | User think time is not our processing time; avoids "10:00 elapsed" at the speaker pick |
| D4 | Upload % | Real byte fraction | Time-based | Bytes are known [verified: uploader.ts `loaded/total`] |
| D5 | Bad-file failure at validate | Upload row failed | Transcribe row failed | Matches the "upload a different file" action |
| D6 | Weights | Keep current table now, calibrate later | Re-weight now | No timing evidence yet |
| D7 | "Under 5 minutes" copy | Removed | Keep | Not verifiable |

## Manual steps
None. Staging deploy of api + web via normal workflow.

## Risks / Open Questions
- Elapsed/% after a re-run (Try again): restarts at 45 with `started_at` reset to run start; total flow time is lost. [DEFERRED]
- Typical Chirp 3 batch time vs `audio_s`, and rating stage times on Claude low: unknown; no successful run since 2026-11-16 [verified: brainstorm]. Constants are guesses. [RESOLVED: default — placeholders now, calibrate from staging logs after SP01+SP02]
- Does `@onolys/ui` v0.2.0 export a Spinner/Progress? [RESOLVED: no (verified in the local clone, tag v0.2.0); owner 2026-11-23: add both to onolys-ui, release a new tag, bump the web dependency, no inline SVG fallback; see Cross-repo dependency]
- Exposing `audio_s` on a client-readable doc: duration only, no text; confirm against the AC11 "no text" test. [RESOLVED: numbers only, allowlist + test extended]
- Rating typed during `transcribing` shows "can close this tab": is the draft saved server-side? [RESOLVED: moot — clinician rating UI is off in all builds (VITE_RATING_ENABLED default false); no rating input during processing, so "You can close this tab — we'll keep working" applies from upload-complete through report (except speaker pick) (owner 2026-11-23)] Verified: `web/.env.example:30`, `config.ts` `ratingEnabled()`, `NewSessionPage` `showGoal = !ratingEnabled()`. If the flag is turned on later, `RatingCard` autosaves a server-side draft (PUT final:false), so the hint still holds.
- Mock backend emits `[85, 93, 100]` vs server 96 cap [verified: stateMachine.test.ts:87]; align mock with the real table. [RESOLVED: in scope]

## Acceptance Criteria
1. Steps shown match R1 for every state × `ratingEnabled` (unit table); no "Check audio"/"Session setup" rows.
2. The current step shows a spinner, text "In progress" and accent class; done = check, pending = muted; verified in light and dark visual shots.
3. Bar + N% + Elapsed present from `created` to `running`, absent (hidden, not frozen) at `report_ready`/`failed`/`cancelled`.
4. `deriveProgress`: monotonic in `t`; `< progress_next` while in a stage; ≤ 99 before `report_ready`; frozen in `awaiting_input` (pct and Elapsed unchanged over 10 min); unknown `audio_s` falls back to the default expected duration.
5. Reload mid-transcription keeps Elapsed (from `started_at`) and does not drop the bar; fallback-poll doc behaves the same.
6. Hint copy matches R5 per state; the old "Usually under 5 minutes" is gone.
7. With `prefers-reduced-motion: reduce` nothing animates; `aria-live` text changes only on step change; bar has accessible name/value.
8. Cancel slot present for all SP04 cancellable states with no layout shift when it swaps to "Cancelling…".
9. API: `session_status` carries the new fields; allowlist/no-text test passes; `advance` unit tests cover `started_at`, `waited_ms`, `progress_next` per state/stage; `openapi.json`, `docs/contracts/public`, `schema.d.ts` regenerated and consistent.
10. Cross-repo: `@onolys/ui` new tag exports `Spinner` and `Progress`; `web/package.json` points at it; `SessionPage` imports both from the package; no inline spinner SVG in the web code.
11. Tests updated: `timeline.test.ts` (rows), new `progress.test.ts`, `SessionPage.test.tsx` (hint per phase, Elapsed in upload/transcribing, spinner text), `stateMachine.test.ts`, one visual e2e shot per phase (`web/e2e_review/visual.spec.cjs`).
12. Docs: `docs/concepts/user-rating.md` exists, is linked from `docs/concepts/README.md`, and states self-rating is not offered today (flag off, code dormant), matching the R5 background hint; the rating step appears only when `ratingEnabled()`.
