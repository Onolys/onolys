from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests

from onolys_api.adapters.base import AdapterError
from onolys_api.config import Settings

pytestmark = pytest.mark.unit


def test_sender_selection_and_fake_recording():
    from onolys_api.adapters import build_email_sender
    from onolys_api.adapters.fake import FakeEmailSender
    from onolys_api.adapters.real import ResendEmailSender, UnconfiguredEmailSender

    fake = build_email_sender(Settings())
    assert isinstance(fake, FakeEmailSender)
    fake.send("person@example.com", "subject", "<p>body</p>", "body")
    assert fake.messages == [
        {"to": "person@example.com", "subject": "subject", "html": "<p>body</p>", "text": "body"}
    ]
    assert isinstance(build_email_sender(Settings(adapters="real")), UnconfiguredEmailSender)
    assert isinstance(
        build_email_sender(Settings(adapters="real", resend_api_key="key")), ResendEmailSender
    )


def test_unconfigured_sender():
    from onolys_api.adapters.real import UnconfiguredEmailSender

    with pytest.raises(AdapterError, match="^email_unconfigured$"):
        UnconfiguredEmailSender().send("person@example.com", "subject", "html", "text")


def test_resend_sends_idempotency_key_header(monkeypatch):
    from onolys_api.adapters.real import ResendEmailSender

    post = Mock(return_value=SimpleNamespace(status_code=202))
    monkeypatch.setattr(requests, "post", post)
    ResendEmailSender("key", "sender").send(
        "person@example.com", "subject", "html", "text", idempotency_key="reset-abc-7"
    )
    assert post.call_args.kwargs["headers"] == {
        "Authorization": "Bearer key",
        "Idempotency-Key": "reset-abc-7",
    }


def test_fake_records_idempotency_key():
    from onolys_api.adapters.fake import FakeEmailSender

    fake = FakeEmailSender()
    fake.send("a@example.com", "s", "h", "t", idempotency_key="k1")
    assert fake.messages[0]["idempotency_key"] == "k1"


def test_resend_request_shape(monkeypatch):
    from onolys_api.adapters.real import ResendEmailSender

    post = Mock(return_value=SimpleNamespace(status_code=202))
    monkeypatch.setattr(requests, "post", post)
    ResendEmailSender("key", "Onolys <no-reply@onolys.com>").send(
        "person@example.com", "subject", "html", "text"
    )
    post.assert_called_once_with(
        "https://api.resend.com/emails",
        headers={"Authorization": "Bearer key"},
        json={
            "from": "Onolys <no-reply@onolys.com>",
            "to": ["person@example.com"],
            "subject": "subject",
            "html": "html",
            "text": "text",
        },
        timeout=5,
        allow_redirects=False,
    )


@pytest.mark.parametrize(
    "response",
    [
        requests.Timeout("person@example.com secret"),
        SimpleNamespace(status_code=400, text="person@example.com secret"),
        SimpleNamespace(status_code=503, text="person@example.com secret"),
    ],
)
def test_resend_errors_are_safe(monkeypatch, response):
    from onolys_api.adapters.real import ResendEmailSender

    post = (
        Mock(side_effect=response)
        if isinstance(response, Exception)
        else Mock(return_value=response)
    )
    monkeypatch.setattr(requests, "post", post)
    with pytest.raises(AdapterError) as caught:
        ResendEmailSender("key", "sender").send("person@example.com", "subject", "html", "text")
    assert caught.value.code == "email_send_failed"
    assert "person@example.com" not in str(caught.value)
    assert "secret" not in str(caught.value)
    assert caught.value.__cause__ is None
    post.assert_called_once()
