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


def test_overview_header_saved_progress_and_real_line_session_choices(routes):
    from onolys_eval_backend.eval_sessions import canonical_sha256

    scenario, _, c, base = routes("lines")
    group = scenario["eval_run"]
    group.update(done_units=11, total_units=15, skipped_units=2)
    first, second = group["sessions"]
    original_sid = first["session_id"]
    uploaded_sid = "upload-actual-session-id"
    first["session_id"] = uploaded_sid
    first["dataset_session_id"] = None
    scenario["transcripts"][uploaded_sid] = scenario["transcripts"].pop(original_sid)
    for cell in scenario["cells"]:
        if cell["sid"] == original_sid:
            cell["sid"] = uploaded_sid
    for doc in scenario["run_docs"].values():
        if doc["session_id"] == original_sid:
            doc["session_id"] = uploaded_sid
    # Non-clinician, absent and out-of-span gold IDs do not add matched lines.
    gold = scenario["gold"][first["gold_sha256"]]
    gold["utterance_codes"] += [
        {"turn_id": tid, "codes": [], "note": None} for tid in ("t2", "outside", "t1")]
    sha = canonical_sha256(gold)
    scenario["gold"][sha] = gold
    first["gold_sha256"] = sha
    scenario["transcripts"][second["session_id"]]["sha256"] = "changed"
    header = c.get(base + "/overview", headers=AUTH).json()["header"]
    assert header["progress"] == {"done_units": 11, "total_units": 15, "skipped_units": 2}
    assert header["line_sessions"] == [
        {"session_id": uploaded_sid, "matched_lines": 5},
        {"session_id": second["session_id"], "matched_lines": None}]
    assert header["coverage"]["runs_total"] == 8  # AI compare coverage stays separate.


def test_line_session_choices_without_gold_are_zero(routes):
    scenario, _, c, base = routes("lines")
    for entry in scenario["eval_run"]["sessions"]:
        entry["gold_sha256"] = None
    header = c.get(base + "/overview", headers=AUTH).json()["header"]
    assert all(row["matched_lines"] == 0 for row in header["line_sessions"])


def test_operational_best_marks_all_ties_and_keeps_real_values(routes):
    scenario, _, c, base = routes("lines")
    for doc in scenario["run_docs"].values():
        doc["run_info"]["usage"]["cost_usd"] = 0
    rows = c.get(base + "/overview", headers=AUTH).json()["leaderboard"]
    assert all(row["operational_best"] == {"failures": True, "cost": True, "time": True}
               for row in rows)
    assert all(row["cost"]["per_run_usd"] == 0 and row["time"]["mean_seconds"] == 75
               and row["failures"] == [] for row in rows)


def test_operational_best_excludes_skipped_and_missing_values(routes):
    scenario, _, c, base = routes("provider_skipped")
    rows = c.get(base + "/overview", headers=AUTH).json()["leaderboard"]
    skipped = {combo["combo_key"] for combo in scenario["eval_run"]["combos"]
               if combo["provider"] == "gemini"}
    assert all(not any(row["operational_best"].values())
               for row in rows if row["combo_key"] in skipped)
    scenario, _, c, base = routes("lines")
    for doc in scenario["run_docs"].values():
        doc.pop("run_info", None)
        doc.pop("started", None)
    for cell in scenario["cells"]:
        cell.pop("run_info", None)
        cell.pop("started", None)
    rows = c.get(base + "/overview", headers=AUTH).json()["leaderboard"]
    assert all(row["operational_best"] == {"failures": True, "cost": False, "time": False}
               for row in rows)


def test_operational_best_requires_a_finished_attempt_for_failures(routes):
    scenario, _, c, base = routes("lines")
    key = scenario["eval_run"]["combos"][1]["combo_key"]
    for cell in scenario["cells"]:
        if cell["combo_key"] == key:
            cell["status"] = "cancelled"
    rows = c.get(base + "/overview", headers=AUTH).json()["leaderboard"]
    row = next(row for row in rows if row["combo_key"] == key)
    assert row["failures"] == []
    assert not any(row["operational_best"].values())


def test_deep_dive_cohorts_and_human_means_follow_selected_combos(routes):
    scenario, _, c, base = routes("twelve_sessions")
    key = scenario["eval_run"]["combos"][0]["combo_key"]
    for params in ({}, {"combos": key}):
        overview = c.get(base + "/overview", params=params, headers=AUTH).json()
        deep = c.get(base + "/deep-dive", params=params, headers=AUTH).json()
        assert deep["cohorts"] == overview["cohorts"]
        for metric, cells in deep["counts"]["cells"].items():
            human = deep["counts"]["human"][metric]
            assert human["n"] == deep["cohorts"][metric]["paired"]
            for cell in cells.values():
                if cell["value"] is not None:
                    assert human["value"] == pytest.approx(cell["value"] - cell["bias"])
                    assert human["na"] is None
                else:
                    assert human["value"] is None and human["na"]


