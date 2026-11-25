"""SP06 Task 3: session-balanced counts, globals, cohorts and cells (pure, in-memory inputs)."""
import pytest
from onolys_eval.gold import COUNT_IDS, GLOBAL_IDS
from onolys_eval.summary.gold_view import GoldProjection
from onolys_eval.summary.run_report import ParsedRun
from onolys_eval.summary.session_metrics import SessionInput, compute_metrics

ZERO = dict.fromkeys(COUNT_IDS, 0)
G3 = dict.fromkeys(GLOBAL_IDS, 3)


def human(counts=None, globals_=None):
    return GoldProjection(None, dict(counts if counts is not None else ZERO),
                          dict(globals_ if globals_ is not None else G3), None, None)


def run(counts=None, globals_=None):
    return ParsedRun("miti", "ok", None, {**ZERO, **(counts or {})}, dict(globals_ or G3))


def sess(sid, h, **combos):
    return SessionInput(sid, h, combos)


def q(n):
    return {"question": n}


def test_golden_repeat_mean_miss_then_session_average():
    s1 = sess("s1", human({**ZERO, **q(10)}), A=[run(q(8)), run(q(10)), run(q(12))])
    s2 = sess("s2", human({**ZERO, **q(6)}), A=[run(q(8))] * 3)
    one = compute_metrics([s1], ["A"]).cells["question"]["A"]
    assert one["off"] == pytest.approx(4 / 3) and one["n"] == 1 and one["repeats"] == 3
    assert one["bias"] == pytest.approx(0) and one["observed"] == {"min": 8, "max": 12, "n": 3}
    two = compute_metrics([s1, s2], ["A"]).cells["question"]["A"]
    assert two["off"] == pytest.approx(5 / 3) and two["n"] == 2 and two["repeats"] == 3
    assert two["value"] == pytest.approx((10 + 8) / 2) and two["bias"] == pytest.approx(1)


def test_cohort_11_paired_of_12_and_real_zeros():
    sessions = []
    for i in range(12):
        runs = {"A": [run(q(0))], "B": [run(q(1))]}
        if i == 4:
            runs["A"] = []
        sessions.append(sess(f"s{i}", human(), **runs))
    m = compute_metrics(sessions, ["A", "B"])
    assert m.cohorts["question"] == {"paired": 11, "of": 12}
    assert m.cells["question"]["A"]["n"] == 11 and m.cells["question"]["A"]["off"] == 0  # real zero kept
    assert m.cells["question"]["B"]["off"] == pytest.approx(1)
    assert m.cells["question"]["A"]["best"] and not m.cells["question"]["B"]["best"]
    assert m.cells["question"]["A"]["of"] == 12


def test_cohort_over_requested_combos_only():
    s = [sess("s1", human(), A=[run()], B=[]), sess("s2", human(), A=[run()], B=[run()])]
    assert compute_metrics(s, ["A"]).cohorts["question"]["paired"] == 2
    assert compute_metrics(s, ["A", "B"]).cohorts["question"]["paired"] == 1


def test_annomi_partial_labels():
    labeled = {"question": 2, "sr": 3, "cr": 1, "gi": 0}
    s = [sess("s1", human(labeled, {}), A=[run({"question": 2, "sr": 3, "cr": 1}, {})])]
    m = compute_metrics(s, ["A"])
    for code in ("persuade", "confront", "affirm", "seek_collab", "emphasize_autonomy",
                 "persuade_permission"):
        assert m.cells[code]["A"]["na"] == {"reason": "not labeled in this dataset"}
        assert m.cells[code]["A"]["value"] is None and m.cells[code]["A"]["n"] == 0
    for g in GLOBAL_IDS:
        assert m.cells[g]["A"]["na"]["reason"] == "not labeled in this dataset"
    for t in ("technical", "relational"):
        assert m.cells[t]["A"]["na"] == {"reason": "needs cct, sst, partnership, empathy"}
    assert m.cells["reflection_question_ratio"]["A"]["value"] == pytest.approx(2.0)
    assert m.cells["pct_cr"]["A"]["value"] == pytest.approx(0.25)
    assert m.cells["count_error"]["A"]["codes_labeled"] == 4
    assert m.cells["count_error"]["A"]["off"] == 0


