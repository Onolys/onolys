import pytest
from onolys_engine_core.errors import ConfigError

from onolys_api.config import Settings

pytestmark = pytest.mark.unit


def test_defaults_local():
    s = Settings.from_env({"APP_BASE_URL": "https://app.onolys.com", "ENV": "local"})
    assert (s.env, s.service_mode, s.auth_mode, s.adapters) == ("local", "combined", "fake", "stub")
    assert s.firestore_database == "(default)"
    assert (s.eval_cap_day, s.ai_cap_day) == (10, 5)


def test_parses_all_vars():
    s = Settings.from_env(
        {
            "APP_BASE_URL": "https://app.onolys.com",
            "ENV": "staging",
            "UID_HMAC_KEY": "k",
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
            "AI_CAP_DAY": "2",
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
    assert (s.eval_cap_day, s.ai_cap_day) == (7, 2)
    assert s.git_sha == "sha" and s.worker_url == "https://w"


def test_non_local_defaults_are_api_idp_real():
    s = Settings.from_env(
        {"APP_BASE_URL": "https://app.onolys.com", "ENV": "prod", "UID_HMAC_KEY": "k"}
    )
    assert (s.service_mode, s.auth_mode, s.adapters) == ("api", "idp", "real")


@pytest.mark.parametrize("env", ["staging", "prod"])
def test_fake_auth_rejected_outside_local(env):
    with pytest.raises(ConfigError, match="AUTH_MODE=fake"):
        Settings.from_env(
            {"APP_BASE_URL": "https://app.onolys.com", "ENV": env, "AUTH_MODE": "fake"}
        )


@pytest.mark.parametrize("env", ["local", "test"])
def test_fake_auth_allowed_locally(env):
    assert (
        Settings.from_env(
            {"APP_BASE_URL": "https://app.onolys.com", "ENV": env, "AUTH_MODE": "fake"}
        ).auth_mode
        == "fake"
    )


@pytest.mark.parametrize(
    "bad",
    [
        {"SERVICE_MODE": "x"},
        {"ENV": "dev"},
        {"ADAPTERS": "x"},
        {"AUTH_MODE": "x"},
        {"EVAL_CAP_DAY": "many"},
        {"EVAL_CAP_DAY": "-1"},
        {"AI_CAP_DAY": "-1"},
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
    d = Settings.from_env({"APP_BASE_URL": "https://app.onolys.com", "ENV": "local"})
    assert (d.stt_cap_factor, d.stt_cap_min_s, d.stt_time_limit_s) == (3.0, 300.0, 1200.0)
    s = Settings.from_env(
        {
            "APP_BASE_URL": "https://app.onolys.com",
            "ENV": "local",
            "STT_CAP_FACTOR": "2",
            "STT_CAP_MIN_S": "120",
            "STT_TIME_LIMIT_S": "900",
        }
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


def test_env_is_required():
    """A8: an unset ENV must not silently mean local (fake auth, no /tasks OIDC)."""
    with pytest.raises(ConfigError, match="ENV is required"):
        Settings.from_env({})


@pytest.mark.parametrize("env", ["local", "test"])
def test_local_env_refused_on_cloud_run(env):
    with pytest.raises(ConfigError, match="Cloud Run"):
        Settings.from_env(
            {"APP_BASE_URL": "https://app.onolys.com", "ENV": env, "K_SERVICE": "onolys-api"}
        )


def test_cloud_run_with_prod_env_is_fine():
    s = Settings.from_env(
        {
            "APP_BASE_URL": "https://app.onolys.com",
            "ENV": "prod",
            "K_SERVICE": "onolys-api",
            "UID_HMAC_KEY": "k",
        }
    )
    assert s.env == "prod"


@pytest.mark.parametrize("env", ["staging", "prod"])
def test_uid_hmac_key_required_outside_local(env):
    """A19: an empty key makes `uid_hash` a public, unkeyed-looking hash."""
    with pytest.raises(ConfigError, match="UID_HMAC_KEY"):
        Settings.from_env({"APP_BASE_URL": "https://app.onolys.com", "ENV": env})
    assert (
        Settings.from_env(
            {"APP_BASE_URL": "https://app.onolys.com", "ENV": env, "UID_HMAC_KEY": "k"}
        ).uid_hmac_key
        == "k"
    )


def test_uid_hmac_key_optional_locally():
    assert (
        Settings.from_env({"APP_BASE_URL": "https://app.onolys.com", "ENV": "local"}).uid_hmac_key
        == ""
    )


@pytest.mark.parametrize(
    "env,url",
    [
        ("staging", "https://onolys-app-staging.web.app"),
        ("prod", "https://app.onolys.com"),
        ("prod", "https://onolys-app.web.app"),
        ("local", "http://localhost:5173"),
        ("test", "http://localhost:8080"),
    ],
)
def test_app_base_url_allowed(env, url):
    s = Settings.from_env({"ENV": env, "UID_HMAC_KEY": "k", "APP_BASE_URL": url})
    assert s.app_base_url == url
    assert s.email_from == "Onolys <no-reply@onolys.com>"
    assert s.resend_api_key == ""


@pytest.mark.parametrize(
    "url",
    [
        "app.onolys.com",
        "http://app.onolys.com",
        "https://evil.example",
        "https://app.onolys.com.evil.example",
        "https://user@app.onolys.com",
        "https://app.onolys.com/auth/action",
        "https://app.onolys.com?next=evil",
        "https://app.onolys.com#fragment",
        "https://app.onolys.com:invalid",
        "https://app.onolys.com:8443",
        "https://app.onolys.com\\evil",
        " https://app.onolys.com",
        "https://app.onolys.com\n",
        "http://localhost:99999",
        "http://127.0.0.1:5173",
    ],
)
def test_app_base_url_rejects_invalid_origin(url):
    with pytest.raises(ConfigError, match="APP_BASE_URL"):
        Settings.from_env({"ENV": "test", "APP_BASE_URL": url})


@pytest.mark.parametrize("env", ["local", "test", "staging", "prod"])
@pytest.mark.parametrize("mode", ["api", "worker", "voice", "combined"])
def test_app_base_url_is_optional_in_every_mode(env, mode):
    s = Settings.from_env({"ENV": env, "SERVICE_MODE": mode, "UID_HMAC_KEY": "k",
                           "AUTH_MODE": "fake" if env in ("local", "test") else "idp"})  # fmt: skip
    assert s.app_base_url == ""


@pytest.mark.parametrize("mode", ["api", "worker", "voice"])
def test_invalid_app_base_url_still_rejected_in_any_mode(mode):
    with pytest.raises(ConfigError, match="APP_BASE_URL"):
        Settings.from_env({"ENV": "staging", "SERVICE_MODE": mode, "UID_HMAC_KEY": "k",
                           "APP_BASE_URL": "https://evil.example.com"})  # fmt: skip


def test_client_ip_trusted_hops_setting():
    base = {"ENV": "local"}
    assert Settings.from_env(base).client_ip_trusted_hops == 1
    assert Settings.from_env({**base, "CLIENT_IP_TRUSTED_HOPS": "0"}).client_ip_trusted_hops == 0
    for bad in ("-1", "x"):
        with pytest.raises(ConfigError, match="CLIENT_IP_TRUSTED_HOPS"):
            Settings.from_env({**base, "CLIENT_IP_TRUSTED_HOPS": bad})


@pytest.mark.parametrize("env", ["staging", "prod"])
def test_localhost_not_allowed_outside_local(env):
    with pytest.raises(ConfigError, match="APP_BASE_URL"):
        Settings.from_env(
            {"ENV": env, "UID_HMAC_KEY": "k", "APP_BASE_URL": "http://localhost:5173"}
        )


def test_email_settings_read_overrides():
    s = Settings.from_env(
        {
            "ENV": "test",
            "APP_BASE_URL": "http://localhost:5173",
            "EMAIL_FROM": "Test <test@onolys.com>",
            "RESEND_API_KEY": "secret",
        }
    )
    assert s.email_from == "Test <test@onolys.com>"
    assert s.resend_api_key == "secret"


def test_normal_startup_allows_missing_app_base_url(monkeypatch):
    from onolys_api.app import create_app

    monkeypatch.setenv("ENV", "test")
    monkeypatch.delenv("APP_BASE_URL", raising=False)
    assert create_app().state.settings.app_base_url == ""


def test_staging_startup_without_resend_key():
    from onolys_api.app import create_app
    from onolys_api.repo.fake import FakeRepo
    from onolys_api.storage.fake import FakeBlobStore

    s = Settings.from_env(
        {
            "ENV": "staging",
            "UID_HMAC_KEY": "k",
            "ADAPTERS": "stub",
            "AUTH_PROJECT": "test-project",
            "APP_BASE_URL": "https://onolys-app-staging.web.app",
        }
    )
    blobs = FakeBlobStore()
    app = create_app(s, repo=FakeRepo(blobs), blobs=blobs)
    assert app.state.settings.resend_api_key == ""
