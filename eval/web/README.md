# Eval web

The allowlisted MITI 4.2.1 evaluation app. This independent Vite + React + TypeScript app uses the prod sign-in code from `web/src/auth` through `@prod-auth`. React and Firebase resolve to one copy. Every route, including Compare deep links, requires sign-in and a successful backend access check before it loads evaluation data. There is no auth bypass.

Run `npm ci`, then `npm run dev`. Configure `VITE_EVAL_API_URL` with the eval backend origin and the prod Firebase web-app values (auth domain `eval.onolys.com`) as `VITE_FIREBASE_API_KEY`, `VITE_FIREBASE_AUTH_DOMAIN`, `VITE_FIREBASE_PROJECT_ID`, and `VITE_FIREBASE_APP_ID`. Put local values in `.env.local` (ignored).

Sign-up, email verification and password reset happen in the prod app (https://app.onolys.com). Accounts need a verified email and a spot on the eval access list; a 403 shows “No access” with sign out.

New run creates the server-driven evaluation. History and run detail show fresh progress on open and poll active runs using reads only. Leaving the page does not affect execution. Cancel requires confirmation: completed results remain, in-flight runs finish, and no new runs start. Partial badges show saved scheduler counters, including Human reference units; skipped providers and retry cooldowns remain visible.

History and run detail link to Compare for done and partial runs. Compare has four URL-addressable tabs: Overview, Deep dive, More analysis and Line view (`?run=<id>&view=compare&tab=overview|deep|more|lines`). Filters and drill-down selections remain in the URL. The frontend renders SP06 projections through authenticated `/v1/eval-runs/{id}/compare/*` endpoints. It does not calculate quality metrics or choose winners. Operational best marks come from `leaderboard[].operational_best`, including ties. Compare's Partial badge uses `header.progress`; the separate coverage/cohort lines show the API's AI-only comparison coverage and exclusions.

Charts use SVG/CSS without a chart dependency. Each has a “How to read” caption and a semantic table twin. Wide tables have labelled keyboard-focusable scroll regions, and heatmap row labels stay sticky. The leaderboard stacks below 760 px. Transcript text, rationale and evidence come from saved data; absent labels and withheld reasoning retain their explicit states.

Run the complete offline verification from this directory:

```sh
npm run typecheck
npm run lint
npm test
npm run build
```

Tests use fake auth, fake fetch and [synthetic SP06 response fixtures](src/compare/fixtures/README.md); they make no paid/provider calls. Coverage includes cancellation and focus return, tab keyboard navigation, URL drill-downs, missing/partial/skipped states, popup text preservation, chart captions/table twins, and structural CSS/scroll checks for 320, 768 and 1,280 px. jsdom cannot verify layout, visual clipping or screen-reader output. The owner records the browser check at those widths after deployment and runs the first real eval. Agents do not deploy or run live evaluations.

The [initial API contract](../../docs/agent_files/feat-miti-eval-20261123-0026/05-eval-site/api-ui-contract.md) describes the original run flow; the [SP07 specification](../../docs/agent_files/session-report-ux-20261124-1738/07-compare-screens/PRD.md) describes Compare and its current acceptance criteria.
