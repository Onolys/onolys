"""Offline tests for SP06 More analysis and payload-grounded verdicts."""
from dataclasses import replace

import pytest
from onolys_eval.gold import COUNT_IDS, GLOBAL_IDS
from onolys_eval.summary.analysis import (
    baseline,
    build_verdict,
    compute_analysis,
    frontier,
    head_to_head,
    observed_range,
    reliability,
)
from onolys_eval.summary.gold_view import GoldProjection, LineLabel
from onolys_eval.summary.line_metrics import LineSession
from onolys_eval.summary.run_report import ParsedRun
from onolys_eval.summary.session_metrics import SessionInput
from onolys_eval.summary.transcript_view import TurnView

ZERO = dict.fromkeys(COUNT_IDS, 0)
G3 = dict.fromkeys(GLOBAL_IDS, 3)


def run(q=0, *, globals_=None, lines=None):
    return ParsedRun("miti", "ok", None, {**ZERO, "question": q},
                     G3 if globals_ is None else globals_,
                     turn_codes=lines or {}, has_lines=True)


def session(sid="s1", *, human=None, **runs):
    return SessionInput(sid, human or GoldProjection(None, ZERO, G3, None, None), runs)


def test_frontier_strict_dominance_equal_points_and_unpriced():
    errors = {c: {"off": e, "n": 2, "na": None} for c, e in
              [("cheap", 3), ("good", 1), ("dominated", 4), ("equal", 1), ("unknown", 0)]}
    costs = {c: {"cost": {"per_run_usd": p, "n": 4, "na": None}} for c, p in
             [("cheap", 1), ("good", 2), ("dominated", 3), ("equal", 2), ("unknown", None)]}
    costs["unknown"]["cost"]["na"] = {"reason": "no price for model"}
    result = frontier(errors, costs)
    assert {p["combo_key"] for p in result["points"]} == {"cheap", "good", "equal"}
    assert result["unpriced"][0]["combo_key"] == "unknown"
    assert result["unpriced"][0]["na"] == {"reason": "no price for model"}
    assert baseline() == {"value": None, "n": 0, "na": {
        "reason": "needs a second human coder, not in this dataset"}}


def test_inclusive_pack_levels_compare_each_repeat_and_session_balance():
    h = GoldProjection(None, {**ZERO, "question": 2, "sr": 2, "cr": 2},
                       {**G3, "partnership": 4}, None, None)  # relational = 3.5: fair
    fair = run(2, globals_={**G3, "empathy": 4})
    below = run(2)
    a = session(human=h, A=[fair, fair, below])
    b = session("s2", human=h, A=[below])
    result = reliability([a, b], ["A"])["A"]
    assert result["levels"]["relational"]["value"] == pytest.approx(1 / 3)
    assert result["levels"]["relational"]["n"] == 2
    assert result["levels"]["relational"]["observed"] == {"min": 3, "max": 3.5, "n": 4}
    assert reliability([a], ["A"])["A"]["levels"]["relational"]["value"] == pytest.approx(2 / 3)


def test_repeat_agreement_uses_global_and_labeled_clinician_turn_units():
    labels = (LineLabel("t1", ("question",), None), LineLabel("t2", (), None))
    h = GoldProjection(None, ZERO, G3, None, labels)
    a = run(lines={"t1": frozenset({"question"})})
    b = run(globals_={**G3, "cct": 4}, lines={"t1": frozenset({"sr"})})
    s = session(human=h, A=[a, b])
    turns = [TurnView(t, "c", True, "two words", None, None) for t in ("t1", "t2")]
    ls = LineSession("s1", h, turns, s.runs)
    result = reliability([s], ["A"], line_sessions=[ls])["A"]["repeat_agreement"]
    assert result["globals"] == {"value": .75, "n": 4, "agree": 3, "na": None}
    assert result["lines"] == {"value": .5, "n": 2, "agree": 1, "na": None}
    one = reliability([replace(s, runs={"A": [a]})], ["A"])["A"]["repeat_agreement"]
    assert one["globals"]["value"] is None and one["globals"]["na"]
    assert one["lines"]["value"] is None and one["lines"]["na"]


