---
status: approved
summary: One new report view (MITI coded-transcript format) for real reports and the public sample, a coded-transcript dialog with utterance links, a new 54-utterance sample fixture, and an engine tips-prompt change so every tip is a concrete change with example wording.
date: 2026-11-23
---
# PRD: Report redesign (MITI coded-transcript format) + sample + tips prompt

Repo/branch: iaudit / `feat/public-nav-sample-report` · Depends on: none to build; SP1 wires `/sample` to `SampleReportPage` (parallel, shared files below) · Owns: `web/src/features/report/*` (ReportPage, SampleReportPage, new view/dialog files, tests), `web/src/mocks/fixtures/{sample.ts,index.ts,fixtures.test.ts,schema.test.ts}`, a new report block in `web/src/styles/app.css`, `engines/miti/src/onolys_miti/data/prompts/tips_system.md` (+ 3 pack fixture hashes), `./mockup.html`

Visual and data source of truth: [`mockup.html`](./mockup.html) (copy of the owner-approved mockup; full 54-utterance transcript, codes, "why" text, tips, globals reasons). Where this PRD and the mockup disagree on layout, the mockup wins; on data flow, this PRD wins.

## TL;DR
Replace the report body (scorecard, reasons-audit, side-by-side transcript) with a single-column document: Header, At a glance, Feedback, Behaviour counts, Coded transcript (button), Method. The full coded transcript (Utt # | P/C | Utterance | Code(s) | Why) opens in a native `<dialog>`; every "Utterance N" reference opens it scrolled to and briefly highlighting that row. Real reports and `/sample` use the same `ReportView`; the real report fetches its transcript, the sample uses a static fixture. No schema change, no engine counting change. Engine tips prompt is tightened so tips are always concrete changes.

## Problem
- Current report is disjointed: per-section widgets, a sticky transcript pane with no clear job, mobile tabs, tips as a flat list. Not how MITI coding is normally read (Utt | speaker | code | explanation). [verified: `ReportPage.tsx` panes/tabs; `app.css:129-154`]
- Sample uses the walking fixture and a yellow banner; it must show the product's real format. [verified: `SampleReportPage.tsx`, `mocks/fixtures/transcripts.ts`]
- Tips can be praise-only or give an alternative with no example wording. [verified: `tips_system.md` allows any "tip", `alternative` is "one or two sentences"]

## Goals / Non-Goals
**Goals**
- One view for real and sample reports, section order and content as in the mockup.
- Coded transcript as a dialog; utterance links from tips and globals.
- Sample fixture whose counts, globals and summaries match its own transcript and validate against `report.schema.json`.
- Tips prompt: concrete change, example wording.

**Non-Goals**
- Clinician/"your rating" columns, "Onolys disagrees" headline, reasons-audit, scorecard diff in the new view.
- Schema, `report.d.ts`, engine counting, or instance-cap changes (cap inert: `compare.py:57-67`).
- Routes, nav, footer, `/sample-report` redirect (SP1); miti landing (SP3).
- Design-system migration (`feat/design-system`).

## Requirements
**View (`ReportView`, section order fixed; ignores `report.layout`)**
1. **Header:** title, `header.change_goal`, meta list: protocol (`header.protocol.label`), coded span, date. Real: title "Report", version select kept (ReportPage only), "newer schema" notice kept. Sample: title "Sample report" plus grey line "Example report from a made-up role-play conversation."; no yellow banner.
2. **At a glance:** four globals (CCT, SST, Partnership, Empathy) on a 1-5 scale with `globals[].onolys.value` and one-line `onolys.reason`; under each reason, an "Evidence: utterances N, M" row of utterance links built from `onolys.evidence` turn_ids (see D5). Below, a 6-row summary table: value | fair | good | status chip (Below fair / Fair / Good). `reference === null` renders "No reference level", no chip. Note "Fair and good are reference levels, not pass marks."
3. **Feedback: ideas to try:** tips by `rank`; card = title (`observation`) + code chip (`item_id`) + What was said (`quote.text` + "Utterance N" link) + Try instead (`alternative`) + Why it matters (`why_it_matters`). Hidden when there are no tips. Warnings `fewer_tips`/`tips_failed` stay as quiet notices.
4. **Behaviour counts:** grouped table per mockup (Information & persuasion; Questions & reflections; MI-adherent + total; MI non-adherent + total = Confront + Persuade). Counts from `behaviours[].onolys_count.mean`, rounded for display.
5. **Coded transcript section:** count line ("N utterances, M from the practitioner") + "Open coded transcript" button.
6. **Method & limits:** `method.statement`, `method.limits`, `method.citation`, "Not official MITI coding" note (`not_official_miti_coding`).
**Dialog (`CodedTranscriptDialog`)**
7. Native `<dialog>` + `showModal()`; desktop about 88vh and `min(1100px, 100vw - 48px)`; full-screen at width <= 640px. Sticky header with title, count and Close button; collapsible code legend (`<details>`); sticky table header; table columns Utt # | Speaker (P/C) | Utterance | Code(s) | Why.
8. Esc and backdrop click close; focus returns to the opener; body scroll locked while open (class on `<html>`).
9. **Utterance link** (`UtteranceLink`): button "N" that opens the dialog, scrolls row N to center and applies a highlight for about 1.5 s; with `prefers-reduced-motion` scroll is instant and highlight is a static outline (no animation).
10. **Rows:** Utt # = 1-based index in `turns`. Why = `instances[].rationale`. A turn with several instances shows all code chips and the rationales joined (as in mockup row 29: "EA: ... PwP: ..."); chips keep instance order. Client turns show no codes. Practitioner turn with no instance shows "—" (real) or "Not coded" (sample only, D3). Row `id` = `utt-N`.
**Data**
11. **Join:** `buildCodedRows(turns, report, opts)` groups `behaviours[].instances` by `turn_id`, resolves code from `item_id`, uses start/end code-point offsets only to validate/skip bad spans (via `lib/codepoints.ts`). An instance whose `turn_id` is absent from `turns` is dropped from the table but still counted in counts.
12. **Real report:** transcript via `GET /sessions/{id}/transcript` (same query as `TranscriptPanel.tsx:11-19`). Report sections render without waiting. If the fetch fails: all non-transcript sections render; the dialog area shows "We couldn't load the transcript." with Try again; utterance links stay as buttons that open that message. Tip quotes and globals still show.
13. **Sample:** static fixture, zero network requests, signed out.
14. **Removed from report pages:** `.report-panes`/`.report-transcript` grid, mobile Report/Transcript tabs, `useSelectedInstance` hash selection, `reportHighlights` use (see D6).
**Sample data**
15. New `web/src/mocks/fixtures/sample.ts` with the 54-utterance drinking role-play from the mockup (turn ids `t1..t54`, speakers P=`spk_0`/role clinician, C=`spk_1`/client), one `behaviours[].instances` entry per code per turn with `rationale` = mockup "Why" text. Counts Q7 SR5 CR7 GI1 Persuade1 PwP3 AF2 Seek2 EA2 Confront1; globals CCT2 SST2 PAR2 EMP3 with the mockup's reasons and `onolys.evidence` Lines for each global (turn ids matching the utterances the mockup references; quotes located by offsets); 3 tips as in the mockup, quotes located by code-point offsets inside their turns.
16. Summaries computed from `pack.yaml` formulas (`:274-304`): Technical 2.0 (fair 3, good 4, Below fair); Relational 2.5 (3.5/4, Below fair); %CR 7/12 = 58% (.4/.5, Good); R:Q 12/7 = 1.7 (1/2, Fair); MIA 6 and MINA 2 (no reference).
**Tips prompt (engine)**
17. `tips_system.md`: every tip must be one concrete change to wording or approach (no praise-only or "keep doing this" tips); `alternative` must contain example wording the practitioner can say, in quotation-ready form. No schema change.
**CSS**
18. New classes only, in a block delimited `/* === Report view (SP2) === */ ... /* === /Report view === */` appended to `app.css`. No inline `style` attributes in markup (the mockup's legend uses some: convert to classes). Chip colours map to existing score tokens (`--color-score-*`) where they exist; new tokens only inside the block. Dark-mode via existing tokens.

## Architecture
```
ReportPage (real)                      SampleReportPage (public)
 useQuery report ──┐                     sample.ts: sampleReport + sampleTurns
 useQuery transcript (parallel)         │
        └───────► <ReportView report turns turnsState notCoded? header slot>
                    ├─ Header(slot) ─ AtAGlance ─ Feedback ─ BehaviourCounts
                    ├─ CodedTranscriptSection (button)  ─┐
                    ├─ Method                             ▼
                    └─ CodedTranscriptDialog <── rows = buildCodedRows(turns, report, {notCoded})
                           ▲ UtteranceLink(n) (in tips, globals) → dialog.open(n)
```
- **`ReportView`** (`features/report/ReportView.tsx`): presentational; props `report`, `turns` (or `{status: loading|error|ready}`), `headerSlot` (real: version select/notice; sample: grey line), optional `notCoded`. Owns dialog state via a small `useCodedDialog()` returning `open(n?)`, shared through context so `UtteranceLink` can be dropped anywhere.
- **`buildCodedRows(turns, report, opts)`** (`features/report/codedRows.ts`, pure, unit-tested): returns `{ n, speaker: "P"|"C"|other, text, codes: {item_id, label, group}[], why: string[] , notCoded: boolean }[]`. Speaker from turn `role` (clinician->P, client->C), else `spk_N` shown as-is.
- **`UtteranceLink`**: `<button type="button" class="uref">`; label = number. In At a glance, links come from structured evidence: `globals[].onolys.evidence` (`Line[]`, each with `turn_id`) is mapped to 1-based Utt # via transcript turn order and rendered as a small "Evidence: utterances 3, 7, 21" row of `UtteranceLink` buttons under each global's reason (turn ids absent from `turns` are skipped; row hidden if none). Optional extra, default not needed: `linkifyUtterances(text, onOpen)` turning "Utterance N" in reason text into links.
- **`CodedTranscriptDialog`**: native `<dialog>` in a ref; `showModal()`/`close()`; effect scrolls `#utt-N` into view after open; legend generated from `behaviours[].item_id` + pack labels already in the report. Existing `features/settings/Modal.tsx` is a div-based, 28rem modal (not reusable for a large table); not extended.
- **Data flow:** the report JSON is the only source of codes; the transcript is only the text. No new API endpoints or schema fields.
- **Touch points shared with SP1:** `routes.tsx` (SP1 imports `SampleReportPage` by its existing path/export and mounts `/sample`), `Layout.tsx` (none for SP2), `app.css` (distinct blocks; SP2 deletes `.report-panes`/`.report-tabs`/`.report-transcript` rules and the `@media` lines at `:152-154`, SP1 edits footer/nav rules only).

## Decisions
| # | Decision | Choice | Alternatives | Why |
|---|---|---|---|---|
| D1 | New view replaces `ReportSections` for real and sample | `ReportView`; `ReportSections.tsx` deleted after grep shows no importers outside ReportPage/SampleReportPage, with its tests ported or removed | keep both, flag by route | one format; leaves no dead twin |
| D2 | Dialog primitive | native `<dialog>` | extend `Modal.tsx`; portal lib | built-in focus trap, Esc, top layer, CSP-safe |
| D3 | "Not coded" for sample closing pleasantry [RESOLVED: auto default - sample-only prop `notCoded` (set of turn ids) passed by `SampleReportPage`; real reports show "—"] | prop on `ReportView` | schema field; code as GI | no schema change; MITI convention shown only where authored |
| D4 | Fixture location [RESOLVED: auto default - keep `sampleReport`/`noRatingReport`/`sampleTranscript` as is, add `sample.ts` with `drinkingSampleReport`/`drinkingSampleTurns`] | new file | overwrite existing | other tests/mocks depend on old ones (grep: `stateMachine.ts:17,317`, `ReportPage.test.tsx:5,45`, `fixtures.test.ts`, `schema.test.ts`) |
| D5 | Utterance links in globals [RESOLVED: orchestrator default - structured evidence turn_ids, no schema change; real engine reasons rarely contain utterance numbers] | `globals[].onolys.evidence` Line[] turn_ids mapped to Utt # via turn order, shown as an "Evidence: utterances 3, 7, 21" row of `UtteranceLink` buttons under each reason; text linkify only an optional extra (default: not needed) | parse reason text | evidence already in schema; works for real reports; sample fixture must carry evidence Lines for each global matching the mockup's referenced utterances |
| D6 | Dead code [RESOLVED: auto default - delete only `ReportSections`, `useSelectedInstance` hash use and `reportHighlights` imports in report pages if grep shows no other importers; keep `ratingEnabled`, `lines.ts`, `Transcript.tsx` + their tests if still imported elsewhere (Transcript/lines are reused by nothing else -> verify, delete only if zero importers)] | grep-driven | keep everything | `ratingEnabled` is used in 6 other files (config, timeline, slots, Interview, Dashboard, NewSession) so stays |
| D7 | Real-report speaker label | role-based P/C, else raw speaker id | always P/C by order | engine roles can be null |
| D8 | Tips prompt only, no code | edit `tips_system.md`; refresh pack fixture hashes | add validator rejecting praise | schema stays; model-side fix |
| D9 | Dialog loading state when transcript pending | button disabled "Loading transcript…" | open empty | clear, no layout jump |
| D10 | Counts display | `onolys_count.mean` rounded | `values[0]` | N>1 runs already average in current UI (test "mean across runs") |

## Manual steps
- None for deploy. Owner may eyeball `/sample` after SP1 lands, light and dark, 375px and desktop.
- Prod check (brainstorm risk): open 2-3 stored real reports and confirm the coded transcript is complete (older engine versions may have capped instances).

## Risks / Open Questions
- Several codes on one turn, or an instance spanning/split across turns: covered by D-row rules and `buildCodedRows` tests with the multi-code row (utt 29, 33, 35, 39, 49). A span crossing turns is not representable (one `turn_id`); the row still lists the code. [RESOLVED: auto default - no special split handling]
- Real globals may carry no evidence Lines, so some globals show no Evidence row. [RESOLVED: auto default - accepted; row hidden when empty; tips links always present]
- Engine tests/fixtures hit by the prompt edit: `tests/test_data.py:49-51` lists the file (no content assert); `test_build_report.py:171-175` compares live hashes with `doc()`; recorded `tips_system.md` hash `c8cc446d70112112` sits in `data/fixtures/evaluation/report_{full,partial,no_rating}.json`. [RESOLVED: auto default - regenerate those three hash values after the edit, then run `test_golden.py`, `test_build_report.py`, `test_data.py`, `test_tips.py`; `test_tips.py` has no prompt-text asserts except the no-rating-words blacklist (word `agree`, `diff`: keep the new prompt free of them)]
- Conflict with `feat/design-system` touching the same files. [RESOLVED: auto default - land first, they rebase]
- Mockup font (Inter via Google Fonts link) violates app CSP. [RESOLVED: auto default - use the app's existing font stack, not the mockup font]
- Hand-coding fairness: sample codes are authored, not engine output. [DEFERRED - owner already accepted]

## Acceptance Criteria
1. `/sample` (after SP1) and `/sessions/:id/reports/:v` render sections in this order: Header, At a glance, Feedback, Behaviour counts, Coded transcript, Method. No scorecard, "Your rating", disagreement headline, reasons-audit, side transcript, or Report/Transcript tabs.
2. Sample: no yellow banner, grey line present, zero network requests while signed out.
3. Sample counts table shows Q7 SR5 CR7 GI1 Persuade1 PwP3 AF2 Seek2 EA2 Confront1, totals 6 and 2; counts recomputed from the 54 rows equal the table (unit test). Globals 2/2/2/3. Summary table 2.0 / 2.5 / 58% / 1.7 / 6 / 2 with chips Below fair, Below fair, Good, Fair, none, none.
4. The sample report JSON validates against `report.schema.json` (added to `schema.test.ts`); sample turns have 54 entries, 27 practitioner.
5. Dialog: "Open coded transcript" opens a modal `<dialog>` with title, count, close, legend, sticky headers; Esc and backdrop close it; focus returns to the opener; a screen reader announces it with its title; at 375px it fills the screen.
6. Clicking "Utterance 25" (tip 1) opens the dialog with row 25 centered and highlighted about 1.5 s; with reduced motion no animation. Same for the Evidence links under each global in At a glance (numbers match the fixture's evidence turn ids).
7. Multi-code row 29 shows EA and PwP chips with both rationales; practitioner turn 53 shows "Not coded" in the sample; a real report's uncoded practitioner turn shows "—".
8. Real report with transcript request failing (500): all other sections render, dialog shows the transcript error with Try again; no uncaught error.
9. CSP: no `style="..."` attribute in rendered report markup (test greps container HTML); build passes; no new external font/script.
10. `tips_system.md` states the concrete-change and example-wording rules; engine tests listed above pass with refreshed hashes; schema unchanged (`git diff` shows no change to `report.schema.json` or `report.d.ts`).
11. Tests updated: `SampleReportPage.test.tsx` (route/heading/banner/Scorecard assertions at `:19-22,35-50` replaced by new-view checks; keeps zero-network and no-controls tests), `ReportPage.test.tsx` (header/version select/not-found/N>1/schema-notice tests kept; assertions on scorecard chips, disagreement blocks, reasons audit, transcript pane and chip pulse `:107-195,236-250` replaced or removed), new tests for `buildCodedRows`, dialog behaviour and the evidence-to-utterance mapping (`linkifyUtterances` tested only if built); fixtures tests extended with the new sample.
