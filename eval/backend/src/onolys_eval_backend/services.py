"""Lazy production composition; constructing an app never loads cloud credentials."""

import asyncio
import os
from functools import cached_property
from pathlib import Path

from onolys_engine_core.engine import Engine
from onolys_engine_core.errors import InputError
from onolys_engine_core.llm.models import Model, load_models, models_path
from onolys_engine_core.llm.routes import RouteRegistry, load_registry
from onolys_engine_core.registry import EngineRegistry

from onolys_eval_backend.config import EvalConfig
from onolys_eval_backend.costs import PriceBook
from onolys_eval_backend.repository import EvalRepository, FirestoreEvalRepository
from onolys_eval_backend.storage import Bucket, GCSBucket


class EvalServices:
    def __init__(self, config: EvalConfig, *, queue=None, stt_factory=None):
        self.config = config
        if queue is not None:
            self.queue = queue
        if stt_factory is not None:
            self.stt_factory = stt_factory

    async def sleep(self, seconds: float) -> None:
        """Injectable backoff sleep for unit retries (tests replace it)."""
        await asyncio.sleep(seconds)

    @cached_property
    def prices(self) -> PriceBook:
        return PriceBook.from_yaml()

    @cached_property
    def bucket(self) -> Bucket:
        from google.cloud import storage

        return GCSBucket(storage.Client(project=self.config.project).bucket(self.config.bucket))

    @cached_property
    def repository(self) -> EvalRepository:
        from google.cloud import firestore

        return FirestoreEvalRepository(
            firestore.Client(
                project=self.config.project,
                database=self.config.firestore_database,
            )
        )

    @cached_property
    def routes(self) -> RouteRegistry:
        return load_registry(Path(self.config.routes_file))

    @cached_property
    def models(self) -> dict[str, Model]:
        return load_models(models_path(os.environ, self.config.routes_file))

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

    @cached_property
    def queue(self):
        from google.cloud import tasks_v2

        from onolys_eval_backend.queue import CloudTasksQueue

        return CloudTasksQueue(self.config, tasks_v2.CloudTasksClient())

    def stt_params(self, language):
        from onolys_engine_core.llm.routes import resolve_preset
        from onolys_miti.stt.select import load_stt_config, select_stt

        _, key = resolve_preset(
            self.config.default_preset, self.routes, {"DEFAULT_PRESET": self.config.default_preset}
        )
        path = Path(self.config.routes_file).parent / "stt_providers.yaml"
        params = select_stt(key, language, config=load_stt_config(path if path.is_file() else None))
        if params.provider in {"google", "google_chirp"} and params.language == "en":
            params = params.model_copy(update={"language": "en-US"})
        return params

    def stt_factory(self, provider):
        from onolys_miti.stt.fixture import FixtureStt
        from onolys_miti.stt.google_chirp import GoogleChirp3

        factories = {
            "google": GoogleChirp3,
            "google_chirp": GoogleChirp3,
            "fixture": lambda: FixtureStt({}),
        }
        if provider not in factories:
            raise InputError("Unknown STT provider.")
        return factories[provider]()
