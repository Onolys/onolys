"""Selection, cost, time, coverage, excluded and status gating. Offline, pure."""
from compare.fakes import FakePriceBook, load_scenario
from onolys_eval.summary import operations as ops
from onolys_eval.summary.run_report import ParsedRun
from onolys_eval.summary.session_metrics import Metrics, _na_cell


def scenario(name):
    s = load_scenario(name)
    return s["eval_run"], s["cells"], FakePriceBook(s["prices"])


def cell(combo="c", sid="s1", repeat=1, attempt=0, status="done", started="2026-01-01T00:00:00Z",
         ended="2026-01-01T00:01:00Z", error=None, usage=None):
    return {"sid": sid, "combo_key": combo, "repeat": repeat, "attempt": attempt, "status": status,
            "started": started, "ended": ended, "error": error, "run_id": f"r{attempt}",
            "run_info": {"usage": usage} if usage is not None else None}


def test_final_attempt_is_highest_per_cell():
    _, cells, _ = scenario("twelve_sessions")
    final = ops.final_attempts(cells)
    assert len(final) == 36  # 12 sessions x 3 combos x 1 repeat
    keys = {(c["sid"], c["combo_key"], c["repeat"]) for c in final}
    assert len(keys) == 36
    retried_done = [c for c in final if c["combo_key"] == "openai/synthetic-mid/low" and c["attempt"] == 1]
    assert len(retried_done) == 1 and retried_done[0]["status"] == "done"
    failed = [c for c in final if c["status"] == "failed"]
    assert len(failed) == 1 and failed[0]["attempt"] == 1  # earlier failed attempt dropped


def test_done_cells_only_done_final():
    _, cells, _ = scenario("twelve_sessions")
    assert len(ops.done_cells(ops.final_attempts(cells))) == 35


def test_time_mean_and_retried_runs_footnote():
    cells = [cell(attempt=0, status="failed", ended="2026-01-01T00:00:10Z"),
             cell(attempt=1, ended="2026-01-01T00:01:00Z"),
             cell(sid="s2", ended="2026-01-01T00:03:00Z")]
    out = ops.operational(cells, [{"combo_key": "c", "litellm_id": "m"}], FakePriceBook({}))["c"]
    assert out["time"] == {"mean_seconds": 120.0, "n": 2, "retried_runs": 1}


def test_time_missing_timestamps_not_counted():
    cells = [cell(status="failed", ended=None), cell(sid="s2")]
    t = ops.operational(cells, [{"combo_key": "c", "litellm_id": "m"}], FakePriceBook({}))["c"]["time"]
    assert t["n"] == 1 and t["mean_seconds"] == 60.0
    none = ops.operational([cell(ended=None)], [{"combo_key": "c", "litellm_id": "m"}],
                           FakePriceBook({}))["c"]["time"]
    assert none["mean_seconds"] is None and none["n"] == 0


def test_unknown_model_cost_is_na_not_zero():
    eval_run, cells, prices = scenario("twelve_sessions")
    out = ops.operational(ops.final_attempts(cells), eval_run["combos"], prices)
    unpriced = out["mistral/synthetic-unpriced/low"]["cost"]
    assert unpriced["total_usd"] is None
    assert unpriced["na"] == {"reason": "no price for mistral/synthetic-unpriced"}
    assert out["claude/synthetic-large/low"]["cost"]["na"] is None
    assert out["claude/synthetic-large/low"]["cost"]["total_usd"] > 0


def test_failed_runs_still_cost_and_reported_cost_wins():
    cells = [cell(usage={"input_tokens": 1_000_000, "output_tokens": 0}),
             cell(sid="s2", status="failed", error={"code": "invalid_output"},
                  usage={"input_tokens": 1_000_000, "output_tokens": 0}),
             cell(sid="s3", usage={"cost_usd": 0.5, "input_tokens": 9})]
    book = FakePriceBook({"m": {"input_usd_per_million": 2.0, "output_usd_per_million": 4.0}})
    out = ops.operational(cells, [{"combo_key": "c", "litellm_id": "m"}], book)["c"]
    assert out["cost"]["total_usd"] == 4.5 and out["cost"]["n"] == 3
    assert out["failures"] == [{"code": "invalid_output", "count": 1}]


