"""Line alignment, presence P/R/F1, confusion with multi bucket (pure)."""
import pytest

from onolys_eval.summary.gold_view import GoldProjection, LineLabel
from onolys_eval.summary.line_metrics import (
    NO_LINE_OUTPUT,
    LineSession,
    compute_line_metrics,
    turn_agreement,
)
from onolys_eval.summary.projections import ParsedRun, TurnView

L = ("question", "sr", "cr", "gi")


def turns(n):  # odd turns are clinician
    return tuple(TurnView(f"t{i}", "A" if i % 2 else "B", bool(i % 2), f"x{i}", None, None)
                 for i in range(1, n + 1))


def human(rows):
    return GoldProjection(None, {}, {}, None, None if rows is None else tuple(
        LineLabel(t, tuple(c), None) for t, c in rows.items()))


def run(rows, engine="miti"):
    return ParsedRun(engine, "ok", None, turn_codes={t: frozenset(c) for t, c in rows.items()},
                     has_lines=engine == "miti")


def sess(sid, h, t, **combos):
    return LineSession(sid, h, t, combos)


def test_confusion_total_plus_multi_equals_aligned_and_masking():
    h = human({"t1": ["question"], "t3": ["sr"], "t5": ["cr", "affirm"], "t7": [], "t9": ["gi"],
               "t2": ["question"]})  # t2 is a client turn: not aligned
    r = run({"t1": ["question"], "t3": ["cr"], "t5": ["cr", "sr"], "t7": ["question", "gi"],
             "t9": ["persuade"]})  # persuade masked -> none
    m = compute_line_metrics([sess("s", h, turns(10), A=[r])], ["A"], L)
    c = m.combos["A"]
    assert m.missing is None and m.codes_labeled == L
    assert c.aligned == 5
    conf = c.confusion
    total = sum(v for row in conf.values() for v in row.values())
    assert total + c.multi == c.aligned == 5
    assert c.multi == 2  # t5 (sr+cr combo), t7 (two combo codes)
    assert conf["question"]["question"] == 1 and conf["sr"]["cr"] == 1
    assert conf["gi"]["none"] == 1  # persuade masked on the combo side
    # t5: human {cr} after masking affirm, combo {cr, sr}: not exact
    assert c.line_accuracy == pytest.approx(1 / 5)


def test_presence_prf_and_macro_f1_multi_code_turn():
    h = human({"t1": ["cr", "sr"], "t3": ["question"], "t5": []})
    r = run({"t1": ["cr"], "t3": ["question"], "t5": ["question"]})
    c = compute_line_metrics([sess("s", h, turns(6), A=[r])], ["A"], L).combos["A"]
    cr, sr, q = c.per_code["cr"], c.per_code["sr"], c.per_code["question"]
    assert (cr["p"], cr["r"], cr["f1"]) == (1.0, 1.0, 1.0)
    assert sr["p"] is None and sr["r"] == 0.0 and sr["f1"] == 0.0
    assert q["p"] == 0.5 and q["r"] == 1.0 and q["f1"] == pytest.approx(2 / 3)
    assert c.per_code["gi"]["f1"] is None  # absent both sides
    assert c.macro_f1 == pytest.approx((1.0 + 0.0 + 2 / 3) / 3)


def test_repeats_then_sessions_average():
    h = human({"t1": ["question"], "t3": ["question"]})
    good, bad = run({"t1": ["question"], "t3": ["question"]}), run({"t1": ["question"]})
    s1 = sess("s1", h, turns(4), A=[good, bad])  # accuracy 1.0, 0.5 -> 0.75
    s2 = sess("s2", h, turns(4), A=[bad])  # 0.5
    c = compute_line_metrics([s1, s2], ["A"], L).combos["A"]
    assert c.line_accuracy == pytest.approx((0.75 + 0.5) / 2)
    assert c.aligned == 4 and c.repeats == 2 and c.sessions == 2


def test_oneshot_lane_and_missing_human_hlqc_phac():
    h = human({"t1": ["question"]})
    m = compute_line_metrics([sess("s", h, turns(2), O=[run({}, "oneshot:x")])], ["O"], L)
    assert m.combos["O"].lane == NO_LINE_OUTPUT == "no line-level output"
    assert m.combos["O"].per_code == {} and m.combos["O"].line_accuracy is None
    none = compute_line_metrics([sess("s", human(None), turns(2), A=[run({})])], ["A"], ())
    assert none.missing == "human" and none.combos == {}


def test_dataset_notes_annomi_and_agreement():
    h = human({"t1": ["question"]})
    s = [sess("s", h, turns(2), A=[run({"t1": ["question"]})])]
    assert compute_line_metrics(s, ["A"], L, dataset_id="annomi").dataset_notes
    assert not compute_line_metrics(s, ["A"], L, dataset_id="casaa-miti-practice").dataset_notes
    rs = [run({"t1": ["question"]}), run({"t1": ["sr"]}), run({})]
    assert turn_agreement({"question"}, rs, "t1", L) == {"k": 1, "r": 3}
