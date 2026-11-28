"""Engine-independent execution contracts."""

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict

from .context import RunContext
from .transcript_v1 import TranscriptV1

ProgressCb = Callable[[str, str], None]


class RunUsage(BaseModel):
    """Common usage counters, with optional engine-specific cache counters."""

    model_config = ConfigDict(extra="allow")

    input_tokens: int
    output_tokens: int
    calls: int
    cost_usd: float | None = None


class RunInfo(BaseModel):
    """Common usage plus engine-specific run provenance."""

    model_config = ConfigDict(extra="allow")

    usage: RunUsage | None = None


class EngineResult(BaseModel):
    output: dict
    artifacts: Any = None
    run_info: RunInfo


class EngineVariant(BaseModel):
    id: str
    label: str


class Engine(ABC):
    name: ClassVar[str]
    version: ClassVar[str]
    accepts_feedback: ClassVar[bool] = False

    @abstractmethod
    async def run(
        self,
        ctx: RunContext,
        transcript: TranscriptV1,
        params: dict,
        progress_cb: ProgressCb | None = None,
    ) -> EngineResult:
        """Execute the engine; engines opt in to using ctx.feedback."""

    @abstractmethod
    def output_schema(self) -> dict:
        """Return the JSON Schema for the final output."""

    def variants(self) -> list[EngineVariant]:
        return []
