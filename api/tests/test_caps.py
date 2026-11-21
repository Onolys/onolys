"""Daily run cap + concurrent-run limit (R8, D14, AC7); GET /usage lives in test_usage_route.py.

Repo-level tests run against FakeRepo and the Firestore emulator (when FIRESTORE_EMULATOR_HOST is
set); the API tests use FakeRepo.
"""

import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest

from onolys_api.config import Settings
from onolys_api.errors import ApiError
from onolys_api.jobs import caps
from onolys_api.repo.fake import FakeRepo
from onolys_api.storage.fake import FakeBlobStore

HAS_EMULATOR = bool(os.environ.get("FIRESTORE_EMULATOR_HOST"))
DAY = "2026-11-20"
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


def uid() -> str:
    return f"u-{uuid.uuid4().hex[:10]}"


def settings(**kw) -> Settings:
    return Settings(env="test", auth_mode="fake", **kw)


def set_user_fields(repo, u: str, **fields) -> None:
    """Write fields onto users/{uid} (the per-user override) on either repo."""
    if isinstance(repo, FakeRepo):
        d = repo._get(f"users/{u}") or {}
        repo._put(f"users/{u}", {**d, **fields})
    else:
        repo._client.collection("users").document(u).set(fields, merge=True)


def code_of(exc: ApiError) -> str:
    return exc.details[0]["code"]


def test_21st_run_of_the_day_is_429_daily_cap_reached(repo):
    u, s = uid(), settings(eval_cap_day=20, max_active_runs=1000)
    for _ in range(20):
        caps.reserve_run(repo, s, u, NOON)
    with pytest.raises(ApiError) as e:
        caps.reserve_run(repo, s, u, NOON)
    assert e.value.status == 429 and code_of(e.value) == "daily_cap_reached"
    assert repo.get_usage(u, DAY).runs == 20  # the refused attempt is not counted


def test_new_utc_day_starts_a_fresh_count(repo):
    u, s = uid(), settings(eval_cap_day=1, max_active_runs=1000)
    caps.reserve_run(repo, s, u, NOON)
    with pytest.raises(ApiError):
        caps.reserve_run(repo, s, u, NOON)
    caps.reserve_run(repo, s, u, NOON + timedelta(days=1))


def test_per_user_override_beats_the_config_default(repo):
    u, s = uid(), settings(eval_cap_day=20, max_active_runs=1000)
    set_user_fields(repo, u, daily_cap=2)
    caps.reserve_run(repo, s, u, NOON)
    caps.reserve_run(repo, s, u, NOON)
    with pytest.raises(ApiError) as e:
        caps.reserve_run(repo, s, u, NOON)
    assert code_of(e.value) == "daily_cap_reached"


def test_concurrent_reservations_never_exceed_the_cap(repo):
    u, s = uid(), settings(eval_cap_day=3, max_active_runs=1000)

    def attempt(_):
        try:
            caps.reserve_run(repo, s, u, NOON)
            return "ok"
        except ApiError as e:
            return code_of(e)

    with ThreadPoolExecutor(6) as ex:
        outs = list(ex.map(attempt, range(6)))
    assert outs.count("ok") == 3 and outs.count("daily_cap_reached") == 3
    assert repo.get_usage(u, DAY).runs == 3


def test_refund_before_any_llm_call_frees_the_slot_and_the_count(repo):
    u, s = uid(), settings(eval_cap_day=1, max_active_runs=1000)
    day = caps.reserve_run(repo, s, u, NOON)
    assert day == DAY
    with pytest.raises(ApiError):
        caps.reserve_run(repo, s, u, NOON)
    caps.release_run(repo, u, day, refund=True)
    assert repo.get_usage(u, DAY).runs == 0
    caps.reserve_run(repo, s, u, NOON)  # the user can run again


def test_release_without_refund_keeps_the_daily_count(repo):
    u, s = uid(), settings(eval_cap_day=1, max_active_runs=1)
    day = caps.reserve_run(repo, s, u, NOON)
    caps.release_run(repo, u, day, refund=False)  # run finished after spending LLM calls
    assert repo.get_usage(u, DAY).runs == 1
    with pytest.raises(ApiError) as e:
        caps.reserve_run(repo, s, u, NOON)
    assert code_of(e.value) == "daily_cap_reached"


