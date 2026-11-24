# Brief for every coding agent on branch fix/review-findings

You implement ONE task (listed in your prompt). Only that task — no other findings, no unrelated refactors.

## Where
- Worktree: /root/projects/onolys/iaudit/.worktrees/review-main-audit, branch `fix/review-findings` (already checked out). Commit here. Never switch branches, never touch main or other worktrees (other agents work in /root/projects/onolys/iaudit and its other .worktrees/*). Never use bare `git stash`. No docker. No real cloud / Firebase / LLM / STT / email calls.
- Another coding agent may be working in this SAME worktree at the same time on a different area (e.g. you on api/, they on web/). So: `git add` ONLY the exact files you changed (never `git add -A` / `.`), commit with `git commit <paths>` style or after adding only your paths; if `index.lock` exists, wait a few seconds and retry. Don't revert or touch files you didn't change. Ignore their uncommitted files.
- Bash may need `dangerouslyDisableSandbox: true` (sandbox fails with a seccomp error here).
- Disk is tight (~1.2 GB). No `uv sync`, no `npm install`. Python: use `/tmp/iaudit-review-venv/bin/python -m pytest ...` (editable install of THIS worktree). Node: existing `web/node_modules`, `frontend/node_modules`, `eval/web/node_modules`. Python packages must be tested in separate pytest processes per package (helper module names collide). Use ports 19000-19999 for anything that listens.

## Firestore emulator (api Firestore-repo changes MUST be verified on it)
Java + jar exist: `java -jar ~/.cache/firebase/emulators/cloud-firestore-emulator-v1.22.0.jar --host=127.0.0.1 --port=<19xxx>` (start in background in the SAME bash command as the tests, or as a background process you kill afterwards). Then `FIRESTORE_EMULATOR_HOST=127.0.0.1:<port> GOOGLE_CLOUD_PROJECT=demo-test /tmp/iaudit-review-venv/bin/python -m pytest api/tests/<file> -m firestore -q -p no:xdist` (check api/tests conftest for the exact env names / project id it expects). Run only the firestore tests relevant to your change. Kill the emulator when done.

## Inputs
- Findings: `docs/agent_files/review-main-audit-20261124/FINDINGS.md` (merged; IDs like H-1, M-3, LM-5, and raw IDs A*/B*/C*/D*). Raw detail: `docs/agent_files/review-main-audit-20261124/findings-*.md`. Codex detail (incl. proposed fixes + test ideas): `docs/agent_files/review-whole-project-main-20261124-20261124-0529/review-2026-11-24-0529.md`.
- Re-read the actual code before changing it — findings cite lines at commit 6ffbf63 and earlier tasks on this branch may have moved them. If a finding turns out wrong, don't "fix" it; report it.
- Project rules: read `AGENTS.md` and `docs/mission.md` (scope: MITI 4.2.1 coding + report + tips; never invent quotations, speaker identities or timestamps). Do not use other docs as a spec.

## Method
- Test first: write a regression test that fails against current code for the right reason, watch it fail, implement minimal fix, watch it pass. Tests must be deterministic: fake clocks, barriers/events, fakes — no real sleeps, no network. Keep new tests small and fast (each well under 1 s); anything slow/emulator-matrix/property-campaign goes behind the existing `nightly` (python marker) or a nightly-only config — don't put slow tests in the PR path.
- Run ONLY tests you created or that your change impacts (the specific test files), plus lint/typecheck for touched package (`ruff check <pkg>`, `npx tsc --noEmit`, `npx eslint <files>`). Never the whole suite.
- If you change an API response/request model, regenerate contracts the way the repo does (`python -m onolys_api.openapi`, `python -m onolys_api.contracts`, web `schema.d.ts` generation — find the scripts) and keep them in sync.
- Mocks: if web mock (`web/src/mocks/`) mirrors server behavior you change, update it to match the real API.
- After 3 failed attempts on something, stop and report.

## Commit
One commit for the task: message `fix: <short summary> (<finding IDs>)`, body optional, ending with trailer:
`Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` (use the model you actually are).

## Report back (final reply, ≤25 lines)
Commit SHA; files changed; exact test commands + real pass/fail counts; each finding ID: fixed / partially / not fixed (why) / rejected (why); new issues noticed (don't act on them); anything needing the owner (cloud apply, product decision).
