# SP07 Task 9 offline verification — 2026-11-25

Scope: `eval/web`, after `606bd3f`, integrating backend projections from `a6157d9`. No backend edits, deploys, live provider calls or dependency changes. TASKS bookkeeping belongs to the orchestrator.

## Completed

- Compare Partial badges render `overview.header.progress` verbatim, including Human scheduler units. Separate coverage still renders AI-only `coverage`; tests deliberately use different totals and cover both cancelled and failure/skipped partial variants.
- Overview Fails/Cost/Time stars use the server's `operational_best` flags. Tests cover ties, deliberately different costs with tied flags, false flags despite available values, and skipped-row suppression. Extracted the leaderboard cell renderer for readability.
- Refreshed all six fixtures through the existing backend `test_compare_routes.routes.__wrapped__(pytest.MonkeyPatch())('lines')` fake-source client with `test_app.AUTH`; only overview/deepDive response files changed. The new progress, line-session, cohort and Human-count containers match actual offline route output. Existing synthetic transcript content was preserved.
- Added malformed progress/best-flag boundary checks with regression tests.
- Shared prod fake auth now proves a Compare deep link makes no API request while signed out; no new auth implementation.
- Table twins now have keyboard-focusable labelled scroll regions. Added structural checks at 320/768/1280 for all four tabs: actual CSS breakpoint and stacked leaderboard declarations, sticky heatmap rows, flexible page widths, labelled/focusable scroll regions, chart captions and semantic table twins. Existing tab, sorting, filter and dialog keyboard/focus tests remain green.
- Updated `eval/web/README.md` with the current flow, endpoint/counter responsibilities, accessibility behavior, offline commands and owner-only browser checks.

## Evidence

Test-first: the new saved-counter and operational-star tests failed against the old UI (2 failures, 15 passes), then passed after integration. Six malformed-boundary tests also failed before validation was added and passed afterward.

Final commands, run from `eval/web`:

| Command | Result |
| --- | --- |
| `npm run typecheck` | exit 0 |
| `npm run lint` | exit 0, including jsx-a11y |
| `npm test` | exit 0: 20 files, 264 tests passed |
| `npm run build` | exit 0: 2,409 modules transformed |
| `git diff --check` (repo root) | exit 0 |

jsdom prints its existing “Not implemented: navigation to another Document” notices during anchor tests; all tests pass. Vite reports the existing >500 kB chunk warning for both baseline and current builds.

## Bundle evidence

Built the committed pre-SP07 tree `7c29aad` from `git archive` in a temporary directory with the existing node_modules and shared prod auth source. The current build uses the same local dependencies, with no installs or network. Asset sizes below are exact bytes; gzip uses Python `gzip.compress(bytes, mtime=0)` at its default level 9 for a consistent comparison (Vite's displayed gzip estimate uses a different setting).

| Asset | Pre-SP07 `7c29aad` | Current | Delta |
| --- | ---: | ---: | ---: |
| JS | 588,016 | 643,706 | +55,690 |
| JS gzip | 181,696 | 195,345 | +13,649 |
| CSS | 54,986 | 61,450 | +6,464 |
| CSS gzip | 11,269 | 12,547 | +1,278 |
| JS + CSS gzip | 192,965 | 207,892 | +14,927 (7.74%) |

Pre-SP07 asset names: `index-C9ZOWLrE.js`, `index-C-NMuj7H.css`. Current: `index-uQY_-Kzd.js`, `index-1WWz0xwc.css`. Font remains 48.25 kB. The immediate pre-Task-9 build (`606bd3f`) was JS 643,167 bytes / gzip 195,244 and CSS 61,450 / gzip 12,547; Task 9 adds 539 JS bytes / 101 gzip bytes. No chart library or other dependency was added. The PRD's narrative “bundle does not grow” is not literally met; the acceptance requirement to record the delta and avoid a new dependency is met.

## Remaining acceptance / owner work

No known missing offline Task 9 acceptance item. jsdom cannot validate actual clipping, visual layout or assistive-technology output. The specification explicitly reserves the recorded 320/768/1280 browser check against the deployed app and the first real evaluation for the owner; neither was attempted. Parent review and TASKS status updates remain with the orchestrator.
