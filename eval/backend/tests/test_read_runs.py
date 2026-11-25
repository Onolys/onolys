"""Read side on the prod pipeline (05 R10/R11): RunDocs, ReportDocs and gold behind the legacy
shapes. No units subcollection; scores are computed on read. Synthetic fixtures only."""

import hashlib
from copy import deepcopy
from datetime import timedelta

import pytest
from onolys_api.repo.models import ReportDoc, RunDoc, utcnow
from onolys_eval._formulas import compute_summaries
from onolys_eval.gold import COUNT_IDS, GLOBAL_IDS
from onolys_eval.metrics import Scores, aggregate, compare
from test_app import AUTH, client
from test_runs import SEL2, start
from test_uploads import gold

from onolys_eval_backend import eval_view
from onolys_eval_backend.read_runs import build_compare

pytest_plugins = ["test_runs"]

UID = "eval-owner"
LOW = "claude/claude-sonnet-5-5/low"
MED, HIGH = "claude/claude-sonnet-5-5/medium", "claude/claude-sonnet-5-5/high"


def scores(**counts):
    data = gold()
    return Scores(
        counts={**data["counts"], **counts}, globals=data["globals"], summaries={"pct_cr": -999}
    ).model_dump(mode="json")


def gold_with(session_id="one", **counts):
    data = {**gold(), "session_id": session_id}
    data["counts"] = {**data["counts"], **counts}
    data["summaries"] = compute_summaries(data["counts"], data["globals"])
    return data


def lean_report(sc):
    """A prod lean report whose projection is exactly the given Scores dump."""
    return {
        "behaviours": [{"item_id": k, "onolys_count": {"mean": v}} for k, v in sc["counts"].items()],
        "globals": [{"item_id": k, "onolys": {"score": v}} for k, v in sc["globals"].items()],
    }


def make_run(c, **overrides):
    """Create through the real endpoint; returns (eval run id, {dataset id: prod sid})."""
    response = start(c, **overrides)
    assert response.status_code == 200, response.text
    rid = response.json()["run_id"]
    doc = c.app.state.services.repository.get_run(rid)
    return rid, {e["dataset_session_id"]: sid for sid, e in doc["sessions"].items()}


def put_run(
    services, rid, sid, combo_key, repeat=0, attempt=0, *, status="done", report=None,
    error=None, usage=None, stage=None, ref_status=None, engine="miti", record=True,
):
    """What the scheduler + prod worker leave behind: a RunDoc, maybe a ReportDoc, a group ref."""
    run_id = hashlib.sha256(f"{rid}|{sid}|{combo_key}|{repeat}|{attempt}".encode()).hexdigest()[:32]
    now = utcnow()
    services.repo.create_run(
        UID, sid, run_id,
        RunDoc(
            change_goal="g", clinician_speaker="c", language="en", transcript_sha256="x" * 64,
            uid=UID, session_id=sid, run_id=run_id, status=status, stage=stage, error=error,
            started=now, ended=None if status in ("pending", "running") else now + timedelta(seconds=7),
            run_info={"usage": usage} if usage else None,
        ),
    )
    if report is not None:
        services.repo.put_report(UID, sid, run_id, ReportDoc(version=1, run_id=run_id, report=report))
    if record:
        doc = services.repository.get_run(rid)
        doc["sessions"][sid]["runs"].append({
            "run_id": run_id, "combo_key": combo_key, "engine": engine, "repeat": repeat,
            "attempt": attempt, "status": ref_status or status,
            **({"error": error} if error else {}),
        })
        services.repository.update_run(rid, {"sessions": doc["sessions"]})
    return run_id


def done(services, rid, sid, combo_key, sc, repeat=0, **kw):
    return put_run(services, rid, sid, combo_key, repeat, report=lean_report(sc), **kw)


def detail(c, rid):
    response = c.get(f"/v1/runs/{rid}", headers=AUTH)
    assert response.status_code == 200, response.text
    return response.json()


def units_of(body, **match):
    return [u for u in body["units"] if all(u.get(k) == v for k, v in match.items())]


