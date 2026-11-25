import pytest

from onolys_oneshot.engine import limit_tips

pytestmark = pytest.mark.unit


def tip(**kw):
    return {"item_id": "cr", "observation": "o", "alternative": "a", "why_it_matters": "w", **kw}


def test_tips_capped_at_seven_and_long_text_cut():
    out = limit_tips({"counts": {}, "tips": [tip(observation="x " * 500, why_it_matters="y" * 400,
                                                  alternative="z " * 300) for _ in range(12)]})
    assert len(out["tips"]) == 7 and out["counts"] == {}
    t = out["tips"][0]
    assert len(t["observation"]) <= 400 and len(t["why_it_matters"]) <= 300
    assert len(t["alternative"]) <= 400 and t["item_id"] == "cr"


def test_normal_output_and_tipless_output_untouched():
    data = {"tips": [tip()]}
    assert limit_tips(data) == data
    assert limit_tips({"counts": {}}) == {"counts": {}}
