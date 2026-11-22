"""Live quality/latency/tips check on the real model (manual; needs the route's API key).

    python -m onolys_miti.check [--preset NAME] [--skip-tips]

Quality: runs the three synthetic fixtures of `data/fixtures/expected.yaml` once each, in
sequence (so latency is not distorted), and compares with the expected counts and global ranges
and the limits in `data/fixtures/thresholds.yaml`: per-code count MAE, globals within 1 point,
bad-output/retry rate, p95 run latency, tokens per run.
Tips: `good_practice` end to end; at least 3 tips whose quote really sits in its turn text.
Exit 0 only when every check passes. Never prints text, quotes or keys.
"""

import argparse
import asyncio
import json
import math
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any

import yaml

from onolys_miti import miti
from onolys_miti import tips as tips_mod
from onolys_miti.context import RunContext
from onolys_miti.llm import LLMConfig, MetricsCollector, make_client
from onolys_miti.run import run_miti
from onolys_miti.transcript import Transcript

FIX = miti.DATA_DIR / "fixtures"
MIN_TIPS = 3
# metric -> (threshold key, "max" = must not exceed, "min" = must reach)
LIMITS: dict[str, tuple[str, str]] = {
    "count_mae": ("count_mae_max", "max"),
    "globals_within_1": ("globals_within_1_min", "min"),
    "bad_output_rate": ("bad_output_rate_max", "max"),
    "p95_latency_s": ("p95_latency_s_max", "max"),
    "tokens_per_run": ("tokens_per_run_max", "max"),
}


@dataclass
class Failure:
    metric: str
    value: float
    limit: float
    kind: str

    def __str__(self) -> str:
        op = "<=" if self.kind == "max" else ">="
        return f"{self.metric} = {self.value:.3f}, need {op} {self.limit:g}"


@dataclass
class Quality:
    metrics: dict[str, float]
    failures: list[Failure] = field(default_factory=list)


def p95(values: list[float]) -> float:
    """Nearest-rank 95th percentile."""
    s = sorted(values)
    return s[max(0, math.ceil(0.95 * len(s)) - 1)]


def distance(score: float, rng: list[float]) -> float:
    lo, hi = rng
    return max(lo - score, score - hi, 0.0)


def bad_call(rec: dict[str, Any]) -> bool:
    return rec["error_kind"] == "bad_output" or rec["attempts"] > 1


def coding_records(metrics: MetricsCollector) -> list[dict[str, Any]]:
    """Call records of the coding run only: the tips call is not what thresholds.yaml limits."""
    return [r for r in metrics.records if r.get("tier") != tips_mod.ROUTE]


def tokens(metrics: MetricsCollector) -> int:
    keys = ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens")
    return sum(r[k] for r in coding_records(metrics) for k in keys)


class CodeTimer:
    """Progress callback timing only the `code` stage (start to done)."""

    def __init__(self, clock=time.monotonic) -> None:
        self._clock = clock
        self._t0: float | None = None
        self.elapsed = 0.0

    def __call__(self, stage: str, status: str) -> None:
        if stage != "code":
            return
        if status == "started":
            self._t0 = self._clock()
        elif status == "done" and self._t0 is not None:
            self.elapsed = self._clock() - self._t0


def evaluate(metrics: dict[str, float], thresholds: dict[str, Any]) -> list[Failure]:
    out = []
    for name, (key, kind) in LIMITS.items():
        if key not in thresholds:
            raise ValueError(f"thresholds file has no {key}")
        limit = float(thresholds[key])
        bad = metrics[name] > limit if kind == "max" else metrics[name] < limit
        if bad:
            out.append(Failure(name, metrics[name], limit, kind))
    return out


def valid_tips(tips: list[Any], transcript: Transcript) -> int:
    """Number of tips whose quote text equals the transcript slice it points at."""
    turns = {t.id: t.text for t in transcript.turns}
    return sum(
        1
        for t in tips
        if t.quote.text == turns.get(t.quote.turn_id, "")[t.quote.start : t.quote.end]
    )


def evaluate_tips(valid: int) -> list[str]:
    return [] if valid >= MIN_TIPS else [f"tips: {valid} valid, need at least {MIN_TIPS}"]


