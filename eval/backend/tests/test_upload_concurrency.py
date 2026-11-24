"""Deterministic upload races; no providers or network."""

from datetime import UTC, datetime, timedelta

import pytest
from test_app import AUTH, client
from test_uploads import transcript, upload

pytest_plugins = ["test_uploads"]


def pending(services):
    c = client(services=services)
    uid = upload(c, "talk.mp3", b"ID3abc", "audio/mpeg").json()["upload_id"]
    services.repository.update_upload(uid, {"stt_handle": "handle"})
    return c, uid


def task(c, uid):
    return c.post("/internal/tasks/transcribe", headers=AUTH, json={"upload_id": uid})


@pytest.mark.parametrize("route", ["read", "task"])
def test_stale_timeout_preserves_completed_upload(services, monkeypatch, route):
    from onolys_eval_backend import uploads

    c, uid = pending(services)
    services.repository.update_upload(uid, {
        "transcribing_since": (datetime.now(UTC) - timedelta(hours=3)).isoformat(),
    })
    expired = uploads._transcribe_expired

    def completion_wins(saved):
        services.repository.update_upload(uid, {"status": "ready", "clinician_speaker": "T"})
        return expired(saved)

    monkeypatch.setattr(uploads, "_transcribe_expired", completion_wins)
    response = c.get(f"/v1/uploads/{uid}", headers=AUTH) if route == "read" else task(c, uid)
    assert response.status_code == 200
    assert services.repository.get_upload(uid)["status"] == "ready"
    if route == "read":
        assert response.json()["status"] == "ready"


def test_stale_provider_failure_preserves_completed_upload(services):
    c, uid = pending(services)

    async def failure(handle):
        services.repository.update_upload(uid, {"status": "ready", "clinician_speaker": "T"})
        raise RuntimeError("late failed poll")

    services.stt.poll = failure
    assert task(c, uid).status_code == 200
    assert services.repository.get_upload(uid)["status"] == "ready"


def test_duplicate_completion_cannot_rewrite_speaker_choice_bytes(services):
    c, uid = pending(services)
    path = services.repository.get_upload(uid)["transcript_path"]
    chosen = transcript(True)
    services.stt.complete = True
    original = services.stt.poll

    async def completed(handle):
        result = await original(handle)
        # A different poll completed and the user selected their clinician meanwhile.
        services.bucket.write_json(path, chosen)
        services.repository.update_upload(uid, {"status": "ready", "clinician_speaker": "T"})
        return result

    services.stt.poll = completed
    assert task(c, uid).status_code == 200
    assert services.repository.get_upload(uid)["status"] == "ready"
    assert services.bucket.read_json(path) == chosen
    assert services.bucket.list(f"uploads/{uid}/transcripts/") == []


def test_initial_start_is_fenced_before_provider_call(services):
    c, uid = pending(services)
    services.repository.update_upload(uid, {"stt_handle": None})
    original = services.stt.start
    calls = []

    async def first_start(audio, params):
        calls.append(True)
        assert len(calls) == 1
        # Reentrant delivery sees the first start in flight and must defer.
        assert task(c, uid).status_code == 200
        return await original(audio, params)

    services.stt.start = first_start
    assert task(c, uid).status_code == 200
    assert len(services.stt.starts) == len(calls) == 1


def test_initial_start_losing_ownership_cannot_publish_handle(services):
    c, uid = pending(services)
    services.repository.update_upload(uid, {"stt_handle": None})

    async def start(audio, params):
        services.repository.update_upload(uid, {"status": "failed", "error": {"code": "timeout"}})
        return "late-handle"

    services.stt.start = start
    assert task(c, uid).status_code == 200
    saved = services.repository.get_upload(uid)
    assert saved["status"] == "failed" and saved.get("stt_handle") is None


@pytest.mark.parametrize("result", ["success", "failure"])
def test_poll_for_old_handle_cannot_finish_replacement_phase(services, result):
    c, uid = pending(services)
    services.stt.complete = True
    original = services.stt.poll

    async def replace(handle):
        services.repository.update_upload(uid, {"stt_handle": "replacement"})
        if result == "failure":
            raise RuntimeError("old handle failed")
        return await original(handle)

    services.stt.poll = replace
    assert task(c, uid).status_code == 200
    saved = services.repository.get_upload(uid)
    assert saved["status"] == "transcribing" and saved["stt_handle"] == "replacement"
    assert "stt_run" not in saved


