"""Synthetic configs exercise the generic baseline without protocol imports."""

import ast
import json
from pathlib import Path

import pytest
import yaml
from onolys_engine_core.errors import ConfigError, InputError
from onolys_engine_core.transcript_v1 import TranscriptV1

from onolys_oneshot.config import config_names, load_config
from onolys_oneshot.render import CORE_FOOTER, render_prompt


@pytest.fixture
def config_root(tmp_path):
    directory = tmp_path / "synthetic"
    directory.mkdir()
    metadata = {
        "name": "synthetic", "version": "1", "max_output_tokens": 123,
        "inputs": ["transcript", "params"], "schema_hint": True,
        "params_schema": {
            "type": "object", "properties": {"change_goal": {"type": "string"}},
            "required": ["change_goal"],
        },
    }
    (directory / "config.yaml").write_text(yaml.safe_dump(metadata))
    (directory / "instructions.md").write_text("Summarize the synthetic input.")
    (directory / "schema.json").write_text(json.dumps({
        "type": "object", "properties": {"summary": {"type": "string"}},
        "required": ["summary"], "additionalProperties": False,
    }))
    return tmp_path


@pytest.fixture
def transcript():
    return TranscriptV1.model_validate({"turns": [
        {"id": "original-a", "speaker": "Speaker A", "role": "clinician", "text": "First", "start_ms": 0, "end_ms": 100},
        {"id": "original-z", "speaker": "Speaker B", "role": "client", "text": "Second"},
        {"id": "original-c", "speaker": "Speaker A", "text": "Third", "start_ms": 200},
    ]})


def test_load_config_defaults_and_discovery(config_root):
    config = load_config("synthetic", root=config_root)
    assert config.name == "synthetic"
    assert config.version == "1"
    assert config.route == "oneshot"
    assert config.max_output_tokens == 123
    assert config.inputs == ("transcript", "params")
    assert len(config.config_hash) == 64
    assert config_names(root=config_root) == ["synthetic"]


@pytest.mark.parametrize("name", [None, "", "absent", "../synthetic", "/synthetic", "a/b", "..", "a\\b"])
def test_unknown_and_unsafe_names_raise_input_error(config_root, name):
    with pytest.raises(InputError):
        load_config(name, root=config_root)


