"""Tips: the model proposes, code validates.

One call on route `tips` sees only Onolys's own representative run (counted instances, globals
with reasons, summaries against their reference) and the clinician's turns, each with the
preceding client turn. The clinician's rating and any comparison never reach the prompt, so tips
derive from Onolys's rating alone.

Code then checks every proposal: the item is in the MITI definition, the quote is found in the named
clinician turn (core `locate`) and replaced by the real substring with offsets, the alternative
is non-empty, at most two sentences and not a copy of the quote, at most two tips per item and one
per (item, turn), and every text passes the tone lint. The first five valid tips are kept. Fewer
than three valid triggers one retry that lists the violations (codes, plus the length limits
for `field_too_long`; never the offending text); still fewer ships fewer with `fewer_tips`; a
failed call ships none with `tips_failed`.
Model choice, limits and sampling belong to the route.
"""

import json
import re
from dataclasses import dataclass
from typing import Any

from onolys_engine.llm import LLMBadOutput, LLMClient, LLMRequest, MetricsCollector
from onolys_engine.text_limits import (
    ALTERNATIVE_MAX,
    MAX_TIPS_PROPOSED,
    OBSERVATION_MAX,
    QUOTE_MAX,
    SENTENCE_MAX,
    TITLE_MAX,
)
from onolys_engine.transcript import Transcript
from pydantic import BaseModel

from onolys_miti import miti
from onolys_miti.code_pass import _opt_int
from onolys_miti.locate import locate
from onolys_miti.prepare import OTHER, SUBJECT, RoleTurn, mark_roles, select_turns
from onolys_miti.report import Tip, TipQuote, Warning
from onolys_miti.result import MitiResult
from onolys_miti.tone import tone_rules

ROUTE = "tips"
MIN_TIPS = 3
MAX_TIPS = 5
MAX_PER_ITEM = 2
MAX_ALT_SENTENCES = 2
DEFAULT_TIPS_MAX_TOKENS = None  # None: the route's output cap applies
PROMPT_FILE = "tips_system.md"

_OUTPUT_FORMAT = (
    "## Output format\n"
    'Reply with JSON only: {"tips": [{"title": "...", "item_id": "...", "observation": "...", '
    '"quote": {"turn_id": "...", "text": "..."}, "alternative": "...", '
    '"why_it_matters": "..."}]}.\n'
    "Propose at most 7 tips, ordered by expected impact. `item_id` is one id from the list of "
    "items. `quote.text` is copied verbatim from the one clinician turn named by `turn_id`. "
    "`alternative` is one or two sentences of replacement wording, not a copy of the quote. "
    "Use at most two tips per item and one tip per item and turn. If the user message lists "
    "`violations`, propose a corrected set that avoids them. Write in English, except quotes, "
    "which stay in the transcript's language."
)


@dataclass(frozen=True)
class _LocateCfg:
    fuzzy_threshold: float = 90
    fuzzy_min_len: int = 12


_CFG = _LocateCfg()


class _Quote(BaseModel):
    turn_id: str
    text: str


class _Proposal(BaseModel):
    title: str | None = None
    item_id: str
    observation: str
    quote: _Quote
    alternative: str
    why_it_matters: str


class TipsResponse(BaseModel):
    tips: list[_Proposal]


class TipsArtifact(BaseModel):
    """Validated tips plus the raw model proposals (for audit; never shown to users)."""

    valid: list[Tip]
    proposals: list[dict[str, Any]]


LIMITS_MESSAGE = (
    f"Over a length limit (characters): title {TITLE_MAX}, observation {OBSERVATION_MAX}, "
    f"alternative {ALTERNATIVE_MAX}, why_it_matters {SENTENCE_MAX}, quote text {QUOTE_MAX}. "
    "Shorten the fields to fit."
)


