"""Equivalence harness for the engine package refactor.

Captured once on the old packages, before any source change; the refactor must reproduce the
stored baselines. Throwaway: removed with the old packages when the new engine lands.

Per case it stores, under `tests/fixtures/equivalence/<case>.json`:
- `payloads`: every call the real `LiteLLMClient` sends to `litellm.acompletion` (patched, the only
  way to see the sent bytes without editing source), sorted by call tag. Each entry is the full
  kwargs (messages, response format and schema, params) plus the call tag.
- `warm_up`: which code calls started before / after the first code call returned.
- `report`: the full `run_miti` report with the volatile keys masked (test_golden.py's rule).
- `aggregate`: the aggregate over the runs, including `representative_run`.

Replies live in `tests/fixtures/equivalence/responses/<fixture>.json`, `{call_tag: response}` (the
`regen_goldens --responses` shape, run 0 tags). They come from `expected.yaml` (poor_practice,
batch_edge) or from the recorded good_practice goldens; later runs reuse the run 0 reply.

Regenerate (only ever on the old code): `python tests/_equivalence.py`.
"""

import asyncio
import contextvars
import importlib.util
import json
import re
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import litellm
import yaml
from onolys_engine_core.context import RunContext
from onolys_engine_core.llm import LiteLLMClient, LLMConfig, MetricsCollector
from onolys_engine_core.llm.fixture_client import FixtureClient
from onolys_engine_core.llm.routes import load_registry, resolve_preset
from onolys_engine_core.text_limits import QUOTE_MAX
from onolys_engine_core.transcript import Transcript

from onolys_miti import miti
from onolys_miti.run import run_miti

TESTS = Path(__file__).resolve().parent
MITI_ROOT = TESTS.parent
REPO = TESTS.parents[2]
OUT = TESTS / "fixtures" / "equivalence"
RESPONSES = OUT / "responses"
FIX = miti.DATA_DIR / "fixtures"
STAGING = REPO / "config" / "staging" / "routes.yaml"
REQUEST_ID = "req-equivalence"
SMAP = {"subject": "A", "other": "B"}

# case -> (fixture, n_runs)
CASES = {
    "good_practice": ("good_practice", 1),
    "good_practice_n3": ("good_practice", 3),
    "poor_practice": ("poor_practice", 1),
    "batch_edge": ("batch_edge", 1),
}
FIXTURES = ("good_practice", "poor_practice", "batch_edge")

# test_golden.py's mask: run provenance and environment, not coding output.
VOLATILE_TOP = ("created_at", "request_id", "run_info")
VOLATILE_HEADER = ("code_version", "params", "models", "preset", "stt")


def masked(report: dict) -> dict:
    out = {k: v for k, v in report.items() if k not in VOLATILE_TOP}
    out["header"] = {k: v for k, v in report["header"].items() if k not in VOLATILE_HEADER}
    return out


