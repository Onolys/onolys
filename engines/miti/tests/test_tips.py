"""Tips proposed by the model, validated in code; stub client only."""

import asyncio
import json
import re

import pytest
from _report_fixtures import load
from onolys_engine.llm import LLMBadOutput, StubClient
from onolys_engine.llm.fixture_client import FailingClient
from onolys_engine.transcript import Transcript

from onolys_miti.result import MitiResult
from onolys_miti.tips import LIMITS_MESSAGE, ROUTE, generate_tips

pytestmark = pytest.mark.unit


# (item, clinician turn, quote copied from the fixture transcript)
Q = {
    "t4": "What makes walking more important to you right now?",
    "t6": "You want to be there for your kids",
    "t9": "Where would a walk fit best in your week?",
    "t11": "Three days a week at lunchtime feels doable to you.",
    "t13": "Why a six and not a three?",
    "t15": "Would it be helpful if I shared some ideas",
    "t17": "What would you like to",
}
ITEMS = ["cct", "sst", "partnership", "empathy", "cr", "question"]


@pytest.fixture(scope="module")
def transcript():
    return Transcript.model_validate(load("transcript.json"))


@pytest.fixture(scope="module")
def smap():
    return load("speaker_map.json")


@pytest.fixture(scope="module")
def result():
    return MitiResult.model_validate(load("miti_result.json"))


def tip(item="cct", turn="t4", quote=None, alt="Try reflecting the goal first, then ask.", **kw):
    return {
        "item_id": item,
        "observation": kw.get("observation", "Onolys reads this as a closed prompt."),
        "quote": {"turn_id": turn, "text": quote if quote is not None else Q[turn]},
        "alternative": alt,
        "why_it_matters": kw.get("why", "Open wording invites more of the client's own reasons."),
    }


def good(n):
    specs = [("cct", "t4"), ("sst", "t6"), ("partnership", "t9"), ("empathy", "t11"),
             ("cr", "t13"), ("question", "t15"), ("gi", "t17")]
    return [tip(i, t, alt=f"Try option {k} in plain words.") for k, (i, t) in enumerate(specs[:n])]


def run(replies, transcript, smap, result):
    """replies: list of dicts (returned in order) or exceptions to raise."""
    stub, seen = StubClient(), []

    def handler(req):
        seen.append(req)
        r = replies[len(seen) - 1]
        if isinstance(r, BaseException):
            raise r
        return {"tips": r}

    for tag in ("tips:r0", "tips:r0:retry"):
        stub.register(tag, handler)
    out = asyncio.run(generate_tips(stub, transcript, smap, result))
    return out, seen


def codes(warnings):
    return [w.code for w in warnings]


def test_valid_three_to_five_ranked_with_real_offsets(transcript, smap, result):
    (art, warns), seen = run([good(7)], transcript, smap, result)
    assert len(seen) == 1 and seen[0].tier == ROUTE == "tips"
    assert [t.rank for t in art.valid] == [1, 2, 3, 4, 5]  # first five kept
    assert warns == [] and len(art.proposals) == 7
    turns = {t.id: t.text for t in transcript.turns}
    for t in art.valid:
        q = t.quote
        assert turns[q.turn_id][q.start:q.end] == q.text


def test_optional_idea_title_is_kept_and_legacy_tips_still_work(transcript, smap, result):
    proposals = good(3)
    proposals[0]["title"] = "  Reflect the client's reasons first  "
    (art, warns), _ = run([proposals], transcript, smap, result)
    assert warns == []
    assert art.valid[0].title == "Reflect the client's reasons first"
    assert art.valid[1].title is None


def test_idea_title_obeys_the_same_tone_validation(transcript, smap, result):
    bad = tip()
    bad["title"] = "You should have listened."
    (art, _), _ = run([[bad, *good(3)]], transcript, smap, result)
    assert all(t.title != bad["title"] for t in art.valid)
    assert len(art.valid) == 3


def test_quote_replaced_by_actual_substring(transcript, smap, result):
    sloppy = tip("cct", "t4", quote="what makes  walking more important to you right now")
    (art, _), _ = run([[sloppy, *good(3)[1:]], ], transcript, smap, result)
    first = art.valid[0].quote
    assert first.text == "What makes walking more important to you right now"
    assert first.text == transcript.turns[3].text[first.start:first.end]


