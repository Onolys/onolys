from urllib.parse import parse_qs, urlsplit

import pytest

from onolys_api.adapters.base import AuthAccount
from onolys_api.adapters.fake import FakeAuthLinks, FakeEmailSender
from onolys_api.config import Settings

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("kind,subject", [("verify", "Verify your email for Onolys"), ("reset", "Reset your Onolys password")])
def test_templates_render_html_and_text_with_only_link_interpolation(kind, subject):
    from onolys_api.email.service import render_email

    link = 'https://app.onolys.com/auth/action?oobCode=secret&next="<tag>"'
    rendered = render_email(kind, link)
    assert rendered.subject == subject
    assert 'href="https://app.onolys.com/auth/action?oobCode=secret&amp;next=&quot;&lt;tag&gt;&quot;"' in rendered.html
    assert rendered.html.count('href=') == 1
    assert link in rendered.text
    for content in (rendered.html, rendered.text):
        assert "single-use" in content
        assert "ignore" in content.lower()


@pytest.mark.parametrize("kind,mode", [("verify", "verifyEmail"), ("reset", "resetPassword")])
def test_service_sends_trusted_recipient_and_app_host(kind, mode):
    from onolys_api.email.service import AuthEmailService

    sender = FakeEmailSender()
    links = FakeAuthLinks({"uid": AuthAccount("person@example.com")})
    service = AuthEmailService(Settings(app_base_url="https://onolys-app-staging.web.app", email_from="Onolys <no-reply@onolys.com>"), links, sender)
    sent = service.send_verification("uid", next_path="/sessions") if kind == "verify" else service.send_password_reset("person@example.com")
    assert sent is True
    (message,) = sender.messages
    assert message["to"] == "person@example.com"
    url = next(line for line in message["text"].splitlines() if line.startswith("https://"))
    assert urlsplit(url).netloc == "onolys-app-staging.web.app"
    assert parse_qs(urlsplit(url).query)["mode"] == [mode]
    assert url.replace("&", "&amp;") in message["html"]


def test_password_reset_passes_idempotency_key_to_sender():
    from onolys_api.email.service import AuthEmailService

    sender = FakeEmailSender()
    links = FakeAuthLinks({"uid": AuthAccount("person@example.com")})
    service = AuthEmailService(Settings(app_base_url="https://app.example.com"), links, sender)
    assert service.send_password_reset("person@example.com", idempotency_key="reset-k-1") is True
    assert sender.messages[0]["idempotency_key"] == "reset-k-1"


def test_service_skips_verified_and_unknown_accounts():
    from onolys_api.email.service import AuthEmailService

    sender = FakeEmailSender()
    links = FakeAuthLinks({"uid": AuthAccount("person@example.com", email_verified=True)})
    service = AuthEmailService(Settings(), links, sender)
    assert service.send_verification("uid") is False
    assert service.send_password_reset("unknown@example.com") is False
    assert sender.messages == []
    assert links.codes == []
