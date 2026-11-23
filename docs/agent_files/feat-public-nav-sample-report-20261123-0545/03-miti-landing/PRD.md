---
status: approved
summary: miti.onolys.com gets the same compact two-line footer (Privacy/Terms link to the app) and a 301 redirect /sample -> https://app.onolys.com/sample; separate repo, separate PR.
date: 2026-11-23
---
# PRD: miti landing footer and sample redirect

Repo/branch: `/root/projects/onolys/miti` (Astro static site), new worktree off `origin/main` (59b5146; local `main` is behind at f34f12f, do not branch from it) · Depends on: SP1 (`/privacy`, `/terms` already exist in the app; `/sample` must exist before the redirect is useful, so deploy after SP1 and SP2 are live) · Owns: `src/components/Footer.astro`, `firebase.json` (`miti` target redirects), `src/components/foundation.test.ts`, `e2e/learner.spec.ts`, `e2e/enterprise.spec.ts` (footer assertions only)

## TL;DR
Make the landing footer match the app's compact footer, link Privacy/Terms to app.onolys.com, keep the Enterprise/Individuals switch as a small link on the links line, and add a 301 from `/sample` to the public app sample report.

## Problem
- Footer is 4 stacked blocks with 3.5rem padding, a "Questions?" line duplicating contact, and no Privacy/Terms. [verified: `src/components/Footer.astro`]
- The landing has no route to the sample report; the app will serve it at `/sample` (SP1/SP2), so `miti.onolys.com/sample` should forward there.

## Goals / Non-Goals
**Goals**
- Same two footer lines as the app, small and tight.
- `miti.onolys.com/sample` -> 301 -> `https://app.onolys.com/sample`.
- Existing footer tests updated, no other test regresses.

**Non-Goals**
- Linking the sample from the hero (later, per brief). Any copy/design change outside the footer. Hosting a copy of the sample in Astro. Touching the `redirect` hosting target (catch-all to miti.onolys.com stays).

## Requirements
1. Footer line 1 (`<ul data-inline-list>`, 3 `li`): `Not official MITI coding` / `Use it to practice and prepare` / `Role-play or de-identified transcripts only`. (Drops "and cannot be submitted as one.")
2. Footer line 2: `Privacy · Terms · Contact · © 2026 Onolys`, plus the page switch as a small link in the same line: Individuals page shows `Enterprise` -> `/enterprise`; Enterprise page shows `Individuals` -> `/`. Order: `Privacy · Terms · Contact · <switch> · © 2026 Onolys`.
3. Privacy -> `https://app.onolys.com/privacy`, Terms -> `https://app.onolys.com/terms` (absolute; plain links, same tab). Contact -> `mailto:tejitpabari99@gmail.com` (current address, unchanged).
4. Remove the "Questions?" paragraph, the long switch sentences (`Individuals? Click here — ...`), and "All rights reserved". Small type (~0.8rem), padding ~0.75-1rem block, no gaps, no border rule. Colours/tokens unchanged.
5. `firebase.json` `miti` target gets `"redirects": [{ "source": "/sample", "destination": "https://app.onolys.com/sample", "type": 301 }]`. Also cover the trailing form: `"/sample{,/}"` as one glob source [verified: Firebase supports `{a,b}` globs; same style as the existing `"/enterprise{,/,.html}"` header source].
6. Year stays the literal `2026` as today unless `Footer.astro` already computes it; do not add runtime date logic. [RESOLVED: auto default - keep static `© 2026`]

## Architecture
- `Footer.astro` keeps the `page: 'learner' | 'enterprise'` prop; the ternary now picks only the small switch link (`data-footer-switch` attribute kept on that element so selectors/tests stay meaningful).
- Scoped `<style>` in the component is used (Astro-emitted, no inline `style=` attribute); keep the existing `--tone-footer` token.
- Redirect lives in hosting config, not Astro: `cleanUrls: true` + `trailingSlash: false` do not interfere because there is no `src/pages/sample*` [verified: `grep -rin sample e2e src` found no `sample` page; only data copy]. Redirects are evaluated before static files in Firebase Hosting.
- Isolation rule to keep: the learner page links `/enterprise` only from header and footer, exactly one `footer a[href="/enterprise"]` [verified: `e2e/enterprise.spec.ts:133`, `enterprise-isolation.test.ts:25`]; the Enterprise page's footer links `/`.

## Decisions

| # | Decision | Choice | Alternatives considered | Why |
|---|---|---|---|---|
| 1 | Switch placement | small link in line 2 | own line | brief: footer two lines |
| 2 | Legal links | absolute app URLs | add legal pages to miti | one source of truth, per brief |
| 3 | Redirect type | 301 in `miti` target | 302; Astro redirect | permanent; works as static hosting config |
| 4 | Redirect scope | `/sample` and `/sample/` | exact only | trailing slash is common |
| 5 | Branching | new worktree off `origin/main` | local main | local main is stale |

## Manual steps
- Review and merge the PR; deploy of the `miti` hosting target happens on merge (owner/CI). Not before the app's `/sample` is live, otherwise the redirect 404s.
- After deploy: owner opens `https://miti.onolys.com/sample` and checks it lands on the app sample.

## Risks / Open Questions
- Footer tests assert old text: `src/components/foundation.test.ts:54-71` (li texts, `Questions? Reach out to ...`, `.copy` text `© 2026 Onolys. All rights reserved.`), `e2e/learner.spec.ts:49` (`...and cannot be submitted as one.`). [RESOLVED: auto default - update to the new strings; keep the `data-inline-list`, one `footer ul`, switch-link and mailto assertions]
- Deploy ordering vs the app (redirect before `/sample` exists). [RESOLVED: auto default - manual step above; merge after SP1+SP2 deployed]
- Whether to test the redirect. [RESOLVED: auto default - vitest reads `firebase.json` and asserts the `miti` target redirect entry (301, destination); live check is manual]
- Redirect `type` on emulator vs prod. [DEFERRED: owner smoke-check after deploy]

## Acceptance Criteria
- Learner and Enterprise pages render a footer of exactly two lines: the disclaimer line and `Privacy · Terms · Contact · switch · © 2026 Onolys`.
- Privacy/Terms hrefs are `https://app.onolys.com/privacy` and `/terms`; Contact is `mailto:tejitpabari99@gmail.com`; no "Questions?" text in the footer.
- Learner footer has exactly one `a[href="/enterprise"]`; Enterprise footer has an `a[href="/"]` switch.
- `firebase.json` `miti` target contains the 301 `/sample` -> `https://app.onolys.com/sample` rule; `redirect` target unchanged; JSON valid.
- Updated vitest footer tests and `e2e/learner.spec.ts` footer assertion pass; no unrelated test changed.
