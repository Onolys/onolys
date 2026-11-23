"""Caller span survives API storage and rejects errors before reserving a run."""

import json

import pytest
from cards import valid_card
from onolys_engine_core.errors import InvalidCodedSpan, SessionTooLong
from test_transcript_upload import AUTH, Queue, create, document, upload

from onolys_api.adapters.error_map import to_public

pytestmark = pytest.mark.unit
SPANS = [{"start_turn": 0, "end_turn": 1}, {"start_ms": 0, "end_ms": 1000}]


def timed_document():
    doc = document()
    for i, turn in enumerate(doc["turns"]):
        turn.update(start_ms=i * 1000, end_ms=(i + 1) * 1000)
    return doc


@pytest.mark.parametrize("span", SPANS + [None])
async def test_create_span_survives_rating_and_first_run(client, app, span):
    app.state.queue = Queue()
    sid = await create(client, coded_span=span)
    assert (await upload(client, sid, json.dumps(timed_document()))).status_code == 202
    r = await client.put(f"/v1/sessions/{sid}/rating", headers=AUTH,
                         json={"final": True, "card": valid_card()})
    assert r.status_code == 202, r.text
    session = app.state.repo.get_session("upload-user", sid)
    run = app.state.repo.get_run("upload-user", sid, session.first_run_id)
    assert (run.coded_span.model_dump(exclude_none=True) if run.coded_span else None) == span


@pytest.mark.parametrize("span", SPANS + [None])
async def test_run_override_is_snapshotted_without_changing_session(client, app, span):
    app.state.queue = Queue()
    sid = await create(client, coded_span=SPANS[0])
    await upload(client, sid, json.dumps(timed_document()))
    r = await client.post(f"/v1/sessions/{sid}/runs", headers=AUTH, json={"coded_span": span})
    assert r.status_code == 202, r.text
    run = app.state.repo.get_run("upload-user", sid, r.json()["run_id"])
    assert (run.coded_span.model_dump(exclude_none=True) if run.coded_span else None) == span
    assert app.state.repo.get_session("upload-user", sid).coded_span.start_turn == 0


@pytest.mark.parametrize("span", SPANS + [None])
async def test_manual_first_run_defaults_to_session_span(client, app, span):
    app.state.queue = Queue()
    sid = await create(client, coded_span=span)
    assert (await upload(client, sid, json.dumps(timed_document()))).status_code == 202
    r = await client.post(f"/v1/sessions/{sid}/runs", headers=AUTH, json={})
    assert r.status_code == 202, r.text
    run = app.state.repo.get_run("upload-user", sid, r.json()["run_id"])
    assert (run.coded_span.model_dump(exclude_none=True) if run.coded_span else None) == span


@pytest.mark.parametrize("prior_span", [SPANS[1], None], ids=["override", "whole-session"])
@pytest.mark.parametrize(
    "body",
    [{}, {"coded_span": {"start_turn": 1, "end_turn": 2}}, {"coded_span": None}],
    ids=["inherit", "new-override", "explicit-null"],
)
async def test_failed_run_retry_preserves_span_unless_overridden(client, app, prior_span, body):
    sid = await create(client, coded_span=SPANS[0])
    assert (await upload(client, sid, json.dumps(timed_document()))).status_code == 202
    app.state.queue = None  # A dispatch failure creates and refunds a failed run snapshot.
    failed = await client.post(
        f"/v1/sessions/{sid}/runs", headers=AUTH, json={"coded_span": prior_span}
    )
    assert failed.status_code == 503, failed.text
    repo = app.state.repo
    (prior,) = repo.list_runs("upload-user", sid)
    assert prior.status == "failed"
    snapshot = prior.model_dump()

    app.state.queue = Queue()
    retry = await client.post(f"/v1/sessions/{sid}/runs", headers=AUTH, json=body)
    assert retry.status_code == 202, retry.text
    run = repo.get_run("upload-user", sid, retry.json()["run_id"])
    expected = body.get("coded_span", prior_span)
    assert (run.coded_span.model_dump(exclude_none=True) if run.coded_span else None) == expected
    assert repo.get_run("upload-user", sid, prior.run_id).model_dump() == snapshot
    assert repo.get_session("upload-user", sid).coded_span.model_dump(exclude_none=True) == SPANS[0]


@pytest.mark.parametrize("span", [{}, {"start_turn": 0}, {"start_turn": 0, "end_turn": 0},
    {"start_turn": True, "end_turn": 2}, {"start_ms": 0.5, "end_ms": 1000},
    {"start_turn": 0, "end_turn": 1, "start_ms": 0, "end_ms": 1000}])
@pytest.mark.parametrize("boundary", ["create", "run"])
async def test_bad_shape_returns_specific_422(client, app, span, boundary):
    app.state.queue = Queue()
    url = "/v1/sessions"
    if boundary == "run":
        sid = await create(client)
        await upload(client, sid, json.dumps(document()))
        url += f"/{sid}/runs"
    r = await client.post(url, headers=AUTH, json={"coded_span": span})
    assert r.status_code == 422, r.text
    assert r.json()["details"][0]["code"] == "invalid_coded_span"


@pytest.mark.parametrize("span", [{"start_turn": 0, "end_turn": 3}, SPANS[1],
                                   {"start_ms": 9999, "end_ms": 10000}])
@pytest.mark.parametrize("boundary", ["upload", "run"])
async def test_content_error_rejected_before_usage(client, app, span, boundary):
    app.state.queue = Queue()
    sid = await create(client, **({"coded_span": span} if boundary == "upload" else {}))
    if boundary == "upload":
        r = await upload(client, sid, json.dumps(document()))
    else:
        await upload(client, sid, json.dumps(document()))
        r = await client.post(f"/v1/sessions/{sid}/runs", headers=AUTH, json={"coded_span": span})
    assert r.status_code == 422, r.text
    assert r.json()["details"][0]["code"] == "invalid_coded_span"
    assert not app.state.queue.calls


async def test_over_limit_upload_requests_narrower_span(client, app):
    sid = await create(client)
    doc = document()
    doc["duration_ms"] = 1500001
    r = await upload(client, sid, json.dumps(doc))
    assert r.status_code == 422, r.text
    assert r.json()["details"][0]["code"] == "session_too_long"
    assert "narrower coded_span" in r.text


@pytest.mark.parametrize("exc,code", [(InvalidCodedSpan("private"), "invalid_coded_span"),
                                     (SessionTooLong("private"), "session_too_long")])
def test_engine_span_errors_keep_public_code(exc, code):
    assert to_public(exc) == (code, False)