def test_combo_run_summary_exposes_resolved_combos_and_base_preset(services):
    c = client(services=services)
    rid, _ = make_run(c)
    saved = services.repository.get_run(rid)
    assert saved["saved_config"]["resolved_combos"] and saved["base_preset"]
    summary = c.get("/v1/runs", headers=AUTH).json()["runs"][0]
    assert summary["resolved_combos"] == saved["saved_config"]["resolved_combos"]
    assert summary["base_preset"] == saved["base_preset"]
    assert detail(c, rid)["resolved_combos"] == saved["saved_config"]["resolved_combos"]


def test_summary_and_detail_carry_new_group_fields(services):
    c = client(services=services)
    rid, by = make_run(c, engines=["miti"])
    services.repository.update_run(rid, {
        "cancelled_at": "2026-11-24T10:00:00+00:00", "skipped_units": 2,
        "provider_skips": {"gemini": {"after_failures": 3, "skipped_cells": 4,
                                     "skipped_at": "2026-11-24T10:01:00+00:00"}},
    })
    expected = [{"provider": "gemini", "after_failures": 3, "skipped_cells": 4,
                 "skipped_at": "2026-11-24T10:01:00+00:00"}]
    (summary,) = c.get("/v1/runs", headers=AUTH).json()["runs"]
    assert summary["cancelled_at"] == "2026-11-24T10:00:00+00:00"
    assert summary["skipped_units"] == 2 and summary["provider_skips"] == expected
    body = detail(c, rid)
    assert body["provider_skips"] == expected and body["skipped_units"] == 2


def test_missing_new_fields_are_tolerated(services):
    services.repository.create_run(
        "old", {"created_at": "2026-01-01T00:00:00+00:00", "input": {}, "engines": [],
                "sessions": {}}, {})
    c = client(services=services)
    (summary,) = c.get("/v1/runs", headers=AUTH).json()["runs"]
    assert summary["cancelled_at"] is None and summary["skipped_units"] == 0
    assert summary["provider_skips"] == []


def test_provider_cooldowns_come_from_slots_docs(services):
    c = client(services=services)
    rid, by = make_run(c, engines=["miti"])
    repo = services.repository
    assert detail(c, rid)["provider_cooldowns"] == []  # no field on the slots doc
    assert repo.claim_slot("anthropic", "r1", rid, 2)
    repo._slots["anthropic"]["cooldown_until"] = "2026-11-24T12:00:00+00:00"
    assert detail(c, rid)["provider_cooldowns"] == [
        {"provider": "anthropic", "cooldown_until": "2026-11-24T12:00:00+00:00"}]


def test_unit_shape_ids_and_never_inline_output(services):
    c = client(services=services)
    rid, by = make_run(c)
    sid = by["one"]
    run_id = done(services, rid, sid, LOW, scores(question=2), usage={
        "input_tokens": 10, "output_tokens": 5, "calls": 1, "cost_usd": 0.25})
    body = detail(c, rid)
    human, ai = units_of(body, engine="human")[0], units_of(body, engine="miti")[0]
    assert human["unit_id"] == f"human-{sid}" and human["session_id"] == "one"
    assert human["status"] == "done" and human["combo_key"] is None
    assert ai["unit_id"] == run_id and ai["run_id"] == run_id and ai["prod_session_id"] == sid
    assert (ai["session_id"], ai["attempt"], ai["repeat"], ai["combo_key"]) == ("one", 0, 0, LOW)
    assert ai["status"] == "done" and ai["cost_usd_est"] == 0.25
    assert ai["run_info"]["usage"]["input_tokens"] == 10
    for unit in body["units"]:
        assert "output" not in unit and "output_ref" not in unit
    assert "runs/" not in str(body)


def test_output_is_served_from_the_report_doc_or_gold(services):
    c = client(services=services)
    rid, by = make_run(c)
    sid = by["one"]
    report = lean_report(scores(question=1))
    run_id = put_run(services, rid, sid, LOW, report=report)
    url = f"/v1/runs/{rid}/units/{{}}/output"
    assert c.get(url.format(run_id)).status_code == 401
    assert c.get(url.format(run_id), headers=AUTH).json() == report
    served = c.get(url.format(f"human-{sid}"), headers=AUTH)
    assert served.status_code == 200 and served.json()["session_id"] == "one"
    assert served.json()["counts"] == gold()["counts"]
    outsider = client(services=services, claims={"email": "o@example.com", "email_verified": True})
    assert outsider.get(url.format(run_id), headers=AUTH).status_code == 403


