"""Offline projection-loader/cache checks using the saved synthetic compare fixture."""
import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from onolys_eval.summary.transcript_view import TranscriptChanged

from onolys_eval_backend.compare_cache import CompareCache
from onolys_eval_backend.compare_load import CompareLoader, GoldHashMismatch, ReadLimitExceeded
from onolys_eval_backend.costs import PriceBook, estimate_route_cost

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "compare"
spec = importlib.util.spec_from_file_location("compare_fixture_fakes", FIXTURES / "fakes.py")
fakes = importlib.util.module_from_spec(spec)
# Dataclasses look up their module while importing.

sys.modules[spec.name] = fakes
spec.loader.exec_module(fakes)


@pytest.fixture
def setup():
    scenario = json.loads((FIXTURES / "counts_golden.json").read_text())
    source = fakes.FakeEvalRunSource(scenario)
    return scenario, source, CompareLoader(source, PriceBook(scenario["prices"]))


def test_load_projects_and_bounds_reads_and_hits_cache(setup):
    scenario, source, loader = setup
    rid = scenario["eval_run"]["eval_run_id"]
    loaded = loader.load(rid)
    assert len(loaded.runs) == 12  # earlier failed attempt is retained only in attempts
    assert len(loaded.attempts) == 13
    assert len(loaded.sessions) == 2
    assert all(r.parsed.status == "ok" for r in loaded.runs)
    assert all("source" not in s.gold.to_dict() for s in loaded.sessions.values())
    assert sum(c[0] == "transcript" for c in source.calls) == 2
    before = len(source.calls)
    assert loader.load(rid) is loaded
    assert [c[0] for c in source.calls[before:]] == ["eval_run", "cells"]


def test_gold_hash_reverified(setup):
    scenario, _, loader = setup
    next(iter(scenario["gold"].values()))["counts"]["question"] += 1
    with pytest.raises(GoldHashMismatch):
        loader.load(scenario["eval_run"]["eval_run_id"])


def test_transcript_change_is_explicit_and_does_not_block_saved_counts(setup):
    scenario, _, loader = setup
    sid = next(iter(scenario["transcripts"]))
    scenario["transcripts"][sid]["sha256"] = "changed"
    loaded = loader.load(scenario["eval_run"]["eval_run_id"])
    assert loaded.runs[0].parsed.counts
    with pytest.raises(TranscriptChanged):
        loaded.sessions[sid].require_turns()


def test_reject_oversized_source_before_loading_documents(setup):
    scenario, source, loader = setup
    loader.max_runs = 1
    with pytest.raises(ReadLimitExceeded):
        loader.load(scenario["eval_run"]["eval_run_id"])
    assert not any(c[0] in {"report", "gold", "transcript", "run_doc"} for c in source.calls)


def test_cache_ttl_invalidation_order_and_lru():
    now = [0.0]
    cache = CompareCache(max_entries=2, clock=lambda: now[0])
    cells = [{"run_id": "a", "status": "running", "ended": None}]
    cache.put("r", cells, "running", "projection")
    now[0] = 9.9
    assert cache.get("r", cells, "running") == "projection"
    now[0] = 10.0
    assert cache.get("r", cells, "running") is None
    cache.put("r", cells, "done", "stable")
    now[0] = 100000
    assert cache.get("r", list(reversed(cells)), "done") == "stable"
    for field, value in [("status", "done"), ("ended", "later"), ("run_id", "b")]:
        changed = deepcopy(cells)
        changed[0][field] = value
        assert cache.get("r", changed, "done") is None
    assert cache.get("other", cells, "done") is None
    cache.put("second", cells, "done", 2)
    cache.get("r", cells, "done")
    cache.put("third", cells, "done", 3)
    assert cache.get("second", cells, "done") is None
    assert cache.get("r", cells, "partial") is None


