"""Execute a packaged config with one structured-output model call."""

from copy import deepcopy
from importlib.metadata import version

from onolys_engine.context import RunContext
from onolys_engine.engine import (
    Engine,
    EngineResult,
    EngineVariant,
    ProgressCb,
    RunInfo,
    RunUsage,
)
from onolys_engine.errors import ConfigError, InputError
from onolys_engine.llm.errors import LLMBadOutput
from onolys_engine.llm.fixture_client import RecordingClient
from onolys_engine.llm.routes import Route, resolve_preset
from onolys_engine.llm.types import LLMRequest
from onolys_engine.text_limits import (
    ALTERNATIVE_MAX,
    MAX_TIPS_PROPOSED,
    OBSERVATION_MAX,
    SENTENCE_MAX,
    clip,
)
from onolys_engine.transcript_v1 import TranscriptV1

from .config import config_names, load_config
from .render import render_prompt


def _route(client, name: str, preset: str | None) -> Route:
    # Read the live client's resolved preset, including when recording fixtures.
    seen = set()
    while isinstance(client, RecordingClient):
        if id(client) in seen:
            raise ConfigError("Cyclic one-shot LLM recording wrapper.")
        seen.add(id(client))
        client = client._inner
    routes = getattr(client, "routes", None)
    if routes is None:
        # Offline fixture/stub clients have no route registry of their own.
        routes, _ = resolve_preset(preset)
    try:
        return routes[name]
    except KeyError:
        raise ConfigError(f"unknown LLM route {name!r}") from None


_TIP_LIMITS = {
    "observation": OBSERVATION_MAX, "alternative": ALTERNATIVE_MAX, "why_it_matters": SENTENCE_MAX,
}


def limit_tips(output: dict) -> dict:
    """Cap the model's tips list and cut overlong tip text (no warning channel: kept, shortened)."""
    tips = output.get("tips")
    if not isinstance(tips, list):
        return output
    out = []
    for tip in tips[:MAX_TIPS_PROPOSED]:
        if isinstance(tip, dict):
            tip = {k: clip(v, _TIP_LIMITS[k])[0] if k in _TIP_LIMITS and isinstance(v, str) else v
                   for k, v in tip.items()}
        out.append(tip)
    return {**output, "tips": out}


class OneshotEngine(Engine):
    """A schema-bound config, safe to share between concurrent runs.

    Callers bind the selected variant with ``OneshotEngine(config=variant_id)``
    before validation or registry inspection. Every run still requires the matching
    ``params['config']``. Binding keeps ``output_schema()`` deterministic before and
    after execution; selecting another variant requires another engine instance.
    """

    name = "oneshot"
    version = version("onolys-oneshot")
    accepts_feedback = True

    def __init__(self, config: str = "miti") -> None:
        self._config = load_config(config)

    def output_schema(self) -> dict:
        return deepcopy(self._config.schema)

    def variants(self) -> list[EngineVariant]:
        return [
            EngineVariant(id=name, label=f"One-shot · {'MITI' if name == 'miti' else name}")
            for name in config_names()
        ]

    async def run(
        self,
        ctx: RunContext,
        transcript: TranscriptV1,
        params: dict,
        progress_cb: ProgressCb | None = None,
    ) -> EngineResult:
        config = self._config
        if params.get("config") != config.name:
            raise InputError("One-shot params.config must match the engine's bound config.")
        route = _route(ctx.llm, config.route, params.get("preset"))
        prompt = render_prompt(
            config, transcript, params, structured_output_mode=route.structured_output_mode,
        )
        user = prompt.user
        if ctx.feedback:
            user += "\n\nValidation feedback:\n" + ctx.feedback
        response = await ctx.llm.complete_json(
            LLMRequest(
                tier=config.route,
                system=prompt.system,
                user=user,
                response_schema=self.output_schema(),
                call_tag=f"oneshot.{config.name}",
                max_tokens=config.max_output_tokens,
                temperature=0,
                deadline=ctx.deadline,
            ),
            ctx.metrics,
        )
        if not isinstance(response.parsed, dict):
            raise LLMBadOutput("One-shot response must be a JSON object.")
        usage = response.usage
        span = params.get("coded_span")
        applied_span = (
            {key: value for key, value in span.items() if value is not None}
            if span is not None else {"start_turn": 0, "end_turn": len(transcript.turns)}
        )
        return EngineResult(
            output=limit_tips(response.parsed),
            run_info=RunInfo(
                engine=self.name,
                config=config.name,
                config_version=config.version,
                config_hash=config.config_hash,
                span=applied_span,
                model=response.model,
                route=config.route,
                structured_output_mode=route.structured_output_mode,
                usage=RunUsage(
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                    calls=1,
                    cost_usd=usage.cost_usd,
                    cache_read_tokens=usage.cache_read_tokens,
                    cache_write_tokens=usage.cache_write_tokens,
                ),
            ),
        )
