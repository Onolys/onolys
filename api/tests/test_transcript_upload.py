"""Direct transcript upload follows the existing speaker and first-run gates."""

import json
from dataclasses import replace

import pytest
from cards import valid_card

from onolys_api.jobs import caps
from onolys_api.repo.base import NotFoundError
from onolys_api.repo.models import transcript_sha256

pytestmark = pytest.mark.unit
AUTH = {"Authorization": "Bearer test:upload-user"}
WORDS = " ".join(["word"] * 30)


class Queue:
    def __init__(self):
        self.calls = []

    def enqueue(self, payload, delay_s=0):
        self.calls.append(payload)


@pytest.fixture
def queue(app):
    app.state.queue = Queue()
    return app.state.queue


async def create(client, **body):
    r = await client.post("/v1/sessions", headers=AUTH, json=body)
    assert r.status_code == 202, r.text
    return r.json()["session"]["id"]


def document(roles=True):
    return {
        "turns": [
            {
                "id": "t1",
                "speaker": "Therapist",
                "text": WORDS,
                **({"role": "clinician"} if roles else {}),
            },
            {
                "id": "t2",
                "speaker": "Client",
                "text": WORDS,
                **({"role": "client"} if roles else {}),
            },
        ]
    }


async def upload(client, sid, body, media="application/json", headers=None):
    return await client.put(
        f"/v1/sessions/{sid}/transcript",
        headers={**(headers or AUTH), "Content-Type": media},
        content=body,
    )


@pytest.mark.parametrize("kind", ["json", "tc", "named", "partial"])
async def test_upload_gate_and_normalized_storage(client, app, queue, kind):
    sid = await create(client)
    if kind in ("tc", "named"):
        labels = ("T", "C") if kind == "tc" else ("Therapist", "Client")
        body, media = f"{labels[0]}: {WORDS}\n{labels[1]}: {WORDS}", "text/plain"
    else:
        doc = document()
        if kind == "partial":
            doc["turns"][1].pop("role")
        body, media = json.dumps(doc), "application/json"
    r = await upload(client, sid, body, media)
    assert r.status_code == 202, r.text
    assert r.json()["session"]["status"] == "awaiting_input"
    s = app.state.repo.get_session("upload-user", sid)
    assert s.transcript_ready
    assert s.speaker_confirmed == (kind in ("json", "tc"))
    assert s.clinician_speaker == ({"json": "Therapist", "tc": "T"}.get(kind))
    assert s.stt is None
    t = app.state.repo.get_transcript("upload-user", sid, "current").transcript
    assert t.language == "en" and len(t.turns) == 2
    assert not queue.calls
    assert app.state.repo.get_usage("upload-user", caps.utc_date()).runs == 0


@pytest.mark.parametrize("large_body", [False, True])
@pytest.mark.parametrize("session_language,transcript_language", [("auto", None), ("de", "fr")])
async def test_upload_persists_hash_and_effective_language(
    client, app, queue, large_body, session_language, transcript_language
):
    sid = await create(client, language=session_language)
    doc = document()
    doc["language"] = transcript_language
    if large_body:
        # Stay within the upload word limit while exceeding inline byte storage.
        doc["turns"] = [
            {**doc["turns"][i % 2], "id": f"t{i}", "text": "é" * 10_000 + " word"}
            for i in range(30)
        ]
    response = await upload(client, sid, json.dumps(doc, ensure_ascii=False))
    assert response.status_code == 202, response.text
    raw = app.state.repo.get_transcript("upload-user", sid, "current", resolve=False)
    resolved = app.state.repo.get_transcript("upload-user", sid, "current")
    assert (raw.pointer is not None) == large_body
    assert raw.language == (transcript_language or ("en" if session_language == "auto" else session_language))
    assert raw.sha256 == transcript_sha256(resolved.transcript)


@pytest.mark.parametrize("before", [True, False])
async def test_first_run_accounts_exact_n_runs(client, app, queue, before):
    sid = await create(client, n_runs=3)
    url = f"/v1/sessions/{sid}/rating"
    if before:
        assert (
            await client.put(url, headers=AUTH, json={"final": True, "card": valid_card()})
        ).status_code == 202
    r = await upload(client, sid, json.dumps(document()))
    assert r.status_code == 202, r.text
    if not before:
        assert (
            await client.put(url, headers=AUTH, json={"final": True, "card": valid_card()})
        ).status_code == 202
    s = app.state.repo.get_session("upload-user", sid)
    assert s.state == "running" and s.first_run_id
    assert len(queue.calls) == 1 and queue.calls[0].kind == "run"
    assert app.state.repo.get_usage("upload-user", caps.utc_date()).runs == 3
    again = await upload(client, sid, json.dumps(document()))
    assert again.status_code == 409
    assert app.state.repo.get_usage("upload-user", caps.utc_date()).runs == 3


async def test_named_upload_waits_for_speaker_confirmation(client, app, queue):
    sid = await create(client)
    await client.put(
        f"/v1/sessions/{sid}/rating", headers=AUTH, json={"final": True, "card": valid_card()}
    )
    assert (
        await upload(client, sid, f"Pat: {WORDS}\nSam: {WORDS}", "text/plain")
    ).status_code == 202
    assert not queue.calls
    r = await client.post(
        f"/v1/sessions/{sid}/speakers/confirm", headers=AUTH, json={"clinician_speaker": "Pat"}
    )
    assert r.status_code == 202 and r.json()["session"]["status"] == "running"
    assert app.state.repo.get_usage("upload-user", caps.utc_date()).runs == 1


