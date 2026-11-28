"""Onolys evaluation engine.

Provisional public surface: the names the API imports. The API imports only from
`onolys_engine` (a ruff ban rejects `onolys_engine.<submodule>` outside the engine). The
final surface (`public.py` plus `Engine`) replaces this list in the engine-surface task.
"""

from .config import locate_config_file
from .context import RunContext
from .engine import Engine, EngineResult, RunInfo, RunUsage
from .errors import (
    ConfigError,
    InputError,
    InvalidCodedSpan,
    OnolysError,
    RunAborted,
    SessionTooLong,
)
from .llm import (
    LiteLLMClient,
    LLMBadOutput,
    LLMConfig,
    LLMRequest,
    LLMUnavailable,
    MetricsCollector,
    StubClient,
    Usage,
)
from .llm.errors import FixtureMiss, LLMError, LLMRateLimited, LLMTimeout, is_transient
from .llm.models import EFFORTS, load_models, models_path
from .llm.quiet import LITELLM_LOGGERS, quiet_litellm
from .llm.routes import (
    DEFAULT_PRESET_ENV,
    Route,
    RouteRegistry,
    allowed_presets,
    combo_routes,
    default_preset_name,
    load_registry,
    resolve_preset,
)
from .presets import PresetInfo, list_presets
from .registry import EngineRegistry
from .safe_log import LOG_FIELDS, PROVIDER_ERROR_MAX_CHARS, log_event
from .spans import apply_coded_span, selected_duration_ms, validate_portion_limits
from .transcript import Transcript, Turn
from .transcript_v1 import TranscriptTurnV1, TranscriptV1
from .validate import ValidationIssue, validate_output
from .validated_run import OutputInvalid, run_validated

__all__ = [
    "ConfigError",
    "DEFAULT_PRESET_ENV",
    "EFFORTS",
    "Engine",
    "EngineRegistry",
    "EngineResult",
    "FixtureMiss",
    "InputError",
    "InvalidCodedSpan",
    "LITELLM_LOGGERS",
    "LLMBadOutput",
    "LLMConfig",
    "LLMError",
    "LLMRateLimited",
    "LLMRequest",
    "LLMTimeout",
    "LLMUnavailable",
    "LOG_FIELDS",
    "LiteLLMClient",
    "MetricsCollector",
    "OnolysError",
    "OutputInvalid",
    "PROVIDER_ERROR_MAX_CHARS",
    "PresetInfo",
    "Route",
    "RouteRegistry",
    "RunAborted",
    "RunContext",
    "RunInfo",
    "RunUsage",
    "SessionTooLong",
    "StubClient",
    "Transcript",
    "TranscriptTurnV1",
    "TranscriptV1",
    "Turn",
    "Usage",
    "ValidationIssue",
    "allowed_presets",
    "apply_coded_span",
    "combo_routes",
    "default_preset_name",
    "is_transient",
    "list_presets",
    "load_models",
    "load_registry",
    "locate_config_file",
    "log_event",
    "models_path",
    "quiet_litellm",
    "resolve_preset",
    "run_validated",
    "selected_duration_ms",
    "validate_output",
    "validate_portion_limits",
]
