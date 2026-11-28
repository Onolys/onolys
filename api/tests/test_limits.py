"""effective_cap override resolution and the usage models."""

import json
import logging

import pytest
from onolys_engine_core.json_logging import render

from onolys_api.config import Settings
from onolys_api.repo.limits import KIND_FIELD, LimitDefaults, effective_cap
from onolys_api.repo.models import RunDoc, UsageDoc

D = LimitDefaults(eval_day=10, interview_day=5)


def test_defaults_from_settings():
    assert LimitDefaults.from_settings(Settings()) == D


def test_no_overrides_uses_defaults():
    assert effective_cap(None, "eval", "day", D) == 10
    assert effective_cap({}, "interview", "day", D) == 5


def test_partial_limits():
    u = {"limits": {"eval": {"day": 25}}}
    assert effective_cap(u, "eval", "day", D) == 25
    assert effective_cap(u, "interview", "day", D) == 5


def test_zero_is_valid_override():
    assert effective_cap({"limits": {"interview": {"day": 0}}}, "interview", "day", D) == 0


@pytest.mark.parametrize("bad", ["12", -1, 1.5, True, False, [], {}, "secret-value"])
def test_malformed_leaf_falls_back_without_logging_value(bad, caplog):
    caplog.set_level(logging.DEBUG)
    u = {"limits": {"eval": {"day": bad}}}
    assert effective_cap(u, "eval", "day", D) == 10
    assert any(r.levelno == logging.WARNING for r in caplog.records)
    for r in caplog.records:
        # code_version (from GIT_SHA, e.g. "abc123" in CI) may legitimately contain "12".
        payload = json.loads(render(r))
        payload.pop("code_version", None)
        dumped = json.dumps(payload)
        assert "secret-value" not in dumped and "12" not in dumped


@pytest.mark.parametrize("limits", ["x", 5, ["a"], {"eval": "x"}, {"eval": 3}])
def test_malformed_structure_never_raises(limits):
    assert effective_cap({"limits": limits}, "eval", "day", D) == 10


def test_models():
    assert KIND_FIELD == {"eval": "runs", "interview": "interviews"}
    assert UsageDoc().interviews == 0
    assert (
        RunDoc(
            change_goal="",
            clinician_speaker="S1",
            language="en",
            transcript_sha256="test-hash",
            uid="u",
            session_id="s",
            run_id="r",
        ).counted
        is True
    )


# ---- unit-cost cap decisions and the per-user override branches ------------------


def _d():
    from onolys_api.repo.limits import LimitDefaults

    return LimitDefaults(eval_day=10, interview_day=5)


def test_decide_reserve_units_must_all_fit():
    from onolys_api.repo.limits import decide_reserve

    d = _d()
    day = {"runs": 7}
    assert decide_reserve(None, day, "eval", d, 2, units=3) == "ok"  # 7 + 3 == cap
    assert decide_reserve(None, day, "eval", d, 2, units=4) == "day_cap"
    assert decide_reserve(None, {"runs": 10}, "eval", d, 2) == "day_cap"  # default 1 unit


def test_decide_start_units_exempt_and_active_limit():
    from onolys_api.repo.limits import decide_start

    d = _d()
    assert decide_start(None, {"runs": 8}, d, 2, False, 3) == "day_cap"
    assert decide_start(None, {"runs": 8}, d, 2, False, 2) == "ok"
    assert decide_start(None, {"runs": 99}, d, 2, True, 5) == "ok"  # exempt
    # user=None means no active runs; a real user at the limit is refused
    assert decide_start(None, None, d, 1, True) == "ok"
    assert decide_start({"active_runs": 1}, None, d, 1, True) == "concurrent"
    assert decide_start({"active_runs": 1, "max_active_runs": 5}, None, d, 1, False) == "ok"
    assert decide_start({"active_runs": 0}, None, d, 0, True) == "concurrent"


def test_effective_cap_override_branches():
    from onolys_api.repo.limits import effective_cap

    d = _d()
    assert effective_cap(None, "eval", "day", d) == 10  # no user, no limits
    assert effective_cap({}, "eval", "day", d) == 10
    assert effective_cap({"limits": {"eval": {"day": 25}}}, "eval", "day", d) == 25
    # partial override: the other kind falls back to the default
    partial = {"limits": {"eval": {"day": 25}}}
    assert effective_cap(partial, "interview", "day", d) == 5
    assert effective_cap({"limits": {"eval": {"day": 0}}}, "eval", "day", d) == 0  # 0 is valid
    # malformed shapes are ignored, never raise
    assert effective_cap({"limits": "x"}, "eval", "day", d) == 10
    assert effective_cap({"limits": {"eval": 5}}, "eval", "day", d) == 10
    assert effective_cap({"limits": {"eval": {"day": True}}}, "eval", "day", d) == 10