def test_large_report_is_resolved_through_its_blob_pointer(services):
    c = client(services=services)
    rid, by = make_run(c, engines=["miti"])
    report = {**lean_report(scores()), "pad": "x" * 600_000}
    run_id = put_run(services, rid, by["one"], LOW, report=report)
    stored = services.repo.get_report(UID, by["one"], run_id, resolve=False)
    assert stored.pointer is not None and stored.report is None
    assert c.get(f"/v1/runs/{rid}/units/{run_id}/output", headers=AUTH).json() == report


def test_output_rejects_unknown_foreign_and_malformed_units(services):
    c = client(services=services)
    rid, by = make_run(c)
    other_rid, other_by = make_run(c)
    foreign = put_run(services, other_rid, other_by["one"], LOW, report=lean_report(scores()))
    failed = put_run(services, rid, by["one"], LOW, status="failed", error="internal_error")
    for unit in [foreign, failed, "missing", "bad.id", "human-nope", f"human-{other_by['one']}x"]:
        assert c.get(f"/v1/runs/{rid}/units/{unit}/output", headers=AUTH).status_code == 404, unit
    for suffix in ["/missing", f"/{rid}/units/missing/output", "/bad.id"]:
        assert c.get("/v1/runs" + suffix, headers=AUTH).status_code == 404


def test_compare_repeats_equal_core_unit_aggregate(services):
    services.bucket.write_json(
        "datasets/synthetic/one/gold.json", gold_with(question=2, sr=1, cr=1))
    c = client(services=services)
    rid, by = make_run(c, repeats=3)
    sid = by["one"]
    low, high = scores(question=0, sr=0, cr=0), scores(question=4, sr=2, cr=2)
    done(services, rid, sid, LOW, low, 0)
    done(services, rid, sid, LOW, high, 1)
    put_run(services, rid, sid, LOW, 2, status="failed", error="internal_error")
    body = detail(c, rid)
    result = body["compare"]
    assert result["has_human"] is True and len(result["metrics"]) == 16
    assert [m["id"] for m in result["metrics"]][-2:] == ["reflection_question_ratio", "pct_cr"]
    session = result["sessions"][0]
    assert session["session_id"] == "one" and session["human"]["pct_cr"] == 0.5
    cell = session["cells"][0]
    assert cell["n"] == 2 and cell["failed"] == 1 and len(cell["unit_ids"]) == 3
    assert cell["values"]["question"] == {"mean": 2, "min": 0, "max": 4, "n": 2}
    assert cell["values"]["pct_cr"] == {"mean": 0.5, "min": 0.5, "max": 0.5, "n": 1}
    assert cell["diff"]["question"] == 0
    human = scores(question=2, sr=1, cr=1)
    expected = aggregate(
        [compare(Scores.model_validate(human), Scores.model_validate(s)) for s in [low, high]]
    )
    (agg,) = result["aggregates"]
    assert agg["engine"] == "miti" and agg["combo_key"] == LOW and "preset" not in agg
    assert agg["metrics"] == expected and expected["counts"]["question"]["mae"] == 2
    assert any("consensus" in note for note in result["notes"])
    assert cell["error_code"] == "internal_error"


def two_session_services(services):
    source = services.bucket.read_json("datasets/synthetic/manifest.json")
    source["sessions"].append({**deepcopy(source["sessions"][0]), "session_id": "two"})
    services.bucket.write_json("datasets/synthetic/manifest.json", source)
    other = services.bucket.read_json("datasets/synthetic/one/transcript.json")
    other["turns"][0]["text"] = "a distinct opening " + "actual speech " * 30
    services.bucket.write_json("datasets/synthetic/two/transcript.json", other)


