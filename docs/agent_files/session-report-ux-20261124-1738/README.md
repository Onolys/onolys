---
status: in-progress
summary: Implementation and review complete; branch pushed at 549b3b3; final integrated verification in progress.
date: 2026-11-24
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

All requested product/eval code follow-ups and independent review are complete; Compare/Summary remains [design-only](eval-compare-summary-proposal.md) (`eccd65b`). The branch was pushed to origin at `549b3b3`; no PR or deployment was performed. Final integrated verification is in progress. See the [latest pointer](review-2026-11-24-2222.md) for commits, task-checkpoint evidence and current remote state.
