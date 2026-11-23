"""Lazy production composition; constructing an app never loads cloud credentials."""

from functools import cached_property
from pathlib import Path

from onolys_engine_core.engine import Engine
from onolys_engine_core.errors import InputError
from onolys_engine_core.llm.routes import RouteRegistry, load_registry
from onolys_engine_core.registry import EngineRegistry

from onolys_eval_backend.config import EvalConfig
from onolys_eval_backend.repository import EvalRepository, FirestoreEvalRepository
from onolys_eval_backend.storage import Bucket, GCSBucket


class EvalServices:
    def __init__(self, config: EvalConfig):
        self.config = config

    @cached_property
    def bucket(self) -> Bucket:
        from google.cloud import storage

        return GCSBucket(storage.Client(project=self.config.project).bucket(self.config.bucket))

    @cached_property
    def repository(self) -> EvalRepository:
        from google.cloud import firestore

        return FirestoreEvalRepository(firestore.Client(
            project=self.config.project, database=self.config.firestore_database,
        ))

    @cached_property
    def routes(self) -> RouteRegistry:
        return load_registry(Path(self.config.routes_file))

    @cached_property
    def registry(self) -> EngineRegistry:
        from onolys_miti.engine import MitiEngine
        from onolys_oneshot.engine import OneshotEngine

        registry = EngineRegistry(prod_name=self.config.prod_engine)
        registry.register(MitiEngine())
        registry.register(OneshotEngine(config="miti"))
        return registry

    @cached_property
    def _bound_engines(self) -> dict[str, Engine]:
        from onolys_oneshot.engine import OneshotEngine

        engines = {}
        for info in self.registry.engines():
            if info.variants:
                for variant in info.variants:
                    # The only variant engine in eval is the immutable config-bound one-shot.
                    engines[f"{info.name}:{variant.id}"] = OneshotEngine(config=variant.id)
            else:
                engines[info.name] = self.registry.get(info.name)
        return engines

    def engine(self, engine_id: str) -> Engine:
        """Resolve selectable IDs to an engine whose schema is already variant-bound."""
        try:
            return self._bound_engines[engine_id]
        except KeyError:
            raise InputError("Unknown eval engine.") from None