def test_release_never_goes_below_zero(repo):
    u = uid()
    caps.release_run(repo, u, DAY, refund=True)
    caps.release_run(repo, u, DAY, refund=True)
    assert repo.get_usage(u, DAY).runs == 0
    s = settings(eval_cap_day=5, max_active_runs=1)
    caps.reserve_run(repo, s, u, NOON)
    with pytest.raises(ApiError):  # the stray releases did not create extra slots
        caps.reserve_run(repo, s, u, NOON)


def test_third_concurrent_active_run_is_429_and_a_finished_run_frees_a_slot(repo):
    u, s = uid(), settings(eval_cap_day=20, max_active_runs=2)
    d1 = caps.reserve_run(repo, s, u, NOON)
    caps.reserve_run(repo, s, u, NOON)
    with pytest.raises(ApiError) as e:
        caps.reserve_run(repo, s, u, NOON)
    assert e.value.status == 429 and code_of(e.value) == "daily_cap_reached"
    assert repo.get_usage(u, DAY).runs == 2  # the refused attempt is not counted
    caps.release_run(repo, u, d1, refund=False)
    caps.reserve_run(repo, s, u, NOON)


def test_concurrent_attempts_cannot_exceed_the_active_run_limit(repo):
    u, s = uid(), settings(eval_cap_day=20, max_active_runs=2)

    def attempt(_):
        try:
            caps.reserve_run(repo, s, u, NOON)
            return "ok"
        except ApiError as e:
            return code_of(e)

    with ThreadPoolExecutor(6) as ex:
        outs = list(ex.map(attempt, range(6)))
    assert outs.count("ok") == 2 and outs.count("daily_cap_reached") == 4


def test_per_user_active_limit_override(repo):
    u, s = uid(), settings(eval_cap_day=20, max_active_runs=2)
    set_user_fields(repo, u, max_active_runs=1)
    caps.reserve_run(repo, s, u, NOON)
    with pytest.raises(ApiError):
        caps.reserve_run(repo, s, u, NOON)


def test_usage_view_and_reset_time(repo):
    u, s = uid(), settings(eval_cap_day=20)
    v = caps.usage_view(repo, s, u, NOON)
    assert (v.eval.day.used, v.eval.day.cap) == (0, 20)
    assert v.eval.day.resets_at == datetime(2026, 11, 21, tzinfo=UTC)
    assert v.eval.month.resets_at == datetime(2026, 12, 1, tzinfo=UTC)
    caps.reserve_run(repo, s, u, NOON)
    set_user_fields(repo, u, daily_cap=7)
    v = caps.usage_view(repo, s, u, NOON)
    assert (v.eval.day.used, v.eval.day.cap, v.eval.month.used) == (1, 7, 1)


# ---- SP11: reserve/release/usage_view (kinds, periods) ----

DEC = datetime(2026, 12, 31, 12, 0, tzinfo=UTC)


def fill(repo, s, u, kind, n, now=NOON):
    for _ in range(n):
        caps.reserve(repo, s, u, kind, now)


def refused(repo, s, u, kind, now=NOON) -> ApiError:
    with pytest.raises(ApiError) as e:
        caps.reserve(repo, s, u, kind, now)
    assert e.value.status == 429
    return e.value


def period_of(exc: ApiError):
    return exc.details[0].get("period")


def test_11th_eval_is_daily_cap_period_day(repo):
    u, s = uid(), settings(max_active_runs=1000)
    fill(repo, s, u, "eval", 10)
    e = refused(repo, s, u, "eval")
    assert code_of(e) == "daily_cap_reached" and period_of(e) == "day"
    day, month = repo.get_usage_docs(u, DAY)
    assert (day.runs, month.runs) == (10, 10)  # refused attempt counted nothing


def test_101st_eval_is_monthly_cap_period_month(repo):
    u, s = uid(), settings(max_active_runs=1000)
    for i in range(10):  # 10 days x 10 = 100
        fill(repo, s, u, "eval", 10, NOON + timedelta(days=i - 9))
    e = refused(repo, s, u, "eval", NOON + timedelta(days=1))
    assert code_of(e) == "monthly_cap_reached" and period_of(e) == "month"