def test_failures_include_unparseable_not_skipped():
    _, cells, _ = scenario("provider_skipped")
    eval_run = load_scenario("provider_skipped")["eval_run"]
    out = ops.operational(ops.final_attempts(cells), eval_run["combos"], FakePriceBook({}),
                          unparseable={("synthetic-s01", "claude/synthetic-large/low", 1)})
    assert out["gemini/synthetic-small/low"]["failures"] == [{"code": "provider_error", "count": 5}]
    assert out["claude/synthetic-large/low"]["failures"] == [{"code": "unparseable", "count": 1}]
    assert out["gemini/synthetic-small/low"]["time"]["n"] == 5  # skipped cells have no time


def test_partial_cancelled_nothing_imputed():
    eval_run, cells, _ = scenario("cancelled_partial")
    final = ops.final_attempts(cells)
    done = ops.done_cells(final)
    assert len(done) == 7 and len({c["sid"] for c in done}) == 4
    cov = ops.coverage(eval_run, final)
    assert cov == {"eval_status": "partial", "cancelled_at": "2026-11-20T12:30:00Z", "runs_done": 7,
                   "runs_total": 24, "runs_skipped": 0, "skipped_providers": []}
    ex = ops.excluded(final)
    assert len(ex) == 17 and {e["reason"] for e in ex} == {"cancelled"}
    assert set(ex[0]) == {"session_id", "combo_key", "repeat", "reason"}


def test_provider_skipped_fixture():
    eval_run, cells, _ = scenario("provider_skipped")
    final = ops.final_attempts(cells)
    cov = ops.coverage(eval_run, final)
    assert cov["runs_done"] == 24 and cov["runs_total"] == 36 and cov["runs_skipped"] == 7
    assert cov["skipped_providers"] == [{"provider": "gemini", "after_failures": 5}]
    reasons = [e["reason"] for e in ops.excluded(final)]
    assert reasons.count("provider_unavailable") == 7 and reasons.count("failed:provider_error") == 5
    assert ops.skipped_combo_keys(eval_run) == {"gemini/synthetic-small/low"}


def test_excluded_unparseable_not_started_and_missing_code():
    cells = [cell(sid="a"), cell(sid="b", status="queued", started=None, ended=None),
             cell(sid="c", status="running"), cell(sid="d", status="failed")]
    ex = ops.excluded(ops.final_attempts(cells), unparseable={("a", "c", 1)})
    assert [(e["session_id"], e["reason"]) for e in ex] == [
        ("a", "unparseable"), ("b", "not_started"), ("c", "not_started"), ("d", "failed:unknown")]


def test_split_parsed_groups_by_session_and_drops_unparseable():
    ok = ParsedRun(engine="miti", status="ok", reason=None)
    bad = ParsedRun(engine="miti", status="unparseable", reason="schema_mismatch")
    pairs = [(cell(sid="a", repeat=1), ok), (cell(sid="a", repeat=2), ok), (cell(sid="b"), bad)]
    runs, unparseable = ops.split_parsed(pairs)
    assert runs == {"a": {"c": [ok, ok]}}
    assert unparseable == {("b", "c", 1)}


def test_mark_skipped_cells_na_never_zero():
    m = Metrics(cells={"miss": {"a": {"value": 1.0, "off": 1.0, "best": True, "na": None},
                                "g": {"value": 0, "off": 0, "best": True, "na": None}},
                       "count_error": {}})
    ops.mark_skipped(m, ["g"])
    assert m.cells["miss"]["g"]["na"] == {"reason": "skipped: provider unavailable"}
    assert m.cells["miss"]["g"]["value"] is None and m.cells["miss"]["g"]["best"] is False
    assert m.cells["miss"]["a"]["best"] is True
    assert m.cells["count_error"]["g"]["na"]["reason"] == "skipped: provider unavailable"
    assert _na_cell("x")["value"] is None


def test_status_gating():
    for name, expected in [("running", "not_finished"), ("no_completed", "no_completed_runs"),
                           ("cancelled_partial", None), ("twelve_sessions", None),
                           ("provider_skipped", None)]:
        eval_run, cells, _ = scenario(name)
        assert ops.gate(eval_run, cells) == expected, name
    for status in ("queued", "running", "deleting"):
        assert ops.gate({"status": status}, []) == "not_finished"
    skipped_failed = [cell(status="skipped"), cell(sid="b", status="failed")]
    assert ops.gate({"status": "partial"}, skipped_failed) == "no_completed_runs"
    assert ops.gate({"status": "done"}, [cell()]) is None
