"""Session import and gold copy (05 R3): one shared prod session per distinct input."""

import hashlib
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from onolys_api.repo.fake import FakeRepo
from onolys_api.repo.models import transcript_sha256
from onolys_api.storage.fake import FakeBlobStore
from onolys_engine_core.transcript_input import validate_transcript_input
from test_uploads import gold, transcript

from onolys_eval_backend.eval_sessions import SessionSource, canonical_sha256, ensure_session
from onolys_eval_backend.runs import _hash
from onolys_eval_backend.storage import InMemoryBucket

UID = "eval-owner"


@pytest.fixture
def env():
    blobs = FakeBlobStore()
    repo = FakeRepo(blobs)
    repo.ensure_user(UID)
    datasets = InMemoryBucket()
    datasets.write_json("datasets/synthetic/one/transcript.json", transcript())
    datasets.write_json("datasets/synthetic/one/gold.json", gold())
    return SimpleNamespace(
        blobs=blobs, repo=repo, datasets=datasets, bucket=InMemoryBucket(),
        config=SimpleNamespace(eval_owner_uid=UID, default_preset="configured-prod"),
    )


def src(**kw):
    base = dict(
        dataset_id="synthetic", dataset_session_id="one", source="dataset", title="One",
        transcript_path="datasets/synthetic/one/transcript.json",
        gold_path="datasets/synthetic/one/gold.json", change_goal="Test goal",
        coded_span={"start_turn": 0, "end_turn": 2}, language=None,
    )
    return SessionSource(**{**base, **kw})


def n_sessions(env):
    return len([p for p in env.repo._docs if p.startswith("sessions/") and p.count("/") == 1])


def test_canonical_sha256_matches_old_hash_and_prod_transcript_hash():
    data = {"b": "é", "a": [1, {"z": None}]}
    assert canonical_sha256(data) == _hash(data)
    assert canonical_sha256(data) == hashlib.sha256(
        json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()
    t = validate_transcript_input(transcript())
    assert canonical_sha256(t.model_dump(mode="json")) == transcript_sha256(t)


def test_same_inputs_same_sid_one_doc_and_shape(env):
    a = ensure_session(env, src())
    b = ensure_session(env, src())
    assert a == b and len(a) == 32 and int(a, 16) >= 0 and n_sessions(env) == 1
    s = env.repo.get_session(UID, a)
    assert (s.state, s.n_runs, s.preset, s.title) == ("awaiting_input", 1, "configured-prod", "One")
    assert s.transcript_ready and s.speaker_confirmed and s.clinician_speaker == "T"
    assert s.change_goal == "Test goal" and s.coded_span.model_dump() == {"start_turn": 0, "end_turn": 2}
    assert (s.eval.dataset_id, s.eval.dataset_session_id, s.eval.source) == ("synthetic", "one", "dataset")
    tdoc = env.repo.get_transcript(UID, a, "current")
    assert tdoc.sha256 == canonical_sha256(validate_transcript_input(transcript()).model_dump(mode="json"))


def test_changed_goal_span_or_transcript_gives_new_sid(env):
    base = ensure_session(env, src())
    assert ensure_session(env, src(change_goal="Other goal")) != base
    assert ensure_session(env, src(coded_span={"start_turn": 0, "end_turn": 1})) != base
    changed = transcript()
    changed["turns"][1]["text"] = "different"
    env.datasets.write_json("datasets/synthetic/one/transcript.json", changed)
    g = gold()
    env.datasets.write_json("datasets/synthetic/one/gold.json", g)
    assert ensure_session(env, src()) != base
    assert n_sessions(env) == 4


def test_gold_copied_once_content_addressed_and_not_under_uploads(env):
    sid = ensure_session(env, src())
    g = gold()
    from onolys_eval.gold import Gold

    sha = canonical_sha256(Gold.model_validate(g).model_dump(mode="json", by_alias=True))
    s = env.repo.get_session(UID, sid)
    assert (s.eval.gold.sha256, s.eval.gold.path) == (sha, f"gold/{sha}.json")
    assert json.loads(env.blobs.get_bytes(f"gold/{sha}.json")) == Gold.model_validate(g).model_dump(
        mode="json", by_alias=True
    )
    writes = []
    orig = env.blobs.put_bytes
    env.blobs.put_bytes = lambda *a, **k: (writes.append(a[0]), orig(*a, **k))
    ensure_session(env, src())
    assert [w for w in writes if w.startswith("gold/")] == []
    assert env.blobs.list_keys("eval-uploads/") == []


def test_no_gold_and_invalid_gold(env):
    sid = ensure_session(env, src(gold_path=None))
    assert env.repo.get_session(UID, sid).eval.gold is None
    bad = gold()
    bad["utterance_codes"] = [{"turn_id": "nope", "codes": []}]
    env.datasets.write_json("datasets/synthetic/one/gold.json", bad)
    before = n_sessions(env)
    with pytest.raises(HTTPException):
        ensure_session(env, src())
    assert n_sessions(env) == before and env.blobs.list_keys("gold/") == []


def test_upload_source_reads_upload_bucket(env):
    env.bucket.write_json("eval-uploads/u1/transcript.json", transcript())
    sid = ensure_session(env, src(
        dataset_id=None, dataset_session_id="u1", source="upload", gold_path=None,
        transcript_path="eval-uploads/u1/transcript.json",
    ))
    s = env.repo.get_session(UID, sid)
    assert s.eval.dataset_id is None and s.eval.source == "upload"


def test_double_create_race_is_noop(env, monkeypatch):
    real = env.repo.create_session
    from onolys_api.repo.base import ConflictError

    def racing(uid, sid, session, status):
        real(uid, sid, session, status)  # the other worker won
        raise ConflictError()

    env.repo.create_session = racing
    sid = ensure_session(env, src())
    assert n_sessions(env) == 1
    assert env.repo.get_session(UID, sid).state == "awaiting_input"
