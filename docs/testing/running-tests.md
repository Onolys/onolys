# Running the engine tests

**Audience:** contributors.

From the repo root:

```bash
uv sync --frozen --package onolys-miti
uv run --package onolys-miti pytest engines/miti -q
uv run --package onolys-miti ruff check engines/miti
```

The whole suite runs offline with no API key (`-m "not live"` is the default `addopts`). Tests that need a model use `StubClient`, `FixtureClient` or the golden fixtures in `engines/miti/src/onolys_miti/data/fixtures/`; a changed prompt, route name or template changes the fixture key and fails `tests/test_golden.py` with `FixtureMiss` (re-record: [engines/miti/README.md](../../engines/miti/README.md#golden-fixtures)).

| Where | What |
|---|---|
| `engines/miti/tests/` | The engine: MITI data, code and globals passes, tips, report, scoring, LLM routes and clients, STT, voice, logging. |
| `api/tests/` | The api: routes, auth, jobs, error map, public contract. Emulator tests need the Firestore emulator ([reference/testing.md](../reference/testing.md#firestore-emulator)). |
| `web/src/**/*.test.ts(x)` | The web app (vitest). |
| `eval/backend/tests/` | The internal evaluation backend, including its allowlist on top of the prod api auth (`onolys_api.auth`). |

`engines/miti/tests/test_naming_guard.py` keeps old names out of the engine. Live checks (manual, never in CI): [local-setup.md](local-setup.md#owner-live-checks). Property tests and mutation runs: [fuzz-and-mutation.md](fuzz-and-mutation.md).
