---
status: draft
summary: Turn brainstorm Rules 1-16 into docs/rules/coding-rules.md, move design-rules.md beside it, point AGENTS.md (and a one-line CLAUDE.md) at both; enforced by reviewer reading, no new CI.
date: 2026-11-28
---
# PRD: 00 Rules file (coding rules + design-rules move)

Repo/branch: Onolys/onolys / `refactor/revamp` · Depends on: none (Phase 0) · Owns: `docs/rules/coding-rules.md` (new), `docs/rules/design-rules.md` (moved from `docs/design-rules.md`), `AGENTS.md`, `docs/README.md` (rows only), `CLAUDE.md` (new, one line). Does not own: any code, `scripts/ci/*` (01), eval scope text in design-rules (03).

## TL;DR
Write the 16 agreed rules as a short, enforceable doc every later sub-project and every future change follows. `git mv` design-rules.md into the same folder and fix the 2 live references. AGENTS.md points all agents at coding rules, frontend agents also at design rules. Add root `CLAUDE.md` = `@AGENTS.md` so Claude Code actually loads it. Rules are enforced by reviewers reading them; no new CI guard. Everything is docs-only; docs/ is otherwise frozen in the revamp.

## Problem
| Gap | Evidence |
|---|---|
| Rules live only in a brainstorm snapshot; later PRDs/agents would each re-interpret them | [verified: `brainstorm.md` Rules 1-16; no `docs/rules/`] |
| Only a frontend rules doc exists, at `docs/design-rules.md` (29 lines, 6 rules) | [verified: `docs/design-rules.md`] |
| Agents are told about design rules only; nothing mentions code structure | [verified: `AGENTS.md:26-28`] |
| No `CLAUDE.md`; Claude Code reads that name, not `AGENTS.md` | [verified: `ls CLAUDE.md` -> absent; loader behaviour from Claude Code docs, ~90% confident, not re-run here] |

## Goals / Non-Goals
**Goals:** one citable rules doc (stable numbers 1-16); design rules moved with history and references fixed; agents reliably pointed at both; owner decisions on rules 2, 7, 10 recorded in the doc.
**Non-Goals:** applying the rules to code (01, 04-09 do); rewriting design rules' content; ADR fold-in / `architecture.md` (rule 13 is stated but applies after the docs freeze); new lint/CI checks; docs changes beyond the files above.

## Requirements
**R1 coding-rules.md.** Same shape as design-rules.md: numbered rules, each with **Do / Don't** and a short example where useful; grouped Structure (1-6), Code shape (7-11), Docs and tests (12-14), UI and clean-up (15-16). Numbers are fixed so PRDs cite "rule 9". Language-neutral wording; examples in Python, with the TS equivalent noted where it differs (`constants.ts`, `web/tests/`). Rule contract (wording locked by brainstorm; examples are this PRD's):

| # | Rule | Example in doc | Reviewer |
|---|---|---|---|
| 1 | Organize by feature, not layer | `audio/{validate,ffmpeg,transcode}.py`, not `services/`+`models/`+`utils/` | Block |
| 2 | Fewer files: one per feature; split past ~300 lines (guidance only, not a CI gate) | `audio/validate.py` stays one file until it passes ~300 lines | Flag |
| 3 | Libraries + YAML; runner loops the list, no `if/elif` on kinds | `- use: rules.max_per_volley {with: {n: 1}}` resolved by `@step` name | Block |
| 4 | One folder per evaluation type; one pipeline YAML per evaluation (no base+overrides) | `evaluations/miti/{pipeline.yaml,prompts/,fewshot/}`; shared protocols in `protocols/` | Block |
| 5 | Package boundary: engine = `Engine.run` + one public types module; product features (STT, voice, rating, scenarios) live in the product | `from onolys_engine import Engine, EngineError`, never `...steps.prepare` | Block |
| 6 | Dev tools in `tools/`, not shipped | `engine/tools/` | Flag |
| 7 | Use a class for a major concept even if only one variant exists today (future variants likely); plain or static functions otherwise; apply judgment and the code principles, don't over-engineer; max one level of inheritance | converter base + 1 small class per dataset | Flag |
| 8 | Generic base fn + thin named wrappers; wrappers only fill parameters | `get_doc(path, Model, uid)` -> `get_session(uid, sid)` | Flag |
| 9 | One implementation per piece of logic; tests/dev inject a stub client at the lowest layer. **Firestore stub = the emulator** (not in-memory); no parallel fake classes | LLM fixture client, local-folder blob client, in-process queue, email recorder; no `repo/fake.py` | Block |
| 10 | Constants: one `constants.py` per package (engine, api; eval in its own repo); per-environment values in env YAML/env vars; no literals elsewhere | collection names, storage paths, limits, model ids, state names | Block |
| 11 | One source per instruction; shared prompt/rule text generated, not copied | MITI definitions in `protocols/miti-4.2.1/definitions/*.md` rendered into every evaluation's prompt | Block |
| 12 | Plain-words docstrings: what, and why if not obvious; no spec/planning ids | no `PRD R6`, `SP09`, `FX46` | Flag |
| 13 | One `architecture.md`, kept current, instead of ADRs. **Not applied in the revamp (docs frozen); doc states this** | n/a | Defer |
| 14 | Tests mirror source; behaviour-named files; shared helpers in `tests/helpers/` | `src/x/audio/validate.py` -> `tests/audio/test_validate.py`; `web/src/features/x` -> `web/tests/features/x` | Flag |
| 15 | `@onolys/common` is the design system: themes, tokens, every reusable component and common shell piece, generic UI helpers; products keep only product-specific parts | header, footer, account menu, theme toggle, sign-in, `format` live in the package | Block |
| 16 | No legacy/compat code before launch; git history is the archive | old setups, shims, migration/guard tests, legacy CSS layers deleted, not kept | Block |