def test_6th_interview_is_day_and_31st_is_month(repo):
    u, s = uid(), settings()
    fill(repo, s, u, "interview", 5)
    e = refused(repo, s, u, "interview")
    assert code_of(e) == "interview_cap_reached" and period_of(e) == "day"
    for i in range(1, 6):
        fill(repo, s, u, "interview", 5, NOON - timedelta(days=i))
    e = refused(repo, s, u, "interview", NOON - timedelta(days=6))
    assert code_of(e) == "interview_cap_reached" and period_of(e) == "month"


def test_month_wins_when_both_exhausted(repo):
    u, s = uid(), settings(eval_cap_day=1, eval_cap_month=1, max_active_runs=1000)
    caps.reserve(repo, s, u, "eval", NOON)
    e = refused(repo, s, u, "eval")
    assert code_of(e) == "monthly_cap_reached" and period_of(e) == "month"
    s2 = settings(ai_cap_day=1, ai_cap_month=1)
    caps.reserve(repo, s2, u, "interview", NOON)
    e = refused(repo, s2, u, "interview")
    assert code_of(e) == "interview_cap_reached" and period_of(e) == "month"


def test_day_rolls_over_but_month_persists(repo):
    u, s = uid(), settings(eval_cap_day=1, eval_cap_month=2, max_active_runs=1000)
    caps.reserve(repo, s, u, "eval", NOON)
    caps.reserve(repo, s, u, "eval", NOON + timedelta(days=1))  # new day: fresh day count
    e = refused(repo, s, u, "eval", NOON + timedelta(days=2))  # month spent
    assert period_of(e) == "month"


def test_month_rolls_over(repo):
    u, s = uid(), settings(eval_cap_day=5, eval_cap_month=1, max_active_runs=1000)
    caps.reserve(repo, s, u, "eval", DEC)
    refused(repo, s, u, "eval", DEC)
    caps.reserve(repo, s, u, "eval", DEC + timedelta(days=1))  # 2027-01-01


def test_kinds_are_independent(repo):
    u, s = uid(), settings(eval_cap_day=1, ai_cap_day=1, max_active_runs=1000)
    caps.reserve(repo, s, u, "eval", NOON)
    caps.reserve(repo, s, u, "interview", NOON)
    refused(repo, s, u, "eval")
    refused(repo, s, u, "interview")
    day, month = repo.get_usage_docs(u, DAY)
    assert (day.runs, day.interviews, month.runs, month.interviews) == (1, 1, 1, 1)


def test_interview_ignores_concurrent_limit_and_active_runs(repo):
    u, s = uid(), settings(max_active_runs=1)
    caps.reserve(repo, s, u, "eval", NOON)
    caps.reserve(repo, s, u, "interview", NOON)  # not blocked by the eval slot
    assert repo.get_user(u).active_runs == 1


def test_refund_decrements_day_and_month_and_frees_active_slot(repo):
    u, s = uid(), settings(max_active_runs=1)
    r = caps.reserve(repo, s, u, "eval", NOON)
    assert repo.get_user(u).active_runs == 1
    caps.release(repo, u, r, refund=True)
    day, month = repo.get_usage_docs(u, DAY)
    assert (day.runs, month.runs, repo.get_user(u).active_runs) == (0, 0, 0)


def test_refund_interview_decrements_both(repo):
    u, s = uid(), settings()
    r = caps.reserve(repo, s, u, "interview", NOON)
    caps.release(repo, u, r, refund=True)
    day, month = repo.get_usage_docs(u, DAY)
    assert (day.interviews, month.interviews) == (0, 0)


def test_no_refund_keeps_counts_but_frees_active_runs(repo):
    u, s = uid(), settings(max_active_runs=1)
    r = caps.reserve(repo, s, u, "eval", NOON)
    caps.release(repo, u, r, refund=False)
    day, month = repo.get_usage_docs(u, DAY)
    assert (day.runs, month.runs, repo.get_user(u).active_runs) == (1, 1, 0)
    caps.reserve(repo, s, u, "eval", NOON)  # slot is free again


