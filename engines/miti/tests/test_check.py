"""Offline tests for the pure parts of `onolys_miti.check` (no model, no network)."""

import pytest
from onolys_engine_core.transcript import Transcript

from onolys_miti import check

pytestmark = pytest.mark.unit

THRESHOLDS = {
    "count_mae_max": 1.5,
    "globals_within_1_min": 0.75,
    "bad_output_rate_max": 0.10,
    "p95_latency_s_max": 90,
    "tokens_per_run_max": 120000,
}
GOOD = {
    "count_mae": 1.0,
    "globals_within_1": 0.9,
    "bad_output_rate": 0.0,
    "p95_latency_s": 30.0,
    "tokens_per_run": 50000.0,
}


def test_parse_args_defaults_and_preset():
    a = check.parse_args([])
    assert a.preset is None and a.skip_tips is False
    assert check.parse_args(["--preset", "fast"]).preset == "fast"


def test_parse_args_rejects_unknown_flag():
    with pytest.raises(SystemExit):
        check.parse_args(["--nope"])


def test_p95_nearest_rank():
    assert check.p95([1.0, 2.0, 3.0]) == 3.0
    assert check.p95(list(map(float, range(1, 21)))) == 19.0


def test_distance():
    assert check.distance(3, [2, 4]) == 0
    assert check.distance(1, [2, 4]) == 1
    assert check.distance(6, [2, 4]) == 2


def test_evaluate_passes_inside_limits():
    assert check.evaluate(GOOD, THRESHOLDS) == []


def test_evaluate_reports_each_breach():
    bad = {**GOOD, "count_mae": 2.0, "globals_within_1": 0.5}
    fails = check.evaluate(bad, THRESHOLDS)
    assert [f.metric for f in fails] == ["count_mae", "globals_within_1"]
    assert "need <=" in str(fails[0]) and "need >=" in str(fails[1])


def test_evaluate_missing_threshold_key():
    with pytest.raises(ValueError, match="count_mae_max"):
        check.evaluate(GOOD, {})


def test_bad_call_and_tokens():
    assert check.bad_call({"error_kind": "bad_output", "attempts": 1})
    assert check.bad_call({"error_kind": None, "attempts": 2})
    assert not check.bad_call({"error_kind": None, "attempts": 1})

    class M:
        records = [
            {"input_tokens": 1, "output_tokens": 2, "cache_read_tokens": 3, "cache_write_tokens": 4}
        ]

    assert check.tokens(M()) == 10


def _tr():
    return Transcript.model_validate(
        {
            "language": "en",
            "turns": [{"id": "t1", "speaker": "A", "text": "hello there"}],
        }
    )


def test_valid_tips_counts_exact_quotes_only():
    class Q:
        def __init__(self, text, s, e):
            self.text, self.start, self.end, self.turn_id = text, s, e, "t1"

    class T:
        def __init__(self, q):
            self.quote = q

    tips = [T(Q("hello", 0, 5)), T(Q("nope", 0, 5))]
    assert check.valid_tips(tips, _tr()) == 1


def test_evaluate_tips_threshold():
    assert check.evaluate_tips(3) == []
    assert check.evaluate_tips(2) == ["tips: 2 valid, need at least 3"]


def test_main_help_exits_zero(capsys):
    with pytest.raises(SystemExit) as e:
        check.main(["--help"])
    assert e.value.code == 0
    assert "--preset" in capsys.readouterr().out


def _rec(tier, tok, **kw):
    return {
        "tier": tier,
        "input_tokens": tok,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "error_kind": None,
        "attempts": 1,
        **kw,
    }


def test_coding_records_exclude_tips_usage():
    class M:
        records = [_rec("tips", 1000, attempts=2), _rec("mid", 10), _rec("cheap", 5)]

    assert [r["tier"] for r in check.coding_records(M())] == ["mid", "cheap"]
    assert check.tokens(M()) == 15
    assert not any(check.bad_call(r) for r in check.coding_records(M()))


def test_code_timer_measures_only_code_stage():
    clock = iter([100.0, 130.0, 131.0, 500.0])
    t = check.CodeTimer(clock=lambda: next(clock))
    t("code", "started")
    t("code", "done")
    t("tips", "started")
    t("tips", "done")
    assert t.elapsed == 30.0
