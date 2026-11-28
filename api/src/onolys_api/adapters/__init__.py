"""Engine adapters: the only seam to the engines. `ADAPTERS=stub|real`."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from onolys_miti.stt.fixture import FixtureStt

from onolys_api.adapters.base import (
    AdapterError,
    AuthLinks,
    EmailSender,
    Evaluation,
    EvaluationOutput,
    ProgressCb,
    Stage,
    StageStatus,
    Stt,
    Voice,
)
from onolys_api.adapters.fake import (
    FakeAuthLinks,
    FakeEmailSender,
    FakeEvaluation,
    FakeStt,
    FakeVoice,
)
from onolys_api.config import Settings

__all__ = [
    "AuthLinks", "FakeAuthLinks", "build_auth_links",
    "EmailSender", "FakeEmailSender", "build_email_sender",
    "AdapterError", "Adapters", "Evaluation", "EvaluationOutput", "FakeEvaluation", "FakeStt",
    "FakeVoice", "FixtureStt", "ProgressCb", "Stage", "StageStatus", "Stt", "Voice",
    "build_adapters",
    "build_voice_adapter",
]  # fmt: skip


@dataclass(frozen=True)
class Adapters:
    stt: Stt
    evaluation: Evaluation
    voice: Voice = field(default_factory=FakeVoice)


def build_adapters(
    settings: Settings,
    *,
    stt_registry: Mapping[str, Callable[[], Any]] | None = None,
    llm_factory: Callable[[dict], Any] | None = None,
) -> Adapters:
    """`ADAPTERS=stub` -> fakes; `real` -> the real engine adapters. The keyword hooks (a provider
    registry, an LLM client factory) let tests run the real wiring with fixture STT/LLM."""
    if settings.adapters == "stub":
        return Adapters(stt=FakeStt(), evaluation=FakeEvaluation(), voice=FakeVoice())
    from onolys_api.adapters.real import RealEvaluation, RealStt, RealVoice

    evaluation = (
        RealEvaluation(settings, llm_factory=llm_factory)
        if llm_factory else RealEvaluation(settings)
    )
    return Adapters(stt=RealStt(stt_registry), evaluation=evaluation, voice=RealVoice())


def build_voice_adapter(settings: Settings) -> Voice:
    """The voice service needs only `Voice` (no STT or evaluation wiring)."""
    if settings.adapters == "stub":
        return FakeVoice()
    from onolys_api.adapters.real import RealVoice

    return RealVoice()


def build_email_sender(settings: Settings) -> EmailSender:
    if settings.adapters == "stub":
        return FakeEmailSender()
    from onolys_api.adapters.real import ResendEmailSender, UnconfiguredEmailSender

    if not settings.resend_api_key:
        return UnconfiguredEmailSender()
    return ResendEmailSender(settings.resend_api_key, settings.email_from)


def build_auth_links(settings: Settings) -> AuthLinks:
    if settings.adapters == "stub":
        return FakeAuthLinks()
    from onolys_api.adapters.real import FirebaseAuthLinks

    return FirebaseAuthLinks(settings.auth_project or settings.gcp_project, settings.app_base_url)
