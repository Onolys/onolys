---
status: done
summary: Task 2 facilitative volley parsing; 105 focused tests pass, existing hand counts and request stubs unchanged.
date: 2026-11-24
---
# Step 1: facilitative turns

`prepare.build_volleys` now retains clinician turns on both sides of client input shorter than 3 whitespace words, or shorter than 6 non-space characters when at least half its letters are Thai, Chinese or Japanese. These numeric thresholds are engineering choices. Exactly 3 words / 6 characters break. This follows R1, D1 and AC1; the contradictory R1 trade-off sentence about the three-word example is not implemented.

A direct question in the preceding clinician turn overrides size: the final `?`, `？` or `؟` must be followed by at most 3 words / 6 characters. Trailing whitespace and closing quotes/brackets are removed first. Earlier questions with longer statement tails do not override size. Reflection acknowledgement is not special-cased (D2). Client text remains intact in `Prepared.turns` and remains available for later context work; only clinician turns enter codable volleys. Bounded rendered context remains Task 6.

Manual source: local cached MITI 4.2.1 text, E.1 on p.13 and E.3 on pp.15–16. The manual defines facilitative input semantically, permits question/reflection answers to parse, and prefers fewer parses. The character/word and punctuation heuristics are not manual requirements.

## Existing fixture audit

Read all existing transcript turns and hand utterances in `expected.yaml`. Added explicit hand volley groupings to the three existing fixtures and a test that checks them. No expected code counts or summaries change:

| Fixture | Volleys | Batches | Rendered request words | Hand count drift | Coverage residual |
|---|---:|---:|---:|---:|---:|
| good_practice | 10 | 1 | 4527 | 0 | 0 |
| poor_practice | 12 | 1 | 4191 | 0 | 0 |
| short_session | 5 | 1 | 3681 | 0 | 0 |

`good_practice` groups consecutive clinician t8/t9; all intervening client turns have at least 3 words. `poor_practice` t23 is exactly 3 words and breaks under the strict threshold; its final one-word t25 has no clinician speech after it. `short_session` has substantive intermediate client turns; its final two-word t11 also has no following clinician turn. Thus p.13 / pp.15–16 require no existing count adjustment. All three have zero same-volley double persuasion both before and after this step. These synthetic fixtures do not measure model accuracy.

## Golden and full adapter evidence

Ran `tools/regen_goldens.py`: request hashes, request sizes and existing synthetic response bytes remain identical because the three fixture volley structures do not change. No response override or invented response was needed. Only current pack metadata in the report and `test_data.py` was repinned. `test_miti_pack.py` also held a pre-existing stale `d98e79648859d15e` pin; it now pins current `a6296dcf8f4acefb` (subsequent pack changes must repin it too).

Ran the historical full adapter byte test before refreshing: it failed at byte 1771. Recursive inspection of the complete candidate found exactly seven changed values, all `e068479e6bb821dd` → `a6296dcf8f4acefb`: `/run_info/{miti,evaluation}/pack/hash`, `/report/run_info/{miti,evaluation}/pack/hash`, `/report/header/protocol/pack_hash`, `/artifacts/code/run_info/pack/hash`, `/artifacts/code/protocol/pack_hash`. Every other report, artifact and run_info value is identical. Only generated `created_at` is normalized.

Historical `tests/fixtures/adapter_pre_input_locks.json` and its assertion remain available at SP01 commit `ce65eef`. The current fixture is explicitly renamed `adapter_manual_alignment.json`; its test/docstring names the alignment baseline and links that historical evidence by commit. No additional field is masked.

## Verification

- Red: new preparation tests on old behavior: **13 failed, 34 passed**; failures show facilitative inputs incorrectly splitting volleys. Separate pack/code-pass checks exposed the expected obsolete volley settings assertion and the stale pack pin.
- Green: `.venv/bin/python -m pytest engines/miti/tests/test_prepare.py engines/miti/tests/test_golden.py engines/miti/tests/test_data.py engines/miti/tests/test_offline_tools.py engines/miti/tests/test_miti_pack.py engines/miti/tests/test_code_pass.py engines/miti/tests/test_code_pass_miti.py -q` → **105 passed in 1.94s**.
- Ruff on all changed Python implementation/test files → **All checks passed!**
- Final unchanged regeneration → **No changes.** `step1.json` generated after final source edits.
- No model/client calls, API keys, network, or live measurement. No full test suite run.
