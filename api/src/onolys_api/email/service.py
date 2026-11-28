"""Render and send auth emails; the only interpolated value is the action link."""

from dataclasses import dataclass
from html import escape
from importlib.resources import files
from string import Template

from onolys_api.adapters.base import AdapterError, AuthAccount, AuthLinks, EmailSender
from onolys_api.config import Settings
from onolys_api.email.links import EmailKind, build_action_link

SUBJECTS: dict[EmailKind, str] = {
    "verify": "Verify your email for Onolys",
    "reset": "Reset your Onolys password",
}


@dataclass(frozen=True)
class RenderedEmail:
    subject: str
    html: str
    text: str


def _template(name: str) -> Template:
    return Template(files("onolys_api.email").joinpath("templates", name).read_text("utf-8"))


def render_email(kind: EmailKind, link: str) -> RenderedEmail:
    return RenderedEmail(
        subject=SUBJECTS[kind],
        html=_template(f"{kind}.html.tmpl").substitute(link=escape(link, quote=True)),
        text=_template(f"{kind}.txt.tmpl").substitute(link=link),
    )


class AuthEmailService:
    def __init__(self, settings: Settings, links: AuthLinks, sender: EmailSender) -> None:
        self._settings = settings
        self._links = links
        self._sender = sender

    def _send(
        self,
        kind: EmailKind,
        to: str,
        code: str,
        next_path: str | None = None,
        idempotency_key: str | None = None,
    ) -> None:
        link = build_action_link(self._settings, kind, code, next_path=next_path)
        email = render_email(kind, link)
        if idempotency_key:
            self._sender.send(
                to, email.subject, email.html, email.text, idempotency_key=idempotency_key
            )
        else:
            self._sender.send(to, email.subject, email.html, email.text)

    def require_configured(self) -> None:
        if not self._settings.app_base_url:  # same path as a missing RESEND_API_KEY
            raise AdapterError("email_unconfigured")

    def get_account(self, uid: str) -> AuthAccount:
        return self._links.get_user(uid)

    def send_verification(
        self, uid: str, next_path: str | None = None, account: AuthAccount | None = None
    ) -> bool:
        """Send to the account's own address; False when already verified (nothing sent)."""
        self.require_configured()
        account = account or self._links.get_user(uid)
        if account.email_verified:
            return False
        self._send("verify", account.email, self._links.verification(uid), next_path)
        return True

    def send_password_reset(self, email: str, idempotency_key: str | None = None) -> bool:
        """False for unknown/disabled accounts (nothing sent). The key dedupes provider-side."""
        self.require_configured()
        code = self._links.password_reset(email)
        if code is None:
            return False
        self._send("reset", email, code, idempotency_key=idempotency_key)
        return True