def test_matrix_two_sessions_three_combos_hand_computed(services):
    two_session_services(services)
    services.bucket.write_json("datasets/synthetic/one/gold.json", gold_with("one", question=2))
    services.bucket.write_json("datasets/synthetic/two/gold.json", gold_with("two", question=4))
    c = client(services=services)
    sel = {"models": ["claude"], "tiers": ["claude-sonnet-5-5"], "efforts": ["low", "medium", "high"]}
    rid, by = make_run(
        c, input={"dataset_id": "synthetic", "session_ids": ["one", "two"]}, selection=sel)
    one, two = by["one"], by["two"]
    g = GLOBAL_IDS[0]
    low_one = scores(question=4)
    low_one["globals"] = {**low_one["globals"], g: 5}
    med_one = scores(question=1)
    med_one["globals"] = {**med_one["globals"], g: 4}
    done(services, rid, one, LOW, low_one, usage={
        "input_tokens": 10, "output_tokens": 5, "calls": 1, "cost_usd": 0.5})
    done(services, rid, one, MED, med_one)
    put_run(services, rid, one, HIGH, status="failed", error="rate_limited",
            usage={"input_tokens": 7, "output_tokens": 1, "calls": 1, "cost_usd": 0.0})
    done(services, rid, two, LOW, scores(question=4), usage={
        "input_tokens": 20, "output_tokens": 10, "calls": 1, "cost_usd": 0.25})
    done(services, rid, two, MED, scores(question=0))
    done(services, rid, two, HIGH, scores(question=6))
    body = detail(c, rid)
    result = body["compare"]
    s_one, s_two = result["sessions"]
    assert (s_one["session_id"], s_two["session_id"]) == ("one", "two")
    cells = {x["combo_key"]: x for x in s_one["cells"]}
    assert list(cells) == [LOW, MED, HIGH] and all(x["engine"] == "miti" for x in cells.values())
    q = cells[LOW]["error"]["question"]
    assert (q["mae"], q["mean_bias"], q["n"]) == (2, 2, 1)
    assert cells[LOW]["error"][g]["mae"] == 2
    assert cells[MED]["error"]["question"]["mean_bias"] == -1
    assert cells[HIGH]["error"] is None and cells[HIGH]["failed"] == 1 and cells[HIGH]["n"] == 0
    assert cells[HIGH]["error_code"] == "rate_limited" and cells[LOW]["error_code"] is None
    cells2 = {x["combo_key"]: x for x in s_two["cells"]}
    assert cells2[LOW]["error"]["question"] == {"mae": 0, "mean_bias": 0, "n": 1}
    assert cells2[MED]["error"]["question"]["mae"] == 4
    assert cells2[HIGH]["error"]["question"]["mean_bias"] == 2
    aggs = {a["combo_key"]: a for a in result["aggregates"]}
    assert list(aggs) == [LOW, MED, HIGH]
    assert aggs[LOW]["metrics"]["counts"]["question"]["mae"] == 1
    assert aggs[MED]["metrics"]["counts"]["question"]["mae"] == 2.5
    assert aggs[MED]["metrics"]["counts"]["question"]["mean_bias"] == -2.5
    assert [aggs[k]["n"] for k in (LOW, MED, HIGH)] == [2, 2, 1]
    assert [aggs[k]["failed"] for k in (LOW, MED, HIGH)] == [0, 0, 1]
    assert aggs[LOW]["within_1"][g] == {"n": 1, "total": 2, "fraction": 0.5}
    assert aggs[LOW]["usage"] == {"input_tokens": 30, "output_tokens": 15, "calls": 2}
    assert aggs[LOW]["cost_usd_est"] == 0.75
    assert aggs[HIGH]["usage"]["input_tokens"] == 7 and aggs[HIGH]["cost_usd_est"] == 0
    assert body["legacy_selection"] is False and body["combo_keys"] == [LOW, MED, HIGH]
    assert body["selection"] == sel


