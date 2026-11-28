import pytest

from onolys_engine.text_limits import clip

pytestmark = pytest.mark.unit


def test_short_text_unchanged():
    assert clip("short", 10) == ("short", False)


def test_long_text_clipped_on_a_word_boundary_within_limit():
    out, clipped = clip("alpha beta gamma delta epsilon", 20)
    assert clipped and out == "alpha beta gamma…" and len(out) <= 20


def test_unbroken_text_hard_cut_within_limit():
    out, clipped = clip("x" * 100, 10)
    assert clipped and len(out) == 10 and out.endswith("…")
