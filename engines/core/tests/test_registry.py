import pytest

from onolys_engine_core.engine import Engine, EngineVariant
from onolys_engine_core.errors import InputError
from onolys_engine_core.registry import EngineRegistry


class StubEngine(Engine):
    name = "stub"
    version = "2.1"

    async def run(self, ctx, transcript, params, progress_cb=None):
        raise NotImplementedError

    def output_schema(self):
        return {"$id": "https://example.invalid/stub.schema.json", "type": "object"}


class VariantEngine(StubEngine):
    name = "variant"
    accepts_feedback = True

    def variants(self):
        return [EngineVariant(id="special", label="Special variant")]


def test_register_get_and_unknown_engine():
    registry = EngineRegistry()
    engine = StubEngine()
    registry.register(engine)
    assert registry.get("stub") is engine
    with pytest.raises(InputError, match="unknown engine.*missing"):
        registry.get("missing")


def test_engine_catalog_preserves_metadata_and_configured_prod():
    registry = EngineRegistry(prod_name="variant")
    registry.register(StubEngine())
    registry.register(VariantEngine())
    assert [info.model_dump() for info in registry.engines()] == [
        {
            "name": "stub", "version": "2.1", "prod": False,
            "output_schema_id": "https://example.invalid/stub.schema.json",
            "accepts_feedback": False, "variants": [],
        },
        {
            "name": "variant", "version": "2.1", "prod": True,
            "output_schema_id": "https://example.invalid/stub.schema.json",
            "accepts_feedback": True,
            "variants": [{"id": "special", "label": "Special variant"}],
        },
    ]
    assert {info.name: info.prod for info in registry.engines(prod_name="stub")} == {
        "stub": True, "variant": False,
    }
    assert {info.name: info.prod for info in registry.engines()} == {
        "stub": False, "variant": True,
    }


def test_no_implicit_prod_engine_or_required_schema_id():
    class AnonymousSchemaEngine(StubEngine):
        def output_schema(self):
            return {"type": "object"}

    registry = EngineRegistry()
    registry.register(AnonymousSchemaEngine())
    info, = registry.engines()
    assert info.prod is False
    assert info.output_schema_id is None
    assert EngineRegistry(prod_name="absent").engines() == []
