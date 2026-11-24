"""Table tests for selection validation, plan_units and the request/run wiring."""
# ruff: noqa: F811, F401

import json
from pathlib import Path

import pytest
from test_app import AUTH, client
from test_runs import services, start

from onolys_eval_backend.matrix import RunTooLarge, SelectionError, plan_units, validate_selection

FIXTURE = json.loads(
    (Path(__file__).parents[2] / "fixtures" / "selection_cases.json").read_text()
)
KEYS = lambda items: [f"{c['model']}/{c['tier']}/{c['effort']}" for c in items]  # noqa: E731


@pytest.mark.parametrize("case", FIXTURE["cases"], ids=lambda c: c["name"])
def test_table(case):
    expect = case["expect"]
    needs = any(e != "human" for e in case["engines"])
    sessions = [{"session_id": f"s{i}"} for i in range(case["sessions"])]

    def run():
        combos, dropped = validate_selection(FIXTURE["models"], case["selection"], needs)
        return combos, dropped, plan_units(sessions, case["engines"], combos, case["repeats"])

    if "error" in expect:
        with pytest.raises((SelectionError, RunTooLarge)) as err:
            run()
        assert str(err.value) == expect["error"]
        return
    combos, dropped, units = run()
    assert KEYS(combos) == expect["combos"] and KEYS(dropped) == expect["dropped"]
    assert len(units) == expect["units"]


def test_plan_units_shape():
    combo = {"model": "claude", "tier": "t", "effort": "low"}
    units = plan_units(
        [{"session_id": "a"}], ["miti", "human"], [combo], 3
    )
    assert units[-1] == {
        "session_id": "a", "engine": "human", "combo": None, "combo_key": None,
        "repeat": 0,
    }
    assert [u["repeat"] for u in units[:3]] == [0, 1, 2]
    assert units[0]["combo_key"] == "claude/t/low" and units[0]["combo"] == combo


SEL = {"models": ["claude"], "tiers": ["claude-sonnet-5-5"], "efforts": ["low", "high"]}


def test_legacy_presets_body_422(services):
    c = client(services=services)
    response = c.post(
        "/v1/runs", headers=AUTH,
        json={"input": {"dataset_id": "synthetic", "session_ids": ["one"]},
              "engines": ["miti"], "presets": ["configured-prod"], "repeats": 1},
    )
    assert response.status_code == 422
    assert services.repository.list_runs() == {}


def test_dataset_without_human_gets_human_units_and_echo(services):
    c = client(services=services)
    response = start(c, engines=["miti"], selection=SEL)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["engines"] == ["miti", "human"]
    units = services.repository.list_units(body["run_id"]).values()
    assert sorted(u["engine"] for u in units) == ["human", "miti", "miti"]
    ai = [u for u in units if u["engine"] == "miti"]
    assert {u["combo_key"] for u in ai} == {
        "claude/claude-sonnet-5-5/low", "claude/claude-sonnet-5-5/high"}
    assert all(u["combo"] and u["repeat"] == 0 for u in ai)
    human = next(u for u in units if u["engine"] == "human")
    assert human["combo"] is None and human["combo_key"] is None


def test_specific_422_message_and_no_writes(services):
    c = client(services=services)
    bad = {"models": ["claude"], "tiers": [], "efforts": ["low"]}
    response = start(c, engines=["miti"], selection=bad)
    assert response.status_code == 422
    assert response.json()["detail"] == "Model 'claude' has no selected tier."
    assert services.repository.list_runs() == {} and services.queue.tasks == []


def test_run_too_large_message(services):
    c = client(services=services)
    ids = [f"s-{i}" for i in range(500)]
    response = start(
        c, input={"dataset_id": "synthetic", "session_ids": ids},
        engines=["human"], selection={"models": [], "tiers": [], "efforts": []},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == (
        "Run has 500 units; the maximum is 499. Remove sessions, combos or repeats.")


def test_rerun_dataset_adds_human_and_rejects_legacy(services):
    c = client(services=services)
    rid = start(c, engines=["miti"], selection=SEL).json()["run_id"]
    ok = c.post(f"/v1/runs/{rid}/rerun", headers=AUTH,
                json={"engines": ["miti"], "selection": SEL, "repeats": 1})
    assert ok.status_code == 200, ok.text
    assert ok.json()["engines"] == ["miti", "human"]
    legacy = c.post(f"/v1/runs/{rid}/rerun", headers=AUTH,
                    json={"engines": ["miti"], "presets": ["other"], "repeats": 1})
    assert legacy.status_code == 422
