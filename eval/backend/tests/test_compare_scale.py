"""Offline largest-run payload and cold-compute regression; no external services."""
import importlib.util
from time import perf_counter
from types import SimpleNamespace

from test_app import AUTH, client
from test_compare_load import FIXTURES, fakes

from onolys_eval_backend import compare_routes
from onolys_eval_backend.costs import PriceBook


def test_499_runs_payload_cache_and_advisory_cold_timing(monkeypatch):
    spec = importlib.util.spec_from_file_location("compare_scale_builder", FIXTURES / "builder.py")
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    scenario = builder.scale(n_sessions=499, combos=("A",)).to_dict()
    assert len(scenario["run_docs"]) == 499
    source = fakes.FakeEvalRunSource(scenario)
    monkeypatch.setattr(compare_routes, "ServiceEvalRunSource", lambda services: source)
    c = client(services=SimpleNamespace(prices=PriceBook(scenario["prices"])))
    path = "/v1/eval-runs/eval-scale/compare/overview"
    started = perf_counter()
    response = c.get(path, headers=AUTH)
    elapsed = perf_counter() - started
    assert response.status_code == 200
    assert len(response.content) < 1_500_000
    assert '"rationale"' not in response.text
    assert response.json()["coverage"]["runs_done"] == 499
    choices = response.json()["header"]["line_sessions"]
    assert len(choices) == 499
    assert all(set(row) == {"session_id", "matched_lines"} for row in choices)
    before = len(source.calls)
    assert c.get(path, headers=AUTH).json() == response.json()
    assert [call[0] for call in source.calls[before:]] == ["eval_run", "cells"]
    combo = scenario["eval_run"]["combos"][0]["combo_key"]
    matched = c.get(path.removesuffix("overview") + "line-matches",
                    params={"combo": combo, "code": "question", "metric": "question"},
                    headers=AUTH)
    assert matched.status_code == 200
    assert len(matched.json()["session_ids"]) <= 499
    assert len(matched.content) < 30_000
    assert all(call[0] in {"eval_run", "cells"} for call in source.calls[before:])
    print(f"499-run cold compute: {elapsed:.3f}s; overview: {len(response.content):,} bytes")
    assert elapsed < 5, f"Advisory 5s offline cold-compute budget exceeded: {elapsed:.3f}s"
