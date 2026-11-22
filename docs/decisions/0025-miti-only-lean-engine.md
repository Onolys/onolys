# 0025. MITI-only lean engine

**Audience:** contributors.

**Status:** accepted 2026-11-22. Supersedes [0017](0017-workspace-routes-shared-core.md), [0018](0018-protocol-pack-data-vs-code.md), [0019](0019-evaluation-engine-and-concern-suppression.md) and [0023](0023-admin-deployment-and-auth.md) (in part: the admin site is now a sign-in shell).

**Context.** Onolys now does one thing: code a session against MITI 4.2.1 and give a report with tips. The 2026-11-20 platform plan had three engines (evidence audit, protocol audit with scoring, clinician audit) over a shared core, and ADRs 0017 and 0018 made the engines protocol-agnostic. Only the MITI coding is used. The extra engines, the clinician self-rating comparison and the old admin review and eval UI add code, CI time and docs nobody needs. Nobody uses prod, so breaking changes are fine.

**Decision.**

- **One engine, MITI hardcoded.** `engines/miti` (`onolys_miti`) holds the MITI definition, prompts, fixtures, report schema, the LLM routes, speech-to-text and the voice adapter. This reverses the protocol-agnostic design of 0017 and 0018. The MITI pack data (`pack.yaml`, `report.yaml`, `rating.schema.json`, prompts) is a fixed file set inside the package, read directly by the engine code (`rules.py`, `score.py`, `result.py`); there is no pack loader, no pluggable protocol packs and no per-protocol hooks.
- **The api uses `onolys_miti` only.** Run stages are `code`, `tips`, `assemble`. The rating endpoints stay, but a run does not compare the rating card.
- **Deleted:** `engines/{core,eaudit,paudit,evaluation}`, `protocols/`, `eval/` (with datasets), the old admin review and eval UI, the eaudit contracts and docs, ADRs 0001-0016 and the concept, implementation and example docs that described them.
- **Admin is a shell.** The admin backend serves only `GET /v1/me` behind the login check. The admin frontend is sign-in plus an empty page. The auth model of 0023 is unchanged.
- **Archive tag `iaudit-archive`** points at commit `1cc7321`, the last commit that holds everything deleted here: `engines/{core,eaudit,paudit,evaluation}`, `protocols/`, `eval/` including datasets, the old frontend review and eval UI, the eaudit docs and contracts, ADRs 0001-0016, the `docs/agent_files/` history, and the CI and nightly workflows at that commit. Tags are never moved.

**SP06 recipe (the separate legacy repo).** The new repo is owned by SP06 and waits for the owner to create the GitHub repo. In the new repo:

```bash
git clone --no-local <onolys> iaudit
cd iaudit
git checkout iaudit-archive
```

Use `git filter-repo` instead of a plain checkout if the history should be kept. Then delete what the legacy repo does not need (`api/`, `web/`, `admin/`, `infra/` and similar). It is a code-only archive: no CI, no build, no secrets.

**Consequences.** Smaller code and docs; one place for MITI facts. Anything from the old engines is read from the tag or the legacy repo, not from `main`. Ground truth for the engine is `engines/miti/README.md`.
