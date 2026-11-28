# refactor/revamp

Branch folder for the Onolys revamp. Base: main. Nothing implemented yet.

| File | What |
| --- | --- |
| `brainstorm.md` | Agreed rules + changes (snapshot of the Claude doc, 2026-11-28) |

## What to do next

1. Run `dev-design` on `brainstorm.md`. It splits the work into sub-projects, one PRD each, and asks only what is still open.
2. Suggested sub-projects, in order (dev-design may merge or split them):
   1. **00-rules-file**: turn the brainstorm's Rules section (rules 1-16) into the repo rules file, so every later sub-project follows it. Open question decides where it lives (AGENTS.md, .claude/ rules, or both).
   2. **01-legacy-purge**: delete legacy and compat code before launch (rule 16): old Terraform root, legacy CSS layer, migration/guard tests, ADR folder folded into architecture.md, spec ids in docstrings, scripts/ci pruned.
   3. **02-eval-split**: move eval/ into its own repo; engine as a git-tag dependency, own sign-in copy or shared package, own sessions.
   4. **03-engine-package**: one engine package; YAML pipeline runner + step and scoring libraries; protocols/ and evaluations/ folders; constants; generic LLM layer.
   5. **04-engine-behaviour**: in-order context, numbered utterance units, volley break on reflection answers, one-shot redesign; fixes the 5 listed inconsistencies.
   6. **05-api-by-feature**: data layer (base + thin wrappers), tasks/, no parallel fakes, STT/voice/rating/scenarios moved out of the engine.
   7. **06-web-and-ui**: app/ + features/ layout, shared components and helpers into @onolys/ui (repo Onolys/onolys-ui), delete web/src/mocks/, one tests/ folder.
   8. **07-infra-per-env**: infra/<env>/ folders absorb config/, one Terraform root, Firebase config in one place.
   9. **08-eval-libraries** (in the new eval repo): metrics + chart libraries, report YAML, dataset converter base class.
3. Resolve each open question in `brainstorm.md` before writing the PRD that depends on it.
4. Owner-only follow-ups go to `/root/projects/onolys/onolys/docs/agent_files/owner-follow-ups.md` (primary checkout, untracked). Add and remove items there; never put owner tasks in PRDs as agent work.
5. Scope: English transcripts only.
