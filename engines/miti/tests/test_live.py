"""Live checks on the real model (manual; excluded by default through `-m 'not live'`).

    set -a; . ~/.config/onolys/keys.env; set +a
    uv run --package onolys-miti pytest engines/miti/tests/test_live.py -m live -s

Env: MITI_LIVE_PRESET picks the route preset (default: the default preset).

- quality: the three synthetic fixtures run once each, in sequence (so latency is not distorted),
  compared with `fixtures/expected.yaml` and the limits in `fixtures/thresholds.yaml`: per-code
  count MAE, globals within 1 point, bad-output rate, p95 run latency, tokens per run.
- tips: good_practice end to end; at least 3 tips whose quote really sits in its transcript turn.
Never prints text, quotes or keys.
"""

import json
import math
import os
import time

import pytest
import yaml

from onolys_miti import miti
from onolys_miti.context import RunContext
from onolys_miti.llm import LLMConfig, MetricsCollector, make_client
from onolys_miti.run import run_miti
from onolys_miti.transcript import Transcript

pytestmark = [pytest.mark.live, pytest.mark.integration]

FIX = miti.DATA_DIR / "fixtures"
MIN_TIPS = 3
# metric -> (threshold key, "max" = must not exceed, "min" = must reach)
LIMITS = {
    "count_mae": ("count_mae_max", "max"),
    "globals_within_1": ("globals_within_1_min", "min"),
    "bad_output_rate": ("bad_output_rate_max", "max"),
    "p95_latency_s": ("p95_latency_s_max", "max"),
    "tokens_per_run": ("tokens_per_run_max", "max"),
}


def p95(values):
    """Nearest-rank 95th percentile."""
    s = sorted(values)
    return s[max(0, math.ceil(0.95 * len(s)) - 1)]


def distance(score, rng):
    lo, hi = rng
    return max(lo - score, score - hi, 0.0)


def bad_call(rec):
    return rec["error_kind"] == "bad_output" or rec["attempts"] > 1


def tokens(metrics):
    keys = ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens")
    return sum(r[k] for r in metrics.records for k in keys)


def need_key():
    if not os.environ.get("GEMINI_API_KEY"):
        pytest.skip("set GEMINI_API_KEY (live LLM)")


def live_client():
    return make_client(LLMConfig(llm_mode="live", preset=os.environ.get("MITI_LIVE_PRESET")))


def load(name):
    tr = Transcript.model_validate_json((FIX / f"{name}.json").read_text(encoding="utf-8"))
    params = json.loads((FIX / f"{name}.params.json").read_text(encoding="utf-8"))
    return tr, params


async def test_live_quality_against_expected_and_thresholds():
    need_key()
    expected = yaml.safe_load((FIX / "expected.yaml").read_text(encoding="utf-8"))["fixtures"]
    limits = yaml.safe_load((FIX / "thresholds.yaml").read_text(encoding="utf-8"))
    client = live_client()
    errors, within, latencies, toks = [], [], [], []
    calls = bad = 0
    for name, exp in expected.items():
        tr, params = load(name)
        metrics = MetricsCollector()
        ctx = RunContext(llm=client, metrics=metrics, request_id=f"live-{name}")
        t0 = time.monotonic()
        out = await run_miti(ctx, tr, params["speaker_map"], {**params, "n_runs": 1})
        latencies.append(time.monotonic() - t0)
        toks.append(tokens(metrics))
        calls += len(metrics.records)
        bad += sum(bad_call(r) for r in metrics.records)
        run = out.artifacts.code.results[0]
        errors += [abs(run.counts.get(c, 0) - n) for c, n in exp["counts"].items()]
        within += [
            distance(run.globals[g].score, spec["range"]) <= 1 for g, spec in exp["globals"].items()
        ]
    metrics_out = {
        "count_mae": sum(errors) / len(errors),
        "globals_within_1": sum(within) / len(within),
        "bad_output_rate": bad / calls if calls else 0.0,
        "p95_latency_s": p95(latencies),
        "tokens_per_run": float(max(toks)),
    }
    print(metrics_out)
    failures = []
    for metric, (key, kind) in LIMITS.items():
        value, limit = metrics_out[metric], float(limits[key])
        if (value > limit) if kind == "max" else (value < limit):
            failures.append(f"{metric} = {value:.3f}, need {'<=' if kind == 'max' else '>='} {limit:g}")
    assert not failures, failures


async def test_live_tips_quote_valid_end_to_end():
    need_key()
    tr, params = load("good_practice")
    ctx = RunContext(llm=live_client(), metrics=MetricsCollector(), request_id="live-tips")
    out = await run_miti(ctx, tr, params["speaker_map"], {**params, "n_runs": 1})
    turns = {t.id: t.text for t in tr.turns}
    valid = [
        t for t in out.report.tips
        if t.quote.text == turns.get(t.quote.turn_id, "")[t.quote.start : t.quote.end]
    ]
    print(f"tips: {len(valid)} valid of {len(out.report.tips)}")
    assert len(valid) >= MIN_TIPS
