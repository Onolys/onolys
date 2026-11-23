---
status: draft
summary: Seven tasks to ship the MITI coded-transcript ReportView, dialog, new 54-utterance sample fixture, and the tips prompt change.
date: 2026-11-23
---
# Tasks: Report redesign (MITI coded-transcript format) + sample + tips prompt

Source of truth: [PRD.md](./PRD.md) (visual reference: [mockup.html](./mockup.html)). Every [RESOLVED] item in the PRD is binding. Routes, nav, footer and `/sample` mounting belong to sibling SP1 (`routes.tsx`, `Layout.tsx`): do not touch them. CI already runs web and engine (miti) tests in `.github/workflows/ci.yml`, so no CI task is needed.

| # | Task | Depends on | Status |
|---|---|---|---|
| 1 | `buildCodedRows` + evidence mapping (pure) | none | done |
| 2 | New sample fixture (54-utterance role-play) | 1 | done |
| 3 | `ReportView` sections + report CSS block | 1, 2 | done |
| 4 | `CodedTranscriptDialog` + `UtteranceLink` | 1, 3 | done |
| 5 | Wire `ReportPage` and `SampleReportPage` | 2, 3, 4 | in-progress |
| 6 | Engine tips prompt + refreshed fixture hashes | none | todo |
| 7 | Dead-code cleanup | 5 | todo |

## Task 1 — buildCodedRows + evidence mapping
What it is / what it means: the pure data join that turns transcript turns plus a report into table rows, and the helper that maps evidence turn ids to 1-based utterance numbers. Everything else renders from this.
What changes at a high level: add `features/report/codedRows.ts`. `buildCodedRows(turns, report, opts)` groups `behaviours[].instances` by `turn_id`, resolves code label/group from `item_id`, validates spans via `lib/codepoints.ts` (bad spans skipped), joins several instances on one turn (chips and rationales in instance order), and maps speaker from role (clinician to P, client to C, else raw id). Instances whose turn is missing are dropped from rows only. Practitioner turns without codes are flagged uncoded ("—", or "Not coded" when in `opts.notCoded`). Add `evidenceUtterances(global, turns)` returning sorted unique Utt numbers, skipping unknown turn ids.
Done when: `codedRows.test.ts`, written first, covers multi-code turn, client turn with no codes, uncoded practitioner turn, `notCoded` set, dropped orphan instance, bad span skipped, null role fallback, counts recomputed from rows, and evidence mapping (unknown ids skipped, empty result).

## Task 2 — New sample fixture
What it is / what it means: the data behind `/sample`, a made-up 54-utterance drinking role-play (27 practitioner) taken from the mockup, so the public sample shows the real product format.
What changes at a high level: add `mocks/fixtures/sample.ts` exporting `drinkingSampleReport`, `drinkingSampleTurns`, and the not-coded turn set (turn 53). Turn ids `t1..t54`, P=`spk_0`/clinician, C=`spk_1`/client. One instance per code per turn with the mockup "Why" text as `rationale`. Counts Q7 SR5 CR7 GI1 Persuade1 PwP3 AF2 Seek2 EA2 Confront1; globals CCT2 SST2 PAR2 EMP3 with the mockup reasons and `onolys.evidence` Lines for each global matching the utterances the mockup cites; 3 tips with quotes located by code-point offsets. Summaries per PRD req 16. Re-export from `index.ts`. Existing fixtures stay untouched (D4).
Done when: `schema.test.ts` validates the new report against `report.schema.json`; `fixtures.test.ts` asserts 54 turns/27 practitioner, counts recomputed via `buildCodedRows` equal the table, totals 6 and 2, globals 2/2/2/3, summary values and chips, tip quotes and evidence offsets resolve inside their turns, evidence turn ids exist. All tests written first.

## Task 3 — ReportView sections and report CSS
What it is / what it means: the single-column document replacing `ReportSections`, shared by real and sample reports.
What changes at a high level: add `ReportView.tsx` (props: `report`, `turns` state, `headerSlot`, optional `notCoded`) rendering in fixed order: Header, At a glance (four globals with value and reason, an "Evidence: utterances 3, 7, 21" row of utterance buttons under each reason hidden when empty, 6-row summary table with chips, "No reference level" for null, reference-level note), Feedback (ranked tip cards, hidden when no tips, `fewer_tips`/`tips_failed` notices), Behaviour counts (grouped table, `onolys_count.mean` rounded), coded transcript section (count line + button, disabled "Loading transcript…" while pending), Method and limits (including not-official-MITI note). Add the delimited `/* === Report view (SP2) === */` CSS block with classes only, existing score tokens and app font stack, no inline styles. Dialog is stubbed behind a context until Task 4.
Done when: `ReportView.test.tsx`, test-first, checks section order, scorecard/disagreement/tabs absent, counts and chips from the sample, null-reference rendering, tips hidden when empty, Evidence rows rendered from evidence ids, and no `style=` attribute in container HTML.

