---
status: draft
summary: miti landing gets the compact two-line footer (legal links to the app) and a 301 /sample redirect to the app sample report.
date: 2026-11-23
---
# Tasks: miti landing footer and sample redirect
Source of truth: 03-miti-landing/PRD.md. Separate repo (`/root/projects/onolys/miti`), separate PR. CI (`.github/workflows/ci.yml`) already runs check, unit tests, build and playwright, so no CI task.

| # | Task | Depends on | Status |
|---|---|---|---|
| 1 | Compact footer | none | done |
| 2 | 301 redirect /sample to app | 1 | done |

## Task 1 — Compact footer
What it is / what it means: First step: in the miti repo create worktree `.worktrees/feat-compact-footer-sample-redirect` on branch `feat/compact-footer-sample-redirect` off `origin/main` (not local main, which is stale), then `npm ci`. Then make the footer match the app's two-line footer (Requirements 1-4, 6; Decisions 1, 2).
What changes at a high level: `Footer.astro` renders line 1 (`data-inline-list`, three `li`, shorter disclaimer) and line 2 `Privacy · Terms · Contact · switch · © 2026 Onolys` with absolute app URLs for Privacy/Terms, the existing mailto, and the page switch (Enterprise / Individuals) as a small link keeping `data-footer-switch`. Remove the "Questions?" paragraph, long switch sentences and "All rights reserved". Small scoped styles, no inline `style=`, tokens unchanged.
Done when: updated `src/components/foundation.test.ts` (li texts, line 2 text, hrefs, mailto, no "Questions?", one `footer ul`, switch link) and `e2e/learner.spec.ts` / `e2e/enterprise.spec.ts` footer assertions pass; learner footer has exactly one `a[href="/enterprise"]`, enterprise has an `a[href="/"]` switch; `enterprise-isolation.test.ts` stays green.

## Task 2 — 301 redirect /sample to app
What it is / what it means: Forward `miti.onolys.com/sample` to the public app sample report (Requirement 5, Decisions 3, 4).
What changes at a high level: Add a `redirects` entry to the `miti` hosting target in `firebase.json`: source glob `/sample{,/}`, destination `https://app.onolys.com/sample`, type 301. The `redirect` target is untouched.
Done when: a vitest (written first) reads `firebase.json` and asserts the `miti` target redirect (source, 301, destination), valid JSON, and the `redirect` target unchanged; it passes.

## Closing note — manual steps
Owner reviews and merges the PR; the `miti` hosting target deploys on merge. Merge only after the app's `/sample` is live (SP1 and SP2 deployed), otherwise the redirect 404s. After deploy, owner opens `https://miti.onolys.com/sample` and confirms it lands on the app sample (also smoke-checks redirect type).
