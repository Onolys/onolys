"""effective_cap override resolution (SP11 R3, D5, D6) and the usage models."""

import json
import logging

import pytest

from onolys_api.config import Settings
from onolys_api.repo.limits import KIND_FIELD, LimitDefaults, effective_cap
from onolys_api.repo.models import RunDoc, UsageDoc, UsageMonthDoc

D = LimitDefaults(eval_day=10, eval_month=100, interview_day=5, interview_month=30)


def test_defaults_from_settings():
    assert LimitDefaults.from_settings(Settings()) == D


def test_no_overrides_uses_defaults():
    assert effective_cap(None, "eval", "day", D) == 10
    assert effective_cap({}, "eval", "month", D) == 100
    assert effective_cap({}, "interview", "day", D) == 5
    assert effective_cap({}, "interview", "month", D) == 30


def test_partial_limits():
    u = {"limits": {"eval": {"day": 25}}}
    assert effective_cap(u, "eval", "day", D) == 25
    assert effective_cap(u, "eval", "month", D) == 100
    assert effective_cap(u, "interview", "day", D) == 5


def test_limits_beat_legacy():
    u = {"daily_cap": 3, "limits": {"eval": {"day": 25}}}
    assert effective_cap(u, "eval", "day", D) == 25


def test_legacy_alone_is_eval_day_only():
    u = {"daily_cap": 3}
    assert effective_cap(u, "eval", "day", D) == 3
    assert effective_cap(u, "eval", "month", D) == 100
    assert effective_cap(u, "interview", "day", D) == 5


def test_zero_is_valid_override():
    assert effective_cap({"limits": {"interview": {"month": 0}}}, "interview", "month", D) == 0
    assert effective_cap({"daily_cap": 0}, "eval", "day", D) == 0


@pytest.mark.parametrize("bad", ["12", -1, 1.5, True, False, [], {}, "secret-value"])
def test_malformed_leaf_falls_back_without_logging_value(bad, caplog):
    caplog.set_level(logging.DEBUG)
    u = {"limits": {"eval": {"day": bad}}}
    assert effective_cap(u, "eval", "day", D) == 10
    assert any(r.levelno == logging.WARNING for r in caplog.records)
    for r in caplog.records:
        # code_version (from GIT_SHA, e.g. "abc123" in CI) may legitimately contain "12".
        payload = json.loads(r.getMessage())
        payload.pop("code_version", None)
        dumped = json.dumps(payload)
        assert "secret-value" not in dumped and "12" not in dumped


def test_malformed_leaf_falls_through_to_legacy():
    u = {"daily_cap": 3, "limits": {"eval": {"day": "x"}}}
    assert effective_cap(u, "eval", "day", D) == 3


@pytest.mark.parametrize("limits", ["x", 5, ["a"], {"eval": "x"}, {"eval": 3}])
def test_malformed_structure_never_raises(limits):
    assert effective_cap({"limits": limits}, "eval", "day", D) == 10


def test_bad_legacy_ignored():
    assert effective_cap({"daily_cap": "3"}, "eval", "day", D) == 10
    assert effective_cap({"daily_cap": -2}, "eval", "day", D) == 10


def test_models():
    assert KIND_FIELD == {"eval": "runs", "interview": "interviews"}
    assert UsageDoc().interviews == 0
    m = UsageMonthDoc()
    assert (m.runs, m.interviews) == (0, 0)
    assert RunDoc(uid="u", session_id="s", run_id="r").counted is True
