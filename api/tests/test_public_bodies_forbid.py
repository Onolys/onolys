"""Public request bodies reject unknown fields; eval fields are unreachable."""

import json

import pytest
from test_transcript_upload import AUTH, Queue, create, document, upload

from onolys_api import openapi

pytestmark = pytest.mark.unit
EVAL_NAMES = ("eval", "engine", "route_override", "combo_key", "eval_run_id")


@pytest.mark.parametrize("extra", [{"engine": "miti"}, {"route_override": {"x": 1}}, {"eval": {}}])
async def test_post_runs_rejects_eval_fields(client, app, extra):
    app.state.queue = Queue()
    sid = await create(client)
    await upload(client, sid, json.dumps(document()))
    r = await client.post(f"/v1/sessions/{sid}/runs", headers=AUTH, json=extra)
    assert r.status_code == 422, r.text


async def test_create_session_rejects_unknown_field(client):
    r = await client.post("/v1/sessions", headers=AUTH, json={"eval": {}})
    assert r.status_code == 422, r.text


async def test_runs_list_never_returns_eval(client, app):
    app.state.queue = Queue()
    sid = await create(client)
    await upload(client, sid, json.dumps(document()))
    r = await client.post(f"/v1/sessions/{sid}/runs", headers=AUTH, json={})
    assert r.status_code == 202, r.text
    run_id = r.json()["run_id"]
    path = f"sessions/{sid}/runs/{run_id}"
    app.state.repo._docs[path]["eval"] = {
        "eval_run_id": "e1", "combo_key": "c", "repeat": 0, "engine": "miti",
        "route_override": {"model": "m"}, "resolved_route": {"litellm_id": "x/y"},
        "engine_version": "v1",
    }
    uid = app.state.repo._docs[path]["uid"]
    assert app.state.repo.get_run(uid, sid, run_id).eval is not None  # the seed is real
    listed = await client.get(f"/v1/sessions/{sid}/runs", headers=AUTH)
    one = await client.get(f"/v1/runs/{run_id}", headers=AUTH)
    assert listed.status_code == one.status_code == 200
    for text in (listed.text, one.text):
        for name in ("eval", "route_override", "resolved_route", "combo_key", "eval_run_id"):
            assert name not in text, name


def test_all_request_bodies_forbid_extras():
    doc = json.loads(openapi.render())
    for name, schema in doc["components"]["schemas"].items():
        if name.endswith("Request") and "properties" in schema:
            assert schema.get("additionalProperties") is False, name