def _too_long(p: _Proposal) -> bool:
    """A field over its limit: the tip is dropped and re-proposed (like `alternative_too_long`)."""
    return (
        len(p.title or "") > TITLE_MAX
        or len(p.observation) > OBSERVATION_MAX
        or len(p.alternative) > ALTERNATIVE_MAX
        or len(p.why_it_matters) > SENTENCE_MAX
        or len(p.quote.text) > QUOTE_MAX
    )


def _sentences(text: str) -> int:
    return len([s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()])


def _squash(text: str) -> str:
    return re.sub(r"\W+", " ", text.casefold()).strip()


def _clinician_turns(
    transcript: Transcript, speaker_map: dict[str, Any], result: MitiResult
) -> list[dict[str, Any]]:
    """Clinician turns of the coded span, each with the preceding client turn (context only)."""
    marked, _ = mark_roles(transcript, speaker_map)
    span = result.coded_span.model_dump() if result.coded_span else None
    kept, _ = select_turns(marked, span)
    keep = {rt.turn.id for rt in kept}
    out: list[dict[str, Any]] = []
    prev: RoleTurn | None = None
    for rt in marked:
        if rt.role == OTHER:
            prev = rt
        elif rt.role == SUBJECT and rt.turn.id in keep:
            out.append(
                {
                    "turn_id": rt.turn.id,
                    "text": rt.turn.text,
                    "preceding_client_turn": (
                        {"turn_id": prev.turn.id, "text": prev.turn.text} if prev else None
                    ),
                }
            )
    return out


def _onolys_view(result: MitiResult) -> dict[str, Any]:
    run = next(r for r in result.results if r.run_index == result.aggregate.representative_run)
    return {
        "counts": run.counts,
        "instances": [
            {
                "turn_id": i.turn_id,
                "code": i.code,
                "quote": i.quote,
                "rationale": i.rationale,
            }
            for i in run.instances
            if i.counted
        ],
        "globals": {
            k: {"score": g.score, "reason": g.reason, "evidence": [e.quote for e in g.evidence]}
            for k, g in run.globals.items()
        },
        "summaries": {
            k: {
                "value": s.value,
                "label": s.label,
                "reference": s.reference.model_dump() if s.reference else None,
            }
            for k, s in run.summaries.items()
        },
    }


def _items_block() -> str:
    lines = ["## Items"] + [f"- {i['id']} ({i['label']}, {i['kind']})" for i in miti.MITI.items]
    return "\n".join(lines)


def _build_request(
    user: dict[str, Any],
    language: str | None,
    run_index: int,
    retry: bool,
    deadline: float | None = None,
) -> LLMRequest:
    system_md = (miti.MITI.data_dir / "prompts" / PROMPT_FILE).read_text(encoding="utf-8").strip()
    prefix = "\n\n".join([system_md, _items_block(), _OUTPUT_FORMAT])
    header = f"## Session\nTranscript language: {language or 'unspecified'}"
    tag = f"{ROUTE}:r{run_index}" + (":retry" if retry else "")
    return LLMRequest(
        tier=ROUTE,
        system="Propose coaching tips from the rating in the user message.",
        user=json.dumps(user, ensure_ascii=False),
        response_model=TipsResponse,
        call_tag=tag,
        cache_prefixes=[prefix, header],
        unit="tips",
        max_tokens=_opt_int(
            miti.MITI.data.get("params", {}).get("tips_max_tokens", DEFAULT_TIPS_MAX_TOKENS)
        ),
        deadline=deadline,
    )


