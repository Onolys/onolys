"""Read-side comparisons, protected output and immutable reruns; synthetic fixtures."""

from copy import deepcopy

import pytest
from onolys_eval.metrics import Scores, aggregate, compare
from test_app import AUTH, client
from test_runs import saved_upload, start
from test_uploads import gold

pytest_plugins = ["test_runs"]


def scores(**counts):
    data = gold()
    return Scores(
        counts={**data["counts"], **counts}, globals=data["globals"], summaries={"pct_cr": -999}
    ).model_dump(mode="json")


def finish(services, rid, values):
    units = services.repository.list_units(rid)
    for uid, score in zip(units, values, strict=True):
        services.repository.update_unit(
            rid,
            uid,
            {
                "status": "failed" if score is None else "done",
                "scores": score,
                "output": {"synthetic": uid},
                "output_ref": None,
            },
        )
    return units


def detail(c, rid):
    response = c.get(f"/v1/runs/{rid}", headers=AUTH)
    assert response.status_code == 200, response.text
    return response.json()


def test_compare_repeats_equal_core_unit_aggregate(services):
    c = client(services=services)
    rid = start(c, repeats=3).json()["run_id"]
    human = scores(question=2, sr=1, cr=1)
    low, high = scores(question=0, sr=0, cr=0), scores(question=4, sr=2, cr=2)
    finish(services, rid, [human, low, high, None])
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
    expected = aggregate(
        [compare(Scores.model_validate(human), Scores.model_validate(s)) for s in [low, high]]
    )
    assert result["aggregates"] == [
        {"engine": "miti", "preset": "configured-prod", "metrics": expected}
    ]
    assert expected["counts"]["question"]["mae"] == 2  # Cell mean's error is zero.
    assert any("consensus" in note for note in result["notes"])
    assert "unit_id" in body["units"][0]


def test_multiple_sessions_and_repeats_aggregate_not_cell_means(services):
    source = services.bucket.read_json("datasets/synthetic/manifest.json")
    other = {**deepcopy(source["sessions"][0]), "session_id": "two"}
    source["sessions"].append(other)
    services.bucket.write_json("datasets/synthetic/manifest.json", source)
    services.bucket.write_json(
        "datasets/synthetic/two/transcript.json",
        services.bucket.read_json("datasets/synthetic/one/transcript.json"),
    )
    services.bucket.write_json("datasets/synthetic/two/gold.json", {**gold(), "session_id": "two"})
    c = client(services=services)
    rid = start(
        c, input={"dataset_id": "synthetic", "session_ids": ["one", "two"]}, repeats=3
    ).json()["run_id"]
    h = scores(question=2)
    samples = [scores(question=0), scores(question=4), scores(question=6)]
    finish(services, rid, [h, *samples, h, samples[0], None, None])
    result = detail(c, rid)["compare"]
    assert [s["session_id"] for s in result["sessions"]] == ["one", "two"]
    expected = aggregate(
        [
            compare(Scores.model_validate(h), Scores.model_validate(s))
            for s in [*samples, samples[0]]
        ]
    )
    assert result["aggregates"][0]["metrics"] == expected
    assert expected["n"] == 4


def test_no_human_even_with_saved_gold_has_no_diffs_or_errors(services):
    c = client(services=services)
    rid = start(c, engines=["miti"], repeats=3).json()["run_id"]
    finish(services, rid, [scores(question=0, sr=0, cr=0), None, None])
    result = detail(c, rid)["compare"]
    assert result["has_human"] is False and result["aggregates"] == []
    session = result["sessions"][0]
    assert session["human"] is None and "diff" not in session["cells"][0]
    assert session["cells"][0]["values"]["pct_cr"] == {
        "mean": None,
        "min": None,
        "max": None,
        "n": 0,
    }


@pytest.mark.parametrize("state", ["queued", "failed"])
def test_unfinished_human_does_not_use_saved_gold(services, state):
    c = client(services=services)
    rid = start(c).json()["run_id"]
    finish(services, rid, [None, scores()])
    uid = next(iter(services.repository.list_units(rid)))
    services.repository.update_unit(rid, uid, {"status": state})
    result = detail(c, rid)["compare"]
    assert result["has_human"] is True
    assert result["sessions"][0]["human"] is None
    assert result["aggregates"][0]["metrics"] == aggregate([])
    assert all(v is None for v in result["sessions"][0]["cells"][0]["diff"].values())


def test_history_provenance_and_private_snapshot_paths(services):
    c = client(services=services)
    rid = start(c).json()["run_id"]
    services.repository.update_run(
        rid,
        {
            "usage": {"input_tokens": 25, "output_tokens": 5, "calls": 2, "cost_usd": None},
            "cost_usd_est": 0.125,
            "unpriced_units": 1,
        },
    )
    saved = services.repository.get_run(rid)
    response = c.get("/v1/runs", headers=AUTH)
    assert response.status_code == 200
    summary = response.json()["runs"][0]
    assert summary["run_id"] == rid
    for field in [
        "input",
        "engine_versions",
        "engine_git_sha",
        "resolved_presets",
        "created_at",
        "usage",
        "cost_usd_est",
        "unpriced_units",
    ]:
        assert summary[field] == saved[field]
    body = detail(c, rid)
    assert "input_ref" not in summary and "input_ref" not in body
    assert "runs/" not in str(summary)
    assert "output_ref" not in str(body)


