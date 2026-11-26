---
status: done
summary: NEEDS_CHANGES — 2 must-fix
date: 2026-11-26
---
# Review — 2026-11-26 — full branch
Diff: origin/main...dc8b3ea3   Personas: Bug Hunter, Security, Architect

## Verdict: NEEDS_CHANGES

### Must-fix
1. [Bug] eval/web/src/Shell.tsx link() builds hrefs from url.pathname. Root.tsx now serves only path="/" and other paths render <ErrorPage notFound />, so on /foo the brand and New Run/History tabs point at /foo and stay on the 404.
2. [Architect] eval/web/src/ColdStart.tsx duplicates web/src/components/SlowStart.tsx (same hook, delay, text). Share the prod copy via an alias.

### Notes (non-blocking)
3. [Bug] ErrorBoundary inside Shell (<ErrorBoundary><Outlet/></ErrorBoundary>) has no reset key: after a render failure, switching tabs still shows the error. Key it on location.
4. [Architect] eval/web/public/theme-init.js comment should point to web/src/lib/theme.ts and web/public/theme-init.js.
5. [Architect] Eval should be consistent with prod via @onolys/ui: native checkboxes and selects in NewRun.tsx should use ui components.
6. [Architect] api queue helper duplication: leave as-is.

### Security: PASS
- canonicalHost: no open redirect.
- enqueue log capped at 200 chars, no credentials.
- run_summary stores error code only.
- ErrorPage text is fixed.
- theme-init.js is same-origin, OK with CSP.

## Next step
dev-code fix round, then re-review.
