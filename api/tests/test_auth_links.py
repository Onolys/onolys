from types import SimpleNamespace
from unittest.mock import Mock
from urllib.parse import parse_qs, urlsplit

import pytest

from onolys_api.adapters.base import AdapterError
from onolys_api.config import Settings

pytestmark = pytest.mark.unit


def test_real_links_resolve_uid_and_discard_sdk_host():
    from onolys_api.adapters.real import FirebaseAuthLinks

    sdk = SimpleNamespace(
        ActionCodeSettings=lambda **kwargs: SimpleNamespace(**kwargs),
        get_user=Mock(
            return_value=SimpleNamespace(
                email="person@example.com", email_verified=False, disabled=False
            )
        ),
        generate_email_verification_link=Mock(
            return_value="https://evil.example/auth?mode=resetPassword&oobCode=secret&apiKey=ignored"
        ),
        generate_password_reset_link=Mock(
            return_value="https://evil.example/auth?oobCode=reset-code"
        ),
    )
    links = FirebaseAuthLinks("project", "https://app.onolys.com", auth_sdk=sdk)
    assert links.verification("uid") == "secret"
    sdk.get_user.assert_called_with("uid")
    assert sdk.generate_email_verification_link.call_args.args[0] == "person@example.com"
    assert links.password_reset("person@example.com") == "reset-code"


@pytest.mark.parametrize(
    "next_path", ["//evil.example", "/\\evil", "https://evil.example", "", "x"]
)
def test_builder_drops_bad_next(next_path):
    from onolys_api.email.links import build_action_link

    url = build_action_link(
        Settings(app_base_url="https://app.onolys.com"), "verify", "secret", next_path=next_path
    )
    assert urlsplit(url).netloc == "app.onolys.com"
    query = parse_qs(urlsplit(url).query)
    assert query == {"mode": ["verifyEmail"], "oobCode": ["secret"]}


@pytest.mark.parametrize("kind,mode", [("verify", "verifyEmail"), ("reset", "resetPassword")])
def test_builder_encodes_code_and_safe_continue_url(kind, mode):
    from onolys_api.email.links import build_action_link

    url = build_action_link(
        Settings(app_base_url="https://onolys-staging-app.web.app"),
        kind,
        "code&extra=bad",
        next_path="/sessions?new=1",
    )
    parts = urlsplit(url)
    assert parts.netloc == "onolys-staging-app.web.app" and parts.path == "/auth/action"
    query = parse_qs(parts.query)
    assert query["mode"] == [mode] and query["oobCode"] == ["code&extra=bad"]
    if kind == "verify":
        continuation = urlsplit(query["continueUrl"][0])
        assert continuation.netloc == parts.netloc
        assert continuation.path == "/verify-email"
        assert parse_qs(continuation.query) == {"next": ["/sessions?new=1"]}
    else:
        assert "continueUrl" not in query


def test_unknown_reset_account_and_safe_sdk_failures():
    from onolys_api.adapters.real import FirebaseAuthLinks

    class UserNotFoundError(Exception):
        pass

    sdk = SimpleNamespace(
        ActionCodeSettings=lambda **kwargs: SimpleNamespace(**kwargs),
        UserNotFoundError=UserNotFoundError,
        generate_password_reset_link=Mock(side_effect=UserNotFoundError("private email")),
    )
    links = FirebaseAuthLinks("project", "https://app.onolys.com", auth_sdk=sdk)
    assert links.password_reset("person@example.com") is None
    sdk.generate_password_reset_link.side_effect = RuntimeError("private email")
    with pytest.raises(AdapterError, match="^auth_links_failed$"):
        links.password_reset("person@example.com")


@pytest.mark.parametrize("name", ["EmailNotFoundError", "UserNotFoundError", "UserDisabledError"])
def test_real_sdk_ineligible_account_errors_mean_no_send(name):
    from firebase_admin import auth

    from onolys_api.adapters.real import FirebaseAuthLinks

    exc = getattr(auth, name)("private email")  # real SDK classes, constructed as the SDK does
    sdk = SimpleNamespace(
        ActionCodeSettings=lambda **kwargs: SimpleNamespace(**kwargs),
        EmailNotFoundError=auth.EmailNotFoundError,
        UserNotFoundError=auth.UserNotFoundError,
        UserDisabledError=auth.UserDisabledError,
        generate_password_reset_link=Mock(side_effect=exc),
    )
    links = FirebaseAuthLinks("project", "https://app.onolys.com", auth_sdk=sdk)
    assert links.password_reset("person@example.com") is None


def test_missing_sdk_code_is_safe_failure():
    from onolys_api.adapters.real import FirebaseAuthLinks

    sdk = SimpleNamespace(
        ActionCodeSettings=lambda **kwargs: SimpleNamespace(**kwargs),
        generate_password_reset_link=Mock(return_value="https://evil.example/?apiKey=secret"),
    )
    with pytest.raises(AdapterError, match="^auth_links_failed$"):
        FirebaseAuthLinks("project", "https://app.onolys.com", auth_sdk=sdk).password_reset(
            "person@example.com"
        )


def test_fake_links_never_use_network():
    from onolys_api.adapters import build_auth_links
    from onolys_api.adapters.fake import FakeAuthLinks

    links = build_auth_links(Settings())
    assert isinstance(links, FakeAuthLinks)
    assert links.password_reset("unknown@example.com") is None


def test_admin_sdk_initializes_lazily_once_per_project(monkeypatch):
    import firebase_admin
    from firebase_admin import auth

    from onolys_api.adapters.real import FirebaseAuthLinks

    apps = {}

    def get_app(name):
        if name not in apps:
            raise ValueError("not initialized")
        return apps[name]

    def initialize_app(*, options, name):
        apps[name] = object()
        return apps[name]

    initialize = Mock(side_effect=initialize_app)
    monkeypatch.setattr(firebase_admin, "get_app", get_app)
    monkeypatch.setattr(firebase_admin, "initialize_app", initialize)
    monkeypatch.setattr(
        auth,
        "generate_password_reset_link",
        lambda *args, **kwargs: "https://sdk.example/?oobCode=code",
    )
    links = [FirebaseAuthLinks("project", "https://app.onolys.com") for _ in range(2)]
    assert initialize.call_count == 0
    assert [link.password_reset("person@example.com") for link in links] == ["code", "code"]
    assert initialize.call_count == 1
