"""Offline compare route contract and privacy tests over saved synthetic documents."""
import json
from types import SimpleNamespace

import pytest
from test_app import AUTH, client
from test_compare_load import FIXTURES, fakes

from onolys_eval_backend import compare_routes
from onolys_eval_backend.costs import PriceBook


@pytest.fixture
def routes(monkeypatch):
    def make(name="counts_golden"):
        scenario = json.loads((FIXTURES / f"{name}.json").read_text())
        source = fakes.FakeEvalRunSource(scenario)
        monkeypatch.setattr(compare_routes, "ServiceEvalRunSource", lambda services: source)
        c = client(services=SimpleNamespace(prices=PriceBook(scenario["prices"])))
        return scenario, source, c, f'/v1/eval-runs/{scenario["eval_run"]["eval_run_id"]}/compare'
    return make


def test_overview_balanced_claims_safe_fields_and_auth(routes):
    scenario, _, c, base = routes()
    assert c.get(base + "/overview").status_code == 401
    response = c.get(base + "/overview", headers=AUTH)
    assert response.status_code == 200
    data = response.json()
    a = scenario["eval_run"]["combos"][0]["combo_key"]
    assert data["heatmap"]["cells"]["question"][a]["off"] == pytest.approx(5 / 3)
    assert data["heatmap"]["cells"]["question"][a]["n"] == 2
    for clause in data["verdict"]:
        for claim in clause["claims"]:
            assert claim["value"] == data["count_error"][claim["combo"]]["off"]
    raw = response.text
    assert all(key not in raw for key in ['"rationale"', '"source"', '"parse"', '"pointer"', '"uid"'])
    assert c.get(base + "/overview?combos=unknown", headers=AUTH).status_code == 422
    one = c.get(base + "/overview", params={"combos": a}, headers=AUTH).json()
    assert [row["combo_key"] for row in one["leaderboard"]] == [a]


@pytest.mark.parametrize("name,code", [("running", "not_finished"), ("no_completed", "no_completed_runs")])
def test_status_errors(routes, name, code):
    _, _, c, base = routes(name)
    response = c.get(base + "/overview", headers=AUTH)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == code


def test_missing_group_and_session_are_404(routes, monkeypatch):
    _, source, c, base = routes()
    assert c.get(base + "/sessions/outside/lines", headers=AUTH).status_code == 404
    from onolys_eval.summary.source import SourceNotFound
    monkeypatch.setattr(source, "eval_run", lambda rid: (_ for _ in ()).throw(SourceNotFound(rid)))
    assert c.get(base + "/overview", headers=AUTH).status_code == 404


def test_no_human_keeps_operational_results(routes):
    scenario, _, c, base = routes()
    for entry in scenario["eval_run"]["sessions"]:
        entry["gold_sha256"] = None
    data = c.get(base + "/overview", headers=AUTH).json()
    assert data["has_human"] is False
    assert all(row["cost"]["per_run_usd"] is not None for row in data["leaderboard"])
    assert not data["verdict"]


def test_partial_provider_skips_and_analysis(routes):
    _, _, c, base = routes("provider_skipped")
    data = c.get(base + "/overview", headers=AUTH).json()
    assert data["coverage"]["eval_status"] == "partial"
    assert data["coverage"]["runs_skipped"] > 0
    skipped = [r for r in data["leaderboard"] if r["na"] and "skipped" in r["na"]["reason"]]
    assert skipped
    assert any(row["n"] > 0 for row in data["leaderboard"])
    assert c.get(base + "/analysis", headers=AUTH).json()["baseline"]["na"]


def test_reasoning_paged_filtered_verbatim_and_withheld(routes):
    scenario, _, c, base = routes()
    first = next(v for v in scenario["reports"].values() if "behaviours" in v["report"])
    inst = next(b for b in first["report"]["behaviours"] if b["instances"])["instances"][0]
    inst["rationale"] = ""
    page = c.get(base + "/reasoning", headers=AUTH).json()
    snippets = [x for g in page["groups"] for x in g["snippets"]]
    assert len(snippets) == 50
    assert page["next_cursor"]
    assert any(x["rationale"] == "" and x["withheld"] for x in snippets)
    second = c.get(base + "/reasoning", params={"cursor": page["next_cursor"]}, headers=AUTH)
    assert second.status_code == 200
    assert second.json() != page
    assert c.get(base + "/reasoning?cursor=bad", headers=AUTH).status_code == 422
    filtered = c.get(base + "/reasoning?code=question", headers=AUTH).json()
    assert all(g["code"] == "question" for g in filtered["groups"])


def test_lines_popup_safe_projections_and_fresh_hash(routes):
    scenario, _, c, base = routes("lines")
    sid = scenario["eval_run"]["sessions"][0]["session_id"]
    path = base + f"/sessions/{sid}/lines"
    response = c.get(path, headers=AUTH)
    assert response.status_code == 200
    data = response.json()
    assert data["turns"]
    assert '"rationale"' not in response.text
    tid = data["turns"][0]["id"]
    popup = c.get(path + f"/{tid}", headers=AUTH).json()
    assert popup["text"] == data["turns"][0]["text"]
    assert "human" in popup and "combos" in popup
    assert c.get(path + "/outside", headers=AUTH).status_code == 404
    scenario["transcripts"][sid]["sha256"] = "changed"
    for suffix in ["", f"/{tid}"]:
        response = c.get(path + suffix, headers=AUTH)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "transcript_changed"


