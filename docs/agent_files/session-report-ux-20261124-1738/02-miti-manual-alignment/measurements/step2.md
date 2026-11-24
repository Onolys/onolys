---
status: done
summary: Persuasion shares one volley slot; all five synthetic hand fixtures have zero count drift and zero double persuasion.
date: 2026-11-24
---
# Step 2 — persuasion slot (SP02 Task 4)

Added the existing exclusive-group mechanism to the pack: permission wins, the losing Persuade remains visible with `superseded_by_persuade_permission`. Same-utterance precedence follows manual p.20; applying that winner across utterances is the approved engineering extension of the p.13 slot. Total MINA excludes the loser. No scoring implementation change was needed.

Test-first command: `.venv/bin/python -m pytest engines/miti/tests/test_score.py engines/miti/tests/test_miti_pack.py engines/miti/tests/test_manual_fixtures.py -q` → **5 failed, 37 passed** before the rule: both order cases kept Persuade counted, pack rule absent, batch-edge actual Persuade 1 versus target 0, audit drift +1.

After implementation and offline golden regeneration: `.venv/bin/python -m pytest engines/miti/tests/test_score.py engines/miti/tests/test_miti_pack.py engines/miti/tests/test_golden.py engines/miti/tests/test_data.py engines/miti/tests/test_offline_tools.py engines/miti/tests/test_manual_fixtures.py -q` → **57 passed**. Tests cover both persuasion orders, distinct volleys, the eight-code maximum, downcount reason and Total MINA. Audit asserts all five fixtures match hand targets and have no counted double persuasion; batch-edge Total MINA is 0 with zero drift.

`step2.json` was generated with `engines/miti/audit_report.py --output <measurements>/step2.json`. Volley/batch counts remain 10/1, 12/1, 5/1, 27/2, 5/1 for good, poor, short, batch-edge and sparse respectively. Rendered request words are 4615, 4279, 3769, 8910, 3616. All have zero residual coverage on these complete synthetic hand utterances. These are deterministic rules and request-word proxies, not accuracy or token/cost measurements. No model client, provider call, network or credentials were used.

Adapter parity was run before refresh and failed as expected. Complete normalized payload inspection showed only pack hash `a6296dcf8f4acefb` → `90176563e1bf97b0` and code-system prompt hash `c2b9e2ee9ad63129` → `fe6abdc6e916c3a8`. No count, global, transcript, artifact shape or other field changed. Current `adapter_manual_alignment.json` and report metadata reflect those hashes; normalization remains only generated `created_at`. Historical SP01 `tests/fixtures/adapter_pre_input_locks.json` and its original assertion at commit `ce65eef` remain preserved. Request-stub response bytes are retained, under their new request key. The regeneration utility now narrowly repins both test pack-hash constants.
