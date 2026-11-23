"""load_scenarios error paths: unreadable schema, bad JSON, duplicate id, empty dir."""

import copy
import json
from pathlib import Path

import pytest
from onolys_engine_core.errors import ConfigError

from onolys_api.voice.scenarios import load_scenarios, public_view, scenarios_dir

pytestmark = pytest.mark.unit
VOICES = ["Kore", "Puck"]


def _sample() -> dict:
    return json.loads((scenarios_dir() / "sample-drinking-ambivalent.json").read_text())


def _dir(tmp_path: Path, *, schema: bool = True) -> Path:
    if schema:
        (tmp_path / "scenario.schema.json").write_text(
            (scenarios_dir() / "scenario.schema.json").read_text()
        )
    return tmp_path


def test_missing_schema_is_config_error(tmp_path):
    with pytest.raises(ConfigError, match="schema unreadable"):
        load_scenarios(_dir(tmp_path, schema=False), voices=VOICES)


def test_malformed_schema_is_config_error(tmp_path):
    (tmp_path / "scenario.schema.json").write_text("{not json")
    with pytest.raises(ConfigError, match="schema unreadable"):
        load_scenarios(tmp_path, voices=VOICES)


def test_malformed_scenario_json_names_file_only(tmp_path):
    d = _dir(tmp_path)
    (d / "broken.json").write_text('{"persona": "SECRET-PERSONA-TEXT"')
    with pytest.raises(ConfigError) as e:
        load_scenarios(d, voices=VOICES)
    assert "broken.json" in str(e.value)
    assert "SECRET-PERSONA-TEXT" not in str(e.value)


def test_duplicate_scenario_id_rejected(tmp_path):
    d = _dir(tmp_path)
    sc = _sample()
    (d / "a.json").write_text(json.dumps(sc))
    (d / "b.json").write_text(json.dumps(copy.deepcopy(sc)))
    with pytest.raises(ConfigError, match=r"b\.json: duplicate id"):
        load_scenarios(d, voices=VOICES)


def test_voice_not_in_allowed_list_rejected(tmp_path):
    d = _dir(tmp_path)
    (d / "a.json").write_text(json.dumps(_sample()))
    with pytest.raises(ConfigError, match="not a configured voice"):
        load_scenarios(d, voices=["SomeoneElse"])


def test_directory_with_only_schema_has_no_scenarios(tmp_path):
    with pytest.raises(ConfigError, match="no scenarios found"):
        load_scenarios(_dir(tmp_path), voices=VOICES)


def test_valid_dir_loads_by_id_and_schema_file_is_not_a_scenario(tmp_path):
    d = _dir(tmp_path)
    sc = _sample()
    (d / "a.json").write_text(json.dumps(sc))
    assert list(load_scenarios(d, voices=VOICES)) == [sc["id"]]


def test_public_view_has_only_public_fields():
    sc = _sample()
    view = public_view(sc)
    assert set(view) == {"id", "title", "difficulty", "summary", "language", "voice"}
    assert view["title"] == sc["public"]["title"]
