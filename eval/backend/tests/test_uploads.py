"""Private uploads and task chains, with no provider calls."""

import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from onolys_engine_core.transcript_v1 import TranscriptV1
from onolys_miti.stt import SttCompletion, SttParams, SttRun
from test_app import AUTH, client

from onolys_eval_backend.repository import InMemoryEvalRepository
from onolys_eval_backend.storage import InMemoryBucket


def transcript(roles=True):
    return {
        "turns": [
            {
                "id": "t1",
                "speaker": "T",
                "role": "clinician" if roles else None,
                "text": "actual speech " * 30,
            },
            {
                "id": "t2",
                "speaker": "C",
                "role": "client" if roles else None,
                "text": "client speech " * 10,
            },
        ]
    }


class Queue:
    def __init__(self):
        self.tasks = []
        self.task_ids = set()

    def enqueue(self, kind, payload, *, delay_seconds=0, task_id=None):
        if task_id is not None:
            if task_id in self.task_ids:
                return
            self.task_ids.add(task_id)
        self.tasks.append((kind, payload, delay_seconds))


class Stt:
    def __init__(self):
        self.starts = []
        self.polls = []
        self.complete = False

    async def start(self, audio, params):
        self.starts.append((audio, params))
        return "opaque-handle"

    async def poll(self, handle):
        self.polls.append(handle)
        if not self.complete:
            return None
        return SttCompletion(
            transcript=TranscriptV1.model_validate(transcript(False)),
            run=SttRun(
                provider="fake", model="synthetic", language_requested="en", adapter_version="test"
            ),
        )


@pytest.fixture
def services():
    return SimpleNamespace(
        bucket=InMemoryBucket(),
        repository=InMemoryEvalRepository(),
        queue=Queue(),
        stt=Stt(),
        stt_params=lambda language: SttParams(
            provider="fake", model="synthetic", language=language
        ),
    )


def upload(c, name="session.json", raw=None, mime="application/json", **kwargs):
    return c.post(
        "/v1/uploads",
        headers=AUTH,
        files={"file": (name, json.dumps(transcript()).encode() if raw is None else raw, mime)},
        **kwargs,
    )


