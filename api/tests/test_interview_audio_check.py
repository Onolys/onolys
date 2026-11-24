"""02-logging Task 7 (R12, R13, AC7): one `interview_audio_check` line per interview-linked
validation, match or not."""

import dataclasses
import inspect
import json
import logging

import pytest
from onolys_engine_core.json_logging import ContextFilter, JsonFormatter
from test_interview_link import interview, upload

from onolys_api.audio import ProbeResult
from onolys_api.jobs.validate import log_interview_audio_check
from onolys_api.repo.base import NotFoundError
from onolys_api.repo.fake import FakeRepo
from onolys_api.repo.models import ClientInfo, RelayInfo

pytestmark = pytest.mark.unit
EVENT = "interview_audio_check"
BASE = {"session_id", "interview_id", "uploaded_s", "relay_s", "diff_s", "threshold_s", "result"}
VERSIONS = {
    "code_version", "relay_version", "relay_revision", "web_version", "user_agent",
    "recorder_mime", "audio_engine", "audio_format", "audio_streams",
}  # fmt: skip


@pytest.fixture
def repo(blobs):
    return FakeRepo(blobs)


class Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.INFO)
        self.addFilter(ContextFilter())
        self.setFormatter(JsonFormatter())
        self.out: list[dict] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.out.append(json.loads(self.format(record)))


@pytest.fixture
def cap():
    h = Capture()
    root = logging.getLogger()
    old = root.level
    root.addHandler(h)
    root.setLevel(logging.INFO)
    yield h
    root.removeHandler(h)
    root.setLevel(old)


def lines(cap):
    return [d for d in cap.out if d.get("event") == EVENT]


async def test_match_one_info_line_with_all_fields(settings, repo, blobs, cap):
    iid = interview(
        repo, duration_s=300.04,
        client=ClientInfo(
            web_version="abc123", user_agent="UA/1", recorder_mime="audio/webm",
            audio_engine="eng-1",
        ),
        relay=RelayInfo(relay_version="rsha", relay_revision="rrev"),
    )  # fmt: skip
    sid = await upload(settings, repo, blobs, 310.06, iid)
    [d] = lines(cap)
    assert BASE | VERSIONS <= d.keys()
    assert d["result"] == "ok" and d["session_id"] == sid and d["interview_id"] == iid
    assert (d["uploaded_s"], d["relay_s"], d["diff_s"], d["threshold_s"]) == (
        310.1,
        300.0,
        10.0,
        60.0,
    )
    assert (d["web_version"], d["relay_version"], d["relay_revision"]) == ("abc123", "rsha", "rrev")
    assert (d["recorder_mime"], d["audio_engine"], d["user_agent"]) == (
        "audio/webm",
        "eng-1",
        "UA/1",
    )
    assert (d["audio_format"], d["audio_streams"]) == ("wav", 1)


async def test_mismatch_one_line(settings, repo, blobs, cap):
    iid = interview(repo, duration_s=120.0)
    await upload(settings, repo, blobs, 600.0, iid)
    [d] = lines(cap)
    assert d["result"] == "mismatch" and d["diff_s"] == 480.0 and d["threshold_s"] == 60.0
    assert BASE <= d.keys()


@pytest.mark.parametrize(
    ("relay_s", "upload_s", "result", "threshold"),
    [
        (600.0, 689.0, "ok", 90.0),
        (600.0, 691.0, "mismatch", 90.0),
        (180.0, 240.0, "ok", 60.0),
        (180.0, 241.0, "mismatch", 60.0),
    ],
)
async def test_threshold_is_max_of_min_and_pct_one_line_each(
    settings, repo, blobs, cap, relay_s, upload_s, result, threshold
):
    settings = dataclasses.replace(settings, ai_max_seconds=700)
    iid = interview(repo, duration_s=relay_s)
    await upload(settings, repo, blobs, upload_s, iid)
    [d] = lines(cap)
    assert (d["result"], d["threshold_s"]) == (result, threshold)


async def test_skipped_no_relay_duration(settings, repo, blobs, cap):
    iid = interview(repo, duration_s=None)
    await upload(settings, repo, blobs, 310.0, iid)
    [d] = lines(cap)
    assert d["result"] == "skipped_no_relay_duration"
    assert d["uploaded_s"] == 310.0 and "relay_s" not in d and "diff_s" not in d
    assert {"session_id", "interview_id", "threshold_s"} <= d.keys()
    assert not {"web_version", "relay_version", "relay_revision"} & d.keys()  # absent, no error


async def test_skipped_no_interview(settings, repo, blobs, cap, monkeypatch):
    iid = interview(repo)

    real = repo.get_interview

    def flaky(uid, interview_id):  # the session links fine; the interview is gone in `validate`
        if any(f.filename.endswith("jobs/validate.py") for f in inspect.stack()):
            raise NotFoundError()
        return real(uid, interview_id)

    monkeypatch.setattr(repo, "get_interview", flaky)
    sid = await upload(settings, repo, blobs, 310.0, iid)
    [d] = lines(cap)
    assert d["result"] == "skipped_no_interview"
    assert d["session_id"] == sid and d["interview_id"] == iid and d["uploaded_s"] == 310.0
    assert "relay_s" not in d


async def test_plain_session_emits_no_line(settings, repo, blobs, cap):
    await upload(settings, repo, blobs, 310.0)
    assert lines(cap) == []


def test_helper_takes_threshold_and_result_and_logs_codec(cap):
    log_interview_audio_check(
        session_id="s1", interview_id="i1", uploaded_s=100.0, relay_s=10.0,
        threshold_s=60.0, result="mismatch", audio_format="webm",
        probe=ProbeResult(duration_s=100.0, audio_streams=1, codec_name="opus"),
        session_client=ClientInfo(), interview=None,
    )  # fmt: skip
    [d] = lines(cap)
    assert d["audio_codec"] == "opus" and d["threshold_s"] == 60.0 and d["diff_s"] == 90.0
