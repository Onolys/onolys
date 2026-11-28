import logging

import pytest

from onolys_engine_core.json_logging import render
from onolys_engine_core.safe_log import ALLOWED_FIELDS, MAX_VALUE_CHARS, log_event, register_fields

pytestmark = pytest.mark.unit

SENTINEL = "ZZ-SENTINEL-PHI-ZZ"
URI = "gs://secret-bucket/patient-0042.flac"


def _log(caplog, **fields):
    """Formatted JSON lines of the emitted records."""
    with caplog.at_level(logging.INFO, logger="miti"):
        caplog.clear()
        log_event("ev", **fields)
    return "\n".join(render(r) for r in caplog.records)


@pytest.mark.parametrize(
    "name", ["text", "body", "transcript", "excerpt", "message", "turn_text", "error_message"]
)
def test_blocked_parts_dropped_even_if_registered(caplog, name):
    register_fields(frozenset({name}))
    try:
        assert SENTINEL not in _log(caplog, **{name: SENTINEL})
    finally:
        ALLOWED_FIELDS.discard(name)


def test_unknown_field_dropped_and_audio_uri_not_loggable(caplog):
    out = _log(caplog, surprise=SENTINEL, audio_uri=URI, uri=URI, rating=5)
    assert SENTINEL not in out and URI not in out and "rating" not in out


def test_new_generic_fields_allowed(caplog):
    out = _log(
        caplog,
        audio_ms=1200,
        stt_provider="fixture",
        stt_model="m",
        language="en",
        speakers=2,
        job_id="j1",
        step="submit",
    )
    for s in (
        '"audio_ms": 1200',
        '"stt_provider": "fixture"',
        '"stt_model": "m"',
        '"language": "en"',
        '"speakers": 2',
        '"job_id": "j1"',
        '"step": "submit"',
    ):
        assert s in out


def test_register_fields_adds_engine_field(caplog):
    register_fields(frozenset({"zz_engine_field"}))
    try:
        assert '"zz_engine_field": 3' in _log(caplog, zz_engine_field=3)
    finally:
        ALLOWED_FIELDS.discard("zz_engine_field")


def test_value_cap_and_escaping(caplog):
    out = _log(caplog, request_id="a" * 500 + "\nforged=1")
    assert "a" * MAX_VALUE_CHARS in out and "a" * (MAX_VALUE_CHARS + 1) not in out
    assert "\nforged" not in out  # json.dumps escapes the newline in the rendered view


# --- JSON fields, caps, sanitizer ---------------------------------

from onolys_engine_core.safe_log import (  # noqa: E402
    FIELD_CAPS,
    clean_value,
    safe_fields,
    sanitize_provider_text,
)


def _record(caplog, **fields):
    with caplog.at_level(logging.INFO, logger="miti"):
        caplog.clear()
        log_event("ev", **fields)
    assert len(caplog.records) == 1
    return caplog.records[0]


def test_log_event_attaches_fields_as_extra_not_text(caplog):
    rec = _record(caplog, request_id="r1", calls=3, surprise="x")
    assert rec.fields == {"request_id": "r1", "calls": 3}
    assert rec.getMessage() == "ev"


def test_new_allowlist_names_kept(caplog):
    names = (
        "provider model http_status error_type provider_error interview_id uploaded_s "
        "relay_s diff_s threshold_s result code_version revision relay_version "
        "relay_revision web_version user_agent recorder_mime audio_engine audio_format "
        "audio_codec audio_streams"
    ).split()
    for n in names:
        assert n in ALLOWED_FIELDS, n
    assert set(safe_fields({n: 1 for n in names})) == set(names)


def test_message_dropped_but_provider_error_kept(caplog):
    rec = _record(caplog, message=SENTINEL, provider_error="boom", error_type="X")
    assert "message" not in rec.fields
    assert rec.fields["provider_error"] == "boom"


def test_per_field_cap():
    assert FIELD_CAPS == {"provider_error": 300}
    assert len(clean_value("provider_error", "a" * 500)) == 300
    assert len(clean_value("request_id", "a" * 500)) == MAX_VALUE_CHARS
    assert clean_value("calls", 4) == 4


def test_log_event_applies_caps(caplog):
    rec = _record(caplog, provider_error="a" * 500, request_id="b" * 500)
    assert len(rec.fields["provider_error"]) == 300
    assert len(rec.fields["request_id"]) == MAX_VALUE_CHARS


def test_sanitize_quotes_backticks_multiline_truncation():
    long = "x" * 25
    s = f'bad "{long}" and \'{long}\' and `{long}` ok "short"\nsecond line "leak"'
    out = sanitize_provider_text(s)
    assert out.count('"<redacted>"') == 3
    assert long not in out and "second line" not in out and '"short"' in out
    assert len(sanitize_provider_text("e" * 1000)) == 300


def test_sanitize_credentials_and_echo_markers():
    out = sanitize_provider_text(
        "401 Bearer abc.DEF-123 at https://x/y?key=AIzaSECRET&api_key=zzz1 sk-ant-abcdef123456"
    )
    for leak in ("abc.DEF-123", "AIzaSECRET", "zzz1", "sk-ant-abcdef123456"):
        assert leak not in out
    out = sanitize_provider_text("BadRequest Received Messages=[{'role': 'user', 'c': 'PHI'}]")
    assert out.startswith("BadRequest") and "PHI" not in out and "Received Messages" not in out
    out = sanitize_provider_text("litellm.BadRequestError: Invalid Message passed in {PHI}")
    assert "PHI" not in out and "BadRequestError" in out
