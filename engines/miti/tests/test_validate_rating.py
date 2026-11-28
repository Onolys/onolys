"""validate_rating, draft vs final. Code only; Issues carry no text."""

import copy
import logging

import pytest
from onolys_engine_core.json_logging import render

from onolys_miti import miti
from onolys_miti.rating import is_no_rating, validate_rating
from onolys_miti.report import Issue

pytestmark = pytest.mark.unit


def ids(kind):
    return [i["id"] for i in miti.MITI.items if i["kind"] == kind]


@pytest.fixture
def full():
    return {
        "change_goal": "cut down drinking",
        "coded_span": {"from_s": 0, "to_s": 1200},
        "globals": {
            g: {"score": 3, "reason": "r", "example": {"at_s": 12, "text": "t"}}
            for g in ids("global")
        },
        "counts": {c: {"count": 2, "note": "n"} for c in ids("count")},
        "notes": "some notes",
    }


def codes(issues):
    return {(i.path, i.code) for i in issues}


def test_full_card_valid_draft_and_final(full):
    assert validate_rating(full, False) == []
    assert validate_rating(full, True) == []
    assert not is_no_rating(full)


def test_partial_two_globals_valid():
    g = ids("global")[:2]
    card = {"change_goal": "x", "globals": {k: {"score": 4} for k in g}}
    assert validate_rating(card, True) == []
    assert not is_no_rating(card)


def test_all_null_valid_and_no_rating(full):
    card = {"change_goal": "x", "globals": {g: {"score": None} for g in ids("global")},
            "counts": {c: {"count": None} for c in ids("count")}, "notes": ""}
    assert validate_rating(card, True) == []
    assert is_no_rating(card)
    assert is_no_rating({"change_goal": "x"})
    assert is_no_rating({"change_goal": "x", "notes": "   "})
    assert not is_no_rating({"notes": "hello"})
    assert not is_no_rating({"counts": {ids("count")[0]: {"count": 0}}})


def test_over_limit(full):
    g, c = ids("global")[0], ids("count")[0]
    ok = copy.deepcopy(full)
    ok["globals"][g]["reason"] = "a" * 1000
    ok["globals"][g]["example"]["text"] = "a" * 1000
    ok["counts"][c]["note"] = "a" * 1000
    ok["notes"] = "a" * 3000
    assert validate_rating(ok, True) == []
    bad = copy.deepcopy(ok)
    bad["globals"][g]["reason"] += "a"
    bad["globals"][g]["example"]["text"] += "a"
    bad["notes"] += "a"
    assert codes(validate_rating(bad, False)) == {
        (f"globals/{g}/reason", "too_long"),
        (f"globals/{g}/example/text", "too_long"),
        ("notes", "too_long"),
    }
    bad["counts"][c]["note"] += "a"
    assert (f"counts/{c}/note", "too_long") in codes(validate_rating(bad, True))


@pytest.mark.parametrize("score", [0, 6, -1])
def test_out_of_range_score(score):
    g = ids("global")[0]
    got = validate_rating({"globals": {g: {"score": score}}}, False)
    assert codes(got) == {(f"globals/{g}/score", "out_of_range")}


def test_bad_score_and_count_types():
    g, c = ids("global")[0], ids("count")[0]
    got = validate_rating({"globals": {g: {"score": "3"}},
                                 "counts": {c: {"count": 1.5}}}, False)
    assert codes(got) == {(f"globals/{g}/score", "invalid_type"),
                          (f"counts/{c}/count", "invalid_type")}
    assert codes(validate_rating({"counts": {c: {"count": -1}}}, False)) == {
        (f"counts/{c}/count", "out_of_range")}
    assert codes(validate_rating({"globals": {g: {"score": True}}}, False)) == {
        (f"globals/{g}/score", "invalid_type")}


def test_unknown_keys():
    g, c = ids("global")[0], ids("count")[0]
    got = codes(validate_rating({
        "bogus": 1,
        "globals": {"nope": {"score": 3}, c: {"score": 3}, g: {"extra": 1}},
        "counts": {"nope2": {"count": 1}, g: {"count": 1}},
    }, False))
    assert got == {("bogus", "unknown_key"), ("globals/nope", "unknown_key"),
                   (f"globals/{c}", "unknown_key"), (f"globals/{g}/extra", "unknown_key"),
                   ("counts/nope2", "unknown_key"), (f"counts/{g}", "unknown_key")}


def test_bad_span():
    assert codes(validate_rating({"coded_span": {"from_s": 50, "to_s": 10}}, False)) == {
        ("coded_span", "order")}
    assert codes(validate_rating({"coded_span": {"from_s": -1, "to_s": 10}}, False)) == {
        ("coded_span/from_s", "out_of_range")}
    assert validate_rating({"coded_span": None}, False) == []
    assert validate_rating({"coded_span": {"from_s": 5, "to_s": 5}}, False) == []


def test_draft_empty_change_goal_passes_final_fails():
    for card in ({"change_goal": ""}, {"change_goal": "   "}, {}, {"change_goal": None}):
        assert validate_rating(card, False) == []
        assert codes(validate_rating(card, True)) == {("change_goal", "required")}


def test_not_an_object():
    assert codes(validate_rating([1], False)) == {("", "invalid_type")}
    assert codes(validate_rating(None, True)) == {("", "invalid_type")}


def test_issue_has_no_text():
    secret = "SECRET-PHI-TEXT"
    g = ids("global")[0]
    got = validate_rating({"globals": {g: {"score": 9, "reason": secret * 200}},
                                 secret: secret}, True)
    assert got and all(isinstance(i, Issue) for i in got)
    assert all(secret not in i.code and secret * 2 not in i.path for i in got)


def rendered(caplog):
    return "\n".join(render(r) for r in caplog.records)


def test_no_text_logged(caplog):
    secret = "SECRET-PHI-TEXT"
    g = ids("global")[0]
    card = {"change_goal": secret, "notes": secret,
            "globals": {g: {"score": 2, "reason": secret, "example": {"text": secret}}}}
    with caplog.at_level(logging.DEBUG, logger="miti"):
        validate_rating(card, True)
        validate_rating({"notes": secret * 1000, "globals": {g: {"score": 99}}}, False)
    assert caplog.records, "expected a validation log event"
    assert secret not in rendered(caplog)