def test_invented_quote_rejected(transcript, smap, result):
    bad = tip("cct", "t4", quote="Have you considered joining a gym this month?")
    (art, _), seen = run([[bad, *good(3)], [bad]], transcript, smap, result)
    assert all(t.quote.text != bad["quote"]["text"] for t in art.valid)
    assert len(art.valid) == 3


def test_non_clinician_turn_rejected(transcript, smap, result):
    client_tip = tip("cct", "t3", quote="I sit at a desk all day")
    (art, _), _ = run([[client_tip, *good(3)]], transcript, smap, result)
    assert [t.quote.turn_id for t in art.valid] == ["t4", "t6", "t9"]


def test_unknown_item_and_unknown_turn_rejected(transcript, smap, result):
    bad = [tip("nope", "t4"), tip("cct", "t99", quote="x"), *good(4)[1:]]
    (art, _), _ = run([bad], transcript, smap, result)
    assert [t.item_id for t in art.valid] == ["sst", "partnership", "empathy"]


def test_banned_tone_rejected(transcript, smap, result):
    bad = tip("cct", "t4", alt="You should have asked about the goal.")
    bad2 = tip("sst", "t6", observation="This was a mistake.")
    (art, _), _ = run([[bad, bad2, *good(5)[2:]]], transcript, smap, result)
    assert [t.item_id for t in art.valid] == ["partnership", "empathy", "cr"]


def test_alternative_rules(transcript, smap, result):
    empty = tip("cct", "t4", alt="   ")
    long = tip("sst", "t6", alt="One idea. Two ideas. Three ideas.")
    same = tip("partnership", "t9", alt=Q["t9"])
    two_ok = tip("empathy", "t11", alt="Name the feeling first. Then check it out.")
    (art, _), _ = run([[empty, long, same, two_ok, *good(7)[4:]]], transcript, smap, result)
    assert [t.item_id for t in art.valid] == ["empathy", "cr", "question", "gi"]


def test_caps_two_per_item_one_per_item_turn(transcript, smap, result):
    a = tip("cct", "t4", alt="Alt a one.")
    dup = tip("cct", "t4", quote="important to you right now", alt="Alt b one.")  # same (item,turn)
    b = tip("cct", "t6", alt="Alt c one.")
    c = tip("cct", "t9", alt="Alt d one.")  # third for cct
    (art, _), _ = run([[a, dup, b, c, *good(5)[1:4]]], transcript, smap, result)
    got = [(t.item_id, t.quote.turn_id) for t in art.valid]
    assert got.count(("cct", "t4")) == 1
    assert sum(1 for i, _ in got if i == "cct") == 2
    assert len(got) == 5


def test_retry_lists_violations_then_fewer_tips(transcript, smap, result):
    first = [good(1)[0], tip("cct", "t6", quote="made up words here")]
    second = [tip("sst", "t6")]
    (art, warns), seen = run([first, second], transcript, smap, result)
    assert len(seen) == 2 and seen[1].call_tag == "tips:r0:retry"
    assert "violations" not in json.loads(seen[0].user)
    v = json.loads(seen[1].user)["violations"]
    assert any(x["code"] == "quote_not_found" for x in v)
    assert "made up words here" not in seen[1].user  # codes only, no offending text
    assert [t.item_id for t in art.valid] == ["cct", "sst"]
    assert codes(warns) == ["fewer_tips"]
    assert len(art.proposals) == 3


def test_retry_reaches_three_no_warning(transcript, smap, result):
    (art, warns), seen = run([good(1), good(4)[1:]], transcript, smap, result)
    assert len(art.valid) == 4 and warns == [] and len(seen) == 2


def test_zero_valid_ships_empty_with_fewer_tips(transcript, smap, result):
    bad = [tip("cct", "t3", quote="I sit at a desk all day")]
    (art, warns), seen = run([bad, bad], transcript, smap, result)
    assert art.valid == [] and codes(warns) == ["fewer_tips"] and len(seen) == 2


def test_call_error_is_tips_failed(transcript, smap, result):
    stub = FailingClient(RuntimeError("boom"))
    art, warns = asyncio.run(generate_tips(stub, transcript, smap, result))
    assert art.valid == [] and art.proposals == [] and codes(warns) == ["tips_failed"]


def test_bad_output_twice_is_tips_failed(transcript, smap, result):
    bad = LLMBadOutput("truncated")
    (art, warns), seen = run([bad, bad], transcript, smap, result)
    assert len(seen) == 2 and art.valid == [] and codes(warns) == ["tips_failed"]


