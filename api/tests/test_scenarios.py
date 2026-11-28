"""Scenario schema + loader + `GET /scenarios` + persona prompt + leak scan."""

import copy
import json
import logging
from pathlib import Path

import pytest
from leak_helpers import find_leaks, secret_strings
from log_helpers import render
from onolys_engine import ConfigError

from onolys_api.app import create_app
from onolys_api.voice.prompt import build_system_prompt
from onolys_api.voice.scenarios import PUBLIC_FIELDS, load_scenarios, scenarios_dir

pytestmark = pytest.mark.unit
H = {"Authorization": "Bearer test:alice"}
VOICES = ["Kore", "Puck"]


@pytest.fixture
def sample() -> dict:
    return load_scenarios()["sample-drinking-ambivalent"]


def _dir_with(tmp_path: Path, mutate) -> Path:
    src = scenarios_dir()
    (tmp_path / "scenario.schema.json").write_text((src / "scenario.schema.json").read_text())
    sc = copy.deepcopy(json.loads((src / "sample-drinking-ambivalent.json").read_text()))
    mutate(sc)
    (tmp_path / "bad.json").write_text(json.dumps(sc))
    return tmp_path


def test_sample_validates_and_voice_is_configured(sample):
    assert sample["language"] == "en-US" and sample["voice"] == "Kore"
    assert set(sample["public"]) == {"title", "difficulty", "summary"}


@pytest.mark.parametrize(
    "mutate",
    [
        lambda sc: sc.pop("hidden_info"),
        lambda sc: sc.update(response_rules=[]),
        lambda sc: sc.update(difficulty="impossible"),
        lambda sc: sc.update(extra="x"),
        lambda sc: sc.update(voice="NotAVoice"),
    ],
)
def test_invalid_scenario_fails_load(tmp_path, mutate):
    with pytest.raises(ConfigError):
        load_scenarios(_dir_with(tmp_path, mutate), voices=VOICES)


def test_invalid_scenario_fails_app_start(tmp_path, settings, monkeypatch):
    bad = _dir_with(tmp_path, lambda sc: sc.pop("opening_line"))
    monkeypatch.setattr("onolys_api.voice.scenarios.scenarios_dir", lambda: bad)
    with pytest.raises(ConfigError):
        create_app(settings)


def test_load_error_has_no_content(tmp_path):
    d = _dir_with(tmp_path, lambda sc: sc.update(opening_line=""))
    with pytest.raises(ConfigError) as e:
        load_scenarios(d, voices=VOICES)
    assert "/opening_line" in str(e.value)


async def test_get_scenarios_public_keys_only(client, sample):
    r = await client.get("/v1/scenarios", headers=H)
    assert r.status_code == 200
    items = r.json()["scenarios"]
    assert items and all(set(i) == set(PUBLIC_FIELDS) for i in items)

    def keys(o):
        if isinstance(o, dict):
            for k, v in o.items():
                yield k
                yield from keys(v)
        elif isinstance(o, list):
            for v in o:
                yield from keys(v)

    assert not {"persona", "hidden_info", "response_rules"} & set(keys(r.json()))
    assert find_leaks(r.text, sample) == []


async def test_get_scenarios_exposes_allowed_voices_and_each_scenarios_voice(client, app):
    body = (await client.get("/v1/scenarios", headers=H)).json()
    assert body["voices"] == app.state.voices and len(body["voices"]) > 1
    assert "default_voice" not in body  # one rule: the scenario's voice is the default
    for item in body["scenarios"]:
        assert item["voice"] == app.state.scenarios[item["id"]]["voice"]
        assert item["voice"] in body["voices"]


async def test_get_scenarios_requires_auth(client):
    r = await client.get("/v1/scenarios")
    assert r.status_code == 401


def test_prompt_contains_hidden_info_rules_and_opening_line(sample):
    p = build_system_prompt(sample)
    assert sample["hidden_info"] in p
    assert sample["opening_line"] in p
    assert all(r in p for r in sample["response_rules"])
    assert sample["persona"]["name"] in p
    assert sample["change_goal"] in p
    assert "Never break character" in p


def test_leak_scan_detects_leaks(sample):
    assert find_leaks("the prompt: " + build_system_prompt(sample), sample)
    assert find_leaks("She nearly hit a cyclist", sample)
    assert find_leaks("Hello, what brings you here?", sample) == []
    assert len(secret_strings(sample)) > 5


async def test_no_leak_in_responses_or_logs(app, client, sample, caplog):
    """Responses and logs. Relay frames: the relay tests reuse `find_leaks` on every frame."""
    caplog.set_level(logging.DEBUG)
    prompt = build_system_prompt(sample)  # as a relay connection would hold it in memory
    assert prompt
    texts = []
    for path in ("/v1/scenarios", "/v1/healthz", "/v1/openapi.json", "/v1/usage", "/v1/sessions"):
        r = await client.get(path, headers=H)
        texts.append(r.text)
    bad = await client.get("/v1/scenarios", headers={"Authorization": "Bearer nope"})
    texts.append(bad.text)
    texts.append("\n".join(render(r) for r in caplog.records))
    for t in texts:
        assert find_leaks(t, sample) == []