async def test_daily_cap_holds_upload(client, app, queue):
    app.state.settings = replace(app.state.settings, eval_cap_day=0)
    sid = await create(client)
    await client.put(
        f"/v1/sessions/{sid}/rating", headers=AUTH, json={"final": True, "card": valid_card()}
    )
    r = await upload(client, sid, json.dumps(document()))
    assert r.status_code == 202, r.text
    s = app.state.repo.get_session("upload-user", sid)
    assert s.state == "awaiting_input" and s.error.code == "daily_cap_reached"
    assert not queue.calls
    assert app.state.repo.get_usage("upload-user", caps.utc_date()).runs == 0


@pytest.mark.parametrize(
    "body,media,code,field",
    [
        ("", "text/plain", "empty_transcript", "turns"),
        ("{}", "application/json", "transcript_invalid", "turns"),
        ("{secret", "application/json", "transcript_invalid", "$"),
        ("\xff", "text/plain", "transcript_invalid", "$"),
        ("T: short", "text/plain", "empty_transcript", "turns"),
        ("x" * (1024 * 1024 + 1), "text/plain", "transcript_too_large", "$"),
        (
            json.dumps(
                {"turns": [{"id": str(i), "speaker": "s", "text": "x"} for i in range(5001)]}
            ),
            "application/json",
            "transcript_invalid",
            "turns",
        ),
        (
            json.dumps({"turns": [{"id": "1", "speaker": "s", "text": "x" * 20001}]}),
            "application/json",
            "transcript_invalid",
            "turns/0/text",
        ),
        (
            json.dumps(
                {"turns": [{"id": str(i), "speaker": str(i), "text": WORDS} for i in range(9)]}
            ),
            "application/json",
            "transcript_invalid",
            "turns",
        ),
    ],
)
async def test_invalid_uploads_leave_session_created(client, app, queue, body, media, code, field):
    sid = await create(client)
    body = body.encode("latin1") if body == "\xff" else body
    r = await upload(client, sid, body, media)
    assert r.status_code == (413 if code == "transcript_too_large" else 422), r.text
    detail = r.json()["details"][0]
    assert detail["code"] == code and detail["field"] == field and detail["issue"]
    assert "secret" not in r.text
    assert app.state.repo.get_session("upload-user", sid).state == "created"
    with pytest.raises(NotFoundError):
        app.state.repo.get_transcript("upload-user", sid, "current")
    assert not queue.calls


async def test_two_clinicians_rejected(client, queue):
    sid = await create(client)
    doc = document()
    doc["turns"][1]["role"] = "clinician"
    r = await upload(client, sid, json.dumps(doc))
    assert r.status_code == 422 and r.json()["details"][0]["code"] == "transcript_invalid"


async def test_auth_owner_media_and_state(client, app, queue):
    sid = await create(client)
    url = f"/v1/sessions/{sid}/transcript"
    assert (await client.put(url, content="x")).status_code == 401
    assert (
        await upload(client, sid, "x", headers={"Authorization": "Bearer test:other"})
    ).status_code == 404
    assert (await upload(client, sid, "x", "application/pdf")).status_code == 415
    app.state.repo.update_session("upload-user", sid, {"state": "uploading"})
    assert (await upload(client, sid, json.dumps(document()))).status_code == 409


async def test_streamed_body_limit_never_stores_valid_prefix(client, app, queue):
    sid = await create(client)

    async def chunks():
        yield json.dumps(document()).encode()
        yield b" " * (1024 * 1024)

    r = await upload(client, sid, chunks())
    assert r.status_code == 413 and r.json()["details"][0]["code"] == "transcript_too_large"
    assert not app.state.repo.get_session("upload-user", sid).transcript_ready
    with pytest.raises(NotFoundError):
        app.state.repo.get_transcript("upload-user", sid, "current")


async def test_exact_body_limit_is_accepted(client, queue):
    sid = await create(client)
    body = json.dumps(document()).encode()
    body += b" " * (1024 * 1024 - len(body))
    r = await upload(client, sid, body)
    assert r.status_code == 202, r.text


async def test_deeply_nested_json_is_a_safe_input_error(client, queue):
    sid = await create(client)
    r = await upload(client, sid, "[" * 10000 + "]" * 10000)
    assert r.status_code == 422
    assert r.json()["details"][0]["code"] == "transcript_invalid"


async def test_racing_transcript_put_cannot_overwrite_the_winner(client, app, queue):
    """A competing PUT commits between the `created` check and the write."""
    from onolys_engine_core.transcript_input import validate_transcript_input

    from onolys_api.jobs.machine import advance

    repo = app.state.repo
    sid = await create(client)
    winner = validate_transcript_input({"turns": [
        {"id": "t1", "speaker": "A", "text": "winner " * 60, "role": "clinician"},
        {"id": "t2", "speaker": "B", "text": "other " * 60, "role": "client"},
    ]})  # fmt: skip
    fired = []

    def race_once():
        if not fired:
            fired.append(1)
            repo.put_transcript("upload-user", sid, "current", winner)
            advance(repo, "upload-user", sid, to="awaiting_input", step=None)

    for name in ("put_transcript", "transition_session"):  # old write path / new write path
        real = getattr(repo, name)

        def wrapped(*a, _real=real, **kw):
            race_once()
            return _real(*a, **kw)

        setattr(repo, name, wrapped)
    r = await upload(client, sid, json.dumps(document()))
    assert r.status_code == 409, r.text
    t = repo.get_transcript("upload-user", sid, "current").transcript
    assert t.turns[0].text.startswith("winner")  # the loser did not overwrite it