def test_bad_output_then_good_recovers(transcript, smap, result):
    (art, warns), _ = run([LLMBadOutput("x"), good(3)], transcript, smap, result)
    assert len(art.valid) == 3 and warns == []


def test_prompt_has_no_clinician_rating_or_diff(transcript, smap, result):
    (_, _), seen = run([good(3)], transcript, smap, result)
    req = seen[0]
    blob = json.dumps(
        [req.system, req.user, req.cache_prefixes, req.cache_prefix], ensure_ascii=False
    ).lower()
    for word in ("clinician_rating", "clinician rating", "diff", "differs", "flagged", "agree",
                 "within_one", "self-rating", "self_rating", "rating card"):
        assert not re.search(rf"\b{re.escape(word)}\b", blob), word
    user = json.loads(req.user)
    assert set(user) == {"change_goal", "onolys", "clinician_turns"}
    assert set(user["onolys"]) == {"counts", "instances", "globals", "summaries"}
    # clinician turns only, each with the preceding client turn as context
    ids = [t["turn_id"] for t in user["clinician_turns"]]
    assert "t3" not in ids and "t4" in ids
    t4 = next(t for t in user["clinician_turns"] if t["turn_id"] == "t4")
    assert t4["preceding_client_turn"]["turn_id"] == "t3"
    assert "temperature" not in req.__dict__ or req.temperature == 0.0


def test_deadline_reaches_both_attempts(transcript, smap, result):
    stub, seen = StubClient(), []

    def handler(req):
        seen.append(req)
        return {"tips": good(1)}

    for tag in ("tips:r0", "tips:r0:retry"):
        stub.register(tag, handler)
    asyncio.run(generate_tips(stub, transcript, smap, result, deadline=77.0))
    assert len(seen) == 2 and [r.deadline for r in seen] == [77.0, 77.0]


def test_overlong_title_drops_that_tip_with_field_too_long(transcript, smap, result):
    bad = tip()
    bad["title"] = "x " * 60  # 120 chars > 80
    from onolys_miti.tips import _clinician_turns, _Proposal, validate_proposals

    turns = _clinician_turns(transcript, smap, result)
    valid, violations = validate_proposals([_Proposal(**bad), *[_Proposal(**p) for p in good(3)]], turns)
    assert violations == [{"index": 0, "code": "field_too_long", "message": LIMITS_MESSAGE}]
    for n in ("title 80", "observation 400", "alternative 400", "why_it_matters 300", "quote text 500"):
        assert n in LIMITS_MESSAGE
    assert len(valid) == 3


def test_retry_for_field_too_long_tells_the_model_the_limits(transcript, smap, result):
    bad = tip()
    bad["title"] = "x " * 60
    (_, _), seen = run([[bad, *good(2)], good(4)], transcript, smap, result)
    v = json.loads(seen[1].user)["violations"]
    assert v == [{"index": 0, "code": "field_too_long", "message": LIMITS_MESSAGE}]
    assert "title 80" in seen[1].user and "x x x" not in seen[1].user  # limits, not the text


@pytest.mark.parametrize("field,limit", [("observation", 400), ("why", 300), ("alt", 400)])
def test_overlong_body_fields_are_dropped_not_truncated(transcript, smap, result, field, limit):
    long = "Word. " * 200
    bad = tip(**({"observation": long} if field == "observation" else {"why": long} if field == "why" else {}))
    if field == "alt":
        bad["alternative"] = "w" * (limit + 1)
    (art, _), _ = run([[bad, *good(3)]], transcript, smap, result)
    assert len(art.valid) == 3
    assert all(len(t.observation) <= 400 and len(t.why_it_matters) <= 300 and len(t.alternative) <= 400 for t in art.valid)


def test_title_at_the_limit_is_kept(transcript, smap, result):
    ok = good(3)
    ok[0]["title"] = "t" * 80
    (art, _), _ = run([ok], transcript, smap, result)
    assert art.valid[0].title == "t" * 80


def test_more_than_seven_proposals_are_capped_in_the_artifact(transcript, smap, result):
    many = [tip("cct", "t4", alt=f"Option {k} in plain words.") for k in range(30)]
    (art, _), _ = run([many], transcript, smap, result)
    assert len(art.proposals) == 7
