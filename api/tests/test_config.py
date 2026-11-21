import pytest
from onolys_core.errors import ConfigError

from onolys_api.config import Settings

pytestmark = pytest.mark.unit


def test_defaults_local():
    s = Settings.from_env({})
    assert (s.env, s.service_mode, s.auth_mode, s.adapters) == ("local", "combined", "fake", "stub")
    assert s.firestore_database == "(default)"
    assert (s.eval_cap_day, s.eval_cap_month) == (10, 100)
    assert (s.ai_cap_day, s.ai_cap_month) == (5, 30)


def test_parses_all_vars():
    s = Settings.from_env(
        {
            "ENV": "staging",
            "SERVICE_MODE": "worker",
            "AUTH_MODE": "idp",
            "ADAPTERS": "real",
            "GCP_PROJECT": "p",
            "REGION": "r",
            "FIRESTORE_DATABASE": "staging",
            "AUTH_PROJECT": "ap",
            "AUDIO_BUCKET": "b",
            "CORS_ORIGINS": "https://a.com, https://b.com ,",
            "EVAL_CAP_DAY": "7",
            "EVAL_CAP_MONTH": "70",
            "AI_CAP_DAY": "2",
            "AI_CAP_MONTH": "9",
            "TASKS_QUEUE": "q",
            "TASKS_SA": "sa",
            "WORKER_URL": "https://w",
            "ROUTES_FILE": "r.yaml",
            "DEFAULT_PRESET": "d",
            "GIT_SHA": "sha",
        }
    )
    assert s.service_mode == "worker" and s.firestore_database == "staging"
    assert s.cors_origins == ("https://a.com", "https://b.com")
    assert (s.eval_cap_day, s.eval_cap_month, s.ai_cap_day, s.ai_cap_month) == (7, 70, 2, 9)
    assert s.git_sha == "sha" and s.worker_url == "https://w"


def test_non_local_defaults_are_api_idp_real():
    s = Settings.from_env({"ENV": "prod"})
    assert (s.service_mode, s.auth_mode, s.adapters) == ("api", "idp", "real")


@pytest.mark.parametrize("env", ["staging", "prod"])
def test_fake_auth_rejected_outside_local(env):
    with pytest.raises(ConfigError, match="AUTH_MODE=fake"):
        Settings.from_env({"ENV": env, "AUTH_MODE": "fake"})


@pytest.mark.parametrize("env", ["local", "test"])
def test_fake_auth_allowed_locally(env):
    assert Settings.from_env({"ENV": env, "AUTH_MODE": "fake"}).auth_mode == "fake"


@pytest.mark.parametrize(
    "bad",
    [
        {"SERVICE_MODE": "x"},
        {"ENV": "dev"},
        {"ADAPTERS": "x"},
        {"AUTH_MODE": "x"},
        {"EVAL_CAP_DAY": "many"},
        {"AI_CAP_MONTH": "1.5"},
        {"EVAL_CAP_DAY": "-1"},
        {"AI_CAP_DAY": "-1"},
        {"EVAL_CAP_MONTH": "-1", "EVAL_CAP_DAY": "0"},
        {"EVAL_CAP_DAY": "11", "EVAL_CAP_MONTH": "10"},
        {"AI_CAP_DAY": "6", "AI_CAP_MONTH": "5"},
        {"STT_CAP_FACTOR": "lots"},
        {"STT_CAP_FACTOR": "0"},
        {"STT_CAP_MIN_S": "-5"},
        {"STT_CAP_MIN_S": "900", "STT_TIME_LIMIT_S": "600"},
    ],
)
def test_invalid_values(bad):
    with pytest.raises(ConfigError):
        Settings.from_env(bad)


def test_stt_cap_defaults_and_overrides():
    d = Settings.from_env({})
    assert (d.stt_cap_factor, d.stt_cap_min_s, d.stt_time_limit_s) == (3.0, 300.0, 1200.0)
    s = Settings.from_env(
        {"STT_CAP_FACTOR": "2", "STT_CAP_MIN_S": "120", "STT_TIME_LIMIT_S": "900"}
    )
    assert (s.stt_cap_factor, s.stt_cap_min_s, s.stt_time_limit_s) == (2.0, 120.0, 900.0)


def test_daily_run_cap_removed_everywhere():
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[2]
    assert not hasattr(Settings(), "daily_run_cap")
    paths = [root / "api/.env.example", root / "api/src/onolys_api/config.py"]
    paths += (root / "infra").rglob("*.tf")
    paths += (root / ".github/workflows").glob("*.yml")
    paths += [p for p in (root / "scripts/ci").glob("*") if p.is_file()]
    for p in paths:
        if ".terraform" in p.parts:
            continue
        text = p.read_text().lower()
        assert "daily_run_cap" not in text, p
