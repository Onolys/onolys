"""Equivalence baseline captured on the old packages: the refactor must reproduce it.

Each case runs the full `run_miti` on the real `LiteLLMClient` with `litellm.acompletion` patched
(replies by call tag) and compares the sent provider payloads, the code-call warm-up order, the
masked report and the aggregate with the stored baseline. Throwaway: removed with the old packages.
"""

import json

import pytest
from _equivalence import (
    CASES,
    FIXTURES,
    OUT,
    RESPONSES,
    baseline_path,
    build_responses,
    capture,
    dumps,
    masked,
)

from onolys_miti import miti

pytestmark = pytest.mark.unit

GOLDEN_REPORT = json.loads(
    (miti.DATA_DIR / "fixtures" / "evaluation" / "report_no_rating.json").read_text("utf-8")
)


def _baseline(case: str) -> dict:
    return json.loads(baseline_path(case).read_text("utf-8"))


def _normal(value):
    """What `capture` returns, as it reads back from disk."""
    return json.loads(dumps(value))


@pytest.mark.parametrize("case", CASES)
async def test_payloads_match_baseline(case):
    got = _normal(await capture(case))
    want = _baseline(case)
    assert [p["call_tag"] for p in got["payloads"]] == [p["call_tag"] for p in want["payloads"]]
    for g, w in zip(got["payloads"], want["payloads"], strict=True):
        assert g == w, g["call_tag"]


@pytest.mark.parametrize("case", CASES)
async def test_report_and_aggregate_match_baseline(case):
    got = _normal(await capture(case))
    want = _baseline(case)
    assert got["report"] == want["report"]
    assert got["aggregate"] == want["aggregate"]
    assert got["warm_up"] == want["warm_up"]


@pytest.mark.parametrize("case", CASES)
async def test_second_capture_is_identical(case):
    assert dumps(await capture(case)) == dumps(await capture(case))


def test_warm_up_first_code_call_returns_before_any_other_code_call_starts():
    for case in CASES:
        warm = _baseline(case)["warm_up"]
        assert warm["first_code_call"] == "miti_code:r0:b1"
        assert warm["started_before_first_returned"] == []
    assert _baseline("batch_edge")["warm_up"]["started_after_first_returned"] == ["miti_code:r0:b2"]
    assert _baseline("good_practice_n3")["warm_up"]["started_after_first_returned"] == [
        "miti_code:r1:b1",
        "miti_code:r2:b1",
    ]


def test_batch_edge_splits_at_the_batch_boundary():
    tags = [p["call_tag"] for p in _baseline("batch_edge")["payloads"]]
    assert [t for t in tags if t.startswith("miti_code")] == ["miti_code:r0:b1", "miti_code:r0:b2"]
    user = {p["call_tag"]: p["messages"][-1]["content"] for p in _baseline("batch_edge")["payloads"]}
    volleys = [
        [v["volley_id"] for v in json.loads(user[t])["volleys"]]
        for t in ("miti_code:r0:b1", "miti_code:r0:b2")
    ]
    assert (len(volleys[0]), len(volleys[1])) == (25, 2)
    assert volleys[0][-1] == "v25" and volleys[1][0] == "v26"


def test_good_practice_baseline_equals_the_existing_golden_report():
    want = _baseline("good_practice")["report"]
    assert want == _normal(masked(GOLDEN_REPORT))


def test_three_runs_aggregate_has_a_representative_run():
    agg = _baseline("good_practice_n3")["aggregate"]
    assert agg["representative_run"] in (0, 1, 2)
    assert len(next(iter(agg["counts"].values()))["values"]) == 3


@pytest.mark.parametrize("fixture", FIXTURES)
def test_stored_replies_match_what_expected_yaml_and_goldens_produce(fixture):
    assert json.loads((RESPONSES / f"{fixture}.json").read_text("utf-8")) == _normal(
        build_responses(fixture)
    )


def test_baseline_folder_holds_exactly_the_cases():
    assert {p.name for p in OUT.glob("*.json")} == {f"{c}.json" for c in CASES}
