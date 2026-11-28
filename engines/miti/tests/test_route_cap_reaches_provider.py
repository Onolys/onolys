"""The route's output cap (not a hard-coded engine value) reaches litellm for every miti call."""

import asyncio
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from conftest import install_demo
from onolys_engine.llm import LiteLLMClient, LLMConfig, LLMError
from onolys_engine.llm.routes import load_registry, resolve_preset
from onolys_engine.transcript import Turn

from onolys_miti.code_pass import code_pass
from onolys_miti.globals_pass import globals_pass
from onolys_miti.prepare import Prepared, RoleTurn, Volley
from onolys_miti.tips import _build_request as tips_request

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[3]
STAGING = ROOT / "config/staging/routes.yaml"


class Recorder:
    """Stands in for the engine client: records the requests the passes build."""

    def __init__(self):
        self.requests = []

    async def complete_json(self, req, metrics=None):
        self.requests.append(req)
        raise LLMError("stop after recording")


def _prepared():
    turn = Turn(id="t1", speaker="A", text="You want to walk more.", start_ms=0, end_ms=500)
    prev = Turn(id="p1", speaker="B", text="client said something")
    return Prepared(
        turns=[RoleTurn(turn, "subject")],
        volleys=[Volley("v1", [turn], {"client_turns": [prev.text]})],
    )


def _requests(tmp_path, pack_data):
    tips = tips_request({}, None, 0, False)  # real MITI pack (no tips_max_tokens)
    pack_data["params"] = {}  # no pack override: engine defaults
    install_demo(tmp_path / "p", pack=pack_data)
    rec = Recorder()
    params = {"change_goal": "walk more"}
    for fn in (code_pass, globals_pass):
        with pytest.raises(Exception):  # noqa: B017 - the recorder aborts the pass
            asyncio.run(fn(rec, _prepared(), params))
    return [*rec.requests, tips]


def _kwargs_seen(routes, requests):
    seen = []

    async def acompletion(**kwargs):
        seen.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="{}"), finish_reason="stop")],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
        )

    async def no_sleep(_):
        return None

    client = LiteLLMClient(
        LLMConfig(llm_mode="live", routes=routes), acompletion=acompletion, sleep=no_sleep
    )
    for req in requests:
        with pytest.raises(LLMError):  # "{}" is not valid for the schema; kwargs are what we check
            asyncio.run(client.complete_json(replace(req, retry=False)))
    return seen


def test_default_routes_cap_is_route_cap(tmp_path, pack_data):
    routes, _ = resolve_preset("default", load_registry(STAGING, env={}), env={})
    reqs = _requests(tmp_path, pack_data)
    assert [r.tier for r in reqs] == ["miti_code", "miti_globals", "tips"]
    assert all(r.max_tokens is None for r in reqs)
    seen = _kwargs_seen(routes, reqs)
    assert [k["max_tokens"] for k in seen] == [64000, 64000, 64000]


def test_effort_high_cap_is_model_max(tmp_path, pack_data):
    env = {"LLM_EFFORT": "high", "MODELS_FILE": str(ROOT / "config/models.yaml")}
    registry = load_registry(STAGING, env=env)
    routes, _ = resolve_preset("default", registry, env=env)
    want = routes["mid"].max_output_tokens
    assert want >= 64000
    seen = _kwargs_seen(routes, _requests(tmp_path, pack_data))
    assert [k["max_tokens"] for k in seen] == [want, want, want]
    assert [k["reasoning_effort"] for k in seen] == ["high"] * 3
