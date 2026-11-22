"""Live checks on the real model (manual; excluded by default through `-m 'not live'`).

    set -a; . ~/.config/onolys/keys.env; set +a
    (same checks as `python -m onolys_miti.check`; logic lives in onolys_miti/check.py)
    uv run --package onolys-miti pytest engines/miti/tests/test_live.py -m live -s

Env: MITI_LIVE_PRESET picks the route preset (default: the default preset).

- quality: the three synthetic fixtures run once each, in sequence (so latency is not distorted),
  compared with `fixtures/expected.yaml` and the limits in `fixtures/thresholds.yaml`: per-code
  count MAE, globals within 1 point, bad-output rate, p95 run latency, tokens per run.
- tips: good_practice end to end; at least 3 tips whose quote really sits in its transcript turn.
Never prints text, quotes or keys.
"""

import os

import pytest

from onolys_miti import check

pytestmark = [pytest.mark.live, pytest.mark.integration]



def need_key():
    if not os.environ.get("GEMINI_API_KEY"):
        pytest.skip("set GEMINI_API_KEY (live LLM)")


def client():
    return check.live_client(os.environ.get("MITI_LIVE_PRESET"))


async def test_live_quality_against_expected_and_thresholds():
    need_key()
    q = await check.run_quality(client())
    print(q.metrics)
    assert not q.failures, [str(f) for f in q.failures]


async def test_live_tips_quote_valid_end_to_end():
    need_key()
    valid, total = await check.run_tips(client())
    print(f"tips: {valid} valid of {total}")
    assert not check.evaluate_tips(valid)
