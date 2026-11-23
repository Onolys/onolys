---
stage: brainstorm
status: approved
summary: Compact footer, three-button nav, New Session chooser and Sessions list split, and a MITI-style (CASAA coded-transcript) report with a public sample at app.onolys.com/sample
date: 2026-11-23
---

# Public nav, sessions split & MITI-style report — brainstorm

## TL;DR
Tidy the app chrome and rebuild the report. Compact footer everywhere (app + miti landing). Nav becomes three buttons (Sessions, New Session, Sample report). `/` opens a New Session chooser; Sessions becomes its own list page. The report (real and sample) is redesigned after the MITI coded-transcript format (CASAA training transcript): at-a-glance scores, ranked feedback cards, behaviour counts, a full coded transcript table, method. The sample becomes a public page at app.onolys.com/sample, reached from miti.onolys.com/sample by redirect, opening in a new tab.

## Problem
Owner review of the current app: footer too tall (gaps, redundant "Questions?" line next to Contact); sample report is a small nav link; logged-in home mixes the "Sessions" heading, two start cards and the session list; nav items are plain links; the sample report reads as disjointed (yellow "Sample" banner, sticky right-side transcript panel with no clear purpose, sections not clearly separated, feedback/tips poorly formatted) and doesn't resemble how MITI coding is normally reported (reference: CASAA MITI 4 training transcript session 1 — table Utt# | P/C | utterance | Final code | Explanation, then Global Rating table). Users: MI practitioners practising; prospects evaluating via the sample.

## Decision log

