# Task 3 notes — has_gold for shipped dataset sessions (R4, AC2)

Dataset `casaa-miti421-video2013` (eval/datasets): 8 sessions in the manifest.
Checked 2026-11-24 against the converted cache that is uploaded to the bucket
(`~/.cache/onolys-eval/casaa-miti421-video2013/<session>/gold.json`; `convert_dataset`
writes gold.json for every session or deletes it and exits 1). All 8 files exist and
validate as `onolys_eval.gold.Gold`:

confirmed-smoker, rounder, my-father-also-hit-me, overuse-of-directing,
overuse-of-following, suspiscious-smoker, living-with-diabetes,
orientation-to-a-parenting-class -> has_gold = true (8/8).

Result: the `skipped: no_gold` fallback is not needed for shipped data. `plan_units`
still supports it (session `has_gold: false` -> human unit flagged `skipped: "no_gold"`),
but `create_run` keeps its existing "Human requires gold" 422 when a dataset gold object
is missing in the bucket (unchanged behaviour), so the flag is currently unused by the server.
