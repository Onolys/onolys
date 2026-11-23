import pytest

from onolys_miti.prepare import prepare
from onolys_miti.result import CodedSpan
from onolys_miti.span import MAX_CODED_S, SpanChoice, default_window, select_coded_span
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
    c = default_window(session(MAX_CODED_S), "s1")
    assert isinstance(c, SpanChoice)
    assert c.coded_span is None and c.mode == "whole" and c.duration_s == MAX_CODED_S
    assert c.seed == "s1" and c.warnings == []


def test_over_20_min_picks_window_inside_session():
    total = 2470
    c = default_window(session(total), "s1")
    assert c.mode == "random_window" and c.duration_s == total
    span = c.coded_span
    assert span.end_ms - span.start_ms == MAX_CODED_S * 1000
    assert 0 <= span.start_ms and span.end_ms <= total * 1000
    assert isinstance(span, CodedSpan)
    assert [(w.code, w.severity) for w in c.warnings] == [("coded_window", "info")]
    assert "of a 41:10 session" in c.warnings[0].detail


def test_same_seed_same_window_across_calls():
    a = default_window(session(3000), "abc").coded_span
    b = default_window(session(3000), "abc").coded_span
    assert a == b


def test_stable_known_value_across_processes():
    # sha256-derived (not salted hash()): pinned so a change is noticed.
    c = default_window(session(3000), "abc")
    assert c.coded_span.start_ms == 63000


def test_different_seeds_vary():
    froms = {default_window(session(3600), f"seed-{i}").coded_span.start_ms for i in range(20)}
    assert len(froms) > 5


def test_no_timestamps_is_whole():
    t = Transcript(turns=[Turn(id="a", speaker="A", text="x"), Turn(id="b", speaker="B", text="y")])
    c = default_window(t, "s")
    assert c.coded_span is None and c.mode == "whole" and c.duration_s is None
    assert c.warnings == []


def test_duration_falls_back_to_start_ms():
    t = Transcript(turns=[Turn(id="a", speaker="A", text="x", start_ms=1_500_000)])
    c = default_window(t, "s")
    assert c.duration_s == 1500 and c.mode == "random_window"
    assert c.coded_span.start_ms <= 300000


def test_prepare_honors_caller_turn_span():
    p = prepare(session(1200), {"speaker_map": SM, "change_goal": "g", "coded_span": {"start_turn": 2, "end_turn": 12}})
    assert [rt.turn.id for rt in p.turns] == [f"t{i}" for i in range(2, 12)]
    assert p.duration_ms == 600000


def test_whole_default_does_not_choose_window():
    c = select_coded_span(session(1440), "s")
    assert c.mode == "whole" and c.coded_span is None and c.warnings == []


@pytest.mark.parametrize("span", [
    {}, {"start_turn": 0}, {"start_turn": -1, "end_turn": 2},
    {"start_turn": 2, "end_turn": 2}, {"start_turn": 0, "end_turn": 11},
    {"start_turn": 0.0, "end_turn": 2}, {"start_turn": False, "end_turn": 2},
    {"start_ms": 0, "end_ms": 60000, "start_turn": 0, "end_turn": 2},
    {"start_ms": 10, "end_ms": 0}, {"from_s": 0, "to_s": 60},
])
def test_invalid_explicit_spans_fail(span):
    from onolys_engine_core.errors import InputError
    with pytest.raises(InputError, match="invalid_coded_span") as error:
        prepare(session(600), {"speaker_map": SM, "change_goal": "g", "coded_span": span})
    assert error.value.code == "invalid_coded_span"


def test_word_limit_applies_to_coded_portion():
    from onolys_engine_core.errors import InputError
    t = Transcript(turns=[Turn(id=str(i), speaker="A" if i % 2 == 0 else "B", text="word " * 501) for i in range(12)])
    with pytest.raises(InputError, match="narrower coded_span") as error:
        prepare(t, {"speaker_map": SM, "change_goal": "g"})
    assert error.value.code == "session_too_long"
    assert len(prepare(t, {"speaker_map": SM, "change_goal": "g", "coded_span": {"start_turn": 0, "end_turn": 10}}).turns) == 10


def test_prepare_applies_engine_span_kwarg():
    t = session(3000)
    c = default_window(t, "s")
    p = prepare(t, {"speaker_map": SM, "change_goal": "g"}, coded_span=c.coded_span)
    assert 0 < len(p.turns) < len(t.turns)


@pytest.mark.parametrize("word_count", [6000, 6001])
def test_word_limit_boundary(word_count):
    from onolys_engine_core.errors import SessionTooLong
    words = ["word"] * word_count
    turns = [Turn(id=str(i), speaker="A" if i % 2 == 0 else "B", text=" ".join(words[i::10])) for i in range(10)]
    t = Transcript(turns=turns)
    if word_count > 6000:
        with pytest.raises(SessionTooLong, match="narrower coded_span"):
            prepare(t, {"speaker_map": SM, "change_goal": "g"})
    else:
        assert len(prepare(t, {"speaker_map": SM, "change_goal": "g"}).turns) == 10


def test_turn_span_duration_is_relative_to_selected_range():
    t = session(3000)
    span = {"start_turn": 30, "end_turn": 40}
    p = prepare(t, {"speaker_map": SM, "change_goal": "g", "coded_span": span})
    assert p.duration_ms == 600000
    assert [rt.turn.id for rt in p.turns] == [f"t{i}" for i in range(30, 40)]


def test_twenty_five_minutes_is_allowed():
    assert prepare(session(1500), {"speaker_map": SM, "change_goal": "g"}).duration_ms == 1500000
