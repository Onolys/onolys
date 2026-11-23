"""Explicit engine registration and configuration-selected catalog metadata."""

from pydantic import BaseModel

from .engine import Engine, EngineVariant
from .errors import InputError


class EngineInfo(BaseModel):
    name: str
    version: str
    prod: bool
    output_schema_id: str | None
    accepts_feedback: bool
    variants: list[EngineVariant]


class EngineRegistry:
    def __init__(self, prod_name: str | None = None) -> None:
        self._engines: dict[str, Engine] = {}
        self._prod_name = prod_name

    def register(self, engine: Engine) -> None:
        self._engines[engine.name] = engine

    def get(self, name: str) -> Engine:
        try:
            return self._engines[name]
        except KeyError:
            raise InputError(f"unknown engine {name!r}") from None

    def engines(self, prod_name: str | None = None) -> list[EngineInfo]:
        """List engines, marking the name supplied by the caller's settings as prod."""
        selected = self._prod_name if prod_name is None else prod_name
        return [
            EngineInfo(
                name=engine.name,
                version=engine.version,
                prod=engine.name == selected,
                output_schema_id=engine.output_schema().get("$id"),
                accepts_feedback=engine.accepts_feedback,
                variants=engine.variants(),
            )
            for engine in self._engines.values()
        ]
