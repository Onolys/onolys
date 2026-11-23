---
status: draft
summary: New `eval/core` package (onolys_eval) fetches the 8 CASAA 2013 video-series MITI 4.2.1 transcripts, converts coded PDFs to transcript.v1 + gold.v1 (per-utterance codes -> counts, plus globals), stores them in a private staging bucket, and a CLI runs the lean engine on one session and prints ours vs gold. Metrics module reused by SP5.
date: 2026-11-23
---
# PRD: SP2 CASAA dataset + gold format + CLI eval spike

Repo/branch: Onolys/onolys (local `iaudit`) / `feat/miti-eval` · Depends on: SP1 (`transcript.v1` schema; stub with the engine `Turn` shape until it lands) · Blocks: SP5 (imports registry, gold, metrics, bucket layout)
Owns: `eval/core/**` (new uv member), `eval/datasets/**` (manifests, overrides; no data), root `pyproject.toml` workspace line, one staging bucket in `infra/`. Not owned: `engines/**`, `api/**`, `admin/**`, `web/**`, `eval/backend` (SP5).

## TL;DR
A small Python package `onolys_eval` with four parts: dataset manifest + downloader, CASAA PDF -> `transcript.v1` + `gold.v1` converter (with manual-override fallback), pure metrics (MAE per code and per global, R:Q and %CR from one formula for gold and ours), and a CLI `onolys-eval run` that codes one CASAA session with the lean engine and prints a side-by-side table. Data never enters git: it lives in `~/.cache/onolys-eval/` locally and in a private staging bucket for SP5. The spike runs fully local, so it needs no bucket and no SP1 code.

## Problem
We do not know how close lean MITI is to expert coding. CASAA publishes coded transcripts as PDFs (not machine-readable), the repo is public, and SP5 needs a stable dataset + gold + metrics contract before the site is built.

## Verified facts about CASAA [verified: fetched casaa.unm.edu/tools/miti.html and PDFs, 2026-11-23]
- The page has two groups. The **2013 "Helping People Change" video series = 8 sessions, transcripts only (video is sold by Change Companies, no audio)**: confirmed-smoker, rounder, my-father-also-hit-me, overuse-of-directing, overuse-of-following, suspiscious-smoker (sic), living-with-diabetes, orientation-to-a-parenting-class. Size 12-126 utterances each. Separately, **12 role-play sessions have MP3 audio** (`session1`..`session5` + 7 named ones, ~54 utterances each, MITI 4 training series). The brief's example URLs (`session1-1.mp3`, `session11.pdf`) belong to the role-play group, not the 2013 series.
- Coded PDFs hold **per-utterance codes** (utterance number, P/I/C speaker, text, "Code" column, sometimes "Notes") and the **4 globals** (CCT/SST/PAR/EMP, 1-5) at the end. Session totals are printed only in some (Rounder lists GI/Persuade/Q/SR/CR/Af/Seek/Emphasize/Confront). So gold counts are **derived** by summing utterance codes; printed totals are a parser self-check.
- No timestamps, no change goal field (some headers give `Focus:` e.g. "Tobacco cessation"), no coded-window statement. Headers/layout differ per PDF (`P` vs `I` clinician, `Final Code` vs `Code`, intro prose, `Part` vs `PAR`).
- Labels wrap across lines and rows can carry two codes: `Persuade / with` (= Persuade with Permission), `Emphasize / Persuade with` (EA + PwP), `AF / Q`. `NC`/`NOT CODED` = no code.
- Engine item ids to reuse as gold keys [verified: `engines/miti/.../data/pack.yaml`]: counts `gi persuade persuade_permission question sr cr affirm seek_collab emphasize_autonomy confront`; globals `cct sst partnership empathy`; summaries `technical relational pct_cr reflection_question_ratio total_mia total_mina`. Formulas live in the pack and `onolys_miti.formula.evaluate`.
- Without timestamps the engine codes the whole transcript (`span.py`: `duration_s` None; window only when > 20 min). All CASAA sessions are short, so full-session coding needs no SP1 `coded_span`.

## Goals / Non-Goals
**Goals:** reproducible fetch + convert of the 8 sessions; a gold schema SP5 and later datasets can reuse; metrics module with no I/O; CLI spike answering "how far off is lean MITI on 1 session"; private bucket layout.
**Non-Goals:** utterance-level alignment (gold stores per-utterance codes, nobody compares them yet); Firestore run history, site, engine/preset multi-select (SP5); the role-play audio set and MI-TAGS/AnnoMI (manifest format must allow them; [DEFERRED]); engine changes; committing any dataset content.

