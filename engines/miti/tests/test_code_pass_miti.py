"""The shipped pack renders into a valid code-pass prompt (no model call)."""

import pytest

from onolys_miti import miti
from onolys_miti.code_pass import build_requests_parts

pytestmark = pytest.mark.unit


def test_miti_prompt_renders_codes_and_examples():
    parts = build_requests_parts({"change_goal": "g"}, "en")
    first = parts.cache_prefixes[0]
    assert "### Example 1" in first and '"volleys"' in first
    assert "synthetic" not in first  # example markers are not sent to the model
    for item in miti.MITI.items:
        if item["kind"] == "count":
            assert f"- {item['id']} (" in first
    codes = parts.response_model.model_json_schema()
    assert "cr" in str(codes)
