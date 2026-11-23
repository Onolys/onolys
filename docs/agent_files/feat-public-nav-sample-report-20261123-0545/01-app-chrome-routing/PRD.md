---
status: approved
summary: Compact footer, three-button nav (Sessions / New Session / Sample report), `/` redirects to a new `/new` chooser, `/sessions` becomes the past-sessions list, `/sample` public route wiring with `/sample-report` redirect; page content of /sample is SP2.
date: 2026-11-23
---
# PRD: App chrome and routing

Repo/branch: iaudit / `feat/public-nav-sample-report` · Depends on: none (SP2 supplies `/sample` page content; SP1 wires it to the existing `SampleReportPage`) · Owns: `web/src/routes/{routes.tsx,Layout.tsx,Footer.tsx,placeholders.tsx,RouteError.tsx}`, `web/src/features/dashboard/*` (split into New Session + Sessions pages), `web/src/features/session/SessionPage.tsx` (navigate/link targets only), `web/src/features/interview/{InterviewPage,NewInterviewPage}.tsx` (navigate/link targets only), nav/footer/layout rules in `web/src/styles/app.css`, tests listed below. Does NOT own report CSS or `features/report/*`.

## TL;DR
Footer shrinks to two small lines. Logged-in nav becomes three buttons. `/` redirects to `/new`, a chooser page holding the two start cards moved out of `Dashboard`. The session list moves to `/sessions`. The sample report gets a public route `/sample`; `/sample-report` redirects there. Pure front-end restructure: no API, schema or engine change.

## Problem
- Footer is tall (3.5rem padding, 5 blocks, redundant "Questions?" line next to Contact). [verified: `web/src/routes/Footer.tsx:8-24`, `app.css` `.app-footer` padding `3.5rem`]
- "Sample report" is a plain nav link; Sessions/New session are plain links. [verified: `Layout.tsx:7-20`]
- Home (`/`) mixes h1 "Sessions", two start cards and the list. [verified: `Dashboard.tsx` h1 at ~113, `landing-cards`, `useInfiniteQuery client.GET("/sessions")`]
- Sample report is only reachable from the Dashboard empty state and nav, in the same tab, at `/sample-report`.

## Goals / Non-Goals
**Goals**
- Compact footer used by every route (single `Footer` component).
- Nav per auth state exactly as in Requirements.
- `/new` chooser, `/sessions` list, `/` -> `/new`, `/sample` public, `/sample-report` -> `/sample`.
- Every internal link/navigate that meant "home/sessions list" re-pointed deliberately.

**Non-Goals**
- Report view, sample content, fixtures, tips prompt (SP2). Any report CSS.
- miti landing (SP3). Account menu changes. Design-system migration (feat/design-system).
- Pagination/polling behaviour changes: moved verbatim.

## Requirements

**Footer** (`Footer.tsx`, `app.css` `.app-footer*`)
1. Line 1: `Not official MITI coding · Use it to practice and prepare · Role-play or de-identified transcripts only`.
2. Line 2: `Privacy · Terms · Contact · © <current year> Onolys` (Privacy -> `/privacy`, Terms -> `/terms` via `Link`; Contact -> `mailto:${CONTACT_EMAIL}` from `config.ts`). Separator is a CSS `::before` dot, as today.
3. Small type (~0.8rem), padding ~`var(--space-3)` vertical, no margins between lines, no border rule, no "Questions?" line. Keep colours/tokens.

**Nav** (`Layout.tsx` `NAV`, `app.css`)

| Phase | Items |
|---|---|
| verified | `Sessions` (`/sessions`), `New Session` (`/new`), `Sample report` (`/sample`, `target="_blank" rel="noopener noreferrer"`); all `btn btn-secondary`-style buttons; account menu unchanged |
| signedOut | `Sample report` button centred in the nav; `Log in`, `Sign up` stay right (current classes `nav-login`, `btn btn-primary nav-signup`) |
| unverified / loading | unchanged (brand only / empty) |