## Task 4 — CodedTranscriptDialog and UtteranceLink
What it is / what it means: the large coded-transcript table in a native `<dialog>` and the small number button that opens it at a given row.
What changes at a high level: add `CodedTranscriptDialog.tsx`, `UtteranceLink.tsx` and `useCodedDialog()` (shared via context, `open(n?)`). Dialog: `showModal()`, sticky header (title, count, Close), collapsible `<details>` legend built from report codes, sticky table header, columns Utt # | Speaker | Utterance | Code(s) | Why, row ids `utt-N`, 88vh/`min(1100px, 100vw - 48px)`, full-screen at 640px or less. Esc and backdrop close, focus returns to opener, `<html>` class locks body scroll. Link scrolls row N to center and highlights about 1.5 s; reduced motion gives instant scroll and a static outline. Error state shows "We couldn't load the transcript." with Try again, links still open. Dialog CSS goes in the Task 3 block.
Done when: `CodedTranscriptDialog.test.tsx` and `UtteranceLink.test.tsx`, test-first, cover open/close via button, Esc, backdrop, focus return, accessible name, scroll lock class, link opens and centers row 25, highlight class, reduced-motion path, multi-code row 29 chips and both rationales, "Not coded" on turn 53, "—" in real mode, and error plus retry.

## Task 5 — Wire ReportPage and SampleReportPage
What it is / what it means: connect the new view to both entry points and remove the old layout.
What changes at a high level: `ReportPage` fetches the report and the transcript in parallel (same query as `TranscriptPanel`), renders `ReportView` immediately, keeps version select, not-found and newer-schema notice in the header slot, and passes transcript loading/error/ready. `SampleReportPage` renders `ReportView` from the Task 2 fixture with title "Sample report", the grey example line, no yellow banner, `notCoded` set, and zero network. Delete the `.report-panes`, `.report-transcript`, `.report-tabs` rules and their media lines in `app.css`. Do not edit `routes.tsx` or `Layout.tsx` (SP1).
Done when: updated `ReportPage.test.tsx` (kept: header, version select, not-found, N>1 mean, schema notice; replaced: scorecard, disagreement, reasons audit, pane and pulse assertions; added: transcript 500 keeps other sections and shows Try again) and `SampleReportPage.test.tsx` (new-view checks, no banner, grey line, zero network, no controls) pass, written first.

## Task 6 — Engine tips prompt and hashes
What it is / what it means: make every tip a concrete change with example wording, with no schema or counting change.
What changes at a high level: edit `engines/miti/src/onolys_miti/data/prompts/tips_system.md` so each tip is one concrete wording or approach change (no praise-only or "keep doing this"), and `alternative` contains example wording the practitioner can say in quotation-ready form. Avoid the words `agree` and `diff` (blacklist in `test_tips.py`). Regenerate the recorded `tips_system.md` hash (`c8cc446d70112112`) in `data/fixtures/evaluation/report_{full,partial,no_rating}.json`.
Done when: `test_golden.py`, `test_build_report.py`, `test_data.py` and `test_tips.py` pass, with a test-first assertion in `test_data.py` that the prompt states the concrete-change and example-wording rules; `git diff` shows no change to `report.schema.json` or `report.d.ts`.

## Task 7 — Dead-code cleanup
What it is / what it means: remove what the new view orphaned, nothing more (D6).
What changes at a high level: grep for importers, then delete `ReportSections.tsx` (and port or remove its tests), `useSelectedInstance` hash use and `reportHighlights` imports in the report pages. Delete `Transcript.tsx`, `lines.ts`, `TranscriptPanel.tsx` and their tests only if grep shows zero importers. Keep `ratingEnabled` (used in 6 other files).
Done when: grep output recorded in the commit body shows zero remaining importers for each deleted file; web typecheck, lint and the report-feature plus fixtures tests pass; tests that existed only for deleted code are removed in the same commit.

## Closing note — manual steps (owner)
- Eyeball `/sample` after SP1 lands: light and dark, 375px and desktop.
- Prod check: open 2-3 stored real reports and confirm the coded transcript is complete (older engine versions may have capped instances).
- No deploy steps.