def _load_audit():
    spec = importlib.util.spec_from_file_location("audit_report", MITI_ROOT / "audit_report.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------- replies


def _tips_from_utterances(utterances: list[dict]) -> dict:
    """Up to three synthetic tips, one per distinct code; each quote is an expected utterance
    (an exact substring of its clinician turn). The wording is fixed template text."""
    tips, seen = [], set()
    for u in utterances:
        code = u["code"]
        if code is None or code in seen or len(u["quote"]) > QUOTE_MAX:
            continue
        seen.add(code)
        tips.append(
            {
                "title": f"Synthetic tip for {code}",
                "item_id": code,
                "observation": f"Synthetic fixture observation for {code}.",
                "quote": {"turn_id": u["turn_id"], "text": u["quote"]},
                "alternative": "Synthetic fixture alternative wording.",
                "why_it_matters": "Synthetic fixture reason.",
            }
        )
        if len(tips) == 3:
            break
    return {"tips": tips}


def _tip_request_tag() -> str:
    return "tips:r0"


def _code_responses(spec: dict, requests) -> dict[str, dict]:
    """One code reply per batch request: the expected utterances of the batch's volleys."""
    by_turn: dict[str, list[dict]] = {}
    for u in spec["utterances"]:
        by_turn.setdefault(u["turn_id"], []).append(u)
    out = {}
    for req in requests:
        if req.tier != "miti_code":
            continue
        volleys = []
        for v in json.loads(req.user)["volleys"]:
            utterances = [
                {
                    "quote": u["quote"],
                    "code": u["code"],
                    "rationale": u.get("rationale", "Hand-authored fixture"),
                }
                for t in v["clinician_turns"]
                for u in by_turn.get(t["turn_id"], [])
            ]
            volleys.append({"volley_id": v["volley_id"], "utterances": utterances})
        out[req.call_tag] = {"volleys": volleys}
    return out


def _globals_response(spec: dict) -> dict:
    return {
        "globals": {
            gid: {
                "score": g["score"],
                "reason": g["reason"],
                "evidence": [{"turn_id": e["turn_id"], "quote": e["quote"]} for e in g["evidence"]],
                "poor_practice_cited": [
                    {"turn_id": e["turn_id"], "quote": e["quote"]}
                    for e in g.get("poor_practice_cited", [])
                ],
            }
            for gid, g in spec["globals"].items()
        }
    }


def build_responses(fixture: str) -> dict[str, dict]:
    """`{call_tag: response}` for run 0 of `fixture`, from the recorded goldens (good_practice) or
    from `expected.yaml` (the others)."""
    audit = _load_audit()
    spec = yaml.safe_load((FIX / "expected.yaml").read_text("utf-8"))["fixtures"][fixture]
    transcript, params, prepared = audit.load_fixture(spec)
    requests = audit.render_requests(prepared, params, transcript.language)
    if fixture == "good_practice":
        gold = FIX / "golden" / "good_practice"
        out = {
            r.call_tag: json.loads((gold / f"{FixtureClient.key_for(r)}.json").read_text("utf-8"))
            for r in requests
        }
        report = json.loads((FIX / "evaluation" / "report_no_rating.json").read_text("utf-8"))
        tips = [
            {**{k: t[k] for k in ("title", "item_id", "observation", "alternative", "why_it_matters")
                if k in t},
             "quote": {"turn_id": t["quote"]["turn_id"], "text": t["quote"]["text"]}}
            for t in report["tips"]
        ]
        out[_tip_request_tag()] = {"tips": tips}
        return out
    out = _code_responses(spec, requests)
    glob = next(r for r in requests if r.tier == "miti_globals")
    out[glob.call_tag] = _globals_response(spec)
    out[_tip_request_tag()] = _tips_from_utterances(spec["utterances"])
    return out


def load_responses(fixture: str) -> dict[str, dict]:
    return json.loads((RESPONSES / f"{fixture}.json").read_text("utf-8"))


# ---------------------------------------------------------------- capture


_TAG: contextvars.ContextVar[str] = contextvars.ContextVar("call_tag", default="")


class BadRequestError(Exception):
    """Named like the provider error so the client does not retry it."""


class TaggingClient:
    """Thin wrapper over the real `LiteLLMClient`: only records the call tag of the request in
    flight, so the patched `litellm.acompletion` can answer by tag. The request is passed on
    unchanged."""

    def __init__(self, inner: LiteLLMClient) -> None:
        self._inner = inner
        self.routes = inner.routes

    async def complete_json(self, req, metrics=None):
        token = _TAG.set(req.call_tag)
        try:
            return await self._inner.complete_json(req, metrics)
        finally:
            _TAG.reset(token)


def _routes():
    registry = load_registry(STAGING, env={})
    return resolve_preset("default", registry, env={})[0]


def _run0_tag(tag: str) -> str:
    return re.sub(r":r\d+", ":r0", tag)


def _json_safe(value):
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _warm_up(events: list[tuple[str, str]]) -> dict:
    """Code calls that started before / after the first code call returned."""
    code = [(kind, tag) for kind, tag in events if tag.startswith("miti_code:")]
    started = [tag for kind, tag in code if kind == "start"]
    first = started[0]
    done = next(i for i, (kind, tag) in enumerate(code) if kind == "end" and tag == first)
    before = [t for kind, t in code[:done] if kind == "start" and t != first]
    after = [t for kind, t in code[done:] if kind == "start"]
    return {
        "first_code_call": first,
        "started_before_first_returned": sorted(before),
        "started_after_first_returned": sorted(after),
    }


@contextmanager
def _patched_acompletion(replies: dict[str, dict], calls: list, events: list):
    async def acompletion(**kwargs):
        tag = _TAG.get()
        events.append(("start", tag))
        await asyncio.sleep(0)
        try:
            reply = replies[_run0_tag(tag)]
        except KeyError:
            raise BadRequestError(f"no reply for call tag {tag}") from None
        calls.append({"call_tag": tag, **_json_safe(kwargs)})
        await asyncio.sleep(0)
        events.append(("end", tag))
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=json.dumps(reply, ensure_ascii=False)),
                    finish_reason="stop",
                )
            ],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
        )

    with patch.object(litellm, "acompletion", acompletion):
        yield


async def capture(case: str) -> dict:
    """Run `case` through `run_miti` on the real `LiteLLMClient` with replies by call tag."""
    fixture, n_runs = CASES[case]
    spec = yaml.safe_load((FIX / "expected.yaml").read_text("utf-8"))["fixtures"][fixture]
    transcript = Transcript.model_validate(json.loads((FIX / spec["transcript"]).read_text("utf-8")))
    params = {"n_runs": n_runs, "change_goal": spec["change_goal"]}
    calls: list[dict] = []
    events: list[tuple[str, str]] = []

    async def no_sleep(_):
        return None

    with _patched_acompletion(load_responses(fixture), calls, events):
        client = TaggingClient(
            LiteLLMClient(LLMConfig(llm_mode="live", routes=_routes()), sleep=no_sleep)
        )
        ctx = RunContext(llm=client, metrics=MetricsCollector(), request_id=REQUEST_ID)
        out = await run_miti(ctx, transcript, SMAP, params)
    return {
        "case": case,
        "payloads": sorted(calls, key=lambda c: c["call_tag"]),
        "warm_up": _warm_up(events),
        "report": masked(json.loads(out.report.model_dump_json())),
        "aggregate": json.loads(out.artifacts.code.aggregate.model_dump_json()),
    }


def dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def baseline_path(case: str) -> Path:
    return OUT / f"{case}.json"


def main() -> None:
    RESPONSES.mkdir(parents=True, exist_ok=True)
    for fixture in FIXTURES:
        (RESPONSES / f"{fixture}.json").write_text(dumps(build_responses(fixture)), "utf-8")
    for case in CASES:
        baseline_path(case).write_text(dumps(asyncio.run(capture(case))), "utf-8")
        print("wrote", baseline_path(case))


if __name__ == "__main__":
    sys.path.insert(0, str(TESTS))
    main()
