# onolys-miti

MITI 4.2.1 coding engine: a session transcript in, the no-rating report out
(`run_miti(ctx, transcript, speaker_map, params, progress_cb)`). The MITI definition, prompts,
fixtures and report schema ship inside the package under `src/onolys_miti/data/`.

`MitiEngine` implements the shared `onolys_engine_core.engine.Engine` interface and
wraps `run_miti` without changing its signature or report. `MitiEngine.output_schema()`
returns the report schema; `run()` returns an `EngineResult` with the report, artifacts
and usage. The API registers it explicitly and selects it through the engine registry.

Shared infrastructure lives in the `onolys-engine-core` workspace package. Import
`RunContext` from `onolys_engine_core.context`, `Turn` from
`onolys_engine_core.transcript`, `TranscriptV1` from
`onolys_engine_core.transcript_v1`, and LLM clients/routes from
`onolys_engine_core.llm`. Retry helpers, safe logging and transcript text parsing also
live in core. MITI keeps its coding passes, schemas, prompts, fixture data, code-point
spans, STT and voice adapters; it does not re-export moved core modules.

## Tests

From the repo root (`uv sync --frozen --package onolys-miti` first):

```bash
uv run --no-sync --package onolys-miti pytest engines/miti -m "not live"
uv run --no-sync --package onolys-miti ruff check engines/miti

# Shared infrastructure and its AST import-boundary guard have their own CI job.
uv sync --frozen --package onolys-engine-core
LITELLM_LOCAL_MODEL_COST_MAP=True uv run --no-sync --package onolys-engine-core pytest engines/core -m "not live"
uv run --no-sync --package onolys-engine-core ruff check engines/core
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
quote the transcript. `tests/test_voice_live.py` opens a real Gemini voice session.

## Golden fixtures

`data/fixtures/golden/good_practice/` holds recorded model replies, keyed by a hash of the whole
request (route, call tag, prompts, schema name). Any change to a prompt, route name or template
changes the key and makes `tests/test_golden.py` fail with `FixtureMiss`; re-record with
`MITI_LLM_RECORD=1` on a live run.

## API integration

What the api imports from this package:

- Report schema: `onolys_miti.report.schema_path()`.
- Rating card: `onolys_miti.rating.validate_rating(obj, final)`, `onolys_miti.rating.is_no_rating`,
  `onolys_miti.report.Issue`.
- Rating schema: `onolys_miti.miti.MITI.rating_schema`.
- Scenarios directory: `MITI.data_dir / "scenarios"`.
- Test fixtures: `miti.DATA_DIR / "fixtures" / "evaluation"`.
- Engine entry: `MitiEngine().run(ctx, transcript, params, progress_cb)`;
  `params["speaker_map"]` supplies the speaker roles. Direct callers may still use
  `run_miti(ctx, transcript, speaker_map, params, progress_cb)`.
- Session selection: the entire transcript is coded unless `params["coded_span"]` narrows it.
- Env vars: `MITI_MODEL_CHEAP`, `MITI_MODEL_MID`, `MITI_MODEL_STRONG`, `MITI_LLM_RESPONSE_FORMAT`,
  `MITI_LLM_RECORD`.
- LLM routes: `miti_code`, `miti_globals`, `tips`.
