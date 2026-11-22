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
| 03 | [03-web](03-web/PRD.md) | Rating card hidden behind `VITE_RATING_ENABLED`; upload screen = audio + goal + Submit (no time range); MITI-only report; no legacy stage names or old-report compat | 02 (stage names only) | 2 | PRD draft |
| 04 | [04-admin-shell](04-admin-shell/PRD.md) | admin backend drops engines, serves only `GET /v1/me`; frontend = sign-in + empty page | none | 1 | PRD draft |
| 05 | [05-cleanup](05-cleanup/PRD.md) | Tag `iaudit-archive` at 1cc7321, delete eaudit/paudit/evaluation/core/protocols/eval, CI + docs rewrite, infra cleanup + terraform apply, rename sweep, regenerate uv.lock | 01, 02, 03, 04 | 3 | PRD draft |
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
- Nobody uses prod: breaking changes are fine; no backward-compat, no deploy-ordering care (owner 2026-11-22).
- Rating card hidden behind `VITE_RATING_ENABLED` (default off); code kept.
- Upload screen = audio + change goal + one Submit; no user-entered time range. Engine/api picks the coded span automatically: whole session if <=20 min, else a reproducible random 20-min window. Submit locks everything. Sends `PUT /rating` `no_rating`, so existing run gate works with no api change.
- Web drops legacy stage names and old-report compatibility; stage names are `code|tips|assemble` only.
- CI job for `engines/miti` added in SP05 (SP01 writes unit tests only).
- Infra cleanup happens now: admin LLM secret env, `ROUTES_FILE`/`DEFAULT_PRESET` and `admin_llm` IAM removed (SP04); old Dockerfile env `PAUDIT_PROTOCOLS_DIR`/`IAUDIT_CONTRACTS_DIR` removed (SP02/SP04/SP05). Agent runs `terraform apply` for staging and prod (not owner-only); if credentials are missing at run time, record BLOCKED.
- Rename everything away from paudit/iaudit/eaudit: route names `paudit_*` -> `miti_*` (SP02); SP05 sweeps scripts, CI, infra names/labels (forced replacements fine; keep GCP projects and Terraform-state buckets), docs, README title -> "Onolys MITI".
- Archive tag `iaudit-archive` on 1cc7321, push to origin: approved (SP05). Delete only after it.
- Branch protection does not require checks by name: no manual step.
- Implementer-check items (SP04 `check-staging.py`, Dockerfile manifests, `uv.lock` regen; SP05 Dockerfile COPY, infra mentions) are resolved as "implementer verifies at coding time, existing default".
- SP06 is a code-only archive (no CI/build/secrets); new repo cloned at `/root/projects/onolys/iaudit-legacy`, no rename of existing local `iaudit` folder.
- Basic tips kept.
- Admin stays as shell (`GET /v1/me`).
- Report keeps no-rating shape, schema 0.0.1.

## Open questions

- [BLOCKED] SP06: new iaudit repo URL/name + push access (owner). Only SP06 waits; the rest proceeds.
- All other SP01-SP05 items are [RESOLVED] in their PRDs (owner 2026-11-22) or are implementer verify-at-coding-time notes with a default.

## Owner-only tasks

- Provide the new iaudit repo URL (and push access) for SP06.

## Next step

Run dev-tasks, then dev-code. SP06 starts when the repo URL is given.