def test_config_cannot_escape_root_by_symlink(config_root, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside")
    (config_root / "escape").symlink_to(outside, target_is_directory=True)
    with pytest.raises(InputError):
        load_config("escape", root=config_root)


@pytest.mark.parametrize("filename", ["config.yaml", "instructions.md", "schema.json"])
def test_hash_tracks_every_file_byte(config_root, filename):
    before = load_config("synthetic", root=config_root).config_hash
    assert load_config("synthetic", root=config_root).config_hash == before
    path = config_root / "synthetic" / filename
    path.write_bytes(path.read_bytes() + b"\n")
    assert load_config("synthetic", root=config_root).config_hash != before


def test_render_preserves_order_ids_labels_and_only_present_timestamps(config_root, transcript):
    config = load_config("synthetic", root=config_root)
    prompt = render_prompt(config, transcript, {"config": "synthetic", "change_goal": "Read", "private": "hidden"})
    assert prompt.system.startswith(config.instructions)
    assert CORE_FOOTER in prompt.system
    assert '"summary"' in prompt.system
    assert "[original-a] Speaker A/clinician [start_ms=0, end_ms=100]: First" in prompt.user
    assert "[original-z] Speaker B/client: Second" in prompt.user
    assert "[original-c] Speaker A [start_ms=200]: Third" in prompt.user
    assert prompt.user.index("original-a") < prompt.user.index("original-z") < prompt.user.index("original-c") < prompt.user.index('"change_goal"')
    assert "private" not in prompt.user
    assert "hidden" not in prompt.user
    assert '"config"' not in prompt.user
    assert "None" not in prompt.user


def test_render_respects_input_order_and_span(config_root, transcript):
    path = config_root / "synthetic" / "config.yaml"
    metadata = yaml.safe_load(path.read_text())
    metadata["inputs"] = ["params", "transcript"]
    path.write_text(yaml.safe_dump(metadata))
    prompt = render_prompt(load_config("synthetic", root=config_root), transcript, {
        "change_goal": "Read", "coded_span": {"start_turn": 1, "end_turn": 2},
    })
    assert "original-a" not in prompt.user
    assert "original-c" not in prompt.user
    assert "original-z" in prompt.user
    assert prompt.user.index('"change_goal"') < prompt.user.index("original-z")
    assert [turn.id for turn in prompt.transcript.turns] == ["original-z"]
    assert len(transcript.turns) == 3
    assert "coded_span" not in prompt.user


@pytest.mark.parametrize("params", [{}, {"change_goal": 1}])
def test_bad_params_rejected(config_root, transcript, params):
    with pytest.raises(InputError):
        render_prompt(load_config("synthetic", root=config_root), transcript, params)


@pytest.mark.parametrize("hint,mode,expected", [(True, "json_object", True), (False, "json_object", False), (True, "json_schema", False), (False, "json_schema", False)])
def test_schema_hint_mode_switch(config_root, transcript, hint, mode, expected):
    path = config_root / "synthetic" / "config.yaml"
    metadata = yaml.safe_load(path.read_text())
    metadata["schema_hint"] = hint
    path.write_text(yaml.safe_dump(metadata))
    prompt = render_prompt(load_config("synthetic", root=config_root), transcript, {"change_goal": "Read"}, structured_output_mode=mode)
    assert ('"summary"' in prompt.system) == expected


def test_no_params_schema_renders_no_arbitrary_params(config_root, transcript):
    path = config_root / "synthetic" / "config.yaml"
    metadata = yaml.safe_load(path.read_text())
    del metadata["params_schema"]
    path.write_text(yaml.safe_dump(metadata))
    prompt = render_prompt(load_config("synthetic", root=config_root), transcript, {"private": "hidden"})
    assert "hidden" not in prompt.user
    assert "{}" in prompt.user


def test_invalid_package_config_is_config_error(config_root):
    (config_root / "synthetic" / "schema.json").write_text('{"type": "invalid"}')
    with pytest.raises(ConfigError):
        load_config("synthetic", root=config_root)


def test_oneshot_imports_no_miti_modules():
    sources = list((Path(__file__).resolve().parents[1] / "src" / "onolys_oneshot").rglob("*.py"))
    assert sources
    for path in sources:
        for node in ast.walk(ast.parse(path.read_text())):
            modules = [alias.name for alias in node.names] if isinstance(node, ast.Import) else (
                [node.module or ""] if isinstance(node, ast.ImportFrom) and node.level == 0 else []
            )
            assert not any(module.split(".")[0] == "onolys_miti" for module in modules), path


def test_runtime_dependency_is_core_only():
    import tomllib

    metadata = tomllib.loads((Path(__file__).resolve().parents[1] / "pyproject.toml").read_text())
    assert metadata["project"]["dependencies"] == ["onolys-engine-core"]


def test_time_span_preserves_untimed_turns(config_root, transcript):
    prompt = render_prompt(load_config("synthetic", root=config_root), transcript, {
        "change_goal": "Read", "coded_span": {"start_ms": 150, "end_ms": 300},
    })
    assert [turn.id for turn in prompt.transcript.turns] == ["original-z", "original-c"]
    assert "original-a" not in prompt.user


def test_params_schema_enforces_extra_property_rule(config_root, transcript):
    path = config_root / "synthetic" / "config.yaml"
    metadata = yaml.safe_load(path.read_text())
    metadata["params_schema"]["additionalProperties"] = False
    path.write_text(yaml.safe_dump(metadata))
    config = load_config("synthetic", root=config_root)
    with pytest.raises(InputError, match="params"):
        render_prompt(config, transcript, {"change_goal": "Read", "private": "hidden"})
    render_prompt(config, transcript, {"change_goal": "Read", "config": "synthetic"})


def test_omitted_input_is_not_rendered(config_root, transcript):
    path = config_root / "synthetic" / "config.yaml"
    metadata = yaml.safe_load(path.read_text())
    metadata["inputs"] = ["params"]
    path.write_text(yaml.safe_dump(metadata))
    prompt = render_prompt(load_config("synthetic", root=config_root), transcript, {"change_goal": "Read"})
    assert "original-a" not in prompt.user
    assert "Transcript:" not in prompt.user


def test_default_package_root_rejects_unknown_configs():
    assert "absent" not in config_names()
    with pytest.raises(InputError):
        load_config("absent")