"Reviewer" = how a reviewer treats a violation (see D6). Rules 2, 7, 10 carry the owner decisions (Risks).

**R2 Move.** `git mv docs/design-rules.md docs/rules/design-rules.md` (content verbatim, history preserved). Update every live reference [verified: `grep -rIn design-rules . --exclude-dir=agent_files` -> exactly 2: `AGENTS.md:28`, `docs/README.md:6`]. `docs/agent_files/*` mentions stay (frozen history; check_links excludes them [verified: `scripts/ci/check_links.py:md_files`]).

**R3 AGENTS.md.** Replace the "Frontend work" section with "Rules": all agents read `docs/rules/coding-rules.md` before changing code; agents touching UI (`web/`, any UI) also read `docs/rules/design-rules.md`. Add a `docs/rules/` row to the "Where docs go" table. Drop ", admin" from the old sentence (admin frontend deleted in PR #85 [verified: no `frontend/` in tree]). Mission paragraph untouched. No terms from the docs-scope guard's banned list (`eaudit|paudit|caudit|Interview Evidence`) [verified: `check_docs_scope.sh:9` greps AGENTS.md].

**R4 docs/README.md.** Replace the design-rules row with one row per file under `rules/` (links `rules/coding-rules.md`, `rules/design-rules.md`). No other row changes. The links must resolve or CI fails [verified: `ci.yml:60,62` run `check_links.py` and `check_docs_scope.sh`, which both resolve README links].

**R5 CLAUDE.md.** Root `CLAUDE.md` containing only `@AGENTS.md` (see D5).

**R6 Enforcement.** Documented in the rules doc header (3 lines): the reviewer (dev-review architecture persona, human reviewers) reads these rules against the diff; later PRDs cite rule numbers in Requirements; `dev-code` task specs say "follow `docs/rules/coding-rules.md`". No lint or CI added; optional greps (spec ids in docstrings, `fake.py` files, literal collection names) are [DEFERRED] since the revamp is pruning `scripts/ci/`.

## Architecture
```
CLAUDE.md  (@AGENTS.md)  ->  AGENTS.md  --all code-->  docs/rules/coding-rules.md  (16 rules)
                                         --UI code-->   docs/rules/design-rules.md  (moved, unchanged)
docs/README.md rows -> both files            later PRDs/TASKS cite "rule N"; reviewer checks diff against them
```
coding-rules.md layout: 3-line header (scope, enforcement, copied-per-repo note) -> four groups -> rules in the Do/Don't form. Estimated ~120 lines, no code beyond 2-3 snippets (YAML runner, base+wrapper).

## Decisions
| # | Decision | Choice | Alternatives considered | Why |
|---|---|---|---|---|
| 1 | Rule numbering | Keep brainstorm 1-16 verbatim | Regroup/renumber | Brainstorm, PRDs 01-09 already cite these numbers |
| 2 | Format | Do/Don't + short example, as design-rules.md | Prose essay | Matches existing doc; checkable by a reviewer |
| 3 | Two docs | coding-rules and design-rules separate, same folder | One merged file | Locked; agents load only what applies |
| 4 | Move mechanics | `git mv`, content unchanged | Copy + redirect stub | Rule 16 (no legacy); history kept. The "eval/web" scope line in it is stale after the eval split; 03 edits it then |
| 5 | CLAUDE.md | Add, content exactly `@AGENTS.md` | Do nothing; duplicate AGENTS.md text; symlink | Claude Code loads CLAUDE.md, not AGENTS.md; import keeps one source (rule 11); other agent tools still read AGENTS.md; symlink breaks on some checkouts |
| 6 | Enforcement | Reviewer reads rules; rules tagged Block (structural) vs Flag (style/convention) | CI lint guards | Revamp prunes `scripts/ci/`. Note dev-review's feedback bar bans style/naming findings [verified: `dev-common.md` "Feedback bar"], so Flag rules (2, 6-8, 12, 14) only surface if the reviewer is pointed at this doc; PRDs/TASKS must cite them |
| 7 | docs/rules/README.md | None; docs/README.md rows are the index | Add index README | Owner: no docs changes beyond the rules files; `check_docs_scope` does not require one [verified: globs only existing `docs/*/README.md`] |
| 8 | Owner-decided items | Rule 2 guidance only (~300, no CI gate); rule 7 per owner wording; TS `constants.ts` adopted | Hard gate; base only after two variants | Owner decision 2026-11-28 |
| 9 | Non-Python | Rules apply to web/TS too; constants -> `constants.ts`, tests -> `web/tests/` mirroring `src/` | Python-only | Brainstorm says "all code"; 07 already agreed `web/tests/` |
| 10 | Rules per repo | Rules files are COPIED into each repo (this repo `docs/rules/`; eval repo and onolys-common keep own copies, synced by hand); no cross-repo pull | Pull at CI time; shared repo | Owner dislikes cross-repo copies/deps but accepts this one |

## Manual steps
- Optional: in a fresh Claude Code session, run `/memory` and confirm `AGENTS.md` is loaded through `CLAUDE.md`.

## Risks / Open Questions
- [RESOLVED: guidance only, ~300 lines, not a CI gate] Rule 2 split threshold.
- [RESOLVED: rewritten] Rule 7: class for a major concept even with one variant today; plain/static functions otherwise; judgment, no over-engineering; max one inheritance level.
- [RESOLVED: git tag, no registry] Engine shared via git tag (eval pins `engine-v0`, later `engine-v1`; as `@onolys/common` does). Owned by 03, not a coding rule.
- [RESOLVED: copied per repo] Rules COPIED into each repo (this repo `docs/rules/`; eval repo and onolys-common keep own copies, synced by hand); no cross-repo pull.
- [RESOLVED: adopted] TS counterpart of rule 10: `constants.ts` per app/package (D9).
- [RESOLVED: locked] Emulator stubs; `constants.py` per package; voice stays in api; one pipeline YAML per evaluation; English only.
- [RESOLVED: D5] CLAUDE.md pointer added.
- [DEFERRED] Rule 13 (`architecture.md`, ADR fold-in): docs frozen in the revamp.
- [DEFERRED] Optional lint greps for rules 9, 10, 12 (see R6).
- [DEFERRED] Doc line `Apply to every UI: web/, eval/web` in design-rules: fixed by 03 when eval leaves.
- Interplay: 01 may prune `check_docs_scope.sh` / `check_links.py`. This SP's README edits satisfy both either way; no ordering constraint.

## Acceptance Criteria
- `docs/rules/coding-rules.md` has rules numbered 1-16, each with Do/Don't; rule 2 says ~300 lines is guidance only; rule 7 uses the owner wording; rule 13 states it is not applied during the revamp; rule 9 names the Firestore emulator; rule 10 says one `constants.py` per package; rule 4 says one pipeline YAML per evaluation.
- `docs/design-rules.md` gone; `git log --follow docs/rules/design-rules.md` shows prior history; content identical apart from the path.
- `grep -rIn "design-rules" . --exclude-dir=agent_files --exclude-dir=node_modules` returns only `docs/rules/design-rules.md` paths.
- `AGENTS.md` names both rules files with the all-code / UI split; `CLAUDE.md` is exactly `@AGENTS.md`.
- `python3 scripts/ci/check_links.py` and `bash scripts/ci/check_docs_scope.sh` pass.
- No files changed outside the Owns list; no code or CI changes.
