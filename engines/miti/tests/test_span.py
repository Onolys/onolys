import pytest

from onolys_miti.prepare import prepare
from onolys_miti.result import CodedSpan
from onolys_miti.span import MAX_CODED_S, SpanChoice, select_coded_span
from onolys_miti.transcript import Transcript, Turn

pytestmark = pytest.mark.unit

SM = {"subject": "A", "other": "B"}


def session(total_s, step_s=60):
    """Alternating A/B turns every `step_s`, last turn ends at total_s."""
    turns, t, i = [], 0, 0
    while t < total_s:
        end = min(t + step_s, total_s)
        turns.append(
            Turn(id=f"t{i}", speaker="A" if i % 2 == 0 else "B", text="x y z",
                 start_ms=t * 1000, end_ms=end * 1000)
        )
        t, i = end, i + 1
    return Transcript(turns=turns)


def test_at_most_20_min_is_whole():
    c = select_coded_span(session(MAX_CODED_S), "s1")
    assert isinstance(c, SpanChoice)
    assert c.coded_span is None and c.mode == "whole" and c.duration_s == MAX_CODED_S
    assert c.seed == "s1" and c.warnings == []


def test_over_20_min_picks_window_inside_session():
    total = 2470
    c = select_coded_span(session(total), "s1")
    assert c.mode == "random_window" and c.duration_s == total
    span = c.coded_span
    assert span.to_s - span.from_s == MAX_CODED_S
    assert 0 <= span.from_s and span.to_s <= total
    assert isinstance(span, CodedSpan)
    assert [(w.code, w.severity) for w in c.warnings] == [("coded_window", "info")]
    assert "of a 41:10 session" in c.warnings[0].detail


def test_same_seed_same_window_across_calls():
    a = select_coded_span(session(3000), "abc").coded_span
    b = select_coded_span(session(3000), "abc").coded_span
    assert a == b


def test_stable_known_value_across_processes():
    # sha256-derived (not salted hash()): pinned so a change is noticed.
    c = select_coded_span(session(3000), "abc")
    assert c.coded_span.from_s == 63


def test_different_seeds_vary():
    froms = {select_coded_span(session(3600), f"seed-{i}").coded_span.from_s for i in range(20)}
    assert len(froms) > 5


def test_no_timestamps_is_whole_with_span_ignored():
    t = Transcript(turns=[Turn(id="a", speaker="A", text="x"), Turn(id="b", speaker="B", text="y")])
    c = select_coded_span(t, "s")
    assert c.coded_span is None and c.mode == "whole" and c.duration_s is None
    assert [w.code for w in c.warnings] == ["span_ignored"]


def test_duration_falls_back_to_start_ms():
    t = Transcript(turns=[Turn(id="a", speaker="A", text="x", start_ms=1_500_000)])
    c = select_coded_span(t, "s")
    assert c.duration_s == 1500 and c.mode == "random_window"
    assert c.coded_span.from_s <= 300


def test_prepare_ignores_caller_coded_span_param():
    t = session(600)
    base = prepare(t, {"speaker_map": SM, "change_goal": "g"})
    given = prepare(t, {"speaker_map": SM, "change_goal": "g", "coded_span": {"from_s": 0, "to_s": 60}})
    assert len(given.turns) == len(base.turns) and given.warnings == base.warnings


def test_prepare_applies_engine_span_kwarg():
    t = session(3000)
    c = select_coded_span(t, "s")
    p = prepare(t, {"speaker_map": SM, "change_goal": "g"}, coded_span=c.coded_span)
    assert 0 < len(p.turns) < len(t.turns)
