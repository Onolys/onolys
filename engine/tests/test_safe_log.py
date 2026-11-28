import logging

import pytest

from onolys_engine.safe_log import LOG_FIELDS, log_event, sanitize_provider_text

pytestmark = pytest.mark.unit


def _record(caplog, **fields):
    with caplog.at_level(logging.INFO, logger="miti"):
        caplog.clear()
        log_event("ev", **fields)
    assert len(caplog.records) == 1
    return caplog.records[0]


def test_log_event_attaches_fields_as_extra_not_text(caplog):
    rec = _record(caplog, request_id="r1", calls=3)
    assert rec.fields == {"request_id": "r1", "calls": 3}
    assert rec.getMessage() == "ev"
    assert rec.name == "miti"


def test_log_event_level(caplog):
    with caplog.at_level(logging.INFO, logger="miti"):
        log_event("bad", logging.ERROR, status="failed")
    assert caplog.records[0].levelno == logging.ERROR


def test_log_fields_is_a_static_frozenset_without_text_like_names():
    assert isinstance(LOG_FIELDS, frozenset)
    assert {"request_id", "status", "provider_error", "run_index", "stage_status"} <= LOG_FIELDS
    blocked = ("text", "body", "transcript", "excerpt", "message")
    assert not [n for n in LOG_FIELDS if any(p in n for p in blocked)]


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