def test_protected_inline_and_spilled_output_and_cross_run_rejection(services):
    c = client(services=services)
    rid = start(c).json()["run_id"]
    uids = list(finish(services, rid, [scores(), scores()]))
    path = f"/v1/runs/{rid}/units/{uids[0]}/output"
    assert c.get(path).status_code == 401
    outsider = client(
        services=services, claims={"email": "other@example.com", "email_verified": True}
    )
    assert outsider.get(path, headers=AUTH).status_code == 403
    assert c.get(path, headers=AUTH).json() == {"synthetic": uids[0]}
    ref = f"runs/{rid}/{uids[1]}.json"
    services.bucket.write_json(ref, {"large": "synthetic"})
    services.repository.update_unit(rid, uids[1], {"output": None, "output_ref": ref})
    assert c.get(f"/v1/runs/{rid}/units/{uids[1]}/output", headers=AUTH).json() == {
        "large": "synthetic"
    }
    services.repository.update_unit(rid, uids[1], {"output_ref": f"runs/another/{uids[1]}.json"})
    assert c.get(f"/v1/runs/{rid}/units/{uids[1]}/output", headers=AUTH).status_code == 404
    services.repository.update_unit(rid, uids[1], {"output_ref": f"runs/{rid}/../secret.json"})
    assert c.get(f"/v1/runs/{rid}/units/{uids[1]}/output", headers=AUTH).status_code == 404
    for suffix in ["/missing", f"/{rid}/units/missing/output", "/bad.id"]:
        assert c.get("/v1/runs" + suffix, headers=AUTH).status_code == 404


def test_rerun_saved_upload_preserves_effective_inputs_and_rechecks_hashes(services):
    saved_upload(services, has_gold=True)
    c = client(services=services)
    rid = start(
        c,
        input={"upload_id": "saved"},
        change_goal="original goal",
        language="fr",
        coded_span={"start_turn": 0, "end_turn": 1},
    ).json()["run_id"]
    old = services.repository.get_run(rid)
    services.bucket.write_json("uploads/saved/transcript.json", {"overwritten": True})
    services.bucket.write_json("uploads/saved/gold.json", {"overwritten": True})
    services.repository.update_upload("saved", {"status": "failed", "change_goal": "changed"})
    selection = {"engines": ["human", "oneshot:miti"], "presets": ["other"], "repeats": 3}
    response = c.post(f"/v1/runs/{rid}/rerun", headers=AUTH, json=selection)
    assert response.status_code == 200, response.text
    new_id = response.json()["run_id"]
    assert new_id != rid
    new = services.repository.get_run(new_id)
    assert new["created_by"] == "alice@example.com"
    for field in ["input", "change_goal", "language", "coded_span"]:
        assert new[field] == old[field]
    before, after = old["input_ref"]["sessions"][0], new["input_ref"]["sessions"][0]
    for field in ["transcript_sha256", "gold_sha256", "change_goal", "language", "coded_span"]:
        assert after[field] == before[field]
    assert detail(c, new_id)["compare"]["notes"].count("human_span_differs") == 1
    assert new["total_units"] == 4
    before_count = len(services.repository.list_runs())
    for replacement in [
        {"input": {"upload_id": "another"}},
        {"change_goal": "replace"},
        {"coded_span": None},
        {"input_ref": old["input_ref"]},
        {"repeats": True},
    ]:
        assert (
            c.post(
                f"/v1/runs/{rid}/rerun", headers=AUTH, json={**selection, **replacement}
            ).status_code
            == 422
        )
    assert len(services.repository.list_runs()) == before_count
    modified = services.bucket.read_json(before["transcript_path"])
    modified["language"] = "de"
    services.bucket.write_json(before["transcript_path"], modified)
    assert c.post(f"/v1/runs/{rid}/rerun", headers=AUTH, json=selection).status_code == 422
    assert len(services.repository.list_runs()) == before_count
    assert c.post("/v1/runs/missing/rerun", headers=AUTH, json=selection).status_code == 404


def test_rerun_dataset_snapshot_survives_deleted_sources_and_gold_hash_is_checked(services):
    c = client(services=services)
    rid = start(c).json()["run_id"]
    old = services.repository.get_run(rid)
    services.bucket.write_json("datasets/synthetic/manifest.json", {"overwritten": True})
    services.bucket.write_json("datasets/synthetic/one/transcript.json", {"overwritten": True})
    services.bucket.write_json("datasets/synthetic/one/gold.json", {"overwritten": True})
    selection = {"engines": ["human", "miti"], "presets": ["other"], "repeats": 1}
    response = c.post(f"/v1/runs/{rid}/rerun", headers=AUTH, json=selection)
    assert response.status_code == 200, response.text
    new = services.repository.get_run(response.json()["run_id"])
    source = new["input_ref"]["sessions"][0]
    for key in ["change_goal", "coded_span", "language", "transcript_sha256", "gold_sha256"]:
        assert source[key] == old["input_ref"]["sessions"][0][key]
    path = old["input_ref"]["sessions"][0]["gold_path"]
    changed = services.bucket.read_json(path)
    changed["parse"]["warnings"].append("Synthetic integrity check")
    services.bucket.write_json(path, changed)
    count = len(services.repository.list_runs())
    assert c.post(f"/v1/runs/{rid}/rerun", headers=AUTH, json=selection).status_code == 422
    assert len(services.repository.list_runs()) == count


def test_factory_prices_are_lazy_without_cloud(services):
    from test_app import ENV

    from onolys_eval_backend.config import EvalConfig
    from onolys_eval_backend.costs import PriceBook
    from onolys_eval_backend.services import EvalServices

    factory = EvalServices(EvalConfig.from_env(ENV))
    assert "prices" not in factory.__dict__
    assert isinstance(factory.prices, PriceBook)
    assert "bucket" not in factory.__dict__ and "repository" not in factory.__dict__
