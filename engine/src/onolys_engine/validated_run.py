"""Shared, bounded output validation for API and evaluation engine callers."""

from dataclasses import asdict

from .context import RunContext
from .engine import Engine, EngineResult, ProgressCb, RunUsage
from .errors import OnolysError
from .transcript_v1 import TranscriptV1
from .validate import ValidationIssue, build_feedback, validate_output

MAX_FIRST_ISSUES = 10


class OutputInvalid(OnolysError):
    """An engine exhausted its schema-validation attempts; no raw output is retained.

    ``validation`` is safe for run details. ``usage`` includes every completed
    attempt, including invalid outputs, so failed evaluations can account for cost.
    """

    code = "output_invalid"
    retryable = False

    def __init__(
        self, attempts: int, issues: list[ValidationIssue], usage: RunUsage | None = None,
    ):
        super().__init__("The engine returned an answer that did not match its schema.")
        self.attempts = attempts
        self.first_issues = issues[:MAX_FIRST_ISSUES]
        self.usage = usage

    @property
    def validation(self) -> dict:
        return {
            "attempts": self.attempts,
            "first_issues": [asdict(issue) for issue in self.first_issues],
        }


def _sum_usage(attempts: list[RunUsage | None]) -> RunUsage | None:
    if len(attempts) == 1:
        return attempts[0]
    known = [usage for usage in attempts if usage is not None]
    if not known:
        return None
    # Cache counters are optional numeric extras on the portable RunUsage contract.
    cache_totals = {}
    for usage in known:
        for key, value in (usage.model_extra or {}).items():
            if key.startswith("cache_") and isinstance(value, (int, float)):
                cache_totals[key] = cache_totals.get(key, 0) + value
    priced = len(known) == len(attempts) and all(u.cost_usd is not None for u in known)
    return RunUsage(
        input_tokens=sum(u.input_tokens for u in known),
        output_tokens=sum(u.output_tokens for u in known),
        calls=sum(u.calls for u in known),
        cost_usd=sum(u.cost_usd for u in known) if priced else None,
        **cache_totals,
    )


async def run_validated(
    engine: Engine,
    ctx: RunContext,
    transcript: TranscriptV1,
    params: dict,
    progress_cb: ProgressCb | None = None,
) -> EngineResult:
    """Validate an engine result, retrying once only for feedback-capable engines.

    Engine exceptions propagate unchanged. Caller feedback is restored on every
    exit so a shared context cannot carry correction feedback into the next run.
    """
    original_feedback = ctx.feedback
    usages = []
    try:
        for attempt in range(1, 3 if engine.accepts_feedback else 2):
            try:
                result = await engine.run(ctx, transcript, params, progress_cb)
            except Exception as exc:
                # A later attempt failing must not lose the spend of the completed ones.
                if usages and getattr(exc, "usage", None) is None:
                    try:
                        exc.usage = _sum_usage(usages)  # type: ignore[attr-defined]
                    except AttributeError:
                        pass
                raise
            usages.append(result.run_info.usage)
            issues = validate_output(result.output, engine.output_schema())
            usage = _sum_usage(usages)
            if not issues:
                return result.model_copy(update={
                    "run_info": result.run_info.model_copy(update={
                        "usage": usage,
                        "validation": {"attempts": attempt},
                    }),
                })
            if not engine.accepts_feedback or attempt == 2:
                raise OutputInvalid(attempt, issues, usage)
            ctx.feedback = build_feedback(issues)
    finally:
        ctx.feedback = original_feedback
