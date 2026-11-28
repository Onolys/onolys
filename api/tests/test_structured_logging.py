"""One Cloud Logging JSON shape for our code, the engine, LiteLLM and other libraries.

`logs.configure` installs google-cloud-logging's `StructuredLogHandler` on the root logger with
the PHI `logging.Filter`; the assertions read the JSON lines that reach stderr. The alert filter
(`jsonPayload.status="failed"`) and the runbook (`jsonPayload.request_id`) read top-level keys.
"""

import asyncio
import json
import logging
import subprocess
import sys
from types import SimpleNamespace

import pytest
from onolys_engine_core.safe_log import LOG_FIELDS, log_event

from onolys_api import logs

pytestmark = pytest.mark.unit

NAMES = ("miti", "onolys_api.events", "litellm", "LiteLLM", "LiteLLM Router", "LiteLLM Proxy",
         "httpx", "somelib")  # fmt: skip
SENTINEL = "SENTINEL-PHI-4417"


@pytest.fixture
def cfg(capsys, monkeypatch):
    monkeypatch.delenv("K_REVISION", raising=False)
    root = logging.getLogger()
    saved_root = (list(root.handlers), root.level)
    saved = {n: (list(logging.getLogger(n).handlers), logging.getLogger(n).level,
                 logging.getLogger(n).propagate) for n in NAMES}  # fmt: skip
    logs.configure(SimpleNamespace(git_sha="abc123", uid_hmac_key="k"))
    capsys.readouterr()

    def lines():
        err = capsys.readouterr().err
        return [json.loads(x) for x in err.splitlines() if x]

    yield lines
    root.handlers[:], root.level = saved_root
    for n, (h, lvl, p) in saved.items():
        lg = logging.getLogger(n)
        lg.handlers[:], lg.level, lg.propagate = h, lvl, p


# ---- the alert fields ----


def test_failed_line_has_top_level_status_failed_and_request_id(cfg):
    logs.failed(
        "run_failed", session_id="s1", run_id="r1", step="run", error_code="llm_failed",
        exc_class="LLMError", request_id="rq-7",
    )
    (d,) = cfg()
    # Cloud Logging exposes these as jsonPayload.status / jsonPayload.request_id
    assert d["status"] == "failed" and d["request_id"] == "rq-7"
    assert d["severity"] == "ERROR" and d["message"] == d["event"] == "run_failed"
    assert d["session_id"] == "s1" and d["run_id"] == "r1" and d["code_version"] == "abc123"


def test_request_id_comes_from_the_bound_context_when_not_explicit(cfg):
    with logs.log_context(request_id="rq-ctx", session_id="s1"):
        logs.emit("probe", status="failed")
    (d,) = cfg()
    assert d["status"] == "failed" and d["request_id"] == "rq-ctx" and d["session_id"] == "s1"


def test_engine_log_event_status_and_request_id_pass_through_unchanged(cfg):
    log_event("miti.done", logging.ERROR, request_id="rq-8", status="failed", runs_ok=0)
    (d,) = cfg()
    assert d["status"] == "failed" and d["request_id"] == "rq-8" and d["runs_ok"] == 0
    assert d["severity"] == "ERROR" and d["event"] == "miti.done"


def test_allowlist_is_the_engine_fields_plus_the_api_ones():
    assert LOG_FIELDS <= logs.ALLOWED_FIELDS and logs.API_FIELDS <= logs.ALLOWED_FIELDS
    assert {"status", "request_id"} <= LOG_FIELDS and {"status", "request_id"} <= logs.API_FIELDS


# ---- the PHI filter ----


def test_phi_filter_drops_text_like_and_unknown_fields_and_caps_values(cfg):
    log_event(
        "ev", request_id="r" * 500, transcript=SENTINEL, text=SENTINEL, surprise=SENTINEL,
        audio_uri=SENTINEL, calls=2, provider_error="e" * 500,
    )
    (d,) = cfg()
    assert SENTINEL not in json.dumps(d)
    assert len(d["request_id"]) == logs.MAX_VALUE_CHARS and len(d["provider_error"]) == 300
    assert d["calls"] == 2


def test_phi_filter_still_redacts_with_the_handler_installed(cfg):
    logs.emit("probe", session_id="s1", transcript=SENTINEL, surprise=SENTINEL, status="ok")
    out = cfg()
    assert SENTINEL not in json.dumps(out) and out[0]["session_id"] == "s1"


def test_dict_messages_and_json_looking_messages_cannot_inject_keys(cfg):
    logging.getLogger("miti").info({"status": "failed", "transcript": SENTINEL})
    logging.getLogger("miti").info('{"status": "failed", "request_id": "forged"}')
    out = cfg()
    assert SENTINEL not in json.dumps(out)
    assert all(d.get("status") != "failed" and d.get("request_id") != "forged" for d in out)


def test_every_line_is_single_line_json_and_hostile_text_cannot_forge(cfg):
    logging.getLogger("somelib").warning('a\r\n{"severity": "FORGED"}\nline2 x')
    log_event("ev", request_id="r\r\nforged")
    out = cfg()
    assert len(out) == 2
    assert out[0]["severity"] == "WARNING" and out[0]["logger"] == "somelib"
    assert "\n" not in out[0]["message"] and "\r" not in out[0]["message"]
    assert out[1]["request_id"] == "r\r\nforged"[:200] and out[1]["event"] == "ev"


def test_exception_reduced_to_class_name_for_all_loggers(cfg):
    for name in ("somelib", "miti", "google_genai.x"):
        try:
            raise ValueError("SENTINEL-EXC-TEXT")
        except ValueError:
            logging.getLogger(name).exception("boom %s", "SECRET-ARG")
    out = cfg()
    assert [d["exc_class"] for d in out] == ["ValueError"] * 3
    raw = json.dumps(out)
    assert "SENTINEL" not in raw and "SECRET-ARG" not in raw and "Traceback" not in raw


