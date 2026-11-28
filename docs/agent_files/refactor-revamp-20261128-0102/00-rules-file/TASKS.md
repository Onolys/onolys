---
status: draft
summary: 5 docs-only tasks - write coding rules, move design-rules, update AGENTS.md/README/CLAUDE.md, verify with link and grep checks
date: 2026-11-28
---
# Tasks: 00 Rules file (coding rules + design-rules move)
Source of truth: docs/agent_files/refactor-revamp-20261128-0102/00-rules-file/PRD.md. Docs-only: no code, no new CI. Proof = existing CI doc checks (`check_links.py`, `check_docs_scope.sh`) plus grep/git checks named per task. All PRD [RESOLVED] items are binding; none open.

| # | Task | Depends on | Status |
|---|---|---|---|
| 1 | Move design-rules.md into docs/rules/ | - | todo |
| 2 | Write coding-rules.md (rules 1-16) | 1 | todo |
| 3 | Update AGENTS.md and docs/README.md | 1, 2 | todo |
| 4 | Add root CLAUDE.md pointer | 3 | todo |
| 5 | Final verification against acceptance criteria | 1-4 | todo |

## Task 1 — Move design-rules
What it is / what it means: the frontend rules doc sits beside the new coding rules, with history kept (PRD R2, D4).
What changes at a high level: `git mv` docs/design-rules.md to docs/rules/design-rules.md, content verbatim (stale "eval/web" scope line stays; 03 fixes it). Fix the two live references (AGENTS.md, docs/README.md) enough that links do not break; Task 3 finalizes wording. Frozen agent_files mentions stay.
Done when: old path gone; `git log --follow docs/rules/design-rules.md` shows prior history; `git diff -M` shows a pure rename; `grep -rIn design-rules . --exclude-dir=agent_files --exclude-dir=node_modules` returns only new-path hits.

## Task 2 — Write coding-rules.md
What it is / what it means: one citable doc with stable rule numbers 1-16 that later sub-projects cite (PRD R1, R6, D1-D3, D8-D10).
What changes at a high level: new docs/rules/coding-rules.md in the design-rules.md shape (numbered, Do/Don't, short example). Groups: Structure 1-6, Code shape 7-11, Docs and tests 12-14, UI and clean-up 15-16. Short header: scope, enforcement by reviewer reading (Block vs Flag tags, no CI), copied-per-repo note (eval, onolys-common keep hand-synced copies). Bake in owner decisions: rule 2 ~300 lines guidance only; rule 7 class for major concept even with one variant, plain functions otherwise, no over-engineering, one inheritance level max; rule 9 Firestore emulator; rule 10 one constants.py per package, `constants.ts` for TS; rule 4 one pipeline YAML per evaluation; rule 13 stated but not applied during revamp. Python examples, TS equivalents noted; ~120 lines.
Done when: grep confirms headings 1-16 each with Do/Don't; greps find "300", "emulator", "constants.ts", "one level", and the rule-13 not-applied note; `check_links.py` passes.

## Task 3 — Point AGENTS.md and docs/README.md at both
What it is / what it means: agents are told to read coding rules for all code and design rules for UI (PRD R3, R4).
What changes at a high level: AGENTS.md "Frontend work" section becomes "Rules" (all agents: coding-rules; UI work in web/ or any UI: also design-rules); drop ", admin"; add a docs/rules/ row to "Where docs go"; mission paragraph untouched; no banned-list terms. docs/README.md: replace the design-rules row with one row per file under rules/. No other rows change.
Done when: `python3 scripts/ci/check_links.py` and `bash scripts/ci/check_docs_scope.sh` pass; grep shows both rule paths in AGENTS.md and docs/README.md; diff shows only the intended hunks.

## Task 4 — Add CLAUDE.md
What it is / what it means: Claude Code loads CLAUDE.md, not AGENTS.md; a one-line import keeps a single source (PRD R5, D5).
What changes at a high level: new root CLAUDE.md containing exactly `@AGENTS.md`.
Done when: `cat CLAUDE.md` equals the single line; `check_docs_scope.sh` still passes. Owner-only optional check noted below.

## Task 5 — Verify acceptance criteria
What it is / what it means: prove the whole SP meets the PRD Acceptance Criteria before review.
What changes at a high level: nothing; run checks and fix any gaps in Tasks 1-4 only.
Done when: `git diff --stat` against the branch base touches only the Owns list (coding-rules.md, design-rules.md rename, AGENTS.md, docs/README.md, CLAUDE.md), no code/CI files; rules 1-16 all present; design-rules grep and `git log --follow` checks pass; both CI doc scripts pass; CI workflow unchanged.

Owner-only: optionally run `/memory` in a fresh Claude Code session to confirm AGENTS.md loads through CLAUDE.md (PRD Manual steps).
