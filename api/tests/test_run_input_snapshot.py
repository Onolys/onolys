"""Run input snapshots are atomic and equivalent in both repository implementations."""

# ruff: noqa: F811

import uuid

import pytest
from onolys_engine import Transcript, Turn
from pydantic import ValidationError
from test_first_run import new_session, repo, user_counters  # noqa: F401

from onolys_api.repo.fake import FakeRepo
from onolys_api.repo.limits import LimitDefaults
from onolys_api.repo.models import BlobPointer, RunDoc, TranscriptDoc

D = LimitDefaults(eval_day=20, interview_day=5)
DATE = "2026-11-24"


def raw(repo, path, value):
    if isinstance(repo, FakeRepo):
        repo._put(path, value)
    else:
        repo._client.document(path).set(value)


def start(repo, uid, sid, entry, rid="r1", **kw):
    args = (uid, sid, rid, DATE, D, 5, "test-version", 45)
    if entry == "first":
        return repo.start_first_run(*args)
    return repo.start_run(*args, ("awaiting_input", "failed"), None, None, **kw)


def ready(repo):
    uid = "snapshot-" + uuid.uuid4().hex
    sid = new_session(
        repo,
        uid,
        state="awaiting_input",
        ready=True,
        speaker_confirmed=True,
        clinician_speaker="S1",
        rating_submitted=True,
        change_goal="Walk daily",
        language="auto",
    )
    return uid, sid


@pytest.mark.parametrize(
    "field", ["change_goal", "clinician_speaker", "language", "transcript_sha256"]
)
def test_run_snapshot_fields_required(field):
    values = dict(
        uid="u",
        session_id="s",
        run_id="r",
        change_goal="",
        clinician_speaker="S1",
        language="auto",
        transcript_sha256="hash",
    )
    values.pop(field)
    with pytest.raises(ValidationError):
        RunDoc(**values)


@pytest.mark.parametrize("entry", ["first", "manual"])
@pytest.mark.parametrize("pointer,language", [(False, "en"), (True, "auto")])
def test_start_copies_metadata_without_loading_transcript(
    repo, monkeypatch, entry, pointer, language
):
    uid, sid = ready(repo)
    transcript = Transcript(turns=[Turn(id="t1", speaker="S1", text="Hello")], language=None)
    doc = TranscriptDoc.build(
        transcript,
        BlobPointer(key="not-present.json", uri="gs://test-bucket/not-present.json", size_bytes=1)
        if pointer
        else None,
        language,
    )
    raw(repo, f"sessions/{sid}/transcripts/current", doc.to_store())
    monkeypatch.setattr(repo, "get_transcript", lambda *a: pytest.fail("body loaded at start"))
    assert start(repo, uid, sid, entry) == "started"
    run = repo.get_run(uid, sid, "r1")
    assert (run.change_goal, run.clinician_speaker, run.language, run.transcript_sha256) == (
        "Walk daily",
        "S1",
        language,
        doc.sha256,
    )
    assert (run.preset, run.n_runs, run.code_version, run.stt.provider) == (
        "p1",
        1,
        "test-version",
        "x",
    )


@pytest.mark.parametrize("entry", ["first", "manual"])
@pytest.mark.parametrize(
    "missing",
    [
        "clinician_speaker",
        "speaker_type",
        "transcript",
        "hash",
        "language",
        "hash_type",
        "language_empty",
    ],
)
def test_start_refuses_missing_inputs_without_charging(repo, entry, missing):
    uid, sid = ready(repo)
    if missing == "clinician_speaker":
        repo.update_session(uid, sid, {"clinician_speaker": None})
    elif missing == "speaker_type":
        path = f"sessions/{sid}"
        if isinstance(repo, FakeRepo):
            value = repo._get(path)
        else:
            value = repo._client.document(path).get().to_dict()
        raw(repo, path, {**value, "clinician_speaker": 1})
    elif missing == "transcript":
        path = f"sessions/{sid}/transcripts/current"
        if isinstance(repo, FakeRepo):
            repo._docs.pop(path)
        else:
            repo._client.document(path).delete()
    else:
        doc = repo.get_transcript(uid, sid, "current").to_store()
        if missing == "hash_type":
            doc["sha256"] = 123
        elif missing == "language_empty":
            doc["language"] = ""
        else:
            doc.pop("sha256" if missing == "hash" else "language")
        raw(repo, f"sessions/{sid}/transcripts/current", doc)
    assert start(repo, uid, sid, entry) == "not_ready"
    assert repo.list_runs(uid, sid) == []
    assert user_counters(repo, uid, DATE) == (0, 0)


def test_manual_start_without_rating_snapshots_empty_goal(repo):
    uid, sid = ready(repo)
    repo.update_session(uid, sid, {"rating_submitted": False, "change_goal": None})
    assert start(repo, uid, sid, "manual") == "started"
    assert repo.get_run(uid, sid, "r1").change_goal == ""


@pytest.mark.parametrize("changed", [False, True])
def test_retry_keeps_failed_run_and_inputs_or_refuses_changed_hash(repo, changed):
    uid, sid = ready(repo)
    assert start(repo, uid, sid, "first") == "started"
    repo.update_run(uid, sid, "r1", {"status": "failed"})
    repo.release_run_slot(uid, sid, "r1", True, DATE)
    repo.update_session(
        uid, sid, {"state": "failed", "error": {"code": "upstream_unavailable", "step": "run", "kind": "transient"}}
    )
    old = repo.get_run(uid, sid, "r1")
    if changed:
        doc = repo.get_transcript(uid, sid, "current").to_store()
        doc["sha256"] = "different"
        raw(repo, f"sessions/{sid}/transcripts/current", doc)
    assert start(repo, uid, sid, "manual", rid="r2", retry_max=3) == (
        "not_ready" if changed else "started"
    )
    assert repo.get_run(uid, sid, "r1") == old
    assert repo.get_session(uid, sid).first_run_id == "r1"
    assert repo.get_session(uid, sid).retry_count == (0 if changed else 1)
    if not changed:
        new = repo.get_run(uid, sid, "r2")
        for field in ("change_goal", "clinician_speaker", "language", "transcript_sha256"):
            assert getattr(new, field) == getattr(old, field)
    assert user_counters(repo, uid, DATE) == ((0, 0) if changed else (1, 1))
