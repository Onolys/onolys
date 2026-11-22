---
status: draft
summary: Index — slim Onolys to a lean MITI-only engine; move iaudit to its own repo
date: 2026-11-22
---
# MITI lean engine — design index

TL;DR: Onolys only does MITI coding (10 behavior codes per clinician utterance, 4 globals, summary scores, evidence) + basic tips; it no longer evaluates clinician self-ratings.
New `engines/miti` (`onolys_miti`) replaces core+paudit+evaluation; eaudit dropped; admin site becomes a sign-in + empty shell.
iaudit material is deleted after tag `iaudit-archive` and moved to a separate repo (blocked on owner's GitHub URL).

## Sub-projects

| # | Folder | Scope | Depends on | Phase | Status |
|---|--------|-------|------------|-------|--------|
| 01 | [01-engine-miti](01-engine-miti/PRD.md) | New `engines/miti` (`onolys-miti`): MITI-hardcoded coding + tips + no-rating report, plus STT/voice/LLM infra api needs | none | 1 | PRD draft |
| 02 | [02-api-switch](02-api-switch/PRD.md) | api imports switch to `onolys_miti`; stages `code\|tips\|assemble`; rating endpoints kept, ignored by run | 01 | 2 | PRD draft |
| 03 | [03-web](03-web/PRD.md) | Rating card hidden behind `VITE_RATING_ENABLED`; session-setup form; MITI-only report; legacy stage names accepted | 02 (stage names only) | 2 | PRD draft |
| 04 | [04-admin-shell](04-admin-shell/PRD.md) | admin backend drops engines, serves only `GET /v1/me`; frontend = sign-in + empty page | none | 1 | PRD draft |
| 05 | [05-cleanup](05-cleanup/PRD.md) | Tag `iaudit-archive` at 1cc7321, delete eaudit/paudit/evaluation/core/protocols/eval, CI + docs rewrite, regenerate uv.lock | 01, 02, 03, 04 | 3 | PRD draft |
| 06 | [06-iaudit-repo](06-iaudit-repo/PRD.md) | Code-only iaudit archive: new repo from tag via git filter-repo (no CI/build); new clone at `/root/projects/onolys/iaudit-legacy`, no local rename | 05 + owner repo URL | 4 | PRD draft — BLOCKED on repo URL |

## Dependency graph

```
01 → 02 → 03
          ↘
04 ──────→ 05 → 06 (blocked)
```

(05 needs 01, 02, 03, 04 all landed.)

## Locked decisions

- Coding goal is MITI-only.
- One engine `engines/miti` with MITI hardcoded (reverses 2026-11-20 protocol-agnostic call); core merged into miti.
- Rating card hidden behind `VITE_RATING_ENABLED` (default off); code kept.
- Setup fields (change goal required, coded span optional) live on the upload screen with a single submit (no separate setup form); sends `PUT /rating` `no_rating`, so existing run gate works with no api change.
- CI job for `engines/miti` added in SP05 (SP01 writes unit tests only).
- SP06 is a code-only archive (no CI/build/secrets); new repo cloned at `/root/projects/onolys/iaudit-legacy`, no rename of existing local `iaudit` folder.
- Basic tips kept.
- Admin stays as shell (`GET /v1/me`).
- Delete only after tag `iaudit-archive` on 1cc7321.
- Stage names `code|tips|assemble`; web accepts legacy names.
- Report keeps no-rating shape, schema 0.0.1; old stored reports render Onolys-only.

## Cross-cutting risks / open questions

SP01
- [OPEN-1] PyPI clash for name `miti` not checked (offline); `onolys_miti` avoids it.
- [RESOLVED: CI job added later in SP05, owner 2026-11-22]
- [OPEN-3] `PackError`/`PackRef`: keep out unless `error_map.py` needs it.
- [OPEN-4] `admin/backend` still imports old packages until SP04; SP05 must wait for both.

SP02
- [RESOLVED: Option A — upload screen sends change goal + optional span via PUT /rating no_rating in one submit; no api change, owner 2026-11-22] (OPEN-1 run gate); verify empty `change_goal` OK.
- [OPEN-2] SP01 interface gaps api needs (schema path accessors, `validate_rating` w/o Pack, scenarios dir, `Issue`, fixtures, `RunContext`/`whole_second_span` paths); SP01 lists them in its README.
- [OPEN-3] In-flight runs during deploy may show stale step label; accepted.
- [OPEN-4] `paudit_code`/`paudit_globals` route names need prod route migration; deferred.
- [OPEN-5] Cloud Run env still sets old vars; harmless; cleanup in SP05 or infra change (owner) if applied to prod.
- [OPEN-6] Image size/memory of dropped deps unverified; measure with `docker build`.

SP03
- [OPEN] Flag off locks setup after one submit (`rating_final`); mistyped goal not correctable; accepted, revisit with SP02 Option B.

SP04
- [OPEN] Does `check-staging.py` or its tests assert admin env has LLM keys/`ROUTES_FILE`? Confirm before R11.
- [OPEN] Other uv workspace manifests the Dockerfile must still COPY; re-read root `pyproject.toml` at coding time.
- [OPEN] `uv.lock` changes; rebase conflicts with SP01 likely; regenerate with `uv lock`.
- Infra: `terraform apply` for admin infra changes (owner).

SP05
- [OPEN-1] Tag push permission/protection; does `iaudit-archive` already exist (owner). Default: push, stop if refused.
- [OPEN-2] Branch-protection required checks may name removed jobs; replace with `miti` after merge (owner).
- [OPEN-3] `api/Dockerfile` COPY of `docs/contracts/*.schema.json`/`config`; depends on SP02; verify image build.
- [OPEN-4] `infra/` mentions assumed untouched (secrets only).

SP06
- [OPEN-1] New repo URL/name + push access; whole SP waits (owner).
- [RESOLVED: /root/projects/onolys/iaudit-legacy, no rename, owner 2026-11-22] (local folder; new `onolys/iaudit-legacy` README rows)
- [RESOLVED: not needed, code-only archive, owner 2026-11-22] OPEN-3 `changes.sh`, OPEN-4 core pruning, OPEN-5 nightly secrets.

## Next step

Owner reviews PRDs, marks each [OPEN] as [RESOLVED: …] or [DEFERRED], then run dev-tasks.