| Decision | Alternative rejected | Why | By |
|---|---|---|---|
| Compact footer: one disclaimer line ("Not official MITI coding · Use it to practice and prepare · Role-play or de-identified transcripts only") + one line "Privacy · Terms · Contact · © year Onolys"; small type, tight padding, no gaps; drop "Questions?" line | keep current | too big, Contact covers it | owner |
| Same footer everywhere incl. miti landing (add Contact, Privacy, Terms → app.onolys.com/privacy, /terms) | app only | consistency | owner |
| Nav (logged in): Sessions, New Session, Sample report — all styled as buttons; account menu unchanged | links | owner request | owner |
| Nav (logged out): Sample report as a button centered in the nav; Log in, Sign up stay right | right-aligned link | owner request ("in the center"); placement read as nav-centered | owner / orchestrator read |
| `/` redirects to `/new` | `/` → sessions list | default landing is starting a session | owner |
| `/new` = chooser with the two existing cards (AI interview → /interviews/new; Rate a recording → /sessions/new upload form); no "Sessions" heading | keep Dashboard | owner request | owner |
| `/sessions` = past sessions list only (moved from Dashboard incl. pagination, chips, Report vN links); no "new" button; empty state points to New Session | list on home | owner request | owner |
| Report flow unchanged: submit → /sessions/:id → /sessions/:id/reports/:v; interview end → /sessions/:id; after the list move, any navigate("/") targets reviewed (SessionPage delete → /sessions, InterviewPage exit) | — | keep existing links working | orchestrator |
| Sample report opens in a new tab from the nav (both states) | same tab | owner request | owner |
| Sample lives in the app at public route `/sample` (old `/sample-report` redirects); miti.onolys.com/sample is a 301 redirect in the miti repo firebase.json to https://app.onolys.com/sample | static copy in miti Astro repo | one codebase, sample always matches the real report | owner |
| Redesign applies to real reports too, not only the sample | sample-only | sample must represent the product | owner |
| Coded transcript (CASAA format: Utt # \| Speaker \| Utterance \| Code(s) \| Why) lives in a large scrollable pop-up (modal dialog, ~88vh desktop, full-screen on phone, sticky header with close, collapsible code legend, sticky table header), opened by an "Open coded transcript" button in the Coded transcript section; every "Utterance N" reference in feedback and at-a-glance opens the pop-up scrolled to and highlighting that line | full table inline on page / side panel | ~50 utterances take too much space inline | owner (pop-up) + orchestrator (utterance links) |
| Section order: Header → At a glance (4 globals on 1–5 scale + 6 summary scores vs fair/good with status chips) → Feedback: ideas to try (ranked cards) → Behaviour counts (grouped, totals) → Coded transcript (button "Open coded transcript" opening the pop-up; legend and table inside the pop-up) → Method & limits | — | MITI format; feedback near top because it is actionable | owner (default) |
| "Why" text shown on every coded line | on click | readable, printable, matches CASAA | owner (default) |
| No engine instance-cap change | raise max_instances_shown | verified: cap is inert — compare.py:57-67 returns all counted instances, build.py:115-116 stores them; tone.py:84,111 only validates the setting | orchestrator |
| No clinician / "Your rating" columns, no "Onolys disagrees" comparison, no reasons-audit section in the new view | build comparison | own ratings are out of scope for now | owner |
| Replace yellow "Sample" banner with one grey line "Example report from a made-up role-play conversation." | banner | quieter, clear | owner |
| Tips as ranked cards: What was said (quote + utterance #) / Try instead (advice + example wording) / Why it matters; every tip must be a concrete change, not praise | current list | owner asked for better feedback format | owner + orchestrator |
| Sample data: the original 54-utterance drinking role-play (client's drinking crept up, ambivalent about cutting down), hand-coded per MITI; counts Q7 SR5 CR7 GI1 Persuade1 PwP3 AF2 Seek2 EA2 Confront1; globals 2/2/2/3 (CCT/SST/PAR/EMP); replaces the walking fixture; not CASAA text verbatim | copy CASAA transcript | CASAA reuse terms unstated; public commercial page | orchestrator (owner OK'd "something like that") |
| "Not coded" chip for pleasantries like closing thanks | code as GI | MITI convention | orchestrator |
| Approved visual mockup stays: https://claude.ai/artifact/1fj2vL8NmuvhRs7BRfWXAN | — | owner: "overall format looks good" | owner |
| Change the engine tips prompt in this branch so every tip is a concrete change (no praise-only tips) and its alternative includes example wording | sample-only | real reports must match the sample | owner |
| miti landing footer: keep the Enterprise/Individuals switch (as a small link in the links line) and the current contact email; only compact it | change them | not requested | owner |

### Builder-check calls (orchestrator)

| Call | Detail |
|---|---|
| "Why" text | = instance.rationale (web/src/api/report.d.ts:334-341) |
| Utt # | 1-based index of transcript turns |
| Several codes on one turn | all chips shown |
| Practitioner turn with no instance | shows "—" (sample fixture marks closing pleasantry "Not coded") |
| Summary score with null reference | no status chip |
| Clinician/rating comparison code (ratingEnabled flag, reasons_audit, headline "Onolys disagrees") | stays in code, not rendered by the new view |
| Sample fixture location | stays in web/src/mocks/fixtures |
| /sample nav | shows the normal nav for the visitor's auth state |
| Nav Sample report link | target="_blank" rel="noopener noreferrer" |
| Tests referencing /sample-report | updated: routes.flaky.test.tsx, legal.test.tsx, Dashboard.test.tsx |
| Real report transcript source | GET /sessions/{id}/transcript (TranscriptPanel.tsx:11-19) |
| miti /sample redirect | goes in the `miti` hosting target's redirects in miti/firebase.json |
| miti footer tests | updated (e.g. foundation.test.ts) |

## Design
The work splits into eight parts. Each is small on its own; the report view is the largest.

| # | Part | Where |
|---|---|---|
| 1 | Footer component | web/src/routes/Footer.tsx + app.css `.app-footer`; miti repo src/components/Footer.astro |
| 2 | Nav (three buttons, centered Sample report when logged out) | web/src/routes/Layout.tsx |
| 3 | Routes: `/` → `/new`; new `/new` chooser (cards from features/dashboard/Dashboard.tsx); new `/sessions` list page (list code from Dashboard.tsx, query key ["sessions"]); `/sample` public; `/sample-report` → `/sample` | web/src/routes/routes.tsx |
| 4 | Report view: new sections; coded transcript in a pop-up (modal), built by joining transcript turns with behaviour instances (turn_id + code-point offsets); utterance links open it at that line. The real report fetches its transcript the way TranscriptPanel does today | features/report/ReportSections.tsx, ReportPage.tsx, SampleReportPage.tsx |
| 5 | Engine instance cap: no change (verified inert) | — |
| 6 | Sample fixture replaced with the new role-play | web/src/mocks/fixtures/report.ts, transcripts.ts |
| 7 | miti repo: firebase.json redirect /sample → app.onolys.com/sample, plus footer | separate repo, separate PR |
| 8 | Engine tips prompt: every tip a concrete change, alternative includes example wording; built by tips.py | engines/miti/src/onolys_miti/data/prompts/tips_system.md (built in engines/miti/src/onolys_miti/tips.py) |

## Goals / non-goals / anti-goals
**Goals**
- All owner feedback items addressed.
- Sample is public, consistent (counts match the transcript) and opens in a new tab.
- Real reports use the same view as the sample.

**Non-goals**
- Clinician / own-ratings UI.
- Linking the sample from the miti landing hero (later).
- Schema changes.
- Design-system migration (the feat/design-system branch handles that separately).

**Anti-goals**
- A sample whose numbers don't match its own transcript.
- A report that looks like separate disconnected widgets.
- Breaking existing report links (/sessions/:id/reports/:v).

## Open risks
- Prod reports made by older engine versions might have capped instances — verify on a sample of stored reports before relying on the full coded transcript.
- Mapping instances to utterances when one turn has several codes or spans split turns. Test: render the fixture plus one real report.
- Conflict with feat/design-system SP2 (app migration to onolys-ui) touching the same files. Mitigation: land this first; SP2 rebases.
- The miti redirect is in a separate repo and deploy.
- App CSP is strict (no inline styles), so new components must use classes.
