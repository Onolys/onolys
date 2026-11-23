"""Render only configured inputs and preserve source transcript identifiers."""

import json
from dataclasses import dataclass
from typing import Literal

from onolys_engine_core.errors import InputError
from onolys_engine_core.spans import (
    apply_coded_span,
    selected_duration_ms,
    validate_portion_limits,
)
from onolys_engine_core.transcript_v1 import TranscriptV1
from onolys_engine_core.validate import validate_output

from .config import OneshotConfig

CORE_FOOTER = (
    "Return only JSON matching the schema; never invent quotes, speakers or timestamps"
)
_CONTROL_PARAMS = {
    "config", "coded_span", "preset", "speaker_map", "n_runs", "seed", "code_version",
}


@dataclass(frozen=True)
class RenderedPrompt:
    system: str
    user: str
    transcript: TranscriptV1


def _transcript_lines(transcript: TranscriptV1) -> str:
    lines = []
    for turn in transcript.turns:
        speaker = f"{turn.speaker}/{turn.role}" if turn.role is not None else turn.speaker
        times = ", ".join(
            f"{name}={value}" for name in ("start_ms", "end_ms")
            if (value := getattr(turn, name)) is not None
        )
        timestamp = f" [{times}]" if times else ""
        lines.append(f"[{turn.id}] {speaker}{timestamp}: {turn.text}")
    return "\n".join(lines)


def render_prompt(
    config: OneshotConfig,
    transcript: TranscriptV1,
    params: dict,
    *,
    structured_output_mode: Literal["json_object", "json_schema"] = "json_object",
) -> RenderedPrompt:
    """Validate model params, select the span, and render in config input order."""
    if structured_output_mode not in ("json_object", "json_schema"):
        raise InputError("Unsupported structured output mode.")
    model_params = {key: value for key, value in params.items() if key not in _CONTROL_PARAMS}
    if config.params_schema is not None and validate_output(model_params, config.params_schema):
        raise InputError("One-shot params do not match the config schema.")
    allowed = (config.params_schema or {}).get("properties", {})
    rendered_params = {key: value for key, value in model_params.items() if key in allowed}
    selected = apply_coded_span(transcript, params.get("coded_span"))
    if config.name == "miti":
        validate_portion_limits(
            selected.turns,
            selected_duration_ms(transcript, selected.turns, params.get("coded_span")),
        )
    system = f"{config.instructions.rstrip()}\n\n{CORE_FOOTER}"
    if config.schema_hint and structured_output_mode == "json_object":
        system += "\n\nOutput JSON Schema:\n" + json.dumps(config.schema, sort_keys=True)
    inputs = {
        "transcript": lambda: "Transcript:\n" + _transcript_lines(selected),
        "params": lambda: "Params:\n" + json.dumps(rendered_params, sort_keys=True),
    }
    user = "\n\n".join(inputs[name]() for name in config.inputs)
    return RenderedPrompt(system=system, user=user, transcript=selected)