def test_line_matches_drill_uses_matrix_alignment_repeats_and_plan_order(routes):
    scenario, source, c, base = routes("lines")
    combo = scenario["eval_run"]["combos"][0]["combo_key"]
    deep = c.get(base + "/deep-dive", headers=AUTH).json()
    before = len(source.calls)
    for human, columns in deep["lines"]["combos"][combo]["confusion"].items():
        for model, count in columns.items():
            response = c.get(base + "/line-matches", params={
                "combo": combo, "code": human, "metric": model}, headers=AUTH)
            assert response.status_code == 200
            ids = response.json()["session_ids"]
            assert bool(ids) == bool(count)
            assert ids == [s["session_id"] for s in scenario["eval_run"]["sessions"]
                           if s["session_id"] in ids]
            assert set(response.json()) == {"session_ids"}
    # Terminal projection is reused; no per-session reads or text are required.
    assert all(call[0] in {"eval_run", "cells"} for call in source.calls[before:])
    multi = c.get(base + "/line-matches", params={
        "combo": combo, "code": "multi", "metric": "multi"}, headers=AUTH).json()
    assert multi == {"session_ids": [scenario["eval_run"]["sessions"][0]["session_id"]]}


def test_line_matches_validates_filters_and_excludes_unavailable_lanes(routes):
    scenario, _, c, base = routes("lines")
    combo = scenario["eval_run"]["combos"][0]["combo_key"]
    params = {"combo": combo, "code": "question", "metric": "question"}
    assert c.get(base + "/line-matches", params=params).status_code == 401
    for field in ("combo", "code", "metric"):
        assert c.get(base + "/line-matches", params={**params, field: "unknown"},
                     headers=AUTH).status_code == 422
    params["combo"] = scenario["eval_run"]["combos"][1]["combo_key"]
    assert c.get(base + "/line-matches", params=params, headers=AUTH).json() == {"session_ids": []}
    # Same no-line behavior when gold rows are missing.
    scenario, _, c, base = routes("lines")
    for session in scenario["eval_run"]["sessions"]:
        session["gold_sha256"] = None
    params["combo"] = combo
    assert c.get(base + "/line-matches", params=params, headers=AUTH).json() == {"session_ids": []}


def test_reasoning_human_notes_are_aligned_verbatim_filtered_and_bounded(routes):
    from onolys_eval_backend.eval_sessions import canonical_sha256

    scenario, _, c, base = routes("lines")
    entry = scenario["eval_run"]["sessions"][0]
    sid = entry["session_id"]
    gold = scenario["gold"][entry["gold_sha256"]]
    gold["utterance_codes"][0]["note"] = "Saved human observation verbatim."
    # Notes outside the pinned span, on the client lane and absent turns are never exposed.
    gold["utterance_codes"] += [{"turn_id": tid, "codes": ["question"], "note": "UNALIGNED"}
                               for tid in ("t1", "t2", "outside")]
    # Fill several pages with aligned notes without adding any report instances.
    turns = scenario["transcripts"][sid]["transcript"]["turns"]
    for i in range(60):
        tid = f"note-{i}"
        turns.insert(2, {"id": tid, "speaker": "A", "role": "clinician", "text": "Synthetic.",
                         "start_ms": 20000, "end_ms": 21000})
        gold["utterance_codes"].append({"turn_id": tid, "codes": ["question"],
                                        "note": f"Human note {i}"})
    for doc in scenario["run_docs"].values():
        if doc["session_id"] == sid:
            doc["coded_span"] = {"start_turn": 1, "end_turn": len(turns)}
    sha = canonical_sha256(gold)
    scenario["gold"][sha] = gold
    entry["gold_sha256"] = sha
    notes, cursor = [], None
    while True:
        params = {"code": "question", **({"cursor": cursor} if cursor else {})}
        page = c.get(base + "/reasoning", params=params, headers=AUTH).json()
        assert sum(len(g["snippets"]) + len(g.get("human_notes", []))
                   for g in page["groups"]) <= 50
        notes += [note for group in page["groups"] for note in group.get("human_notes", [])]
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert len(notes) == 61
    assert {"session_id": sid, "turn_id": "t3", "note": "Saved human observation verbatim."} in notes
    assert all(n["note"] != "UNALIGNED" and set(n) == {"session_id", "turn_id", "note"}
               for n in notes)
    combo = scenario["eval_run"]["combos"][0]["combo_key"]
    filtered = c.get(base + "/reasoning", params={"combo": combo}, headers=AUTH).json()
    assert all(not g.get("human_notes") for g in filtered["groups"])


