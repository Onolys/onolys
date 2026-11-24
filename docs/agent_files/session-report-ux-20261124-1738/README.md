---
status: in-progress
summary: UX done; design for run input locks + MITI manual alignment drafted (PRDs awaiting approval)
date: 2026-11-24
---
# session-report-ux

- [Code run and verification](code-2026-11-24-1738.md)
- [Full branch review — PASS](review-2026-11-24-1739.md)
- [Completed session inputs and MITI runs brainstorm](brainstorm.md)
- [Eval: run input pinning](eval-run-inputs.md)
- [Eval: MITI coding vs manual 4.2.1](eval-miti-coding.md)

## Design: run input locks + MITI manual alignment
| # | Sub-project | Scope | Depends | Status |
|---|---|---|---|---|
| 01 | [Run input locks](01-run-input-locks/PRD.md) | Speaker + goal write-once; inputs copied onto RunDoc in start txn; worker reads RunDoc; transcript sha256 | — | draft |
| 02 | [MITI manual alignment](02-miti-manual-alignment/PRD.md) | Volley break per manual, one persuasion slot/volley, remove globals reset, bounded client context, coverage metric, new fixtures, measurement | — (commits after 01) | draft |

Dependency: `01 ──(commit order only)──▶ 02` ; one PR.

### Locked decisions
- One PR; SP01 commits first, behavior-neutral for engine output.
- No legacy handling: nobody uses the app; old DB entries may be wiped or error on load. New RunDoc input fields required.
- Speaker and change goal are write-once ("once selected is selected"), even after failure.
- Successful report final; only failed runs retry. Auto retry = same run ID; user Retry = new run ID, failed run kept.
- MITI 4.2.1 manual (https://casaa.unm.edu/assets/docs/miti4_21.pdf) is authoritative; globals start at 3, never null; forced evidence reset removed.
- No hard ship gate: baseline-vs-new measurement with check.py + manual audit; claim manual alignment + non-regression, not accuracy.
- Dropped from brainstorm: lineage, requested-vs-actual settings, quote-validation rework, compact anchors, null globals.

### Cross-cutting open questions
- 01 [RESOLVED]: failure is terminal; unconfirmed speaker + failure stays failed.
- 02 [OPEN]: volley `min_other_words: 5` + `?` exception to tune on new fixtures; report schema/UI accepts empty `evidence`; coverage retry thresholds from baseline.
- Live measurement needs GEMINI_API_KEY on the machine.