4. Sample report link renders as a plain anchor/`Link` (not `NavLink`) so it never shows an active state and opens a new tab in both signed-in and signed-out states.
5. Brand link `to="/"` kept (redirects to `/new` for verified; signed-out hits the guard -> login, same as today).
6. Layout keeps working at phone width (wrap, 44px touch targets as existing `.nav-login`).

**Routes** (`routes.tsx`)
7. `{ path: "/", element: <Navigate to="/new" replace /> }` (inside or outside `RequireVerified`: outside is fine, `/new` itself is guarded; signed-out gets `next=/new`).
8. Inside `RequireVerified`: `/new` -> `NewSessionChooser`, `/sessions` -> `SessionsPage`. Existing `/sessions/new`, `/interviews/*`, `/sessions/:id`, `/sessions/:id/reports/:version`, `/settings` untouched. `/sessions` is a static path, no clash with `/sessions/:id`.
9. Public (outside `RequireVerified`, next to `/privacy`): `{ path: "/sample", element: <SampleReportPage /> }` and `{ path: "/sample-report", element: <Navigate to="/sample" replace /> }`. SP2 replaces what `SampleReportPage` renders; SP1 does not edit it.

**New Session chooser (`/new`)**
10. Content = the two existing `landing-card` sections from `Dashboard.tsx` unchanged (AI interview -> `/interviews/new` incl. `usage` query, `interviewBlocking` disabled "Start AI Interview" and `UsageLeft`; Rate a recording -> `/sessions/new`). No "Sessions" heading. Page needs an h1 for the focus-on-route-change effect in `Layout.tsx` ("New Session").

**Sessions list (`/sessions`)**
11. Moved verbatim: `useInfiniteQuery(["sessions"])`, `sessionsRefetchInterval` polling from `chips.ts`, status chips, "Report vN" links, error card/"Try again", "Load more". h1 "Sessions". No "new" button.
12. Empty state: short text plus `Link` to `/new` ("Start a new session"); drop the in-page "See a sample report" link (it is in the nav now).
13. Dashboard component/folder is removed or reduced to the two pages above; shared bits (`STATUS_CHIP`, usage hooks) stay importable.

**Re-pointed targets** [verified: `grep -rn 'navigate("/")\|to="/"' web/src`]

| Site | Today | New |
|---|---|---|
| `SessionPage.tsx:99` navigate after delete | `/` | `/sessions` |
| `SessionPage.tsx:114` "Back to your sessions" | `/` | `/sessions` |
| `InterviewPage.tsx:184` navigate after discard | `/` | `/sessions` |
| `InterviewPage.tsx:224,238` "Back to your sessions" | `/` | `/sessions` |
| `InterviewPage.tsx:268` "Not now" | `/` | `/new` (user was starting something) |
| `NewInterviewPage.tsx:140` "Cancel" | `/` | `/new` |
| `placeholders.tsx:20` NotFound "Back to your sessions" | `/` | `/sessions` |
| `RouteError.tsx:9` "Back to the start" | `/` | `/` (unchanged, resolves to `/new`) |

## Architecture
- Pure router + component move. `Dashboard.tsx` splits along its existing seam: JSX under `<h1>Sessions</h1>` `landing-cards` -> `NewSessionChooser`; `sessions` query, `body` branching and list -> `SessionsPage`. No logic rewrite, so query keys, polling and cache behaviour are unchanged.
- `Layout.tsx`: `NAV` entries gain optional `external`/`className`; the signed-out nav keeps `nav-out`. Centering: CSS only. Options are `margin-inline: auto` on the first child plus `margin-left: auto` on `.nav-login`, or a 3-column grid; implementer picks, must stay readable when wrapped on phones.
- CSP: all styling via classes in `app.css`; no `style=` attributes in markup [verified: `firebase.json` CSP `style-src 'self'`].
- Shared files with SP2: `web/src/styles/app.css` only (both append). SP1 edits only the `.app-header`, `.nav-*`, `.app-footer*` rules and adds new page rules at the end of its own block; SP1 must not touch report CSS. `routes.tsx` is SP1-only; SP2 must not edit it (`SampleReportPage` file path and export name stay stable).

## Decisions