def load_fixture(name: str) -> tuple[Transcript, dict[str, Any]]:
    tr = Transcript.model_validate_json((FIX / f"{name}.json").read_text(encoding="utf-8"))
    params = json.loads((FIX / f"{name}.params.json").read_text(encoding="utf-8"))
    return tr, params


def load_thresholds() -> dict[str, Any]:
    return yaml.safe_load((FIX / "thresholds.yaml").read_text(encoding="utf-8"))


def live_client(preset: str | None = None):
    return make_client(LLMConfig(llm_mode="live", preset=preset))


async def run_quality(client, thresholds: dict[str, Any] | None = None) -> Quality:
    """Run each fixture of expected.yaml once on `client`; compare with the limits."""
    thresholds = thresholds if thresholds is not None else load_thresholds()
    expected = yaml.safe_load((FIX / "expected.yaml").read_text(encoding="utf-8"))["fixtures"]
    errors: list[float] = []
    within: list[bool] = []
    latencies: list[float] = []
    toks: list[int] = []
    calls = bad = 0
    for name, exp in expected.items():
        tr, params = load_fixture(name)
        metrics = MetricsCollector()
        ctx = RunContext(llm=client, metrics=metrics, request_id=f"check-{name}")
        timer = CodeTimer()
        out = await run_miti(ctx, tr, params["speaker_map"], {**params, "n_runs": 1}, timer)
        latencies.append(timer.elapsed)
        toks.append(tokens(metrics))
        code_recs = coding_records(metrics)
        calls += len(code_recs)
        bad += sum(bad_call(r) for r in code_recs)
        run = out.artifacts.code.results[0]
        errors += [abs(run.counts.get(c, 0) - n) for c, n in exp["counts"].items()]
        within += [
            distance(run.globals[g].score, spec["range"]) <= 1 for g, spec in exp["globals"].items()
        ]
    m = {
        "count_mae": sum(errors) / len(errors) if errors else 0.0,
        "globals_within_1": sum(within) / len(within) if within else 1.0,
        "bad_output_rate": bad / calls if calls else 0.0,
        "p95_latency_s": p95(latencies),
        "tokens_per_run": float(max(toks)),
    }
    return Quality(m, evaluate(m, thresholds))


async def run_tips(client) -> tuple[int, int]:
    """good_practice end to end; returns (valid tips, tips in the report)."""
    tr, params = load_fixture("good_practice")
    ctx = RunContext(llm=client, metrics=MetricsCollector(), request_id="check-tips")
    out = await run_miti(ctx, tr, params["speaker_map"], {**params, "n_runs": 1})
    return valid_tips(out.report.tips, tr), len(out.report.tips)


def format_quality(q: Quality, thresholds: dict[str, Any]) -> str:
    lines = []
    for name, (key, kind) in LIMITS.items():
        op = "<=" if kind == "max" else ">="
        lines.append(f"{name:18} {q.metrics[name]:10.3f}   need {op} {float(thresholds[key]):g}")
    lines += [f"FAIL {f}" for f in q.failures]
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="onolys_miti.check",
        description="Live check on the real model: fixture quality vs thresholds.yaml, plus tips.",
    )
    p.add_argument(
        "--preset",
        default=os.environ.get("MITI_LIVE_PRESET"),
        help="route preset (default: $MITI_LIVE_PRESET, else the default preset)",
    )
    p.add_argument("--skip-tips", action="store_true", help="run only the quality check")
    return p.parse_args(argv)


async def _run(preset: str | None, skip_tips: bool) -> int:
    client = live_client(preset)
    thresholds = load_thresholds()
    q = await run_quality(client, thresholds)
    print(format_quality(q, thresholds))
    problems = [str(f) for f in q.failures]
    if not skip_tips:
        valid, total = await run_tips(client)
        print(f"tips: {valid} valid of {total}")
        problems += evaluate_tips(valid)
    print("FAIL" if problems else "PASS")
    return 1 if problems else 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not os.environ.get("GEMINI_API_KEY"):
        print("error: set GEMINI_API_KEY (live LLM)", file=sys.stderr)
        return 1
    try:
        return asyncio.run(_run(args.preset, args.skip_tips))
    except (OSError, ValueError) as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