def validate_proposals(
    proposals: list[_Proposal], turns: list[dict[str, Any]]
) -> tuple[list[Tip], list[dict[str, Any]]]:
    """Valid tips (first five, ranked) and the violations `[{index, code}]` of the rest."""
    rules = tone_rules()
    item_ids = {i["id"] for i in miti.MITI.items}
    by_id = {t["turn_id"]: t["text"] for t in turns}
    valid: list[Tip] = []
    violations: list[dict[str, Any]] = []
    per_item: dict[str, int] = {}
    seen: set[tuple[str, str]] = set()
    for n, p in enumerate(proposals):
        code = None
        text = by_id.get(p.quote.turn_id)
        m = locate(text, p.quote.text, None, _CFG) if text is not None and p.quote.text else None
        if len(valid) >= MAX_TIPS:
            break
        if p.item_id not in item_ids:
            code = "unknown_item"
        elif _too_long(p):
            code = "field_too_long"
        elif text is None:
            code = "not_clinician_turn"
        elif m is None:
            code = "quote_not_found"
        elif not (p.observation.strip() and p.why_it_matters.strip()):
            code = "empty_text"
        elif not p.alternative.strip():
            code = "alternative_empty"
        elif _sentences(p.alternative) > MAX_ALT_SENTENCES:
            code = "alternative_too_long"
        elif _squash(p.alternative) == _squash(text[m.start : m.end]):
            code = "alternative_same_as_quote"
        elif any(
            rules.lint(s) for s in (p.title or "", p.observation, p.alternative, p.why_it_matters)
        ):
            code = "tone"
        elif per_item.get(p.item_id, 0) >= MAX_PER_ITEM:
            code = "item_limit"
        elif (p.item_id, p.quote.turn_id) in seen:
            code = "duplicate_item_turn"
        if code is not None:
            violation = {"index": n, "code": code}
            if code == "field_too_long":
                violation["message"] = LIMITS_MESSAGE  # fixed text, no model output
            violations.append(violation)
            continue
        assert m is not None and text is not None
        per_item[p.item_id] = per_item.get(p.item_id, 0) + 1
        seen.add((p.item_id, p.quote.turn_id))
        valid.append(
            Tip(
                title=p.title.strip() or None if p.title is not None else None,
                rank=len(valid) + 1,
                item_id=p.item_id,
                observation=p.observation.strip(),
                quote=TipQuote(
                    turn_id=p.quote.turn_id,
                    start=m.start,
                    end=m.end,
                    text=text[m.start : m.end],
                ),
                alternative=p.alternative.strip(),
                why_it_matters=p.why_it_matters.strip(),
            )
        )
    return valid, violations


async def generate_tips(
    client: LLMClient,
    transcript: Transcript,
    speaker_map: dict[str, Any],
    miti_result: MitiResult,
    *,
    run_index: int = 0,
    metrics: MetricsCollector | None = None,
    deadline: float | None = None,
) -> tuple[TipsArtifact, list[Warning]]:
    """Tips for one evaluation. Never raises for model trouble: a failed call returns no tips
    and a `tips_failed` warning; fewer than three valid tips adds `fewer_tips`."""
    proposals: list[dict[str, Any]] = []
    try:
        turns = _clinician_turns(transcript, speaker_map, miti_result)
        base = {
            "change_goal": miti_result.change_goal,
            "onolys": _onolys_view(miti_result),
            "clinician_turns": turns,
        }
        parsed: list[_Proposal] = []
        valid: list[Tip] = []
        violations: list[dict[str, Any]] = []
        failed = False
        for attempt in (1, 2):
            user = base if attempt == 1 else {**base, "violations": violations}
            req = _build_request(
                user, miti_result.language, run_index, retry=attempt == 2, deadline=deadline
            )
            try:
                res = await client.complete_json(req, metrics)
            except LLMBadOutput:
                failed = attempt == 2 and not parsed
                if attempt == 2:
                    break
                continue
            kept = res.parsed.tips[:MAX_TIPS_PROPOSED]  # the prompt asks for at most 7
            parsed += kept
            proposals += [p.model_dump() for p in kept]
            valid, violations = validate_proposals(parsed, turns)
            if len(valid) >= MIN_TIPS:
                break
        if failed:
            return TipsArtifact(valid=[], proposals=proposals), [Warning(code="tips_failed")]
    except Exception:  # noqa: BLE001 - a tips failure never blocks the report
        return TipsArtifact(valid=[], proposals=proposals), [Warning(code="tips_failed")]
    warnings = [Warning(code="fewer_tips")] if len(valid) < MIN_TIPS else []
    return TipsArtifact(valid=valid, proposals=proposals), warnings