| # | Decision | Choice | Alternatives considered | Why |
|---|---|---|---|---|
| 1 | `/` redirect mechanism | `<Navigate replace>` route | loader `redirect()` | simplest, matches existing guard components |
| 2 | Sample link element | plain `Link` with `target=_blank` | `NavLink` | no active state; new tab per brief |
| 3 | Footer separators | CSS `::before` dots on `li` | text separators | keeps existing test-friendly markup |
| 4 | Keep `/sample-report` | redirect to `/sample` | delete | old links (and miti) keep working |
| 5 | Move code, do not rewrite | split `Dashboard.tsx` | rewrite lists | zero behaviour risk for polling/pagination |
| 6 | "Not now"/"Cancel" targets | `/new` | `/sessions` | user abandoned starting, not browsing |

## Manual steps
- None for deploy beyond normal app deploy. Owner visually checks nav centring on a phone width.

## Risks / Open Questions
- Many tests render `/` and expect h1 "Sessions" (now lands on `/new` with no Sessions h1): `auth/pages.test.tsx:118,181,318`, `auth/guards.test.tsx:37,48,53`, `routes/routes.test.tsx:9,50`, `flows/flows.test.tsx` (many), `routes/layout.test.tsx:49-109`. [RESOLVED: auto default - tests that mean "land signed in" assert the `/new` h1; tests about the list render `/sessions`]
- Post-login `readNext` default `/` now ends at `/new`; `pages.test.tsx:182,444` assert pathname `/`. [RESOLVED: auto default - keep `next.ts` unchanged, update those assertions to `/new`]
- Active highlighting on `/sessions/new` (matches Sessions prefix). [RESOLVED: auto default - `Sessions` uses `end`; no special casing]
- Button style class for nav buttons. [RESOLVED: auto default - reuse `btn btn-secondary`; verified in Dashboard "Load more"]
- Conflict with feat/design-system SP2 on `Layout.tsx`/`app.css`. [RESOLVED: auto default - land this first, other branch rebases (per brief)]
- Naming: nav label casing "New Session" differs from existing "New session". [RESOLVED: auto default - use "New Session"; update `routes.test.tsx:10`, `flows.test.tsx:98`, `layout.test.tsx:51`]

## Tests to update/add
- Update: `routes/routes.flaky.test.tsx:12`, `routes/legal.test.tsx:49-56` (footer text, link names Privacy/Terms), `routes/routes.test.tsx:8-10`, `routes/layout.test.tsx` (navNames, footer), `features/dashboard/Dashboard.test.tsx` (split into `NewSession` + `Sessions` tests; empty-state link now to `/new`), `auth/guards.test.tsx:28-29`, `flows/flows.test.tsx:364`, plus those in Risks. `features/report/SampleReportPage.test.tsx` is SP2's (route strings only: SP1 changes `/sample-report` -> `/sample` there to stay green, SP2 owns the rest).
- Add: `/` redirects to `/new`; `/sample-report` redirects to `/sample`; `/sample` reachable signed out; nav per phase incl. `target=_blank rel`; each re-pointed navigate target.
- E2E `web/e2e_review/*.cjs`: `mobile.spec.cjs:8` PUBLIC list (`/sample-report` -> `/sample`), `signed-out.spec.cjs:41` screenshot name/route; owner-run (not in unit suite).

## Acceptance Criteria
- Footer on every page is two lines, matching the text above, with no "Questions?" and no "All rights reserved".
- Signed in: nav shows Sessions, New Session, Sample report as buttons; Sample report opens `/sample` in a new tab with `rel="noopener noreferrer"`.
- Signed out: Sample report button is centred; Log in and Sign up right; unverified: brand only.
- `/` lands on `/new`; `/new` shows both cards (cap-disabled interview button still works) and no "Sessions" heading.
- `/sessions` shows past sessions with polling, chips, Report vN links, Load more; empty state links to `/new`.
- `/sample` loads signed out; `/sample-report` ends at `/sample`.
- Deleting a session or discarding an interview lands on `/sessions`.
- Only tests created/impacted run green; no inline `style=` attributes added.