@pytest.mark.parametrize(
    "name,mime,data",
    [
        ("session.json", "application/json", None),
        ("session.txt", "text/plain", ("T: " + "hello " * 55 + "\nC: yes").encode()),
    ],
)
def test_transcripts_persist_v1_and_infer_roles(services, name, mime, data):
    c = client(services=services)
    response = upload(c, name, data, mime, data={"change_goal": "test goal", "language": "en"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ready" and not body["has_gold"]
    saved = services.repository.get_upload(body["upload_id"])
    assert saved["created_by"] == "alice@example.com"
    assert saved["change_goal"] == "test goal"
    actual = services.bucket.read_json(saved["transcript_path"])
    assert actual["turns"][0]["role"] == "clinician"
    assert services.queue.tasks == []
    assert c.get(f"/v1/uploads/{body['upload_id']}", headers=AUTH).json() == body


def test_unknown_speakers_need_observed_pick(services):
    c = client(services=services)
    body = upload(c, raw=json.dumps(transcript(False)).encode()).json()
    assert body["status"] == "awaiting_speakers"
    assert body["speakers"][0] == {"speaker": "T", "samples": [transcript()["turns"][0]["text"]]}
    path = f"/v1/uploads/{body['upload_id']}/speakers"
    assert c.post(path, headers=AUTH, json={"clinician_speaker": "invented"}).status_code == 422
    assert c.post(path, headers=AUTH, json={"clinician_speaker": "T"}).json()["status"] == "ready"
    saved = services.repository.get_upload(body["upload_id"])
    assert services.bucket.read_json(saved["transcript_path"])["turns"][1]["role"] == "client"


@pytest.mark.parametrize(
    "name,mime,data,extra,status",
    [
        ("x.exe", "application/octet-stream", b"bad", {}, 415),
        ("x.json", "application/json", b"secret bad json", {}, 422),
        ("x.mp3", "audio/mpeg", b"not audio", {}, 422),
        ("x.json", "application/json", None, {"coded_span": '{"start_turn":0,"end_turn":99}'}, 422),
    ],
)
def test_invalid_upload_has_no_writes(services, name, mime, data, extra, status):
    response = upload(client(services=services), name, data, mime, data=extra)
    assert response.status_code == status
    assert "secret" not in response.text
    assert services.bucket.list("") == [] and services.queue.tasks == []


def test_bad_gold_before_any_write(services):
    c = client(services=services)
    response = c.post(
        "/v1/uploads",
        headers=AUTH,
        files={
            "file": ("ok.json", json.dumps(transcript()), "application/json"),
            "gold": ("gold.json", b'{"PHI":"secret"}', "application/json"),
        },
    )
    assert response.status_code == 422 and "secret" not in response.text
    assert services.bucket.list("") == [] and services.queue.tasks == []


def test_body_and_file_limits(services, monkeypatch):
    from onolys_eval_backend import uploads

    monkeypatch.setattr(uploads, "MAX_BODY_BYTES", 100)
    response = upload(client(services=services))
    assert response.status_code == 413
    assert services.bucket.list("") == []
    monkeypatch.setattr(uploads, "MAX_BODY_BYTES", 100000)
    monkeypatch.setattr(uploads, "MAX_TRANSCRIPT_BYTES", 10)
    assert upload(client(services=services)).status_code == 413
    assert services.bucket.list("") == []


def test_audio_start_poll_complete_and_terminal_redelivery(services):
    c = client(services=services)
    body = upload(c, "session.wav", b"RIFF\x00\x00\x00\x00WAVEdata", "audio/wav").json()
    uid = body["upload_id"]
    assert body["status"] == "transcribing"
    assert services.queue.tasks == [("transcribe", {"upload_id": uid}, 0)]

    def task():
        return c.post("/internal/tasks/transcribe", headers=AUTH, json={"upload_id": uid})

    assert task().status_code == 200
    assert len(services.stt.starts) == 1 and services.stt.polls == []
    assert services.stt.starts[0][0].uri == f"gs://eval-test/uploads/{uid}/input.wav"
    assert services.queue.tasks[-1] == ("transcribe", {"upload_id": uid}, 15)
    assert task().status_code == 200
    assert len(services.stt.starts) == 1 and services.stt.polls == ["opaque-handle"]
    services.stt.complete = True
    assert task().status_code == 200
    saved = services.repository.get_upload(uid)
    assert saved["status"] == "awaiting_speakers" and saved["stt_run"]["provider"] == "fake"
    actual = services.bucket.read_json(saved["transcript_path"])
    assert "run" not in actual and "provider" not in actual
    assert actual["turns"][0]["text"] == transcript()["turns"][0]["text"]
    before = len(services.queue.tasks)
    assert task().status_code == 200
    assert len(services.queue.tasks) == before and len(services.stt.polls) == 2


def test_stt_error_is_safe_terminal_failure(services):
    async def fail(*args):
        raise ValueError("PHI secret")

    services.stt.start = fail
    c = client(services=services)
    uid = upload(c, "x.mp3", b"ID3abc", "audio/mpeg").json()["upload_id"]
    assert (
        c.post("/internal/tasks/transcribe", headers=AUTH, json={"upload_id": uid}).status_code
        == 200
    )
    response = c.get(f"/v1/uploads/{uid}", headers=AUTH)
    assert response.json()["status"] == "failed" and "secret" not in response.text


def test_cloud_queue_oidc_json_deadline_and_schedule():
    from test_app import ENV

    from onolys_eval_backend.config import EvalConfig
    from onolys_eval_backend.queue import CloudTasksQueue

    calls = []
    sdk = SimpleNamespace(create_task=lambda **kwargs: calls.append(kwargs))
    now = datetime(2026, 11, 23, tzinfo=UTC)
    queue = CloudTasksQueue(EvalConfig.from_env(ENV), sdk, now=lambda: now)
    queue.enqueue("transcribe", {"upload_id": "one"}, delay_seconds=15)
    call = calls[0]
    assert call["parent"] == ENV["TASKS_QUEUE"]
    task = call["task"]
    assert task["http_request"]["url"] == ENV["SERVICE_URL"] + "/internal/tasks/transcribe"
    assert json.loads(task["http_request"]["body"]) == {"upload_id": "one"}
    assert task["http_request"]["oidc_token"] == {
        "service_account_email": ENV["TASKS_SA"],
        "audience": ENV["SERVICE_URL"],
    }
    assert task["dispatch_deadline"]["seconds"] == 900
    assert task["schedule_time"].timestamp() == now.timestamp() + 15


def gold():
    from onolys_eval._formulas import compute_summaries
    from onolys_eval.gold import COUNT_IDS, GLOBAL_IDS

    counts, globals_ = dict.fromkeys(COUNT_IDS, 0), dict.fromkeys(GLOBAL_IDS, 3)
    return {
        "schema": "gold.v1",
        "dataset_id": "synthetic",
        "session_id": "one",
        "source": {
            "coded_url": "https://example.org/coded",
            "uncoded_url": "https://example.org/raw",
            "retrieved_at": "2026-11-23T00:00:00+00:00",
            "sha256": "a" * 64,
        },
        "coded_span": {"start_turn": 0, "end_turn": 2},
        "counts": counts,
        "globals": globals_,
        "summaries": compute_summaries(counts, globals_),
        "utterance_codes": [{"turn_id": "t1", "codes": []}],
        "parse": {"method": "auto", "warnings": []},
    }


@pytest.mark.parametrize("invalid", [None, "id", "span"])
def test_gold_validates_ids_and_span_before_writes(services, invalid):
    data = gold()
    if invalid == "id":
        data["utterance_codes"][0]["turn_id"] = "unknown"
    if invalid == "span":
        data["coded_span"]["end_turn"] = 999
    response = client(services=services).post(
        "/v1/uploads",
        headers=AUTH,
        files={
            "file": ("session.json", json.dumps(transcript()), "application/json"),
            "gold": ("gold.json", json.dumps(data), "application/json"),
        },
    )
    if invalid:
        assert response.status_code == 422
        assert services.bucket.list("") == []
    else:
        assert response.status_code == 200
        assert response.json()["has_gold"] is True
        saved = services.repository.get_upload(response.json()["upload_id"])
        assert services.bucket.read_json(saved["gold_path"])["schema"] == "gold.v1"


def test_queue_failure_retries_persisted_stt_handle(services):
    c = client(services=services)
    uid = upload(c, "x.mp3", b"ID3abc", "audio/mpeg").json()["upload_id"]
    real_enqueue = services.queue.enqueue

    def unavailable(*args, **kwargs):
        raise RuntimeError("unavailable")

    services.queue.enqueue = unavailable
    from test_app import ENV, TASK_CLAIMS, Verifier

    from onolys_eval_backend import create_app

    c = TestClient(
        create_app(ENV, services=services, task_verifier=Verifier(TASK_CLAIMS)),
        raise_server_exceptions=False,
    )
    path = "/internal/tasks/transcribe"
    assert c.post(path, headers=AUTH, json={"upload_id": uid}).status_code == 500
    assert services.repository.get_upload(uid)["status"] == "transcribing"
    services.queue.enqueue = real_enqueue
    assert c.post(path, headers=AUTH, json={"upload_id": uid}).status_code == 200
    assert len(services.stt.starts) == 1 and services.stt.polls == ["opaque-handle"]


def test_missing_upload_and_transcribing_pick(services):
    c = client(services=services)
    assert c.get("/v1/uploads/missing", headers=AUTH).status_code == 404
    uid = upload(c, "x.mp3", b"ID3abc", "audio/mpeg").json()["upload_id"]
    assert (
        c.post(
            f"/v1/uploads/{uid}/speakers", headers=AUTH, json={"clinician_speaker": "T"}
        ).status_code
        == 409
    )


def test_production_stt_params_match_configured_preset_and_language(tmp_path):
    from onolys_engine_core.llm.routes import Preset, RouteRegistry
    from test_app import ENV

    from onolys_eval_backend.config import EvalConfig
    from onolys_eval_backend.services import EvalServices

    (tmp_path / "stt_providers.yaml").write_text("""default: fallback
providers:
  fallback: {provider: fixture, model: fallback}
  configured: {provider: google, model: configured-chirp, options: {location: eu}}
""")
    services = EvalServices(
        EvalConfig.from_env({**ENV, "ROUTES_FILE": str(tmp_path / "routes.yaml")})
    )
    services.routes = RouteRegistry({}, {"configured-prod": Preset({}, stt="configured")})
    params = services.stt_params("fr")
    assert params.provider == "google" and params.model == "configured-chirp"
    assert params.language == "fr" and params.diarization is True
    assert params.options == {"location": "eu"}


def test_services_allow_explicit_queue_and_stt_factory_injection():
    from test_app import ENV

    from onolys_eval_backend.config import EvalConfig
    from onolys_eval_backend.services import EvalServices

    queue, factory = Queue(), lambda provider: Stt()
    services = EvalServices(EvalConfig.from_env(ENV), queue=queue, stt_factory=factory)
    assert services.queue is queue and services.stt_factory is factory


def test_streamed_body_limit_without_content_length(services, monkeypatch):
    from onolys_eval_backend import uploads

    monkeypatch.setattr(uploads, "MAX_BODY_BYTES", 100)
    chunks = [
        b'--boundary\r\nContent-Disposition: form-data; name="file"; filename="x.txt"\r\n',
        b"Content-Type: text/plain\r\n\r\n" + b"x" * 1000 + b"\r\n--boundary--\r\n",
    ]
    response = client(services=services).post(
        "/v1/uploads",
        headers={**AUTH, "Content-Type": "multipart/form-data; boundary=boundary"},
        content=iter(chunks),
    )
    assert response.status_code == 413
    assert services.bucket.list("") == []


def test_named_text_speakers_and_explicit_span(services):
    raw = ("Alex: " + "actual words " * 30 + "\nMorgan: yes").encode()
    response = upload(
        client(services=services),
        "session.txt",
        raw,
        "text/plain",
        data={"coded_span": '{"start_turn": 0, "end_turn": 1}'},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "awaiting_speakers"
    assert [row["speaker"] for row in body["speakers"]] == ["Alex", "Morgan"]
    assert services.repository.get_upload(body["upload_id"])["coded_span"] == {
        "start_turn": 0,
        "end_turn": 1,
    }


def test_app_startup_does_not_create_queue_or_stt_clients(monkeypatch):
    from google.cloud import tasks_v2
    from onolys_miti.stt.google_chirp import GoogleChirp3

    def forbidden(*args, **kwargs):
        raise AssertionError("startup attempted provider I/O")

    monkeypatch.setattr(tasks_v2, "CloudTasksClient", forbidden)
    monkeypatch.setattr(GoogleChirp3, "__init__", forbidden)
    with client() as c:
        assert c.get("/v1/me", headers=AUTH).status_code == 200


def test_in_memory_queue_detaches_enqueued_payload():
    from onolys_eval_backend.queue import InMemoryTaskQueue

    queue = InMemoryTaskQueue()
    payload = {"upload_id": "first"}
    queue.enqueue("transcribe", payload, delay_seconds=15)
    payload["upload_id"] = "changed"
    assert queue.tasks == [
        {"kind": "transcribe", "payload": {"upload_id": "first"}, "delay_seconds": 15}
    ]


@pytest.mark.parametrize(
    ("provider", "language", "expected"),
    [
        ("google", "en", "en-US"),
        ("google_chirp", "en", "en-US"),
        ("google", "en-US", "en-US"),
        ("google", "en-GB", "en-GB"),
        ("google", "fr", "fr"),
        ("fixture", "en", "en"),
    ],
)
def test_default_english_maps_to_supported_google_stt_locale_only(
    tmp_path, provider, language, expected
):
    from onolys_engine_core.llm.routes import Preset, RouteRegistry
    from test_app import ENV

    from onolys_eval_backend.config import EvalConfig
    from onolys_eval_backend.services import EvalServices

    (tmp_path / "stt_providers.yaml").write_text(
        f"default: selected\nproviders:\n  selected: {{provider: {provider}, model: chirp_3}}\n"
    )
    services = EvalServices(
        EvalConfig.from_env({**ENV, "ROUTES_FILE": str(tmp_path / "routes.yaml")})
    )
    services.routes = RouteRegistry({}, {"configured-prod": Preset({}, stt="selected")})
    assert services.stt_params(language).language == expected


# --- LM-18 / D3 / M-7 / B7 ---------------------------------------------------------------


class FakeClock:
    def __init__(self):
        from datetime import UTC, datetime

        self.value = datetime(2026, 1, 1, tzinfo=UTC)

    def __call__(self):
        return self.value

    def advance(self, seconds):
        from datetime import timedelta

        self.value += timedelta(seconds=seconds)


@pytest.fixture
def clock(monkeypatch):
    from onolys_eval_backend import uploads

    fake = FakeClock()
    monkeypatch.setattr(uploads, "_now", fake)
    return fake


def test_endlessly_pending_transcription_stops_at_deadline(services, clock):
    from onolys_eval_backend import uploads

    c = client(services=services)
    uid = upload(c, "x.mp3", b"ID3abc", "audio/mpeg").json()["upload_id"]

    def task():
        return c.post("/internal/tasks/transcribe", headers=AUTH, json={"upload_id": uid})

    task()  # start
    for _ in range(3):  # fake provider stays pending across fresh deliveries
        clock.advance(60)
        assert task().status_code == 200
    enqueued = len(services.queue.tasks)
    assert services.repository.get_upload(uid)["status"] == "transcribing"
    clock.advance(uploads.TRANSCRIBE_DEADLINE_S)
    assert task().status_code == 200
    saved = services.repository.get_upload(uid)
    assert saved["status"] == "failed" and saved["error"]["code"] == "transcription_timeout"
    assert len(services.queue.tasks) == enqueued  # the chain ended: nothing re-enqueued
    services.stt.complete = True
    assert task().status_code == 200 and services.repository.get_upload(uid)["status"] == "failed"


def test_lost_last_poll_is_reconciled_on_read(services, clock):
    from onolys_eval_backend import uploads

    c = client(services=services)
    uid = upload(c, "x.mp3", b"ID3abc", "audio/mpeg").json()["upload_id"]
    assert c.get(f"/v1/uploads/{uid}", headers=AUTH).json()["status"] == "transcribing"
    clock.advance(uploads.TRANSCRIBE_DEADLINE_S + 1)
    body = c.get(f"/v1/uploads/{uid}", headers=AUTH).json()
    assert body["status"] == "failed" and body["error"]["code"] == "transcription_timeout"
    assert services.repository.get_upload(uid)["status"] == "failed"


def test_change_goal_limit_matches_run_request(services):
    c = client(services=services)
    assert upload(c, data={"change_goal": "g" * 4000}).status_code == 200
    assert upload(c, data={"change_goal": "g" * 4001}).status_code == 422


def test_multipart_audio_over_cloud_run_cap_gets_json_error(services, monkeypatch):
    from onolys_eval_backend import uploads

    monkeypatch.setattr(uploads, "MAX_MULTIPART_AUDIO_BYTES", 10)
    response = upload(client(services=services), "x.wav", b"RIFF\x00\x00\x00\x00WAVEdata", "audio/wav")
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "upload_too_large"
    assert uploads.MAX_BODY_BYTES < 32 * 1024 * 1024


def start_direct(c, **body):
    payload = {"filename": "talk.wav", "content_type": "audio/wav", "size": 5000, **body}
    return c.post("/v1/uploads/audio", headers=AUTH, json=payload)


def test_direct_audio_upload_signed_url_then_complete_enqueues_transcription(services):
    c = client(services=services)
    started = start_direct(c, size=200 * 1024 * 1024, change_goal="goal")
    assert started.status_code == 200, started.text
    body = started.json()
    uid = body["upload_id"]
    assert body["status"] == "awaiting_upload" and body["upload"]["method"] == "PUT"
    assert body["upload"]["url"].endswith(f"uploads/{uid}/input.wav")
    assert services.queue.tasks == []
    path = f"uploads/{uid}/input.wav"
    # Not uploaded yet.
    assert c.post(f"/v1/uploads/{uid}/complete", headers=AUTH).status_code == 409
    services.bucket.write_bytes(path, b"RIFF\x00\x00\x00\x00WAVEdata", content_type="audio/wav")
    done = c.post(f"/v1/uploads/{uid}/complete", headers=AUTH)
    assert done.status_code == 200 and done.json()["status"] == "transcribing"
    assert services.queue.tasks == [("transcribe", {"upload_id": uid}, 0)]
    again = c.post(f"/v1/uploads/{uid}/complete", headers=AUTH)  # idempotent
    assert again.status_code == 200 and len(services.queue.tasks) == 1
    assert c.post("/internal/tasks/transcribe", headers=AUTH, json={"upload_id": uid}).status_code == 200
    assert services.stt.starts[0][0].uri == f"gs://eval-test/{path}"


def test_direct_audio_upload_rejects_wrong_bytes_and_bad_requests(services):
    c = client(services=services)
    uid = start_direct(c).json()["upload_id"]
    services.bucket.write_bytes(
        f"uploads/{uid}/input.wav", b"not audio at all....", content_type="audio/wav"
    )
    assert c.post(f"/v1/uploads/{uid}/complete", headers=AUTH).status_code == 422
    assert services.repository.get_upload(uid)["status"] == "failed" and services.queue.tasks == []
    for bad in (
        {"filename": "x.exe"},
        {"size": 0},
        {"size": 301 * 1024 * 1024},
        {"change_goal": "g" * 4001},
        {"extra": 1},
    ):
        assert start_direct(c, **bad).status_code in {413, 415, 422}, bad


def test_slow_storage_does_not_block_other_requests(services):
    # B7: a blocking bucket write runs off the event loop, so /healthz answers meanwhile.
    import threading

    from test_app import ENV, TASK_CLAIMS, Verifier

    from onolys_eval_backend import create_app

    entered, release = threading.Event(), threading.Event()
    original = services.bucket.write_bytes

    def slow(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return original(*args, **kwargs)

    services.bucket.write_bytes = slow
    app = create_app(
        ENV, services=services, task_verifier=Verifier(TASK_CLAIMS),
        verifier=Verifier({"email": "alice@example.com", "email_verified": True}),
    )
    import asyncio

    import httpx

    async def scenario():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as http:
            post = asyncio.create_task(
                http.post(
                    "/v1/uploads",
                    headers=AUTH,
                    files={"file": ("s.json", json.dumps(transcript()).encode(), "application/json")},
                )
            )
            assert await asyncio.to_thread(entered.wait, 1)
            assert (await http.get("/healthz", headers=AUTH)).status_code == 200
            release.set()
            assert (await post).status_code == 200

    asyncio.run(scenario())


def test_direct_completion_retries_failed_enqueue_without_losing_work(services):
    c = client(services=services)
    uid = start_direct(c).json()["upload_id"]
    services.bucket.write_bytes(f"uploads/{uid}/input.wav", b"RIFF1234WAVEdata", content_type="audio/wav")
    enqueue = services.queue.enqueue

    def unavailable(*args, **kwargs):
        raise RuntimeError("queue unavailable")

    services.queue.enqueue = unavailable
    with pytest.raises(RuntimeError, match="queue unavailable"):
        c.post(f"/v1/uploads/{uid}/complete", headers=AUTH)
    services.queue.enqueue = enqueue
    assert c.post(f"/v1/uploads/{uid}/complete", headers=AUTH).status_code == 200
    assert len(services.queue.tasks) == 1


def test_direct_completion_recovers_after_accepted_task_record_failure(services):
    c = client(services=services)
    uid = start_direct(c).json()["upload_id"]
    services.bucket.write_bytes(f"uploads/{uid}/input.wav", b"RIFF1234WAVEdata", content_type="audio/wav")
    update = services.repository.update_upload

    def crash_record(upload_id, patch):
        if patch.get("initial_task_enqueued"):
            raise RuntimeError("record unavailable")
        return update(upload_id, patch)

    services.repository.update_upload = crash_record
    with pytest.raises(RuntimeError, match="record unavailable"):
        c.post(f"/v1/uploads/{uid}/complete", headers=AUTH)
    assert len(services.queue.tasks) == 1
    services.repository.update_upload = update
    assert c.post(f"/v1/uploads/{uid}/complete", headers=AUTH).status_code == 200
    assert len(services.queue.tasks) == 1


def test_delayed_second_completion_does_not_regress_finished_transcription(services):
    c = client(services=services)
    uid = start_direct(c).json()["upload_id"]
    services.bucket.write_bytes(f"uploads/{uid}/input.wav", b"RIFF1234WAVEdata", content_type="audio/wav")
    size = services.bucket.size

    def second_completes_first(path):
        services.bucket.size = size
        assert c.post(f"/v1/uploads/{uid}/complete", headers=AUTH).status_code == 200
        services.repository.update_upload(uid, {"status": "ready"})
        return size(path)

    services.bucket.size = second_completes_first
    response = c.post(f"/v1/uploads/{uid}/complete", headers=AUTH)
    assert response.json()["status"] == "ready"
    assert services.repository.get_upload(uid)["status"] == "ready"
    assert len(services.queue.tasks) == 1