def test_head_to_head_counts_shared_sessions_once_with_ties():
    sessions = [session("win", A=[run(1)] * 3, B=[run(2)]),
                session("tie", A=[run(1)], B=[run(1)]),
                session("lose", A=[run(3)], B=[run(1)]),
                session("missing", A=[run()], B=[]),
                session("unparseable", A=[replace(run(), status="unparseable")], B=[run()])]
    pair = head_to_head(sessions, ["A", "B"])[0]
    assert pair == {"a": "A", "b": "B", "a_closer": 1, "b_closer": 1, "ties": 1, "n": 3,
                    "na": None}


def test_grid_length_observed_and_operations_are_payload_values():
    s = session(A=[run(8), run(10), run(12)])
    s = replace(s, human=replace(s.human, counts={**ZERO, "question": 10}))
    turns = [TurnView("t1", "c", True, "one two three", None, None),
             TurnView("t2", "p", False, "four five", None, None)]
    ops = {"A": {"cost": {"per_run_usd": .25, "n": 3, "na": None},
                 "time": {"mean_seconds": 9, "n": 3}, "failures": []}}
    payload = compute_analysis([s], ["A"], ops,
                               line_sessions=[LineSession("s1", s.human, turns, s.runs)])
    cell = payload["grid"][0]["cells"]["A"]
    assert cell["off"] == pytest.approx(4 / 3) and cell["n"] == 1 and cell["repeats"] == 3
    assert payload["error_vs_length"][0] == {"session_id": "s1", "combo_key": "A",
        "off": pytest.approx(4 / 3), "turns": 2, "words": 5, "n": 1, "repeats": 3}
    assert payload["reliability"]["A"]["time"] == ops["A"]["time"]
    assert observed_range([8, 10, 12]) == {"min": 8, "max": 12, "n": 3}
    assert observed_range([]) == {"min": None, "max": None, "n": 0}


def test_verdict_never_names_na_or_skipped_winner_and_claims_are_grounded():
    payload = {"count_error": {
        "safe": {"off": 2.5, "n": 1, "na": None},
        "missing": {"off": None, "n": 0, "na": {"reason": "not labeled"}},
        "skipped": {"off": 0, "n": 8, "na": None}}, "skipped_combos": ["skipped"]}
    clauses = build_verdict(payload)
    assert len(clauses) == 1 and "1 session" in clauses[0]["text"]
    assert "missing" not in clauses[0]["text"] and "skipped" not in clauses[0]["text"]
    assert clauses[0]["claims"] == [{"metric": "count_error", "combo": "safe", "value": 2.5, "n": 1}]
    assert "2.5" in clauses[0]["text"]
    assert build_verdict({"count_error": {"missing": payload["count_error"]["missing"]}}) == []
    result = compute_analysis([session(A=[run()], skipped=[run()])], ["A", "skipped"], {},
                              skipped_combos=["skipped"])
    assert result["count_error"]["skipped"]["na"]
    assert all("skipped" not in c["text"] for c in result["verdict"])


def test_partial_labels_undefined_repeats_and_empty_analysis_stay_na():
    h = GoldProjection(None, {"question": 2, "sr": 1, "cr": 1}, {}, None, None)
    s = session(human=h, A=[run(2), run(0)])
    levels = reliability([s], ["A"])["A"]["levels"]
    for metric in ("technical", "relational", "reflection_question_ratio"):
        assert levels[metric]["value"] is None
        assert levels[metric]["n"] == 0 and levels[metric]["na"]
    empty = compute_analysis([], [], {})
    assert empty["verdict"] == [] and empty["frontier"]["points"] == []
    assert empty["baseline"]["value"] is None


def test_unavailable_error_cannot_enter_frontier_and_zero_n_cannot_win():
    cells = {"no-human": {"off": None, "n": 0, "na": {"reason": "not labeled"}},
             "empty": {"off": 0, "n": 0, "na": None}}
    assert frontier(cells, {})["points"] == []
    assert frontier(cells, {})["unpriced"] == []
    assert build_verdict({"count_error": cells}) == []


def test_tied_verdict_clauses_use_each_payload_n():
    payload = {"count_error": {c: {"off": 1.25, "n": 2, "na": None} for c in ("A", "B")}}
    clauses = build_verdict(payload)
    assert len(clauses) == 2
    for clause in clauses:
        assert "Tied lowest" in clause["text"] and "2 sessions" in clause["text"]
        for claim in clause["claims"]:
            cell = payload[claim["metric"]][claim["combo"]]
            assert claim["value"] == cell["off"] and claim["n"] == cell["n"]
