"""Shared transcript write helper is byte-identical to the old `_persist`; `eval`
never reaches a public session view or the OpenAPI document."""

import json

import pytest
from onolys_engine import Transcript, Turn

from onolys_api import openapi
from onolys_api.errors import ApiError
from onolys_api.jobs.transcribe import TRANSCRIPT_ID
from onolys_api.repo import large
from onolys_api.repo.fake import FakeRepo
from onolys_api.repo.models import (
    EvalSessionInfo,
    SessionDoc,
    SessionStatusDoc,
    TranscriptDoc,
)
from onolys_api.storage.fake import FakeBlobStore
from onolys_api.transcript_store import store_transcript

pytestmark = pytest.mark.unit
AUTH = {"Authorization": "Bearer test:upload-user"}


def _transcript(text):
    return Transcript(
        turns=[Turn(id=f"t{i}", speaker="A" if i % 2 else "B", text=text) for i in range(4)],
        language="fr",
        duration_ms=1000,
    )


@pytest.mark.parametrize("text", ["hello world", "é" * 200_000])
def test_helper_writes_same_transcript_doc_as_the_old_persist(tmp_path, text):
    blobs = FakeBlobStore(tmp_path / "b", bucket="x")
    repo = FakeRepo(blobs)
    repo.create_session("u", "s", SessionDoc(uid="u", language="auto"), SessionStatusDoc(uid="u"))
    tr = _transcript(text)
    session = repo.get_session("u", "s")
    store_transcript(repo, blobs, "u", "s", session, tr, "A")

    # the old `_persist` body, inlined as the reference
    pointer = large.pack(blobs, "u/s/transcripts/ref.json", tr.model_dump(mode="json"))
    ref = TranscriptDoc.build(tr, pointer, "fr")
    got = repo.get_transcript("u", "s", TRANSCRIPT_ID, resolve=False)
    a, b = got.to_store(), ref.to_store()
    for d in (a, b):
        d.pop("created_at")
        if d.get("pointer"):
            d["pointer"] = {k: v for k, v in d["pointer"].items() if k == "size_bytes"}
    assert json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str)
    s = repo.get_session("u", "s")
    assert s.state == "awaiting_input" and s.transcript_ready and s.speaker_confirmed
    assert s.clinician_speaker == "A" and s.language == "fr"


def test_helper_only_from_created_and_cleans_blob_on_failure(tmp_path):
    blobs = FakeBlobStore(tmp_path / "b", bucket="x")
    repo = FakeRepo(blobs)
    repo.create_session("u", "s", SessionDoc(uid="u"), SessionStatusDoc(uid="u"))
    session = repo.get_session("u", "s")
    store_transcript(repo, blobs, "u", "s", session, _transcript("é" * 200_000), "A")
    n = len(list((tmp_path / "b").rglob("*.json")))
    with pytest.raises(ApiError):  # second write: not `created` any more
        store_transcript(repo, blobs, "u", "s", session, _transcript("é" * 200_000), "A")
    assert len(list((tmp_path / "b").rglob("*.json"))) == n  # the loser's blob was removed


async def test_eval_block_never_in_public_views_or_openapi(client, app):
    repo = app.state.repo
    info = EvalSessionInfo(dataset_id="d", dataset_session_id="SECRET-DS", source="dataset")
    repo.create_session(
        "upload-user", "ab12cd34ef56ab12cd34ef56ab12cd34", SessionDoc(uid="upload-user", eval=info),
        SessionStatusDoc(uid="upload-user"),
    )  # fmt: skip
    for path in ("/v1/sessions/ab12cd34ef56ab12cd34ef56ab12cd34", "/v1/sessions"):
        r = await client.get(path, headers=AUTH)
        assert r.status_code == 200, r.text
        assert "eval" not in r.text.lower().replace("evaluation", "") and "SECRET-DS" not in r.text
    spec = openapi.render()
    for name in ("EvalSessionInfo", "EvalGold", "dataset_session_id"):
        assert name not in spec  # (`eval` itself also names an existing usage-count field)
