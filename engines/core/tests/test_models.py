from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
import yaml

from onolys_engine_core.errors import ConfigError
from onolys_engine_core.llm.models import load_models

pytestmark = pytest.mark.unit


def config():
    return {
        "version": 1,
        "models": {
            "claude": {
                "label": "Claude",
                "provider": "anthropic",
                "api_key_env": "ANTHROPIC_API_KEY",
                "caching_mode": "anthropic_ephemeral",
                "supports_temperature": False,
                "context_tokens": 1000000,
                "max_output_tokens": 128000,
                "tiers": {"sonnet": {"efforts": ["low", "high"], "default_effort": "high"}},
            }
        },
    }


def write_config(path, data=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(config() if data is None else data))
    return path


def test_load_valid_models(tmp_path):
    models = load_models(write_config(tmp_path / "models.yaml"))
    model = models["claude"]
    assert model.provider == "anthropic"
    assert model.api_key_env == "ANTHROPIC_API_KEY"
    assert model.caching_mode == "anthropic_ephemeral"
    assert model.supports_temperature is False
    assert (model.context_tokens, model.max_output_tokens) == (1000000, 128000)
    tier = model.tiers["sonnet"]
    assert tier.efforts == ("low", "high")
    assert tier.default_effort == "high"
    with pytest.raises(FrozenInstanceError):
        model.label = "Changed"
    with pytest.raises(FrozenInstanceError):
        tier.default_effort = "low"


@pytest.mark.parametrize("efforts", [[], ["unknown"], "low", None])
def test_reject_empty_or_invalid_efforts(tmp_path, efforts):
    data = config()
    data["models"]["claude"]["tiers"]["sonnet"]["efforts"] = efforts
    with pytest.raises(ConfigError, match="efforts"):
        load_models(write_config(tmp_path / "models.yaml", data))


def test_reject_default_missing_from_efforts(tmp_path):
    data = config()
    data["models"]["claude"]["tiers"]["sonnet"]["default_effort"] = "medium"
    with pytest.raises(ConfigError, match="default_effort"):
        load_models(write_config(tmp_path / "models.yaml", data))


@pytest.mark.parametrize("field", ["context_tokens", "max_output_tokens"])
@pytest.mark.parametrize("value", [0, -1, True, 1.5, "100"])
def test_require_positive_integers(tmp_path, field, value):
    data = config()
    data["models"]["claude"][field] = value
    with pytest.raises(ConfigError, match=field):
        load_models(write_config(tmp_path / "models.yaml", data))


def test_reject_duplicate_tier_ids_across_models(tmp_path):
    data = config()
    data["models"]["other"] = dict(data["models"]["claude"])
    with pytest.raises(ConfigError, match="duplicate.*sonnet"):
        load_models(write_config(tmp_path / "models.yaml", data))


def test_models_file_env_and_explicit_path_precedence(tmp_path, monkeypatch):
    env_file = write_config(tmp_path / "env.yaml")
    monkeypatch.setenv("MODELS_FILE", str(env_file))
    assert load_models()["claude"].label == "Claude"
    explicit = config()
    explicit["models"]["claude"]["label"] = "Explicit"
    assert load_models(write_config(tmp_path / "explicit.yaml", explicit))["claude"].label == "Explicit"


def test_default_path_next_to_routes_environment_directory(tmp_path, monkeypatch):
    monkeypatch.delenv("MODELS_FILE", raising=False)
    monkeypatch.setenv("ROUTES_FILE", str(tmp_path / "config" / "staging" / "routes.yaml"))
    write_config(tmp_path / "config" / "models.yaml")
    assert load_models()["claude"].provider == "anthropic"


@pytest.mark.parametrize("data", [[], {}, {"version": 2, "models": {}}, {"version": 1, "models": []}])
def test_reject_malformed_schema(tmp_path, data):
    with pytest.raises(ConfigError):
        load_models(write_config(tmp_path / "models.yaml", data))


def test_missing_or_invalid_yaml_is_config_error(tmp_path):
    with pytest.raises(ConfigError):
        load_models(tmp_path / "missing.yaml")
    path = tmp_path / "broken.yaml"
    path.write_text("models: [")
    with pytest.raises(ConfigError):
        load_models(path)


def test_real_config_matches_model_picker_brief():
    models = load_models(Path(__file__).resolve().parents[3] / "config" / "models.yaml")
    assert set(models) == {"claude", "gemini"}
    claude = models["claude"]
    assert (claude.label, claude.provider, claude.api_key_env) == ("Claude", "anthropic", "ANTHROPIC_API_KEY")
    assert (claude.context_tokens, claude.max_output_tokens, claude.supports_temperature) == (1000000, 128000, False)
    assert claude.caching_mode == "anthropic_ephemeral"
    assert {k: (t.efforts, t.default_effort) for k, t in claude.tiers.items()} == {
        "claude-opus-5-5": (("low", "medium", "high", "max"), "medium"),
        "claude-sonnet-5-5": (("low", "medium", "high", "max"), "high"),
        "claude-haiku-5-5": (("low", "medium", "high", "max"), "medium"),
    }
    gemini = models["gemini"]
    assert (gemini.label, gemini.provider, gemini.api_key_env) == ("Gemini", "gemini", "GEMINI_API_KEY")
    assert (gemini.context_tokens, gemini.max_output_tokens, gemini.supports_temperature) == (1048576, 65536, False)
    assert gemini.caching_mode == "provider_implicit"
    assert {k: (t.efforts, t.default_effort) for k, t in gemini.tiers.items()} == {
        f"gemini-4-{name}": (("low", "medium", "high"), default)
        for name, default in [("carbon", "medium"), ("neon", "high"), ("hydrogen", "high"), ("argon", "medium")]
    }
