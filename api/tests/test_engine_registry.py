"""Production engine selection stays in API settings and explicit registration."""

import pytest
from onolys_engine_core.context import RunContext
from onolys_engine_core.engine import EngineResult, RunInfo
from onolys_engine_core.errors import InputError
from onolys_engine_core.registry import EngineRegistry
from onolys_miti import MitiEngine

from onolys_api.adapters import build_adapters
from onolys_api.adapters.error_map import to_public
from onolys_api.adapters.real import RealEvaluation
from onolys_api.config import Settings
from onolys_api.engines import build_engine_registry

pytestmark = pytest.mark.unit


def test_production_engine_default_and_env_override():
    assert Settings().prod_engine == "miti"
    assert Settings.from_env({"ENV": "test"}).prod_engine == "miti"
    assert Settings.from_env({"ENV": "test", "PROD_ENGINE": "custom"}).prod_engine == "custom"


def test_api_registry_explicitly_registers_only_miti_and_marks_prod():
    registry = build_engine_registry(Settings())
    assert isinstance(registry.get("miti"), MitiEngine)
    assert [(e.name, e.prod) for e in registry.engines()] == [("miti", True)]
    other = build_engine_registry(Settings(prod_engine="custom"))
    assert [(e.name, e.prod) for e in other.engines()] == [("miti", False)]
    with pytest.raises(InputError):
        registry.get("oneshot")


async def test_unknown_configured_engine_maps_to_invalid_parameters_without_llm_call():
    def no_llm(routes):
        pytest.fail("unknown engine must fail before building a client")

    evaluation = build_adapters(
        Settings(adapters="real", prod_engine="missing"), llm_factory=no_llm,
    ).evaluation
    with pytest.raises(InputError) as caught:
        await evaluation.run(RunContext(llm=None, metrics=None, request_id="r"), None, {}, {})
    assert to_public(caught.value) == ("invalid_parameters", False)


async def test_configured_engine_is_selected_and_speaker_map_is_in_params():
    class Custom:
        name = "custom"
        accepts_feedback = False

        def output_schema(self):
            return {"type": "object", "properties": {"selected": {"const": "custom"}}}

        async def run(self, ctx, transcript, params, progress_cb):
            assert params["speaker_map"] == {"subject": "S1"}
            assert "rating" not in params and "engine" not in params
            assert progress_cb is None
            return EngineResult(output={"selected": self.name}, run_info=RunInfo())

    registry = EngineRegistry()
    registry.register(Custom())
    evaluation = RealEvaluation(
        Settings(prod_engine="custom"), registry=registry, llm_factory=lambda _: object(),
    )
    params = {"engine": "miti", "rating": {"ignored": True}, "speaker_map": {"subject": "bad"}}
    result = await evaluation.run(
        RunContext(llm=None, metrics=None, request_id="r"), None, {"subject": "S1"}, params,
    )
    assert result.report == {"selected": "custom"} and result.artifacts == {}
    assert params["speaker_map"] == {"subject": "bad"}
