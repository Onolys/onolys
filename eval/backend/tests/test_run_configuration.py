"""Saved configuration is public and rerunnable without changing saved inputs."""

from dataclasses import replace

import pytest
from test_app import AUTH, client
from test_read_runs import detail
from test_runs import SEL1, start

pytest_plugins = ["test_runs"]


def rerun(c, rid, **changes):
    return c.post(
        f"/v1/runs/{rid}/rerun", headers=AUTH,
        json={"engines": ["human", "miti"], "selection": SEL1, "repeats": 1, **changes},
    )


def test_saved_metadata_and_complete_configuration_are_public_without_private_refs(services):
    c = client(services=services)
    response = start(c, name="French pilot", description="Compare the first session", language="fr")
    assert response.status_code == 200, response.text
    rid = response.json()["run_id"]
    saved = services.repository.get_run(rid)
    before = (len(services.queue.tasks), len(services.repository.list_runs()))
    summary = c.get("/v1/runs", headers=AUTH).json()["runs"][0]
    body = detail(c, rid)
    for public in (summary, body):
        for key in (
            "name", "description", "input", "engines", "selection", "repeats",
            "change_goal", "language", "coded_span", "base_preset",
        ):
            assert public[key] == saved[key]
        assert public["resolved_combos"] == saved["saved_config"]["resolved_combos"]
        assert "input_ref" not in public and "created_by" not in public
    assert "units" not in summary and "output" not in summary
    assert before == (len(services.queue.tasks), len(services.repository.list_runs()))


@pytest.mark.parametrize("key,limit", [("name", 200), ("description", 4000)])
def test_metadata_bounds_match_create_and_rerun_and_never_write_on_rejection(services, key, limit):
    c = client(services=services)
    rid = start(c, **{key: "x" * limit}).json()["run_id"]
    before = (len(services.repository.list_runs()), len(services.queue.tasks))
    assert start(c, **{key: "x" * (limit + 1)}).status_code == 422
    assert rerun(c, rid, **{key: "x" * (limit + 1)}).status_code == 422
    assert before == (len(services.repository.list_runs()), len(services.queue.tasks))


@pytest.mark.parametrize("changes", [{}, {"name": "Edited", "description": "Updated"}, {"name": "", "description": None}])
def test_rerun_preserves_omitted_metadata_and_explicit_edits_or_clears(services, changes):
    c = client(services=services)
    rid = start(c, name="Original", description="Original description").json()["run_id"]
    old = services.repository.get_run(rid)
    response = rerun(c, rid, **changes)
    assert response.status_code == 200, response.text
    new = services.repository.get_run(response.json()["run_id"])
    for key in ("name", "description"):
        assert new[key] == changes.get(key, old[key])
    for key in ("input", "change_goal", "language", "coded_span", "base_preset", "saved_config"):
        assert new[key] == old[key]


def test_rerun_uses_saved_preset_after_server_default_changes(services):
    c = client(services=services)
    rid = start(c).json()["run_id"]
    old = services.repository.get_run(rid)
    c.app.state.config = replace(c.app.state.config, default_preset="other")
    response = rerun(c, rid)
    assert response.status_code == 200, response.text
    new = services.repository.get_run(response.json()["run_id"])
    assert new["base_preset"] == old["base_preset"]


@pytest.mark.parametrize("change", ["preset_removed", "model_changed"])
def test_unavailable_saved_configuration_rejects_before_writes(services, change, monkeypatch):
    c = client(services=services)
    rid = start(c).json()["run_id"]
    if change == "preset_removed":
        saved = services.repository.get_run(rid)["saved_config"]
        saved["base_preset"] = "removed-preset"  # no longer in the routes file
        services.repository.update_run(rid, {"saved_config": saved})
    else:
        from onolys_eval_backend import runs

        real = runs.eval_snapshot
        monkeypatch.setattr(
            runs, "eval_snapshot",
            lambda *a: ({**real(*a)[0], "supports_temperature": True}, real(*a)[1]),
        )
    before = (services.audio_bucket.list(""), len(services.queue.tasks), len(services.repository.list_runs()))
    response = rerun(c, rid)
    assert response.status_code == 409, response.text
    assert "configuration" in response.json()["detail"].lower()
    assert "new run" in response.json()["detail"].lower()
    assert before == (services.audio_bucket.list(""), len(services.queue.tasks), len(services.repository.list_runs()))


def test_older_run_without_saved_metadata_or_resolution_can_rerun(services):
    c = client(services=services)
    rid = start(c).json()["run_id"]
    # Model a record written before optional metadata / combo snapshots existed.
    services.repository.update_run(rid, {"name": None, "description": None, "saved_config": None})
    response = rerun(c, rid)
    assert response.status_code == 200, response.text


def test_rerun_new_combo_does_not_require_matching_unselected_saved_combo(services):
    c = client(services=services)
    rid = start(c).json()["run_id"]
    saved = services.repository.get_run(rid)["saved_config"]
    snapshot = saved["resolved_combos"]
    snapshot[next(iter(snapshot))]["litellm_id"] = "historical/model"
    services.repository.update_run(rid, {"saved_config": saved})
    response = rerun(c, rid, selection={**SEL1, "efforts": ["high"]})
    assert response.status_code == 200, response.text
    new = services.repository.get_run(response.json()["run_id"])
    assert list(new["saved_config"]["resolved_combos"]) == ["claude/claude-sonnet-5-5/high"]


def test_rerun_rejects_silently_dropping_a_previously_valid_combo(services):
    c = client(services=services)
    selection = {**SEL1, "efforts": ["low", "high"]}
    rid = start(c, selection=selection).json()["run_id"]
    model = services.models["claude"]
    tier = model.tiers["claude-sonnet-5-5"]
    services.models["claude"] = replace(
        model, tiers={**model.tiers, tier.id: replace(tier, efforts=["low"])},
    )
    response = rerun(c, rid, selection=selection)
    assert response.status_code in (409, 422), response.text
    assert len(services.repository.list_runs()) == 1
