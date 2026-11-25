---
status: design
summary: SP01/SP02 done and pushed; eval-compare-redesign PRDs 03–07 approved with owner answers; next dev-tasks.
date: 2026-11-25
---
# session-report-ux

- [Latest implementation, review and verification pointer](review-2026-11-24-2222.md)
- [Eval shell/form evidence](code-2026-11-24-2212-eval-shell-form.md)
- [Product recovery/internal docs evidence](code-2026-11-24-2216.md)
- [Admin retirement/auth preservation evidence](code-2026-11-24-admin-retirement.md)
- [Code run and verification](code-2026-11-24-1738.md)
- [Initial branch review — PASS](review-2026-11-24-1739.md)
- [SP01 implementation](01-run-input-locks/code-2026-11-24-2130.md)
- [SP01 review — PASS](01-run-input-locks/review-2026-11-24-2130.md)
- [SP02 implementation](02-miti-manual-alignment/code-2026-11-24-2203.md)
- [SP02 review — PASS](02-miti-manual-alignment/review-2026-11-24-2203.md)
- [Eval Compare/Summary proposal — design only](eval-compare-summary-proposal.md)
- [Eval compare mockup (Claude doc, invented data)](https://claude.ai/artifact/QY4Ey566Shy8v249vmZHLE)
- [Completed session inputs and MITI runs brainstorm](brainstorm.md)
- [Eval: run input pinning](eval-run-inputs.md)
- [Eval: MITI coding vs manual 4.2.1](eval-miti-coding.md)

## Design: run input locks + MITI manual alignment
| # | Sub-project | Scope | Depends | Status |
|---|---|---|---|---|
| 01 | [Run input locks](01-run-input-locks/PRD.md) · [tasks](01-run-input-locks/TASKS.md) | Speaker + goal write-once; inputs copied onto RunDoc in start txn; worker reads RunDoc; transcript sha256 | — | done — review PASS |
| 02 | [MITI manual alignment](02-miti-manual-alignment/PRD.md) · [tasks](02-miti-manual-alignment/TASKS.md) | Volley break per manual, one persuasion slot/volley, remove globals reset, bounded client context, coverage metric, new fixtures, measurement | — (commits after 01) | done — review PASS |

Dependency: `01 ──(commit order only)──▶ 02`.

### Locked decisions
- SP01 commits first, behavior-neutral for engine output. The original delivery design targeted one PR; the latest user authorization was a branch push, which completed at `549b3b3`. No PR has been opened.
- No legacy handling: nobody uses the app; old DB entries may be wiped or error on load. New RunDoc input fields required.
- Speaker and change goal are write-once ("once selected is selected"), even after failure.
- Successful report final; only failed runs retry. Auto retry = same run ID; user Retry = new run ID, failed run kept.
- MITI 4.2.1 manual (https://casaa.unm.edu/assets/docs/miti4_21.pdf) is authoritative; globals start at 3, never null; forced evidence reset removed.
- No live measurement (no API key): deterministic offline audit + unit tests + manual audit; claim manual alignment + non-regression, not accuracy.
- Dropped from brainstorm: lineage, requested-vs-actual settings, quote-validation rework, compact anchors, null globals.

### Cross-cutting open questions
- 01 [RESOLVED]: failure is terminal; unconfirmed speaker + failure stays failed.
- 02: no open items (threshold tuning and coverage retry are [DEFERRED]).

All requested product/eval code follow-ups and independent review are complete; Compare/Summary remains [design-only](eval-compare-summary-proposal.md) (`eccd65b`); PRDs 03–07 for it now exist (see Design: eval-compare-redesign). The earlier branch push reached `549b3b3`; final integrated verification through `fc08361` passed and the final evidence is prepared for the authorized branch push. No PR or deployment was performed. See the [latest pointer](review-2026-11-24-2222.md) for commits, task-checkpoint evidence and current remote state.

## Design: eval-compare-redesign
Input is the approved [proposal](eval-compare-summary-proposal.md) (latest 3f00fe0); brainstorm skipped (proposal is the decided design).

| # | Sub-project | Scope | Depends | Status |
|---|---|---|---|---|
| 03 | [Eval environment](03-eval-environment/PRD.md) | Third Terraform env `eval` from infra/modules/environment (Firestore DB `eval`, bucket `onolys-audio-eval`, queue, worker, allowlisted eval-backend, EVAL_MODE on); opt-in module vars leave staging/prod plans unchanged; legacy staging eval removed right away (eval unusable until SP05, accepted); all admin infra and Terraform budget removed; auth package/env names renamed to eval names; owner-run read-only SA runbook | — | draft PRD |
| 04 | [Eval run path](04-eval-run-path/PRD.md) | Prod run path gets internal `is_eval` (eval fields on RunDoc, engine+route override, eval-mode guard, caps bypass, public models reject unknown fields); prod unchanged | 03 (config `ENVS` gets `eval` in SP03) | draft PRD |
| 05 | [Eval backend on prod pipeline](05-eval-backend-on-prod-pipeline/PRD.md) | Eval backend rebuilt on prod pipeline: shared prod sessions, each combo×repeat = prod RunDoc (n_runs=1) via server-side tick scheduler (one active run per session, max 2 sessions in flight per AI provider, runs finish with browser closed), `eval_runs` grouping doc, idempotent Cancel (keeps completed, state `partial`), scoped delete, old eval-only run engine deleted; existing eval screens keep working | 03, 04 | draft PRD |
| 06 | [Compare calculations](06-compare-calculations/PRD.md) | Pure offline-tested server-side compare calculations + authenticated read endpoints; partial (cancelled) eval runs compare completed runs only, missing runs reported | 05 | draft PRD |
| 07 | [Compare screens](07-compare-screens/PRD.md) | Four read-only Compare screens (Overview, Deep dive, More analysis, Line view) in eval/web, hand-rolled SVG/CSS, replacing old Compare/Summary tables; adds confirmed Cancel button and "Partial — cancelled" badge on History, run detail and Compare; live status on reopen | 06 | draft PRD |

```
03 ──▶ 04 ──▶ 05 ──▶ 06 ──▶ 07
```
Also `03 ──▶ 05`.

### Locked decisions
- One prompt per run; any number of combos.
- Human is always the reference.
- Compare within one run only (no cross-run / prompt versions).
- Never average global ratings across interviews: compare per interview, then aggregate. Each session counts once.
- Exact values only, otherwise "n/a" + reason. n always shown; colour from n=1.
- One codebase, two deployments: eval units become prod-shaped RunDocs + eval fields, internal `is_eval`; prod API rejects eval fields; eval API allowlisted and refused unless eval mode on.
- New Terraform env `eval`.
- Gold = bucket files by sha256.
- Retention until owner deletes.
- Scheduler serializes runs per session, parallel across sessions.
- Read-only service-account script prepared but run by owner only.
- No push/PR unless owner asks.

### Owner decisions 2026-11-25
- Concurrency: at most 2 interviews in parallel per AI provider (Anthropic, Gemini), config `EVAL_MAX_PER_PROVIDER`=2, plus one active run per session. Replaces `EVAL_MAX_SESSIONS_IN_FLIGHT=20` (SP05).
- Leave the page: eval runs are fully server-driven; close the browser and the run completes; History/run detail show live status on reopen (SP05, SP07).
- Cancel (new): button on History + run detail with confirm dialog (SP07), idempotent endpoint (SP05); stops new runs, stops in-flight best effort, keeps everything completed; eval run becomes `partial` (or `cancelled` if none completed); Compare uses completed runs only and reports missing ones (SP06); badge "Partial — cancelled at <time>, X of Y runs done" (SP07). Any allowlisted user.
- Retries: 2, backoff 5 s / 20 s, transient errors only; runs failed by a `code_version` change are not retried and stay failed.
- Eval runs use `n_runs=1`; repeats are separate runs.
- Endpoint prefix `/v1/eval-runs/{id}/compare/*` behind eval allowlist auth; cold load measured on a staged run, materialise only if > 5 s (default).
- Firestore rules are deployed to the eval DB (SP03).
- Legacy staging eval is removed now (SP03); eval unusable between SP03 and SP05 (accepted).
- Admin removed altogether; eval gets its own login pieces first (auth package and env names renamed, SP03).
- Eval allowlist = existing emails.
- Terraform budget removed; owner sets spend limits in Anthropic Console and Google Cloud console (final owner step after implementation).
- All other previously open items took their stated defaults (heatmap globals `value=null`, no R:Q/%CR tolerance, separate eval-backend image, shared tick queue, `create_run` additive edit, any allowlisted user may delete, allow concurrent eval runs on a session, keep eval STT flow, A..Z combo letters, etc.), recorded `[RESOLVED: owner 2026-11-25 — default]` in each PRD.
- New open items with defaults: worker stage-boundary stop for in-flight cancelled runs (SP05 R7; fallback: in-flight finish and are kept); "X of Y runs done" counters (SP07).

Next: `dev-tasks` for 03–07.