def test_no_human_has_no_diffs_or_errors(services):
    services.bucket.delete("datasets/synthetic/one/gold.json")
    c = client(services=services)
    rid, by = make_run(c, engines=["miti"], repeats=3)
    done(services, rid, by["one"], LOW, scores(question=0, sr=1, cr=1))
    put_run(services, rid, by["one"], LOW, 1, status="failed", error="internal_error")
    result = detail(c, rid)["compare"]
    assert result["has_human"] is False and result["aggregates"] == []
    session = result["sessions"][0]
    assert session["human"] is None and "diff" not in session["cells"][0]
    assert session["cells"][0]["values"]["pct_cr"]["n"] == 1


def test_final_attempt_is_highest_and_earlier_failures_stay_listed(services):
    services.bucket.write_json("datasets/synthetic/one/gold.json", gold_with(question=2))
    c = client(services=services)
    rid, by = make_run(c, engines=["miti"])
    sid = by["one"]
    first = put_run(services, rid, sid, LOW, attempt=0, status="failed", error="internal_error")
    second = done(services, rid, sid, LOW, scores(question=2), attempt=1)
    body = detail(c, rid)
    ai = units_of(body, engine="miti")
    assert [(u["unit_id"], u["attempt"], u["status"]) for u in ai] == [
        (first, 0, "failed"), (second, 1, "done")]
    assert [u["final"] for u in ai] == [False, True]
    cell = body["compare"]["sessions"][0]["cells"][0]
    assert cell["unit_ids"] == [second] and cell["n"] == 1 and cell["failed"] == 0
    assert body["compare"]["aggregates"][0]["failed"] == 0
    cells = eval_view.list_cells(c.app.state.services, rid)
    assert [(x["attempt"], x["status"], x["run_id"]) for x in cells] == [
        (0, "failed", first), (1, "done", second)]


def test_live_status_then_final_status_without_any_earlier_get(services):
    c = client(services=services)
    rid, by = make_run(c, engines=["miti"])
    sid = by["one"]
    run_id = put_run(services, rid, sid, LOW, status="running", stage="evaluating")
    live = units_of(detail(c, rid), engine="miti")[0]
    assert live["status"] == "running" and live["stage"] == "evaluating"
    # The worker finishes; the scheduler has not ticked: the group ref still says running.
    services.repo.update_run(UID, sid, run_id, {"status": "done", "stage": None, "ended": utcnow()})
    services.repo.put_report(UID, sid, run_id, ReportDoc(
        version=1, run_id=run_id, report=lean_report(scores(question=3))))
    assert services.repository.get_run(rid)["sessions"][sid]["runs"][0]["status"] == "running"
    final = detail(c, rid)
    assert units_of(final, engine="miti")[0]["status"] == "done"
    assert final["compare"]["sessions"][0]["cells"][0]["values"]["question"]["mean"] == 3


def test_waiting_skipped_and_unstarted_cells(services):
    c = client(services=services)
    rid, by = make_run(c, engines=["miti"], selection=SEL2)
    sid = by["one"]
    high = "claude/claude-sonnet-5-5/high"
    put_run(services, rid, sid, LOW, status="failed", error="rate_limited", ref_status="waiting")
    body = detail(c, rid)
    by_combo = {u["combo_key"]: u for u in units_of(body, engine="miti")}
    assert by_combo[LOW]["status"] == "waiting" and by_combo[high]["status"] == "queued"
    assert by_combo[high]["run_id"] is None
    services.repository.update_run(rid, {"provider_skips": {"anthropic": {"skipped_cells": 1}}})
    again = {u["combo_key"]: u for u in units_of(detail(c, rid), engine="miti")}
    assert again[high]["status"] == "skipped"
    out = c.get(f"/v1/runs/{rid}/units/{again[high]['unit_id']}/output", headers=AUTH)
    assert out.status_code == 404


def test_drift_failed_cell_without_run_id_is_listed(services):
    c = client(services=services)
    rid, by = make_run(c, engines=["miti"])
    sid = by["one"]
    doc = services.repository.get_run(rid)
    doc["sessions"][sid]["runs"].append({
        "run_id": None, "combo_key": LOW, "engine": "miti", "repeat": 0, "attempt": 0,
        "status": "failed", "error": "execution_config_changed"})
    services.repository.update_run(rid, {"sessions": doc["sessions"]})
    (unit,) = units_of(detail(c, rid), engine="miti")
    assert unit["status"] == "failed" and unit["run_id"] is None
    assert unit["error"] == {"code": "execution_config_changed"}