def test_deep_dive_has_counts_globals_lines_and_no_rationales(routes):
    _, _, c, base = routes("lines")
    response = c.get(base + "/deep-dive", headers=AUTH)
    assert response.status_code == 200
    assert {"counts", "globals", "lines", "rationale_counts"} <= response.json().keys()
    assert '"rationale"' not in response.text


def test_skipped_only_filter_still_returns_explicit_na(routes):
    scenario, _, c, base = routes("provider_skipped")
    skipped = next(c["combo_key"] for c in scenario["eval_run"]["combos"] if c["provider"] == "gemini")
    response = c.get(base + "/overview", params={"combos": skipped}, headers=AUTH)
    assert response.status_code == 200
    assert response.json()["leaderboard"][0]["na"]["reason"] == "skipped: provider unavailable"
    assert response.json()["verdict"] == []


def test_unpriced_and_no_usage_are_na_and_bad_reports_excluded(routes):
    scenario, _, c, base = routes()
    a = scenario["eval_run"]["combos"][0]["combo_key"]
    for doc in scenario["run_docs"].values():
        if doc["eval"]["engine"] == "miti":
            doc["eval"]["resolved_route"]["litellm_id"] = "unknown"
            doc["run_info"]["usage"].pop("cost_usd", None)
    data = c.get(base + "/overview", headers=AUTH).json()
    assert next(r for r in data["leaderboard"] if r["combo_key"] == a)["cost"]["na"]


def test_filtered_cohort_uses_requested_combos(routes):
    scenario, _, c, base = routes("twelve_sessions")
    all_data = c.get(base + "/overview", headers=AUTH).json()
    best_key = scenario["eval_run"]["combos"][0]["combo_key"]
    one = c.get(base + "/overview", params={"combos": best_key}, headers=AUTH).json()
    assert one["count_error"][best_key]["n"] >= all_data["count_error"][best_key]["n"]


def test_overview_quality_cells_are_server_calculated_and_heatmap_is_bounded(routes):
    scenario, _, c, base = routes("lines")
    data = c.get(base + "/overview", headers=AUTH).json()
    assert len(data["heatmap"]["rows"]) == 16
    assert "count_error" not in data["heatmap"]["cells"]
    for row in data["leaderboard"]:
        for metric in ("globals_within_1", "line_accuracy", "macro_f1"):
            assert {"value", "n", "best", "na"} <= row[metric].keys()
        if row["combo_key"] == scenario["eval_run"]["combos"][0]["combo_key"]:
            assert row["line_accuracy"]["value"] is not None
            assert row["line_accuracy"]["n"] > 0
        if row["combo_key"] == scenario["eval_run"]["combos"][1]["combo_key"]:
            assert row["line_accuracy"]["na"]["reason"] == "no line-level output"
    assert any(row["line_accuracy"]["best"] for row in data["leaderboard"])


def test_skipped_combo_has_no_best_quality_cell(routes):
    _, _, c, base = routes("provider_skipped")
    data = c.get(base + "/overview", headers=AUTH).json()
    for row in data["leaderboard"]:
        if row["na"] and "skipped" in row["na"]["reason"]:
            assert all(not row[k]["best"] and row[k]["value"] is None
                       for k in ("globals_within_1", "line_accuracy", "macro_f1"))


def test_overview_quality_matches_deep_dive_values(routes):
    _, _, c, base = routes("lines")
    overview = c.get(base + "/overview", headers=AUTH).json()
    deep = c.get(base + "/deep-dive", headers=AUTH).json()
    for row in overview["leaderboard"]:
        key = row["combo_key"]
        line = deep["lines"]["combos"][key]
        for metric in ("line_accuracy", "macro_f1"):
            assert row[metric]["value"] == line[metric]
        global_values = [cell[key]["within_1"] for cell in deep["globals"]["cells"].values()]
        assert row["globals_within_1"]["value"] == pytest.approx(sum(global_values) / 4)


def test_unparseable_latest_attempt_excluded_and_not_replaced_by_earlier_done(routes):
    from copy import deepcopy

    scenario, _, c, base = routes()
    old = scenario["cells"][0]
    new = deepcopy(old)
    new.update(attempt=1, run_id="latest-broken", ended="2026-11-21T10:32:10Z")
    scenario["cells"].append(new)
    scenario["run_docs"]["latest-broken"] = deepcopy(scenario["run_docs"][old["run_id"]])
    scenario["reports"]["latest-broken"] = {"report": {}}
    data = c.get(base + "/overview", headers=AUTH).json()
    assert any(e["reason"] == "unparseable" for e in data["excluded"])
    assert data["coverage"]["runs_done"] == 11
    row = next(r for r in data["leaderboard"] if r["combo_key"] == old["combo_key"])
    assert {"code": "unparseable", "count": 1} in row["failures"]