def test_divide_by_zero_is_na_and_reported():
    h = human({**ZERO, "question": 2, "sr": 3, "cr": 1})
    ok = sess("s1", h, A=[run({"question": 2, "sr": 3, "cr": 1})])
    bad_repeat = sess("s2", h, A=[run({"question": 2, "sr": 3, "cr": 1}), run({"sr": 3})])
    zero_human = sess("s3", human({**ZERO, "sr": 3}), A=[run({"question": 1, "sr": 3})])
    m = compute_metrics([ok, bad_repeat, zero_human], ["A"])
    cell = m.cells["reflection_question_ratio"]["A"]
    assert cell["n"] == 1 and cell["off"] == 0
    assert {(e["session_id"], e["combo_key"]) for e in m.excluded
            if e["metric"] == "reflection_question_ratio"} == {("s2", "A"), ("s3", None)}
    assert {e["reason"] for e in m.excluded
            if e["metric"] == "reflection_question_ratio"} == {"no Questions in this session"}
    only_bad = compute_metrics([zero_human], ["A"]).cells["reflection_question_ratio"]["A"]
    assert only_bad["value"] is None and only_bad["na"] is not None and only_bad["n"] == 0


def test_ratio_has_no_tolerance_but_best_is_marked():
    h = human({**ZERO, "question": 2, "sr": 2, "cr": 2})
    s = [sess("s1", h, A=[run({"question": 2, "sr": 2, "cr": 2})], B=[run({"question": 1, "sr": 2, "cr": 2})])]
    row = compute_metrics(s, ["A", "B"]).cells["reflection_question_ratio"]
    assert row["A"]["within_tolerance"] is None and row["A"]["best"] and not row["B"]["best"]


@pytest.mark.parametrize("misses,ok", [(60, True), (61, False)])  # off 0.60 / 0.61 lines
def test_count_tolerance_edges(misses, ok):
    s = [sess("s1", human(), A=[run({"question": 1})] * misses + [run()] * (100 - misses))]
    cell = compute_metrics(s, ["A"]).cells["question"]["A"]
    assert cell["off"] == pytest.approx(misses / 100) and cell["within_tolerance"] is ok


@pytest.mark.parametrize("misses,ok", [(40, True), (41, False)])  # off 0.40 / 0.41 points
def test_global_tolerance_edges(misses, ok):
    total = 100
    s = [sess("s1", human(), A=[run(globals_={**G3, "cct": 4})] * misses
              + [run()] * (total - misses))]
    cell = compute_metrics(s, ["A"]).cells["cct"]["A"]
    assert cell["off"] == pytest.approx(misses / total)  # 0.4 and 0.41
    assert cell["within_tolerance"] is ok and cell["value"] is None


def test_global_buckets_per_interview_then_averaged():
    s1 = sess("s1", human(), A=[run(globals_={**G3, "cct": 3}), run(globals_={**G3, "cct": 4}),
                                 run(globals_={**G3, "cct": 5}), run(globals_={**G3, "cct": 3})])
    s2 = sess("s2", human(), A=[run(globals_={**G3, "cct": 5})])
    cell = compute_metrics([s1, s2], ["A"]).cells["cct"]["A"]
    assert cell["buckets"] == {"same": pytest.approx((0.5 + 0) / 2), "off1": pytest.approx(0.25 / 2),
                               "off2plus": pytest.approx((0.25 + 1) / 2)}
    assert cell["within_1"] == pytest.approx(cell["buckets"]["same"] + cell["buckets"]["off1"])


def test_count_error_sums_codes_then_averages_sessions():
    s1 = sess("s1", human(), A=[run({"question": 2, "sr": 1}), run({"question": 4})])
    s2 = sess("s2", human(), A=[run({"sr": 2})])
    cell = compute_metrics([s1, s2], ["A"]).cells["count_error"]["A"]
    assert cell["off"] == pytest.approx(((3 + 0.5) + 2) / 2)
    assert cell["codes_labeled"] == 10 and cell["n"] == 2


def test_every_cell_has_n_and_no_runs_is_na():
    m = compute_metrics([sess("s1", human(), A=[run()], B=[])], ["A", "B"])
    for row in m.cells.values():
        for cell in row.values():
            assert "n" in cell and "of" in cell
    assert m.cells["question"]["B"]["na"] == {"reason": "no completed runs"}