def test_done_run_with_unreadable_report_is_listed_without_scores(services):
    c = client(services=services)
    rid, by = make_run(c, engines=["miti"])
    put_run(services, rid, by["one"], LOW, report={"behaviours": "broken"})
    body = detail(c, rid)
    assert units_of(body, engine="miti")[0]["status"] == "done"
    cell = body["compare"]["sessions"][0]["cells"][0]
    assert cell["n"] == 0


def test_list_cells_shape_order_and_loaders(services):
    two_session_services(services)
    services.bucket.write_json("datasets/synthetic/two/gold.json", gold_with("two"))
    c = client(services=services)
    rid, by = make_run(
        c, input={"dataset_id": "synthetic", "session_ids": ["two", "one"]}, selection=SEL2)
    high = "claude/claude-sonnet-5-5/high"
    # created out of order on purpose; the listing is session -> plan -> attempt
    done(services, rid, by["one"], high, scores(), usage={
        "input_tokens": 1, "output_tokens": 2, "calls": 1, "cost_usd": 0.1})
    done(services, rid, by["two"], LOW, scores())
    svc = c.app.state.services
    cells = eval_view.list_cells(svc, rid)
    assert [(x["dataset_session_id"], x["combo_key"], x["status"]) for x in cells] == [
        ("two", LOW, "done"), ("two", high, "queued"), ("one", LOW, "queued"), ("one", high, "done")]
    cell = cells[3]
    assert set(cell) == {"sid", "dataset_session_id", "engine", "combo_key", "repeat", "attempt",
                         "run_id", "status", "started", "ended", "error", "run_info", "gold_ref"}
    assert cell["sid"] == by["one"] and cell["run_info"]["cost_usd_est"] == 0.1
    assert cell["run_info"]["usage"]["output_tokens"] == 2 and cell["error"] is None
    assert cell["gold_ref"]["path"].startswith("gold/") and cell["gold_ref"]["sha256"]
    assert cell["started"] is not None and cell["ended"] is not None
    assert eval_view.load_report(svc, cell)["behaviours"]
    assert eval_view.load_report(svc, cells[1]) is None  # not started: no report
    assert eval_view.load_gold(svc, by["one"])["counts"] == gold()["counts"]
    assert eval_view.load_gold(svc, "unknown") is None


def test_legacy_build_compare_is_unchanged_for_a_unit_fixture():
    """The legacy builder is fed legacy-shaped units; its output for a fixed fixture is pinned."""
    run = {"engines": ["human", "miti"], "input": {"session_ids": ["one"]},
           "combos": [{"model": "claude", "tier": "claude-sonnet-5-5", "effort": "low"}]}
    human = {"session_id": "one", "engine": "human", "status": "done", "combo_key": None,
             "scores": {"counts": scores(question=2)["counts"], "globals": scores()["globals"],
                        "quality_label": None}}
    ai = {"session_id": "one", "engine": "miti", "status": "done", "combo_key": LOW,
          "scores": scores(question=4), "run_info": {"usage": {"input_tokens": 3}},
          "cost_usd_est": 0.5}
    result = build_compare(run, {"h": human, "a": ai})
    (cell,) = result["sessions"][0]["cells"]
    assert cell["unit_ids"] == ["a"] and cell["n"] == 1
    assert cell["values"]["question"] == {"mean": 4, "min": 4, "max": 4, "n": 1}
    assert cell["diff"]["question"] == 2 and cell["error"]["question"]["mae"] == 2
    assert result["aggregates"][0]["cost_usd_est"] == 0.5
    assert result["aggregates"][0]["usage"]["input_tokens"] == 3
    assert [m["id"] for m in result["metrics"]] == [*COUNT_IDS, *GLOBAL_IDS, "reflection_question_ratio", "pct_cr"]


