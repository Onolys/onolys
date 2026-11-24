"""The baseline copies MITI data by path and never imports the lean engine."""

import ast
import importlib.util
import json
import re
from pathlib import Path

import pytest
import yaml
from onolys_engine_core.errors import InputError
from onolys_engine_core.llm.routes import load_registry, resolve_preset
from onolys_engine_core.transcript_v1 import TranscriptV1
from onolys_engine_core.validate import validate_output

from onolys_oneshot.config import load_config
from onolys_oneshot.render import render_prompt

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "engines/miti/src/onolys_miti/data"


def test_all_pack_items_have_instruction_definitions():
    instructions = load_config("miti").instructions
    pack = yaml.safe_load((DATA / "pack.yaml").read_text())
    # Both prompt sources must remain present; the copy is authored for one call.
    for name in ("code_system.md", "globals_system.md"):
        assert (DATA / "prompts" / name).read_text()
    for item in pack["items"]:
        assert re.search(rf"(?m)^### `{item['id']}` — {re.escape(item['label'])}$", instructions)
        assert item["definition"].strip() in instructions


def test_generated_schema_matches_committed_scoring_subset():
    spec = importlib.util.spec_from_file_location("gen_miti_schema", ROOT / "scripts/gen_miti_schema.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    schema = load_config("miti").schema
    assert schema == module.generate_schema()
    assert set(schema["properties"]) == {"counts", "globals", "tips"}
    assert len(schema["properties"]["counts"]["properties"]) == 10
    assert len(schema["properties"]["globals"]["properties"]) == 4
    forbidden = {"quote", "instances", "offsets", "summaries", "scorecard", "run_info", "header"}
    assert not forbidden.intersection(re.findall(r'"(\w+)":', json.dumps(schema)))


def test_scoring_subset_requires_all_ids_and_enforces_ranges():
    schema = load_config("miti").schema
    output = {
        "counts": dict.fromkeys(schema["properties"]["counts"]["properties"], 0),
        "globals": dict.fromkeys(schema["properties"]["globals"]["properties"], 3),
        "tips": [],
    }
    assert validate_output(output, schema) == []
    output["counts"]["gi"] = -1
    assert validate_output(output, schema)
    output["counts"]["gi"] = 0
    output["globals"]["cct"] = 6
    assert validate_output(output, schema)
    del output["globals"]["cct"]
    assert validate_output(output, schema)


def test_model_params_exclude_known_engine_controls_but_reject_unknowns():
    config = load_config("miti")
    transcript = TranscriptV1(turns=[])
    controls = {"config": "miti", "preset": "claude", "speaker_map": {"A": "clinician"},
                "n_runs": 1, "seed": 42, "code_version": "test"}
    prompt = render_prompt(config, transcript, {**controls, "change_goal": "walk", "language": "en"})
    assert json.loads(prompt.user.split("Params:\n")[1]) == {"change_goal": "walk", "language": "en"}
    for params in ({}, {"change_goal": 1}, {"change_goal": "walk", "unexpected": True}):
        with pytest.raises(InputError):
            render_prompt(config, transcript, params)


@pytest.mark.parametrize("path", [ROOT / "config/staging/routes.yaml", ROOT / "engines/core/src/onolys_engine_core/llm/routes.default.yaml"])
@pytest.mark.parametrize("preset", ["default", "claude"])
def test_oneshot_route_has_explicit_output_cap(path, preset):
    registry = load_registry(path, env={})
    assert registry.raw_routes["oneshot"]["max_output_tokens"] == load_config("miti").max_output_tokens
    routes, _ = resolve_preset(preset, registry, env={})
    if path.parts[-3:-1] == ("config", "staging") and preset == "default":
        # 01-llm-outage-claude R5: staging text routes moved to Claude; the oneshot eval baseline
        # deliberately stays on its Gemini anchor.
        assert routes["oneshot"].litellm_id == "gemini/gemini-4-neon"
    else:
        assert routes["oneshot"].litellm_id == routes["mid"].litellm_id


def test_schema_generator_has_no_miti_code_imports():
    path = ROOT / "scripts/gen_miti_schema.py"
    for node in ast.walk(ast.parse(path.read_text())):
        modules = [alias.name for alias in node.names] if isinstance(node, ast.Import) else (
            [node.module or ""] if isinstance(node, ast.ImportFrom) else []
        )
        assert not any(name.startswith("onolys_miti") for name in modules)


def test_good_practice_is_existing_synthetic_fixture_with_explicit_roles():
    original = json.loads((DATA / "fixtures/good_practice.json").read_text())
    for turn in original["turns"]:
        turn["role"] = {"A": "clinician", "B": "client"}[turn["speaker"]]
    recorded_input = Path(__file__).parent / "fixtures/transcripts/good_practice.json"
    assert json.loads(recorded_input.read_text()) == original
