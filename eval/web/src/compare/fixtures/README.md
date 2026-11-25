# Compare response fixtures

These JSON files are actual SP06 `compare_routes.py` responses, generated offline from
`eval/fixtures/compare/lines.json` using `eval/backend/tests/test_compare_routes.py`'s
`routes` fixture (refreshed against backend commit `a6157d9`), `test_app.AUTH` and its fake saved-document source. No external service
or model was called. They contain synthetic source text from that existing fixture.

| File | Endpoint suffix |
| --- | --- |
| overview.json | overview |
| deepDive.json | deep-dive |
| analysis.json | analysis |
| reasoning.json | reasoning |
| lines.json | sessions/synthetic-s01/lines |
| turn.json | sessions/synthetic-s01/lines/t2 |

Preserve these payload structures when deriving display-state fixtures. In particular,
`verdict` is an array; Overview's leaderboard quality cells are `globals_within_1`,
`line_accuracy`, and `macro_f1`; the heatmap has exactly 16 rows. Combo keys are opaque:
these saved synthetic scenarios predate current `engine|model/tier/effort` keys. Popup
`combos` is a keyed object, while the other endpoint projections use a descriptor array.

Overview separates `header.progress` (saved scheduler counters, including Human units)
from AI-only `coverage`; `leaderboard[].operational_best` contains the server’s
failures/cost/time winner flags, including ties. The fixture text is synthetic.
