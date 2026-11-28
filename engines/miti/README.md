# onolys-miti

MITI 4.2.1 coding engine: a session transcript in, the no-rating report out
(`run_miti(ctx, transcript, speaker_map, params, progress_cb)`). The MITI definition, prompts,
fixtures and report schema ship inside the package under `src/onolys_miti/data/`.

`MitiEngine` implements the shared `onolys_engine.engine.Engine` interface and
wraps `run_miti` without changing its signature or report. `MitiEngine.output_schema()`
returns the report schema; `run()` returns an `EngineResult` with the report, artifacts
and usage. The API registers it explicitly and selects it through the engine registry.

Shared infrastructure lives in the `onolys-engine` workspace package. Import
`RunContext` from `onolys_engine.context`, `Turn` from
`onolys_engine.transcript`, `TranscriptV1` from
`onolys_engine.transcript_v1`, and LLM clients/routes from
`onolys_engine.llm`. Retry helpers and `log_event` also live in core. MITI keeps its coding passes, schemas,
prompts, fixture data and code-point spans. STT, voice, scenarios, rating-card validation and
upload parsers live in `api/` (`onolys_api.transcription`, `.voice`, `.rating`).

## Tests

From the repo root (`uv sync --frozen --package onolys-miti` first):

```bash
uv run --no-sync --package onolys-miti pytest engines/miti -m "not live"
uv run --no-sync --package onolys-miti ruff check engines/miti

# Shared infrastructure (engine/) has its own tests; the `engine` CI job runs them with miti and one-shot.
uv sync --frozen --package onolys-engine
LITELLM_LOCAL_MODEL_COST_MAP=True uv run --no-sync --package onolys-engine pytest engine -m "not live"
uv run --no-sync --package onolys-engine ruff check engine
```

`-m "not live"` is also the default (`addopts`), so a plain `pytest engines/miti` is offline too.

Live checks (real model and Gemini voice; manual, never in CI) need the provider keys in the
environment:

```bash
set -a; . ~/.config/onolys/keys.env; set +a
uv run --package onolys-miti pytest engines/miti -m live -s
```

The same checks run as a module (exit non-zero on failure; `--preset` or `MITI_LIVE_PRESET` picks
the route preset, `--skip-tips` runs only the quality part):

```bash
uv run --package onolys-miti python -m onolys_miti.check --preset <p>
```

`tests/test_live.py` calls into `onolys_miti/check.py` and runs the three synthetic fixtures against `fixtures/expected.yaml` and
`fixtures/thresholds.yaml` (set `MITI_LIVE_PRESET` to pick a route preset), and checks that tips
quote the transcript. `api/tests/test_voice_live.py` opens a real Gemini voice session.

## Coding rules and limits

Clinician speech is grouped into volleys. Client input shorter than 3 whitespace words
(or 6 non-space characters for predominantly Thai, Chinese or Japanese text) stays inside
the volley unless it answers a detected question. Exactly 3 words / 6 characters breaks.
Question detection uses `?`, `？` or `؟` with a short trailing fragment; these thresholds
and punctuation rules approximate the manual's semantic facilitative-input rule.

Ten behavior labels occupy eight count slots per volley: GI; Persuade or Persuade with
Permission; Question; SR or CR; Affirm; Seeking Collaboration; Emphasizing Autonomy;
Confront. Each code counts at most once; CR takes the reflection slot. Permission takes
the persuasion slot and the losing Persuade stays visible as
`superseded_by_persuade_permission`. Permission precedence across separate utterances is
an engineering extension; the manual explicitly specifies it within one utterance.

Each volley receives text-only context: up to four prior client turns within 150 words
(300 characters for spaceless scripts), plus the previous clinician volley's last 100
whitespace words, including across batch boundaries. Context is interpretive only.
A quote found only there is dropped as `context_quote` and excluded from the retry drop
rate. Older permission and future context can fall outside these bounds.

The four global ratings keep their proposed score when fewer than two supporting quotes
locate, with informational `insufficient_evidence`; the existing poor-practice cap still
applies. Coverage measures clinician whitespace words outside located spans, including
uncoded and down-counted spans. A volley with at least 40 words and no located utterance
gets informational `coverage_gap`; this does not independently retry or fail coding.
Coverage is not a coding-accuracy score, and legitimate uncoded speech is allowed.

Rules, manual pages, formulas and engineering approximations are recorded in the
[branch manual audit](../../docs/agent_files/session-report-ux-20261124-1738/02-miti-manual-alignment/audit.md).
The [measurement summary](../../docs/agent_files/session-report-ux-20261124-1738/02-miti-manual-alignment/measurements/summary.md)
records deterministic evidence and its limitations. No independent human-coding accuracy
claim follows from synthetic fixtures.

## Offline audit and golden fixtures

With workspace dependencies already installed, run from the repo root:

```bash
# Request rendering + deterministic rules on every hand-authored expected.yaml fixture.
.venv/bin/python engines/miti/audit_report.py --output /tmp/miti-audit.json

# Re-key existing good_practice synthetic responses after intentional request changes.
.venv/bin/python engines/miti/tools/regen_goldens.py

# Focused checks for both tools and the synthetic replay.
LITELLM_LOCAL_MODEL_COST_MAP=True .venv/bin/python -m pytest engines/miti/tests/test_offline_tools.py engines/miti/tests/test_golden.py engines/miti/tests/test_data.py -q
```

Neither tool invokes a model/client or needs a provider key. The audit counts whitespace
words in initial code/globals requests (including repeated cache prefixes); it excludes
schemas, tips and retries and does not measure tokens, latency or cost. Counts come from
hand-authored utterances and summary globals from hand targets.

`src/onolys_miti/data/fixtures/golden/good_practice/` holds **synthetic** response stubs,
keyed by request hash. Regeneration reuses response bytes and repins request keys/pack
metadata; an unchanged invocation prints `No changes.` It does not create model outputs
or automatically approve changed report behavior. If volley grouping changes, provide
reviewed response objects keyed by call tag using `--responses <file.json>`; all quotes
must still locate in current clinician speech. New batches need supplied responses.
See [offline maintenance details](../../docs/agent_files/session-report-ux-20261124-1738/02-miti-manual-alignment/measurements/offline-tools.md)
for deliberate report/adapter baseline refresh and historical parity evidence.

## API integration

What the api imports from this package:

- Report schema: `onolys_miti.report.schema_path()`.
- Rating card: `onolys_miti.report.Issue` (validation lives in `onolys_api.rating`).
- Rating schema: `onolys_miti.miti.MITI.rating_schema`.
- Test fixtures: `miti.DATA_DIR / "fixtures" / "evaluation"`.
- Engine entry: `MitiEngine().run(ctx, transcript, params, progress_cb)`;
  `params["speaker_map"]` supplies the speaker roles. Direct callers may still use
  `run_miti(ctx, transcript, speaker_map, params, progress_cb)`.
- Session selection: the entire transcript is coded unless `params["coded_span"]` narrows it.
- Env vars: `MITI_LLM_RESPONSE_FORMAT`,
  `MITI_LLM_RECORD`.
- LLM routes: `miti_code`, `miti_globals`, `tips`.