def test_refund_after_day_rollover_hits_the_reserved_docs(repo):
    u, s = uid(), settings(max_active_runs=1000)
    r = caps.reserve(repo, s, u, "eval", NOON)
    caps.reserve(repo, s, u, "eval", NOON + timedelta(days=1))
    caps.release(repo, u, r, refund=True)  # released "tomorrow"
    d1, m = repo.get_usage_docs(u, DAY)
    d2, _ = repo.get_usage_docs(u, "2026-11-21")
    assert (d1.runs, d2.runs, m.runs) == (0, 1, 1)


def test_refund_after_month_rollover_hits_the_old_month(repo):
    u, s = uid(), settings(max_active_runs=1000)
    r = caps.reserve(repo, s, u, "eval", DEC)
    caps.reserve(repo, s, u, "eval", DEC + timedelta(days=1))
    caps.release(repo, u, r, refund=True)
    _, dec = repo.get_usage_docs(u, "2026-12-31")
    _, jan = repo.get_usage_docs(u, "2027-01-01")
    assert (dec.runs, jan.runs) == (0, 1)


def test_interview_release_floor_zero(repo):
    u = uid()
    caps.release(repo, u, caps.Reservation("interview", DAY), refund=True)
    day, month = repo.get_usage_docs(u, DAY)
    assert (day.interviews, month.interviews) == (0, 0)


def test_user_limits_override_applies_per_kind_period(repo):
    u, s = uid(), settings()
    set_user_fields(repo, u, limits={"interview": {"day": 1}})
    caps.reserve(repo, s, u, "interview", NOON)
    assert period_of(refused(repo, s, u, "interview")) == "day"


def test_usage_view_interview_and_month_fields(repo):
    u, s = uid(), settings()
    caps.reserve(repo, s, u, "interview", NOON)
    v = caps.usage_view(repo, s, u, NOON)
    assert (v.interview.day.used, v.interview.day.cap) == (1, 5)
    assert (v.interview.month.used, v.interview.month.cap) == (1, 30)
    assert (v.eval.month.used, v.eval.month.cap) == (0, 100)
    assert caps.usage_view(repo, s, u, DEC).interview.month.resets_at == datetime(
        2027, 1, 1, tzinfo=UTC
    )


def _parallel(repo, s, u, kinds, now=NOON):
    def attempt(kind):
        try:
            caps.reserve(repo, s, u, kind, now)
            return "ok"
        except ApiError as e:
            return code_of(e)

    with ThreadPoolExecutor(6) as ex:
        return list(ex.map(attempt, kinds))


@pytest.mark.parametrize(
    "kind,code", [("eval", "daily_cap_reached"), ("interview", "interview_cap_reached")]
)
def test_parallel_reserve_day_cap_3(repo, kind, code):
    u = uid()
    s = settings(eval_cap_day=3, ai_cap_day=3, max_active_runs=1000)
    outs = _parallel(repo, s, u, [kind] * 6)
    assert outs.count("ok") == 3 and outs.count(code) == 3
    day, month = repo.get_usage_docs(u, DAY)
    assert (day.runs + day.interviews, month.runs + month.interviews) == (3, 3)


@pytest.mark.parametrize(
    "kind,code", [("eval", "monthly_cap_reached"), ("interview", "interview_cap_reached")]
)
def test_parallel_reserve_month_cap_3(repo, kind, code):
    u = uid()
    s = settings(eval_cap_month=3, ai_cap_month=3, max_active_runs=1000)
    outs = _parallel(repo, s, u, [kind] * 6)
    assert outs.count("ok") == 3 and outs.count(code) == 3


def test_parallel_reserve_mixed_kinds_each_capped_independently(repo):
    u = uid()
    s = settings(eval_cap_day=3, ai_cap_day=3, max_active_runs=1000)
    outs = _parallel(repo, s, u, ["eval"] * 4 + ["interview"] * 4)
    assert outs.count("ok") == 6
    day, _ = repo.get_usage_docs(u, DAY)
    assert (day.runs, day.interviews) == (3, 3)


def test_max_active_runs_setting(monkeypatch):
    assert Settings.from_env({}).max_active_runs == 2
    assert Settings.from_env({"MAX_ACTIVE_RUNS": "3"}).max_active_runs == 3
