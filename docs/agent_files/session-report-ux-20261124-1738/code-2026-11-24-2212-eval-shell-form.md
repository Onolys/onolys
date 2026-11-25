---
status: done
summary: Eval shared UI shell and explicit New Run configuration form implemented and verified offline.
date: 2026-11-24
---

# Eval shell and New Run form

Scope: eval/web shell, authentication presentation, form, API types and build styling. History/RunView implementation and their props are unchanged. Shared ConfigDialog remains with the next task; New Run shows a brief saved-input identification rather than a raw configuration preview.

Implemented actual @onolys/ui v0.3.0 AppHeader, SkipLink, Button and avatar DropdownMenu, matching web's tag and resolved commit 1d0d1b2c00ca079b8da841aa8d919bd6d219d69b. Added Tailwind's Vite plugin/theme source and retained Comparison's table styles, scroll behavior and native controls. The content area uses 80% width with responsive fallbacks. New Run/History navigation preserves unrelated query parameters and browser navigation; history state retains a saved rerun draft without calling its POST endpoint. Signed-in users retain avatar signout after an access denial; allowlist checks still gate protected content.

Added optional name (200 characters) and description (4,000 characters) inputs and API types. Saved values, engines, selections and repeats are prefilled. Empty saved details serialize as null to clear them. New blank details are omitted. Missing saved engine/model/tier/effort choices remain checked and visibly unavailable, blocking submission until explicitly removed/replaced. A 409 from the saved-resolution check remains a visible API error. Input/session configuration is preserved through the existing rerun endpoint. No GET/navigation starts a run.

Dataset metadata now uses spaced definition-list rows. Range progress fills through the maximum (12/12 tested) with native keyboard and accessible value text. Engines/models/tiers/efforts share a responsive four-column row. Repeat help explains repeated coding and Human's once-per-session score.

## Test-first evidence

Before implementation:
- `npm test -- --run src/NewRun.test.tsx`: 2 failed, 27 passed. The new tests failed on missing 100% range fill and missing checked retired engine choice (plus missing metadata inputs).
- `npm test -- --run src/Root.test.tsx`: 1 failed, 6 passed. The new denied-access test failed because Account menu did not exist.

After implementation:
- `npm test -- --run src/NewRun.test.tsx src/Root.test.tsx src/auth/AuthGate.test.tsx src/api.test.ts src/Runs.test.tsx`: **5 files passed, 112 tests passed**. Includes saved draft back-navigation, explicit submission, details clearing, all unavailable selection dimensions, authentication, API transport, History and Comparison regressions.
- `npm run build`: TypeScript passed; Vite built 2,254 modules successfully (CSS 50.81 kB, JS 484.51 kB).
- `npm run lint`: passed, no diagnostics.
- `git diff --check -- eval/web`: passed.

No live provider calls, cloud operations, deployment or browser execution. Installation reported existing Firebase engine requirements above this machine's Node 22 and an npm audit total of four high findings; no dependency remediation was attempted outside this UI task.
