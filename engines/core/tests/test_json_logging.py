"""Task 3: one JSON shape for our code, miti, LiteLLM and other libraries (02-logging R3-R5)."""

import json
import logging
from types import SimpleNamespace

import pytest

from onolys_engine_core.json_logging import JsonFormatter, configure_logging
from onolys_engine_core.log_context import log_context
from onolys_engine_core.safe_log import log_event

pytestmark = pytest.mark.unit

NAMES = ("miti", "onolys_api.events", "litellm", "LiteLLM", "LiteLLM Router", "LiteLLM Proxy",
         "httpx", "somelib")  # fmt: skip


@pytest.fixture
def cfg(capsys, monkeypatch):
    monkeypatch.delenv("K_REVISION", raising=False)
    root = logging.getLogger()
    saved_root = (list(root.handlers), root.level)
    saved = {n: (list(logging.getLogger(n).handlers), logging.getLogger(n).level,
                 logging.getLogger(n).propagate) for n in NAMES}  # fmt: skip
    configure_logging(SimpleNamespace(git_sha="abc123"))
    capsys.readouterr()

    def lines():
        err = capsys.readouterr().err
        return [json.loads(x) for x in err.splitlines() if x]

    yield lines
    root.handlers[:], root.level = saved_root
    for n, (h, lvl, p) in saved.items():
        lg = logging.getLogger(n)
        lg.handlers[:], lg.level, lg.propagate = h, lvl, p


def test_every_line_is_single_line_json_and_hostile_text_cannot_forge(cfg):
    logging.getLogger("somelib").warning('a\r\n{"severity": "FORGED"}\nline2 x')
    log_event("ev", request_id="r\r\nforged")
    out = cfg()
    assert len(out) == 2
    assert out[0]["severity"] == "WARNING" and out[0]["logger"] == "somelib"
    assert "\n" not in out[0]["message"] and "\r" not in out[0]["message"]
    assert out[1]["request_id"] == "r\r\nforged"[:200] and out[1]["event"] == "ev"


def test_miti_info_emitted_once_with_context_and_code_version(cfg):
    with log_context(session_id="s1", run_id="r1", step="rate"):
        log_event("hello", calls=2)
    (d,) = cfg()
    assert d["severity"] == "INFO" and d["message"] == d["event"] == "hello"
    assert d["session_id"] == "s1" and d["run_id"] == "r1" and d["step"] == "rate"
    assert d["calls"] == 2 and d["code_version"] == "abc123"


def test_litellm_warning_kept_debug_dropped_no_duplicates(cfg):
    import litellm

    assert litellm.suppress_debug_info is True
    for name in ("LiteLLM", "LiteLLM Router", "LiteLLM Proxy", "litellm"):
        lg = logging.getLogger(name)
        lg.debug("dbg %s", name)
        lg.info("inf %s", name)
        lg.warning("warn %s", name)
    out = cfg()
    assert [d["message"] for d in out] == [
        "warn LiteLLM",
        "warn LiteLLM Router",
        "warn LiteLLM Proxy",
        "warn litellm",
    ]
    assert {d["logger"] for d in out} == {"LiteLLM", "LiteLLM Router", "LiteLLM Proxy", "litellm"}


def test_httpx_and_third_party_below_info_dropped_info_kept_capped(cfg):
    logging.getLogger("httpx").debug("x")
    logging.getLogger("somelib").info("y" * 1000)
    (d,) = cfg()
    assert d["logger"] == "somelib" and len(d["message"]) == 300


def test_configure_twice_does_not_duplicate(cfg):
    configure_logging(SimpleNamespace(git_sha="abc123"))
    log_event("once")
    assert len(cfg()) == 1


def test_explicit_field_beats_context(cfg):
    with log_context(session_id="from-ctx", step="a"):
        log_event("ev", session_id="explicit")
    (d,) = cfg()
    assert d["session_id"] == "explicit" and d["step"] == "a"


def test_revision_present_when_k_revision_set_absent_otherwise(cfg, monkeypatch):
    log_event("a")
    assert "revision" not in cfg()[0]
    monkeypatch.setenv("K_REVISION", "api-00042-abc")
    log_event("b")
    assert cfg()[0]["revision"] == "api-00042-abc"


def test_exception_reduced_to_class_name_for_all_loggers(cfg):
    for name in ("somelib", "miti"):
        try:
            raise ValueError("SENTINEL-EXC-TEXT")
        except ValueError:
            logging.getLogger(name).exception("failed")
    out = cfg()
    assert [d["exc_class"] for d in out] == ["ValueError", "ValueError"]
    assert "SENTINEL" not in json.dumps(out) and "Traceback" not in json.dumps(out)


def test_non_allowlisted_fields_dropped_by_formatter():
    rec = logging.LogRecord("miti", logging.INFO, "f", 1, "ev", None, None)
    rec.fields = {"request_id": "r", "transcript": "SECRET", "surprise": "S2"}
    d = json.loads(JsonFormatter("v").format(rec))
    assert d["request_id"] == "r" and "SECRET" not in json.dumps(d) and "surprise" not in d


def test_litellm_log_env_not_left_set(monkeypatch):
    monkeypatch.setenv("LITELLM_LOG", "DEBUG")
    root = logging.getLogger()
    before = list(root.handlers)
    try:
        configure_logging(SimpleNamespace(git_sha="x"))
        import os

        assert "LITELLM_LOG" not in os.environ
    finally:
        root.handlers[:] = before