def test_route_cost_uses_pinned_model_and_reported_zero():
    prices = PriceBook({"model/a": {"input_usd_per_million": 2, "output_usd_per_million": 4}})
    doc = {"eval": {"resolved_route": {"litellm_id": "model/a"}},
           "run_info": {"usage": {"input_tokens": 1000000, "output_tokens": 500000}}}
    assert estimate_route_cost(prices, doc).cost_usd == 4
    doc["run_info"]["usage"]["cost_usd"] = 0
    doc["eval"]["resolved_route"]["litellm_id"] = "unknown"
    assert estimate_route_cost(prices, doc).cost_usd == 0
    del doc["run_info"]["usage"]["cost_usd"]
    assert estimate_route_cost(prices, doc).cost_usd is None


def test_loader_running_ttl_and_run_change_reload_saved_documents(setup):
    scenario, source, _ = setup
    clock = [0.0]
    loader = CompareLoader(source, PriceBook(scenario["prices"]),
                           CompareCache(clock=lambda: clock[0]))
    group = scenario["eval_run"]
    group["status"] = "running"
    first = loader.load(group["eval_run_id"])
    clock[0] = 9
    assert loader.load(group["eval_run_id"]) is first
    clock[0] = 10
    second = loader.load(group["eval_run_id"])
    assert second is not first
    scenario["cells"][0]["ended"] = "2026-11-21T10:32:10Z"
    assert loader.load(group["eval_run_id"]) is not second
    assert sum(c[0] == "gold" for c in source.calls) == 6


def test_lines_reverify_transcript_even_after_terminal_cache_hit(setup):
    scenario, _, loader = setup
    rid = scenario["eval_run"]["eval_run_id"]
    loaded = loader.load(rid)
    sid = next(iter(loaded.sessions))
    assert loader.session_turns(loaded, sid)
    scenario["transcripts"][sid]["sha256"] = "changed-after-cache"
    assert loader.load(rid) is loaded
    with pytest.raises(TranscriptChanged):
        loader.session_turns(loaded, sid)


def test_service_source_rejects_oversized_plan_before_reading_run_docs():
    from types import SimpleNamespace

    from onolys_eval_backend.compare_load import ServiceEvalRunSource

    doc = {"sessions": {"s": {}}, "combos": [{}], "engines": ["miti"], "repeats": 500}
    services = SimpleNamespace(repository=SimpleNamespace(get_run=lambda _: doc))
    with pytest.raises(ReadLimitExceeded):
        ServiceEvalRunSource(services).eval_run("r")


def test_service_source_normalizes_sp05_group_and_resolves_saved_gold(monkeypatch):
    from types import SimpleNamespace

    from onolys_eval_backend import compare_load

    sha = "a" * 64
    raw = {"name": "saved", "input": {"dataset_id": "annomi"}, "status": "done",
           "sessions": {"s": {"dataset_session_id": "ds", "transcript_sha256": "t"}},
           "combos": [{}], "engines": ["miti"], "repeats": 1,
           "saved_config": {"resolved_combos": {"ck": {"litellm_id": "provider/model"}}}}
    cell = {"sid": "s", "gold_ref": {"sha256": sha}, "run_id": "run"}
    monkeypatch.setattr(compare_load.eval_view, "list_cells", lambda *args: [cell])
    monkeypatch.setattr(compare_load, "plan_cells", lambda doc: [
        {"combo_key": "ck", "combo": {}, "engine": "miti"}])
    reads = []
    services = SimpleNamespace(
        config=SimpleNamespace(eval_owner_uid="owner"),
        repository=SimpleNamespace(get_run=lambda _: raw),
        blobs=SimpleNamespace(get_bytes=lambda path: reads.append(path) or b'{"counts": {}}'))
    source = compare_load.ServiceEvalRunSource(services)
    group = source.eval_run("r")
    assert group["dataset_id"] == "annomi"
    assert group["sessions"][0]["transcript_sha256"] == "t"
    assert group["combos"][0]["litellm_id"] == "provider/model"
    assert source.gold(sha) == {"counts": {}}
    assert reads == [f"gold/{sha}.json"]
    with pytest.raises(GoldHashMismatch):
        source.gold("../../outside")