def test_view_compare_matches_legacy_builder_on_the_same_scores(services):
    services.bucket.write_json("datasets/synthetic/one/gold.json", gold_with(question=2))
    c = client(services=services)
    rid, by = make_run(c)
    done(services, rid, by["one"], LOW, scores(question=4))
    via_view = detail(c, rid)["compare"]
    run = services.repository.get_run(rid)
    units = {
        "h": {"session_id": "one", "engine": "human", "status": "done", "combo_key": None,
              "scores": {"counts": gold_with(question=2)["counts"], "globals": gold()["globals"]}},
        "a": {"session_id": "one", "engine": "miti", "status": "done", "combo_key": LOW,
              "scores": scores(question=4), "run_info": {"usage": {}}, "cost_usd_est": 0},
    }
    direct = build_compare(run, units)
    strip = lambda r: {k: v for k, v in r.items() if k != "sessions"}  # noqa: E731
    assert strip(via_view)["aggregates"][0]["metrics"] == strip(direct)["aggregates"][0]["metrics"]
    assert via_view["sessions"][0]["cells"][0]["values"] == direct["sessions"][0]["cells"][0]["values"]


def test_partial_human_scores_leave_missing_metrics_null():
    from onolys_eval.metrics import PartialScores

    from onolys_eval_backend.read_runs import _values

    values = _values(PartialScores(counts={"question": 3, "cr": 1, "sr": 1}, quality_label="low"))
    assert values["question"] == 3 and values["gi"] is None and values["cct"] is None
    assert values["pct_cr"] == .5 and values["reflection_question_ratio"] == 2 / 3


def test_history_provenance_and_private_snapshot_paths(services):
    c = client(services=services)
    rid, _ = make_run(c)
    services.repository.update_run(
        rid,
        {
            "usage": {"input_tokens": 25, "output_tokens": 5, "calls": 2, "cost_usd": None},
            "cost_usd_est": 0.125,
            "unpriced_units": 1,
        },
    )
    saved = services.repository.get_run(rid)
    summary = c.get("/v1/runs", headers=AUTH).json()["runs"][0]
    assert summary["run_id"] == rid
    for field in ["input", "engine_versions", "engine_git_sha", "created_at", "usage",
                  "cost_usd_est", "unpriced_units", "total_units", "done_units"]:
        assert summary[field] == saved[field]
    body = detail(c, rid)
    for private in ("input_ref", "sessions", "cells_wait", "saved_config"):
        assert private not in summary and private not in body
    assert "gold/" not in str(body)


def test_history_paginates_past_default_cap_with_stable_cursor(services):
    repository = services.repository
    for i in range(7):
        repository.create_run(
            f"r{i}",
            {"created_at": f"2026-01-01T00:00:0{i}+00:00", "input": {}, "engines": []},
            {},
        )
    c = client(services=services)
    seen, cursor = [], None
    while True:
        params = {"limit": 3, **({"cursor": cursor} if cursor else {})}
        page = c.get("/v1/runs", headers=AUTH, params=params).json()
        seen += [r["run_id"] for r in page["runs"]]
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert seen == [f"r{i}" for i in reversed(range(7))]
    default = c.get("/v1/runs", headers=AUTH).json()
    assert len(default["runs"]) == 7 and default["next_cursor"] is None


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 201}, {"cursor": "!!"}])
def test_history_rejects_bad_limit_or_cursor(services, params):
    assert client(services=services).get("/v1/runs", headers=AUTH, params=params).status_code == 422


def test_summary_exposes_cancel_requested(services):
    c = client(services=services)
    rid, _ = make_run(c)
    assert c.get("/v1/runs", headers=AUTH).json()["runs"][0]["cancel_requested"] is False
    services.repository.cancel_run(rid)
    assert detail(c, rid)["cancel_requested"] is True


def test_factory_prices_are_lazy_without_cloud(services):
    from test_app import ENV

    from onolys_eval_backend.config import EvalConfig
    from onolys_eval_backend.costs import PriceBook
    from onolys_eval_backend.services import EvalServices

    factory = EvalServices(EvalConfig.from_env(ENV))
    assert "prices" not in factory.__dict__
    assert isinstance(factory.prices, PriceBook)
    assert "bucket" not in factory.__dict__ and "repository" not in factory.__dict__
