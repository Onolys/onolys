# Task 9 notes: `claude` preset grep

Grep (excluding docs/agent_files, node_modules, .venv): `DEFAULT_PRESET`, `preset: claude`, `"claude"` preset literals.

Preset `claude` references outside eval:
- engines/core/tests/test_routes.py:87,97 (resolve_preset("claude"), allowed_presets)
- engines/core/tests/test_presets.py:17,30-31
- engines/oneshot/tests/test_golden.py:22,27,30; test_miti_config.py:67,77 (parametrized over config/staging/routes.yaml)
- api/tests/test_fuzz_review.py:189; api/tests/test_staging_presets.py:125-150
- config/prod/routes.yaml:31 and engines/core routes.default.yaml:33 (own `claude` preset, untouched)
- eval/backend runs.py legacy branch: `resolve_preset(unit["preset"], services.routes)` resolves queued legacy units from the staging routes file.

Decision: KEEP staging `claude` preset. Other references exist (oneshot tests read staging file) and removing it would break executing queued legacy `preset:claude` units (PRD: legacy branch stays until drained). `routes.yaml` unchanged; prod unchanged.
