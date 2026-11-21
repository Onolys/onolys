"""One DAILY limit per flow (eval, AI interview) and one active run per user (FX46).

There are no monthly caps: spending across many days never blocks a user who is under today's cap.
"""

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from onolys_api.config import Settings
from onolys_api.errors import ApiError
from onolys_api.jobs import caps
from onolys_api.repo.fake import FakeRepo
from onolys_api.storage.fake import FakeBlobStore

HAS_EMULATOR = bool(os.environ.get("FIRESTORE_EMULATOR_HOST"))
NOON = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)


@pytest.fixture(params=["fake", pytest.param("firestore", marks=pytest.mark.integration)])
def repo(request, tmp_path):
    blobs = FakeBlobStore(tmp_path / "blobs", bucket="test-bucket")
    if request.param == "fake":
        return FakeRepo(blobs)
    if not HAS_EMULATOR:
        pytest.skip("FIRESTORE_EMULATOR_HOST not set")
    from google.auth.credentials import AnonymousCredentials
    from google.cloud import firestore

    from onolys_api.repo.firestore import FirestoreRepo

    client = firestore.Client(project="demo-onolys", credentials=AnonymousCredentials())
    return FirestoreRepo(client, blobs)


def _uid() -> str:
    return f"u-{uuid.uuid4().hex[:10]}"


def _settings(**kw) -> Settings:
    return Settings(env="test", auth_mode="fake", max_active_runs=1000, **kw)


@pytest.mark.parametrize("kind", ["eval", "interview"])
def test_past_the_old_monthly_count_but_under_the_daily_cap_still_reserves(repo, kind):
    u, s = _uid(), _settings(eval_cap_day=10, ai_cap_day=5)
    cap = 10 if kind == "eval" else 5
    for i in range(1, 25):  # 24 days at the daily cap: far past the old 100 / 30 monthly caps
        day = NOON - timedelta(days=i)
        for _ in range(cap):
            caps.release(repo, u, caps.reserve(repo, s, u, kind, day), refund=False)
    caps.reserve(repo, s, u, kind, NOON)  # today is untouched: allowed


@pytest.mark.parametrize("kind", ["eval", "interview"])
def test_daily_cap_is_the_only_limit(repo, kind):
    u, s = _uid(), _settings(eval_cap_day=2, ai_cap_day=2)
    for _ in range(2):
        caps.release(repo, u, caps.reserve(repo, s, u, kind, NOON), refund=False)
    with pytest.raises(ApiError) as e:
        caps.reserve(repo, s, u, kind, NOON)
    d = e.value.details[0]
    assert d["period"] == "day"
    assert d["code"] == ("daily_cap_reached" if kind == "eval" else "interview_cap_reached")


def test_settings_have_no_monthly_caps_():
    s = Settings.from_env({})
    assert not hasattr(s, "eval_cap_month") and not hasattr(s, "ai_cap_month")
    assert Settings.from_env({"EVAL_CAP_MONTH": "1", "AI_CAP_MONTH": "1"}) == s  # ignored


def test_one_active_run_per_user_by_default():
    assert Settings().max_active_runs == 1
    assert Settings.from_env({}).max_active_runs == 1
    assert Settings.from_env({"MAX_ACTIVE_RUNS": "3"}).max_active_runs == 3  # env still overrides


def test_second_concurrent_run_is_held_by_the_default_limit(repo):
    u, s = _uid(), Settings(env="test", auth_mode="fake")  # default max_active_runs
    caps.reserve(repo, s, u, "eval", NOON)
    with pytest.raises(ApiError) as e:
        caps.reserve(repo, s, u, "eval", NOON)
    assert e.value.details[0]["code"] == "daily_cap_reached"
    assert e.value.message == caps.CONCURRENT_MESSAGE
    caps.reserve(repo, s, u, "interview", NOON)  # the AI flow is not an evaluation run
