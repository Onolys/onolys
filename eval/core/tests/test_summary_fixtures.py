"""Smoke test: the synthetic compare fixtures load through the fake source, validate against the
real contracts, cover every compare scenario, and need no network."""
import hashlib
import json
import re
import socket

import pytest
from compare import builder
from compare.fakes import (
    HERE,
    SCENARIOS,
    FakeEvalRunSource,
    FakePriceBook,
    SourceNotFound,
    load_scenario,
)
from onolys_engine_core.transcript import Transcript
from onolys_eval.adapters import miti_lean_scores, oneshot_scores
from onolys_eval.gold import Gold
from onolys_eval.summary.source import EvalRunSource, PriceLookup
from onolys_eval.summary.source import SourceNotFound as CoreNotFound


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("network access in an offline test")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def canon(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()


@pytest.fixture(params=SCENARIOS)
def scenario(request):
    return load_scenario(request.param)


def source_for(*names):
    return FakeEvalRunSource.from_names(*names)


def test_fake_satisfies_protocols_and_not_found():
    src = source_for("counts_golden")
    assert isinstance(src, EvalRunSource)
    assert isinstance(FakePriceBook({}), PriceLookup)
    assert issubclass(SourceNotFound, LookupError) and issubclass(CoreNotFound, LookupError)
    with pytest.raises(SourceNotFound):
        src.eval_run("nope")
    with pytest.raises(SourceNotFound):
        src.gold("0" * 64)


def test_every_scenario_loads_through_the_fake_source(scenario):
    src = FakeEvalRunSource(scenario)
    doc = src.eval_run(scenario["eval_run"]["eval_run_id"])
    assert scenario["synthetic"] is True
    for s in doc["sessions"]:
        gold = src.gold(s["gold_sha256"])
        assert canon(gold) == s["gold_sha256"]
        Gold.model_validate(gold)
        t = src.transcript(s["uid"], s["session_id"])
        assert t["sha256"] == s["transcript_sha256"] == canon(t["transcript"])
        Transcript.model_validate(t["transcript"])
    cells = src.cells(doc["eval_run_id"])
    assert len(cells) == len(doc["runs"])
    for ref, cell in zip(doc["runs"], cells, strict=True):
        assert (ref["run_id"], ref["status"], ref["combo_key"], ref["attempt"]) == (
            cell["run_id"], cell["status"], cell["combo_key"], cell["attempt"])
        if cell["run_id"] is None:
            assert cell["run_info"] is None
            continue
        run = src.run_doc(*(next(s["uid"] for s in doc["sessions"] if s["session_id"] == cell["sid"]),
                            cell["sid"], cell["run_id"]))
        assert run["eval"]["combo_key"] == cell["combo_key"]
        assert run["eval"]["engine"] == cell["engine"]
        assert run["status"] == cell["status"]
        if cell["status"] == "done":
            report = src.report(run["uid"], cell["sid"], cell["run_id"])["report"]
            project = oneshot_scores if cell["engine"].startswith("oneshot:") else miti_lean_scores
            assert all(isinstance(v, (int, float)) for v in project(report).counts.values())
    assert src.calls and all(c[0] in {"eval_run", "cells", "run_doc", "report", "transcript", "gold"}
                             for c in src.calls)


def test_validates_against_real_prod_models(scenario):
    models = pytest.importorskip("onolys_api.repo.models")  # backend/api env only, not eval-core CI
    for t in scenario["transcripts"].values():
        models.TranscriptDoc.model_validate(t)
    for run in scenario["run_docs"].values():
        models.RunDoc.model_validate(run)
    for rep in scenario["reports"].values():
        models.ReportDoc.model_validate(rep)


def test_all_text_is_plainly_synthetic(scenario):
    for t in scenario["transcripts"].values():
        for turn in t["transcript"]["turns"]:
            assert re.fullmatch(r"Synthetic (clinician|client) turn \d+\.", turn["text"])
    for rep in scenario["reports"].values():
        for b in rep["report"].get("behaviours", []):
            for i in b["instances"]:
                assert i["rationale"] in ("", f"Synthetic rationale for {b['item_id']} at {i['turn_id']}.")
        for t in rep["report"].get("tips", []):
            assert t["observation"].startswith("Synthetic")
    assert "synthetic" in (HERE / "README.md").read_text().lower()
    assert HERE.joinpath(f"{scenario['scenario']}.json").stat().st_size < 200_000


def test_committed_files_match_builder(scenario):
    name = scenario["scenario"]
    assert (HERE / f"{name}.json").read_text() == builder.render(builder.build(name))


def finals(scn):
    out = {}
    for c in scn["cells"]:
        out[(c["sid"], c["combo_key"], c["repeat"])] = c
    return out


def counts(scn, sid, combo, rep):
    run = finals(scn)[(sid, combo, rep)]
    return miti_lean_scores(scn["reports"][run["run_id"]]["report"]).counts


def test_counts_golden_repeats_8_10_12():
    scn = load_scenario("counts_golden")
    a = builder.COMBOS["A"]["combo_key"]
    q = [counts(scn, "synthetic-s01", a, r)["question"] for r in (1, 2, 3)]
    assert q == [8, 10, 12]
    gold = Gold.model_validate(scn["gold"][scn["eval_run"]["sessions"][0]["gold_sha256"]])
    assert gold.counts["question"] == 10
    s2 = [counts(scn, "synthetic-s02", a, r)["question"] for r in (1, 2, 3)]
    gold2 = Gold.model_validate(scn["gold"][scn["eval_run"]["sessions"][1]["gold_sha256"]])
    assert s2 == [8, 8, 8] and gold2.counts["question"] == 6
    assert scn["eval_run"]["repeats"] == 3
    b_attempts = [c["attempt"] for c in scn["cells"]
                  if c["sid"] == "synthetic-s02" and c["repeat"] == 2 and c["engine"].startswith("oneshot")]
    assert b_attempts == [0, 1]


def test_annomi_partial_labels_and_ratio_inputs():
    scn = load_scenario("annomi_partial")
    golds = [Gold.model_validate(scn["gold"][s["gold_sha256"]]) for s in scn["eval_run"]["sessions"]]
    g1, _, g3 = golds
    assert (g1.counts["sr"], g1.counts["cr"], g1.counts["question"]) == (3, 1, 2)
    assert g1.summaries.reflection_question_ratio == 2.0 and g1.summaries.pct_cr == 0.25
    assert g1.globals is None and g1.summaries.technical is None
    assert len(g1.counts) == 5 and g1.counts["affirm"] is None
    assert g3.counts["question"] == 0 and g3.summaries.reflection_question_ratio is None
    a = builder.COMBOS["A"]["combo_key"]
    assert counts(scn, "synthetic-s02", a, 2)["question"] == 0
    assert counts(scn, "synthetic-s02", a, 1)["question"] == 2
    assert all(row.codes == [] or len(row.codes) == 1 for g in golds for row in g.utterance_codes)


def test_lines_multi_code_oneshot_and_withheld():
    scn = load_scenario("lines")
    g1 = Gold.model_validate(scn["gold"][scn["eval_run"]["sessions"][0]["gold_sha256"]])
    assert any(len(r.codes) > 1 for r in g1.utterance_codes)
    a, b = builder.COMBOS["A"]["combo_key"], builder.COMBOS["B"]["combo_key"]
    rep2 = scn["reports"][finals(scn)[("synthetic-s01", a, 2)]["run_id"]]["report"]
    at_t7 = [x["item_id"] for x in rep2["behaviours"] for i in x["instances"] if i["turn_id"] == "t7"]
    assert sorted(at_t7) == ["affirm", "cr"]
    rep1 = scn["reports"][finals(scn)[("synthetic-s01", a, 1)]["run_id"]]["report"]
    assert "" in [i["rationale"] for x in rep1["behaviours"] for i in x["instances"]]
    oneshot = scn["reports"][finals(scn)[("synthetic-s01", b, 1)]["run_id"]]["report"]
    assert set(oneshot) == {"counts", "globals", "tips"}
    assert scn["run_docs"][finals(scn)[("synthetic-s01", a, 1)]["run_id"]]["coded_span"] == {
        "start_turn": 1, "end_turn": 12}


def test_twelve_sessions_failed_retried_zero_and_unpriced():
    scn = load_scenario("twelve_sessions")
    assert len(scn["eval_run"]["sessions"]) == 12 and scn["eval_run"]["status"] == "partial"
    a, b, u = (builder.COMBOS[k]["combo_key"] for k in "ABU")
    final = finals(scn)
    assert final[("synthetic-s05", a, 1)]["status"] == "failed" and final[("synthetic-s05", a, 1)]["attempt"] == 1
    assert [c["status"] for c in scn["cells"] if c["sid"] == "synthetic-s03" and c["combo_key"] == b] == ["failed", "done"]
    done = [c for c in final.values() if c["status"] == "done" and c["combo_key"] == a]
    assert len(done) == 11
    zero_both = zero_ours = 0
    for i in range(1, 13):
        sid = f"synthetic-s{i:02d}"
        if (sid, a, 1) not in final or final[(sid, a, 1)]["status"] != "done":
            continue
        human = Gold.model_validate(scn["gold"][scn["eval_run"]["sessions"][i - 1]["gold_sha256"]]).counts
        ours = counts(scn, sid, a, 1)
        zero_both += sum(human[k] == 0 == ours[k] for k in ours)
        zero_ours += sum(human[k] > 0 == ours[k] for k in ours)
    assert zero_both and zero_ours
    u_done = [c for c in final.values() if c["combo_key"] == u]
    assert u_done and all(c["run_info"]["cost_usd_est"] is None for c in u_done)
    assert all(c["run_info"]["cost_usd_est"] is not None for c in final.values() if c["combo_key"] == b)
    assert any(c["run_info"]["usage"].get("cost_usd") is not None for c in final.values() if c["combo_key"] == a)
    assert all(c["run_info"]["usage"]["input_tokens"] > 0 for c in scn["cells"] if c["status"] == "failed")
    assert FakePriceBook(scn["prices"]).estimate({"input_tokens": 1}, "mistral/synthetic-unpriced").cost_usd is None


def test_cancelled_partial_cells_and_no_run_docs():
    scn = load_scenario("cancelled_partial")
    doc = scn["eval_run"]
    assert doc["status"] == "partial" and doc["cancelled_at"]
    statuses = [c["status"] for c in scn["cells"]]
    assert statuses.count("done") == 7 and statuses.count("cancelled") == 17
    assert all(c["run_id"] is None for c in scn["cells"] if c["status"] == "cancelled")
    assert len(scn["run_docs"]) == 7 == len(scn["reports"])
    assert [c["status"] for c in scn["cells"] if c["sid"] == "synthetic-s04"] == ["done", "cancelled"]


def test_provider_skipped_gemini_five_failed_then_skipped():
    scn = load_scenario("provider_skipped")
    doc = scn["eval_run"]
    assert doc["status"] == "partial" and len(doc["sessions"]) == 12 and len(doc["combos"]) == 3
    assert doc["provider_skips"] == [{"provider": "gemini", "after_failures": 5,
                                      "skipped_at": "2026-11-20T13:00:00Z"}]
    gem = [c for c in scn["cells"] if c["combo_key"].startswith("gemini/")]
    assert [c["status"] for c in gem] == ["failed"] * 5 + ["skipped"] * 7
    skipped_refs = [r for r in doc["runs"] if r["status"] == "skipped"]
    assert len(skipped_refs) == 7 and {r["reason"] for r in skipped_refs} == {"provider_unavailable"}
    assert all(c["run_id"] is None for c in gem if c["status"] == "skipped")
    assert sum(c["status"] == "done" for c in scn["cells"]) == 24


@pytest.mark.parametrize("name,quality", [("no_labels_hlqc", ["high", "low"]), ("no_labels_phac", [None, None])])
def test_no_label_datasets(name, quality):
    scn = load_scenario(name)
    golds = [Gold.model_validate(scn["gold"][s["gold_sha256"]]) for s in scn["eval_run"]["sessions"]]
    assert [g.quality_label for g in golds] == quality
    assert all(not g.counts and g.globals is None and g.utterance_codes is None for g in golds)
    assert any(c["status"] == "done" for c in scn["cells"])


def test_no_completed_and_running_statuses():
    nc = load_scenario("no_completed")
    assert nc["eval_run"]["status"] == "cancelled"
    assert not any(c["status"] == "done" for c in nc["cells"]) and not nc["reports"]
    assert {c["status"] for c in nc["cells"]} == {"failed", "cancelled"}
    run = load_scenario("running")
    assert run["eval_run"]["status"] == "running"
    assert {c["status"] for c in run["cells"]} == {"done", "running", "queued"}


def test_fake_price_book_reported_cost_wins_and_unknown_is_none():
    book = FakePriceBook(builder.PRICES)
    assert book.estimate({"input_tokens": 1_000_000, "output_tokens": 0}, "openai/synthetic-mid").cost_usd == 1.0
    assert book.estimate({"cost_usd": 0.0, "input_tokens": 9}, "openai/synthetic-mid").cost_usd == 0.0
    assert book.estimate({"input_tokens": 5}, "nope/none").cost_usd is None


def test_scale_scenario_is_generated_in_memory_under_499_runs():
    scn = builder.scale().to_dict()
    assert len(scn["run_docs"]) == len(scn["reports"]) == 498
    FakeEvalRunSource(scn).cells("eval-scale")