def test_expired_initial_start_lease_is_reclaimed(services):
    c, uid = pending(services)
    services.repository.update_upload(uid, {
        "stt_handle": None, "stt_start_owner": "abandoned",
        "stt_start_until": (datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
    })
    assert task(c, uid).status_code == 200
    saved = services.repository.get_upload(uid)
    assert saved["stt_handle"] == "opaque-handle" and saved["stt_start_owner"] != "abandoned"
    assert len(services.stt.starts) == 1


def test_successful_poll_and_speaker_choice_publish_distinct_immutable_transcripts(services):
    c, uid = pending(services)
    services.stt.complete = True
    assert task(c, uid).status_code == 200
    completed = services.repository.get_upload(uid)
    assert completed["status"] == "awaiting_speakers"
    stt_path = completed["transcript_path"]
    normalized = services.bucket.read_json(stt_path)
    assert [turn["role"] for turn in normalized["turns"]] == [None, None]
    picked = c.post(f"/v1/uploads/{uid}/speakers", headers=AUTH, json={"clinician_speaker": "T"})
    assert picked.status_code == 200 and picked.json()["status"] == "ready"
    ready = services.repository.get_upload(uid)
    assert ready["transcript_path"] != stt_path
    assert services.bucket.read_json(stt_path) == normalized
    assert [turn["role"] for turn in services.bucket.read_json(ready["transcript_path"])["turns"]] == ["clinician", "client"]


def test_invalid_direct_completion_losing_transition_preserves_ready_upload(services):
    from test_uploads import start_direct

    c = client(services=services)
    uid = start_direct(c).json()["upload_id"]
    services.bucket.write_bytes(f"uploads/{uid}/input.wav", b"incorrect bytes", content_type="audio/wav")
    original = services.bucket.read_head

    def competing_completion(path, n):
        services.repository.update_upload(uid, {"status": "ready"})
        return original(path, n)

    services.bucket.read_head = competing_completion
    response = c.post(f"/v1/uploads/{uid}/complete", headers=AUTH)
    assert response.json()["status"] == "ready"
    assert services.repository.get_upload(uid)["status"] == "ready"


@pytest.mark.live
def test_firestore_upload_field_comparisons_are_atomic():
    import os
    from uuid import uuid4

    from google.cloud import firestore

    from onolys_eval_backend.repository import FirestoreEvalRepository

    if not os.environ.get("FIRESTORE_EMULATOR_HOST"):
        pytest.skip("Firestore emulator required")
    db = firestore.Client(project="demo-test")
    repo = FirestoreEvalRepository(db)
    uid = uuid4().hex
    try:
        repo.create_upload(uid, {"status": "transcribing", "stt_handle": "old", "since": "one"})
        assert repo.transition_upload(uid, "transcribing", {"stt_handle": "new"}, match={"stt_handle": "old", "since": "one", "missing": None})
        assert not repo.transition_upload(uid, "transcribing", {"status": "failed"}, match={"stt_handle": "old"})
        assert not repo.transition_upload(uid, "transcribing", {"status": "failed"}, match={"since": "two"})
        assert repo.transition_upload(uid, "transcribing", {"status": "ready"}, match={"stt_handle": "new"})
        assert not repo.transition_upload(uid, "transcribing", {"status": "failed"}, match={"stt_handle": "new"})
        assert repo.get_upload(uid)["status"] == "ready"
    finally:
        repo.uploads.document(uid).delete()
        db.close()


def test_initial_start_reclaimed_owner_cannot_publish_handle(services):
    c, uid = pending(services)
    services.repository.update_upload(uid, {"stt_handle": None})

    async def start(audio, params):
        services.repository.update_upload(uid, {
            "stt_start_owner": "replacement", "stt_handle": "new-handle",
        })
        return "old-handle"

    services.stt.start = start
    assert task(c, uid).status_code == 200
    saved = services.repository.get_upload(uid)
    assert saved["status"] == "transcribing" and saved["stt_handle"] == "new-handle"


def test_start_lease_deferral_queue_failure_stays_retryable(services):
    c, uid = pending(services)
    services.repository.update_upload(uid, {
        "stt_handle": None, "stt_start_owner": "active",
        "stt_start_until": (datetime.now(UTC) + timedelta(minutes=1)).isoformat(),
    })

    def unavailable(*args, **kwargs):
        raise RuntimeError("queue temporarily unavailable")

    services.queue.enqueue = unavailable
    with pytest.raises(RuntimeError, match="queue temporarily unavailable"):
        task(c, uid)
    assert services.repository.get_upload(uid)["status"] == "transcribing"
    assert services.stt.starts == []


def test_concurrent_different_speaker_choice_returns_conflict_and_cleans_loser(services):
    c, uid = pending(services)
    services.stt.complete = True
    assert task(c, uid).status_code == 200
    original = services.bucket.write_json
    published = services.repository.get_upload(uid)["transcript_path"]

    def competing_choice(path, value):
        original(path, value)
        services.repository.update_upload(uid, {
            "status": "ready", "clinician_speaker": "C", "transcript_path": published,
        })

    services.bucket.write_json = competing_choice
    response = c.post(f"/v1/uploads/{uid}/speakers", headers=AUTH, json={"clinician_speaker": "T"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "speaker_conflict"
    assert services.repository.get_upload(uid)["clinician_speaker"] == "C"
    assert services.bucket.list(f"uploads/{uid}/transcripts/") == [published]


def test_candidate_cleanup_failure_preserves_winning_result(services):
    c, uid = pending(services)
    services.stt.complete = True
    original = services.stt.poll

    async def poll(handle):
        result = await original(handle)
        services.repository.update_upload(uid, {"status": "ready"})
        return result

    def unavailable(path):
        raise RuntimeError("cleanup unavailable")

    services.stt.poll = poll
    services.bucket.delete = unavailable
    assert task(c, uid).status_code == 200
    assert services.repository.get_upload(uid)["status"] == "ready"


def test_gcs_candidate_delete_is_idempotent():
    from unittest.mock import Mock

    from google.api_core.exceptions import NotFound

    from onolys_eval_backend.storage import GCSBucket

    remote = Mock()
    bucket = GCSBucket(remote)
    bucket.delete("candidate")
    remote.blob.assert_called_with("candidate")
    remote.blob.return_value.delete.assert_called_once_with()
    remote.blob.return_value.delete.side_effect = NotFound("already absent")
    bucket.delete("candidate")
