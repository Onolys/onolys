---
status: in-progress
summary: SP01 and SP02 implementation and reviews PASS; queued product/eval follow-ups remain.
date: 2026-11-24
---
# session-report-ux

- [Code run and verification](code-2026-11-24-1738.md)
- [Full branch review — PASS](review-2026-11-24-1739.md)
- [SP01 implementation](01-run-input-locks/code-2026-11-24-2130.md)
- [SP01 review — PASS](01-run-input-locks/review-2026-11-24-2130.md)
- [SP02 implementation](02-miti-manual-alignment/code-2026-11-24-2203.md)
- [SP02 review — PASS](02-miti-manual-alignment/review-2026-11-24-2203.md)
- [Eval Compare/Summary proposal — design only](eval-compare-summary-proposal.md)
- [Completed session inputs and MITI runs brainstorm](brainstorm.md)
- [Eval: run input pinning](eval-run-inputs.md)
- [Eval: MITI coding vs manual 4.2.1](eval-miti-coding.md)

## Design: run input locks + MITI manual alignment
| # | Sub-project | Scope | Depends | Status |
|---|---|---|---|---|
| 01 | [Run input locks](01-run-input-locks/PRD.md) · [tasks](01-run-input-locks/TASKS.md) | Speaker + goal write-once; inputs copied onto RunDoc in start txn; worker reads RunDoc; transcript sha256 | — | done — review PASS |
| 02 | [MITI manual alignment](02-miti-manual-alignment/PRD.md) · [tasks](02-miti-manual-alignment/TASKS.md) | Volley break per manual, one persuasion slot/volley, remove globals reset, bounded client context, coverage metric, new fixtures, measurement | — (commits after 01) | done — review PASS |

Dependency: `01 ──(commit order only)──▶ 02` ; one PR.

### Locked decisions
- One PR; SP01 commits first, behavior-neutral for engine output.
- No legacy handling: nobody uses the app; old DB entries may be wiped or error on load. New RunDoc input fields required.
- Speaker and change goal are write-once ("once selected is selected"), even after failure.
- Successful report final; only failed runs retry. Auto retry = same run ID; user Retry = new run ID, failed run kept.
- MITI 4.2.1 manual (https://casaa.unm.edu/assets/docs/miti4_21.pdf) is authoritative; globals start at 3, never null; forced evidence reset removed.
- No live measurement (no API key): deterministic offline audit + unit tests + manual audit; claim manual alignment + non-regression, not accuracy.
- Dropped from brainstorm: lineage, requested-vs-actual settings, quote-validation rework, compact anchors, null globals.

### Cross-cutting open questions
- 01 [RESOLVED]: failure is terminal; unconfirmed speaker + failure stays failed.
- 02: no open items (threshold tuning and coverage retry are [DEFERRED]).

Next: queued product/eval follow-ups recorded in the local handoff; Compare/Summary remains design-only (`eccd65b`). Full whole-branch review and shipping checks remain after those changes. SP02 final verification: 587 offline MITI tests passed, 3 live tests excluded; Ruff passed; golden regeneration unchanged.
