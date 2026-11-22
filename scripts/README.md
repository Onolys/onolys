# scripts/

| File | Purpose |
|---|---|
| `dev.sh` | Start the admin backend and Vite together with matching ports and env. |

## dev.sh

```
scripts/dev.sh [--check]
```

Starts, each in its own process group with prefixed output:

| Prefix | Process | Port |
|---|---|---|
| `[backend]` | `uv run uvicorn --factory onolys_admin_backend.app:create_app` (in `admin/backend/`, `ENV=local ADMIN_AUTH=off`) | 8000 |
| `[web]` | `npm run dev` (in `frontend/`) | 5173 |

Env set by the script: `VITE_ADMIN_API_URL=http://localhost:8000` (origin only), `VITE_MOCK=false` (web).

Flags:

- `--check`: preflight only (`uv`, `node`/`npm`, `frontend/node_modules`, free ports; names the port holder), then exit.

Provider keys (`GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `LITELLM_API_KEY`) are checked for presence only; a warning is printed if none is set. Values are never printed.

After start it waits up to 30 s for backend `/v1/me`, then prints URLs. Ctrl-C (or any child exiting) stops all children (TERM, then KILL after 5 s); a child exit makes the script exit non-zero.

First time: `cd frontend && npm ci`.

The first live smoke of the full script (both up, Ctrl-C leaves no orphans) is an owner manual check. Agents run only `bash -n` and `--check`.

Ports are fixed by this script.