def test_reasoning_global_session_filter_and_cursor_scope(routes):
    scenario, _, c, base = routes("lines")
    sid = scenario["eval_run"]["sessions"][0]["session_id"]
    params = {"session": sid, "kind": "global"}
    response = c.get(base + "/reasoning", params=params, headers=AUTH)
    assert response.status_code == 200
    page = response.json()
    assert page["groups"]
    for group in page["groups"]:
        assert group["code"] in {"cct", "sst", "partnership", "empathy"}
        assert not group.get("human_notes")
        assert all(snippet["session_id"] == sid and "evidence" in snippet
                   for snippet in group["snippets"])
    assert c.get(base + "/reasoning", params={"session": "outside"},
                 headers=AUTH).status_code == 404
    assert c.get(base + "/reasoning", params={"kind": "unknown"},
                 headers=AUTH).status_code == 422
    scenario, _, c, base = routes()
    sid = scenario["eval_run"]["sessions"][0]["session_id"]
    first = c.get(base + "/reasoning", headers=AUTH).json()
    assert first["next_cursor"]
    assert c.get(base + "/reasoning", params={"session": sid, "kind": "global",
                 "cursor": first["next_cursor"]},
                 headers=AUTH).status_code == 422


def test_line_matches_uses_selected_cohort_and_omits_transcript_conflicts(routes):
    scenario, _, c, base = routes("lines")
    first, second = [s["session_id"] for s in scenario["eval_run"]["sessions"]]
    combo, other = [c["combo_key"] for c in scenario["eval_run"]["combos"]]
    for cell in scenario["cells"]:
        if cell["sid"] == first and cell["combo_key"] == other:
            cell["status"] = "cancelled"
    params = {"combo": combo, "code": "question", "metric": "question"}
    assert c.get(base + "/line-matches", params=params, headers=AUTH).json() == {
        "session_ids": [second]}
    assert c.get(base + "/line-matches", params={**params, "combos": combo},
                 headers=AUTH).json() == {"session_ids": [first, second]}
    scenario, _, c, base = routes("lines")
    scenario["transcripts"][first]["sha256"] = "changed"
    assert c.get(base + "/line-matches", params=params, headers=AUTH).json() == {
        "session_ids": [second]}


def test_operational_best_uses_lowest_observation_for_each_metric(routes):
    scenario, _, c, base = routes("lines")
    combo, other = [c["combo_key"] for c in scenario["eval_run"]["combos"]]
    for doc in scenario["run_docs"].values():
        doc["run_info"]["usage"]["cost_usd"] = 0 if doc["eval"]["combo_key"] == combo else 1
        if doc["eval"]["combo_key"] == other:
            doc["ended"] = doc["started"]
    first = next(cell for cell in scenario["cells"] if cell["combo_key"] == combo)
    first.update(status="failed", error={"code": "synthetic"})
    rows = {r["combo_key"]: r for r in c.get(base + "/overview", headers=AUTH).json()["leaderboard"]}
    assert rows[combo]["operational_best"] == {"failures": False, "cost": True, "time": False}
    assert rows[other]["operational_best"] == {"failures": True, "cost": False, "time": True}


def test_operational_best_never_marks_a_combo_whose_runs_all_failed(routes):
    """A combo that only failed (cheap and fast) must not win cost, time or failures."""
    scenario, _, c, base = routes("lines")
    failed, other = [c["combo_key"] for c in scenario["eval_run"]["combos"]]
    for doc in scenario["run_docs"].values():
        doc["run_info"]["usage"]["cost_usd"] = 0 if doc["eval"]["combo_key"] == failed else 1
        if doc["eval"]["combo_key"] == failed:
            doc["ended"] = doc["started"]
    for cell in scenario["cells"]:
        if cell["combo_key"] == failed:
            cell.update(status="failed", error={"code": "invalid_parameters"})
    rows = {r["combo_key"]: r for r in c.get(base + "/overview", headers=AUTH).json()["leaderboard"]}
    assert not any(rows[failed]["operational_best"].values())
    assert rows[other]["operational_best"] == {"failures": True, "cost": True, "time": True}


@pytest.mark.parametrize("path", ["/overview", "/deep-dive", "/analysis", "/reasoning"])
def test_every_projection_carries_dataset_session_labels(routes, path):
    scenario, _, c, base = routes()
    expected = {s["session_id"]: s["dataset_session_id"] for s in scenario["eval_run"]["sessions"]}
    assert expected and all(label != sid for sid, label in expected.items())
    response = c.get(base + path, headers=AUTH)
    assert response.status_code == 200, response.text
    assert response.json()["session_labels"] == expected
