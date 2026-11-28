# Local setup and live verification

Set up every component, run the offline checks, and work through the owner live checks.

**Audience:** contributors and the repository owner.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) and Python 3.12 (`requires-python = ">=3.12,<3.13"`).
- Node and npm. CI uses Node 22; the repo pins no other version.
- For live runs, a provider key that LiteLLM reads. The default models are Google Gemini (`GEMINI_API_KEY`) ([configuration](../reference/configuration.md)). Offline tests and stub modes need no key.

## One-time setup

```bash
uv sync --all-packages        # from the repo root
(cd web && npm ci)
```

## Offline checks

No key or network needed.

```bash
uv run --package onolys-miti pytest engines/miti -m "not live"
uv run --package onolys-miti ruff check engines/miti
uv run --package onolys-api pytest api -m "not live"

(cd web && npm test && npm run typecheck && npm run build)
```

More: [running-tests.md](running-tests.md), [reference/testing.md](../reference/testing.md).

## Retired admin frontend

The former admin backend, root admin launcher and `frontend/` sign-in shell are removed. Product development uses the [main app setup](#main-app-web--api) below; the API alone also has [`api/scripts/dev.sh`](../../api/scripts/dev.sh).

## Owner live checks

These need a key, spend money and are not run by agents.

- [ ] **b. MITI engine live check.** `set -a; . ~/.config/onolys/keys.env; set +a`, then `uv run --package onolys-miti python -m onolys_miti.check --preset <p>`. It runs the three synthetic fixtures against the limits in `fixtures/thresholds.yaml` and checks that tips quote the transcript ([engines/miti/README.md](../../engines/miti/README.md#tests)). Note the cost.
- [ ] **c. Voice check.** `uv run --package onolys-miti pytest engines/miti -m live -s` also opens a real Gemini voice session (`tests/test_voice_live.py`).
- [ ] **d. Refresh recordings (only if prompts changed).** Re-record golden fixtures with `MITI_LLM_RECORD=1` on a live run, then run `pytest engines/miti` offline and commit only synthetic recordings.
- [ ] **e. End to end.** Run the main app (below), upload a short recording, confirm speakers, and read the report and tips.

Then the rest of [pre-release-checklist.md](pre-release-checklist.md).

## Claude Code skills (thepass)

Open this repo in Claude Code and trust the folder: it prompts to install the `thepass` marketplace and plugin (declared in `.claude/settings.json`).

Manual fallback:

```
/plugin marketplace add tejitpabari99/thepass
/plugin install thepass@thepass
```

## Main app (web + api)

Applies to `web/` and `api/`. Needs node 22, `uv`, java 21. Install: `(cd web && npm ci)` and `uv sync --all-packages` from the repo root.

**Mode A: web mock (MSW + fake auth).** `cd web && npm run dev:mock` serves `http://localhost:5173` with the API in-browser. No backend or login: sign up with any email and password (auto-verified, in memory, lost on reload).

**Mode B: Firestore emulator + api (stub adapters) + web live.** Real Firebase Auth cannot run locally (no Auth emulator wiring), so use `AUTH_MODE=fake` on the api (`Bearer test:<uid>`) and `VITE_AUTH_MODE=fake` on the web. Open the app as `localhost`, not `127.0.0.1` (api CORS).

Terminal 1, Firestore emulator (from repo root; firestore on 8081):

```bash
npx -y firebase-tools@15.37.0 emulators:start --only firestore --project demo-onolys
```

Terminal 2, api on port 8000 (`mkdir -p /tmp/onolys-blobs` first; env vars are in `api/.env.example`):

```bash
FIRESTORE_EMULATOR_HOST=127.0.0.1:8081 ENV=local SERVICE_MODE=combined AUTH_MODE=fake ADAPTERS=stub \
GCP_PROJECT=demo-onolys AUTH_PROJECT=demo-onolys FIRESTORE_DATABASE='(default)' \
APP_BASE_URL=http://localhost:5173 CORS_ORIGINS=http://localhost:5173 FAKE_BLOB_DIR=/tmp/onolys-blobs FAKE_BLOB_BASE_URL=http://127.0.0.1:8000 \
uv run --package onolys-api uvicorn --factory onolys_api.app:create_app --host 127.0.0.1 --port 8000
```

Without `FIRESTORE_EMULATOR_HOST`, `ENV=local` uses the in-memory FakeRepo. Combined mode runs the worker in-process with stub STT and the fake engine adapter.

Terminal 3, web live on port 5173 (no vite proxy, hence the absolute API URL):

```bash
cd web && VITE_USE_MOCKS=false VITE_AUTH_MODE=fake VITE_API_BASE_URL=http://127.0.0.1:8000/v1 \
VITE_FIRESTORE_EMULATOR=127.0.0.1:8081 VITE_FIREBASE_PROJECT_ID=demo-onolys VITE_FIRESTORE_DATABASE='(default)' \
npm run dev:live
```

Check: `GET :8000/v1/healthz` returns `{"status":"ok",...}`; `GET /v1/sessions` with `Authorization: Bearer test:alice` returns an empty list.

Not available locally: real auth, real STT/LLM (stub adapters; `ADAPTERS=real` needs GCP creds), the voice relay websocket, the Hosting `/v1` rewrite. The audio `validate` step needs ffmpeg/ffprobe on PATH.

E2E (Playwright, `web/e2e_review`): see its README. Screenshots only with `E2E_SHOTS=1`.
