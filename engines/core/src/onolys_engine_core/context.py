"""Per-run context handed to the engine entry point."""

from dataclasses import dataclass
from typing import Any


@dataclass
class RunContext:
    llm: Any  # LLMClient
    metrics: Any  # MetricsCollector
    request_id: str
    deadline: float | None = None
    feedback: str | None = None