## Requirements
**R1 Package.** `eval/core` = uv member `onolys-eval` (package `onolys_eval`), added to workspace `members` as `eval/*` (SP5's `eval/backend` is the sibling, mirroring `admin/auth` + `admin/backend`). Depends on `onolys_miti` and `pyyaml`; PDF parsing in an optional extra `convert` (`pdfplumber`) so SP5's backend imports metrics/gold without PDF libs. Old untracked `eval/__pycache__` removed locally (not tracked, no repo change).

**R2 Manifest** `eval/datasets/<dataset_id>/manifest.yaml` (committed, no content): `dataset_id`, `title`, `license_note` ("internal use only; reuse terms unconfirmed"), `source_page`, `miti_version: 4.2.1`, `sessions[]: {session_id, title, uncoded_url, coded_url, audio_url?, clinician_labels, change_goal, change_goal_source: header|curated, coded_span: null|{...}, notes}`. First dataset id `casaa-miti421-video2013` (8 sessions). `change_goal` is required by the engine and absent in CASAA: taken from the PDF `Focus:` header when present, else curated by hand in the manifest (a short phrase; no invention beyond what the transcript states).

**R3 Fetch.** `onolys-eval fetch <dataset>` downloads the PDFs (and audio when listed) to `<cache>/<dataset>/raw/<session_id>/`; skips files that exist; records sha256 + retrieved_at in `<cache>/<dataset>/raw/fetch.json`. Default cache `~/.cache/onolys-eval`; the command refuses a cache path inside any git work tree.

**R4 Convert.** `onolys-eval convert <dataset> [--session id]` writes `<cache>/<dataset>/<session_id>/{transcript.json, gold.json}`.
- Rows are found by the left-margin utterance number; columns by x-positions of the header row (pdfplumber words); page headers/footers dropped; continuation lines joined; wrapped code labels joined per utterance then matched against a label map (`GI->gi`, `Persuade`, `Persuade with->persuade_permission`, `Q`, `SR`, `CR`, `AF/Af`, `Seek`, `Emphasize`, `Confront`, `NC/NOT CODED`->none). Layout quirks are per-PDF settings in the manifest (`clinician_labels`, `code_header`), not code forks.
- Transcript: `{language:"en", turns:[{id:"t<n>", speaker:"P|I|C", role, text}]}`, no timestamps. Roles come from the speaker label so the engine runs with a prebuilt `speaker_map` and no speaker gate.
- Self-checks, each a warning: unknown code token; row without text; utterance numbers not 1..N contiguous; globals missing/out of 1-5; derived counts != printed totals when the PDF has them; coded-vs-uncoded PDF text mismatch per utterance.
- **Manual fallback:** `eval/datasets/<id>/overrides/<session_id>.yaml` (committed; holds only utterance ids, code ids, globals, never text) overrides parsed codes/globals. `convert` exits non-zero while any warning is unresolved, unless `--allow-warnings`; `--dump` prints the parsed table for eyeballing against the PDF. Converting the 8 sessions is a one-time job; a parser that needs overrides for 2-3 PDFs is acceptable.

**R5 gold.v1** (`onolys_eval/schemas/gold.v1.schema.json`, shared with SP5): `{schema:"gold.v1", dataset_id, session_id, source:{coded_url, uncoded_url, retrieved_at, sha256}, coded_span: null|{start_ms,end_ms}|{start_turn,end_turn} (SP1 grammar; null = full), counts:{10 ids -> int}, globals:{cct,sst,partnership,empathy -> int 1-5}, summaries:{...computed via onolys_miti.formula at convert time}, utterance_codes?:[{turn_id, codes:[ids], note?}], parse:{method:"auto|auto+override", warnings:[]}}`. Per-utterance codes are optional so datasets with session totals only still fit.

**R6 Metrics** `onolys_eval.metrics` (pure functions, no I/O, no LLM; SP5 reuses unchanged): `Scores{counts, globals, summaries}` is engine-agnostic. `compare(gold, ours) -> SessionComparison` (per key: gold, ours, signed diff, abs diff). `aggregate([SessionComparison]) -> Aggregate` (MAE per count, per global, per summary; mean bias; globals within 1 point; n). R:Q and %CR are always recomputed from counts with the pack formula on both sides; a null (zero denominator) is skipped in MAE and reported as n. Adapter `scores_from_report(report)` maps the lean report to `Scores`; SP3/SP4 engines supply their own adapter. Output is a JSON-serialisable `compare.v1` dict.

**R7 Bucket.** Private GCS bucket `onolys-eval-data-staging` (Terraform in `infra/`, staging only, uniform access, public access prevention enforced, no versioning needed). Layout: `datasets/<dataset_id>/manifest.json` (rendered from yaml, SP5 lists datasets by listing this prefix) and `datasets/<dataset_id>/<session_id>/{transcript.json, gold.json, raw/*.pdf, raw/audio.mp3?}`. `uploads/` is reserved for SP5. `onolys-eval upload <dataset>` copies from cache; needs `gsutil`-free `google-cloud-storage` via ADC. Run `convert` first; upload refuses unresolved warnings.

**R8 CLI** (`onolys-eval`, module `python -m onolys_eval`): `fetch`, `convert`, `upload`, and
`run <dataset> <session_id> [--preset P] [--runs N=1] [--source cache|bucket] [--json-out PATH]`. `run` loads transcript + gold, builds a `RunContext` like `onolys_miti.check`, calls `run_miti(ctx, transcript, speaker_map, {change_goal, language:"en", n_runs, preset})`, maps the report with `scores_from_report`, and prints:
```
casaa-miti421-video2013 / rounder   preset=<p>   engine=miti sha=<git>   tokens=<n> ~$<x>
code                gold  ours  diff
question              10     9    -1
cr                    16    11    -5
...
cct (global)           4     3    -1
pct_cr               0.64  0.55  -0.09
count MAE 1.4 | globals within 1: 3/4
```
Live keys via `set -a; . ~/.config/onolys/keys.env; set +a`. `--json-out` writes `compare.v1` + run metadata; the default path must be outside the repo (error if inside). Exit 0 on a completed comparison (accuracy thresholds are not pass/fail here).

**R9 Public-repo guard.** A test fails if `git ls-files eval/` holds any `*.pdf|*.mp3|transcript.json|gold.json` or a file over 200 KB. `.gitignore` gets `eval/**/raw/` and `eval/**/*.cache`.

## Architecture
```
casaa.unm.edu --fetch--> ~/.cache/onolys-eval/<ds>/raw --convert--> <ds>/<sid>/{transcript,gold}.json
                                                         |--upload--> gs://onolys-eval-data-staging/datasets/<ds>/...
cache|bucket --> run_miti(lean) --> scores_from_report --> metrics.compare(gold, ours) --> table | JSON
```
Shared with other SPs: `gold.v1.schema.json`, `metrics.py` (`Scores`, `compare`, `aggregate`), manifest format, bucket layout, `transcript.json` = `transcript.v1` (SP1).

## Decisions
| Decision | Alternative | Why |
|---|---|---|
| `eval/core` member, `eval/backend` reserved for SP5 | Single `eval/` package | Backend imports metrics without CLI/PDF deps; mirrors `admin/` |
| `pdfplumber` word coordinates, per-PDF settings, override files | `pdftotext -layout` regex | Wrapped code labels and variable columns need positions; poppler is not a Python dep |
| Counts derived from utterance codes, printed totals as check | Trust printed totals | Totals exist in few PDFs |
| Gold keys = engine item ids | CASAA abbreviations | No mapping at compare time |
| Summaries computed with `onolys_miti.formula` for both sides | Copy printed values | Same formula, per brief |
| Spike session = `rounder` (101 utts, printed totals) | Role-play session 1 | Parser can be validated against totals |
| Cache outside repo, upload via ADC | Commit small files | Repo is public |
| Dataset = the 8 video-series sessions (transcript-only); role-play audio set as later dataset | Use the 12 audio sessions first | Locked decision; audio set is cheap to add via manifest |

## Manual steps (owner)
Confirm CASAA reuse terms (internal use only until then). Provide staging GCP access for the upload step and apply the bucket Terraform. Review the curated `change_goal` per session.

## Risks / Open Questions
- [OPEN] Staging creds: no `gcloud` on this machine and no known SA key. Upload needs ADC or a service-account key; spike does not.
- [OPEN] Are the transcripts excerpts of longer videos? Only some headers state a length (confirmed-smoker: 16 min). Assume transcript = coded span, `coded_span: null`.
- [OPEN] Do coded and uncoded PDF texts match utterance for utterance (counts differed by regex for 2 PDFs, possibly `I` vs `P` labels)? Convert check R4 will tell; coded PDF is the source of truth for text.
- [OPEN] Per-PDF accuracy of the parser; how many need overrides. Cheapest test: convert `rounder` and `confirmed-smoker` first.
- [OPEN] Gold is one consensus code per utterance; no inter-coder noise. MAE vs one coder is a ceiling-limited metric. Accept.
- [OPEN] Engine volley rules (one reflection per volley) may differ from how CASAA rows code consecutive clinician turns; count differences may partly be rule mismatch, not model error.
- [OPEN] Exact `Report` field path for counts/globals; confirm in `report.py` when writing `scores_from_report`.
- [OPEN] Token/$ figure: take from `MetricsCollector`; price table source unknown (rough, per brief).
- [DEFERRED] Role-play audio dataset (12 sessions, STT path); utterance-level alignment; `--runs 3` aggregation as median vs mean.
- [RESOLVED: auto-default] SP1 not ready: use engine `Turn` JSON, field-compatible with `transcript.v1`.

## Acceptance Criteria
- `fetch` + `convert casaa-miti421-video2013` yields 8 `transcript.json` + `gold.json` in the cache, all validating against SP1 transcript schema and `gold.v1`; each has zero unresolved warnings (overrides allowed).
- Rounder: derived counts equal the printed totals; globals 4/3/5/5.
- Unit tests (synthetic fixtures, no CASAA text): label map incl. wrapped `Persuade with`, `Emphasize Persuade with`, `AF Q`; metrics MAE/bias/null-skip; R:Q and %CR equal `onolys_miti.formula`; repo guard test.
- `onolys-eval run casaa-miti421-video2013 rounder` against the live model prints the table in R8 and writes `compare.v1` JSON outside the repo.
- `upload` puts the 8 sessions under `datasets/casaa-miti421-video2013/` in the staging bucket; the bucket denies anonymous reads.
- `git ls-files eval/` contains no data files.