def test_message_is_one_line_and_capped(cfg):
    logging.getLogger("miti").info("y" * 1000)
    (d,) = cfg()
    assert d["logger"] == "miti" and len(d["message"]) == logs.MAX_MESSAGE_CHARS


def test_filter_is_safe_to_run_twice_on_one_record():
    rec = logging.LogRecord("miti", logging.INFO, "f", 1, "ev", None, None)
    rec.fields = {"request_id": "r", "calls": 1}
    f = logs.PhiFilter("v")
    assert f.filter(rec) and f.filter(rec)
    assert rec.json_fields == {"event": "ev", "request_id": "r", "calls": 1, "code_version": "v"}


# ---- shape, levels, configure ----


def test_info_line_has_event_context_and_code_version(cfg):
    with logs.log_context(session_id="s1", run_id="r1", step="rate"):
        log_event("hello", calls=2)
    (d,) = cfg()
    assert d["severity"] == "INFO" and d["message"] == d["event"] == "hello"
    assert d["session_id"] == "s1" and d["run_id"] == "r1" and d["step"] == "rate"
    assert d["calls"] == 2 and d["code_version"] == "abc123"


def test_explicit_field_beats_context(cfg):
    with logs.log_context(session_id="from-ctx", step="a"):
        log_event("ev", session_id="explicit")
    (d,) = cfg()
    assert d["session_id"] == "explicit" and d["step"] == "a"


def test_litellm_warning_kept_debug_dropped_no_duplicates(cfg):
    import litellm
    from onolys_engine_core.llm.quiet import quiet_litellm

    quiet_litellm()  # what the lazy-import sites do right after `import litellm`
    for name in ("LiteLLM", "LiteLLM Router", "LiteLLM Proxy", "litellm"):
        lg = logging.getLogger(name)
        lg.debug("dbg %s", name)
        lg.info("inf %s", name)
        lg.warning("warn %s", name)
    out = cfg()
    assert litellm.suppress_debug_info is True
    assert [d["message"] for d in out] == [
        "warn LiteLLM", "warn LiteLLM Router", "warn LiteLLM Proxy", "warn litellm",
    ]


def test_third_party_info_dropped_warning_kept_first_party_info_kept(cfg):
    for name in ("google_genai.models", "httpx", "httpcore", "somelib"):
        logging.getLogger(name).info("i-%s", name)
        logging.getLogger(name).warning("w-%s", name)
    for name in ("onolys_api.routes.x", "onolys_engine_core.llm", "onolys_miti.run", "miti.x"):
        logging.getLogger(name).info("first-%s", name)
    msgs = [d["message"] for d in cfg()]
    assert not [m for m in msgs if m.startswith("i-")]
    assert {f"w-{n}" for n in ("google_genai.models", "httpx", "httpcore", "somelib")} <= set(msgs)
    assert len([m for m in msgs if m.startswith("first-")]) == 4


def test_configure_twice_does_not_duplicate(cfg):
    logs.configure(SimpleNamespace(git_sha="abc123", uid_hmac_key="k"))
    log_event("once")
    assert len(cfg()) == 1


def test_revision_present_when_k_revision_set_absent_otherwise(cfg, monkeypatch):
    log_event("a")
    assert "revision" not in cfg()[0]
    monkeypatch.setenv("K_REVISION", "api-00042-abc")
    log_event("b")
    assert cfg()[0]["revision"] == "api-00042-abc"


def test_litellm_log_env_not_left_set(monkeypatch):
    monkeypatch.setenv("LITELLM_LOG", "DEBUG")
    root = logging.getLogger()
    before = list(root.handlers)
    try:
        logs.configure(SimpleNamespace(git_sha="x", uid_hmac_key="k"))
        import os

        assert "LITELLM_LOG" not in os.environ
    finally:
        root.handlers[:] = before


def test_configure_does_not_import_litellm():
    code = (
        "import sys\nfrom types import SimpleNamespace\nfrom onolys_api import logs\n"
        "logs.configure(SimpleNamespace(git_sha='x', uid_hmac_key='k'))\n"
        "print('litellm' in sys.modules)"
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "False"


# ---- bound log ids ----


def test_bind_reset_restores_prior():
    t1 = logs.bind(session_id="s1", step="a")
    t2 = logs.bind(session_id="s2")
    assert logs.snapshot() == {"session_id": "s2", "step": "a"}
    logs.reset(t2)
    assert logs.snapshot() == {"session_id": "s1", "step": "a"}
    logs.reset(t1)
    assert logs.snapshot() == {}


def test_nested_overrides_only_given_keys_and_no_leak_after_exception():
    with logs.log_context(session_id="s", run_id="r", step="x"):
        with logs.log_context(step="y"):
            assert logs.snapshot() == {"session_id": "s", "run_id": "r", "step": "y"}
        assert logs.snapshot() == {"session_id": "s", "run_id": "r", "step": "x"}
    assert logs.snapshot() == {}
    with pytest.raises(RuntimeError), logs.log_context(request_id="q"):
        raise RuntimeError
    assert logs.snapshot() == {}


def test_snapshot_omits_none_and_unknown_keys_are_rejected():
    with logs.log_context(session_id="s", run_id=None):
        assert logs.snapshot() == {"session_id": "s"}
    with pytest.raises(ValueError):
        logs.bind(bogus="x")


def test_ids_survive_asyncio_run_and_to_thread():
    async def inner():
        return logs.snapshot(), await asyncio.to_thread(logs.snapshot)

    with logs.log_context(session_id="s", step="z"):
        a, b = asyncio.run(inner())
    assert a == b == {"session_id": "s", "step": "z"}
