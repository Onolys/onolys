# Synthetic compare fixtures (SP06)

All data here is SYNTHETIC, invented for offline tests. No dataset transcript, quote, gold label,
audio or provider output is copied. Every transcript line reads "Synthetic clinician turn N." or
"Synthetic client turn N."; rationales, reasons and tips are placeholder sentences.

Regenerate: `uv run --no-sync --package onolys-eval python eval/fixtures/compare/builder.py`
(a test fails if the committed `*.json` drift from `builder.py`).

Each `<scenario>.json` holds one eval run: `eval_run` (grouping doc, SP05 R4 normalized as the
`EvalRunSource` protocol returns it), `cells` (`eval_view.list_cells` shape), `run_docs`
(RunDoc store form incl. `eval`), `reports` (ReportDoc, report inline), `transcripts`
(TranscriptDoc), `gold` (gold.v1 keyed by canonical sha256), `prices`. MITI reports are the
minimal subset the compare code reads (behaviours, globals, instances), not the full
`report.schema.json`.

| Scenario | Covers |
|---|---|
| counts_golden | human question 10, repeats 8/10/12 (miss 1.33); second session miss 2 (off 1.67, n 2, 3 repeats); global buckets same/off1/off2plus; oneshot combo; retried attempt |
| annomi_partial | AnnoMI-style partial labels (question, sr, cr, gi), no globals; SR=3 CR=1 Q=2; repeat with Question 0; human Question 0; one code per line |
| lines | multi-code turns on both sides, repeat disagreement, turn outside coded span, withheld rationale, oneshot without lines |
| twelve_sessions | 12 sessions x 3 combos, one combo failed in one session (11 paired of 12), real zeros, retry, unpriced model |
| cancelled_partial | cancelled after 4 of 12 sessions, one combo missing in session 4; status partial |
| provider_skipped | 12 x 3; Gemini combo 5 failed then 7 skipped (`provider_unavailable`), `provider_skips` entry |
| no_labels_hlqc / no_labels_phac | gold with no counts/globals/line labels (HLQC keeps a quality label) |
| no_completed | no done run (failed + cancelled) |
| running | not finished (done, running, queued) |

`builder.scale()` generates 498 runs in memory (not committed) for size/timing tests.
`fakes.py` has `FakeEvalRunSource` (implements `onolys_eval.summary.source.EvalRunSource`) and
`FakePriceBook` (mirrors the backend `PriceBook.estimate`; unknown model -> `cost_usd` None).
Tests import them as `compare.fakes` (see `eval/core/tests/conftest.py`).
