"""Pure steps before any model call (PRD R2 steps 1-3): role marking, span selection,
input checks and volley building. Protocol-agnostic: "subject" / "other" roles only."""

import unicodedata
from dataclasses import dataclass, field
from typing import Any

from onolys_engine_core.errors import InputError, InvalidCodedSpan, SessionTooLong
from onolys_engine_core.spans import selected_duration_ms, validate_portion_limits
from onolys_engine_core.transcript import Transcript, Turn

from onolys_miti import miti, rules
from onolys_miti.result import CodedSpan, ResultWarning
from onolys_miti.span import select_coded_span

SUBJECT = "subject"
OTHER = "other"


@dataclass(frozen=True)
class RoleTurn:
    turn: Turn
    role: str  # "subject" | "other"


@dataclass(frozen=True)
class Volley:
    id: str  # v1..vN
    turns: list[Turn]  # subject turns, possibly separated by facilitative client input
    prev_other: Turn | None  # most recent other-speaker turn before the volley (context only)


@dataclass(frozen=True)
class CheckInput:
    """What `rules.check_input` sees."""

    turns: list[RoleTurn]  # selected turns
    params: dict[str, Any]
    duration_ms: int | None


@dataclass
class Prepared:
    turns: list[RoleTurn]
    volleys: list[Volley]
    warnings: list[ResultWarning] = field(default_factory=list)
    duration_ms: int | None = None


def _words(text: str) -> int:
    return len(text.split())


def mark_roles(
    transcript: Transcript, speaker_map: dict[str, Any]
) -> tuple[list[RoleTurn], list[ResultWarning]]:
    """`speaker_map["subject"]` is the subject's speaker id. Every other speaker is `other`.
    If the map also names `other`, a speaker matching neither (or no speaker at all) is
    unknown: treated as other, with one `unknown_speaker` warning."""
    subject = speaker_map.get(SUBJECT)
    if not subject:
        raise InputError("speaker_map.subject is required")
    other = speaker_map.get(OTHER)
    out: list[RoleTurn] = []
    unknown: list[str] = []
    for t in transcript.turns:
        if t.speaker == subject:
            out.append(RoleTurn(t, SUBJECT))
            continue
        if t.speaker == "unknown" or (other is not None and t.speaker != other):
            unknown.append(t.id)
        out.append(RoleTurn(t, OTHER))
    warnings = []
    if unknown:
        shown = ", ".join(unknown[:5]) + (" ..." if len(unknown) > 5 else "")
        warnings.append(
            ResultWarning(
                code="unknown_speaker",
                detail=f"{len(unknown)} turn(s) with unknown speaker treated as other: {shown}",
            )
        )
    return out, warnings


def select_turns(
    turns: list[RoleTurn], coded_span: dict[str, Any] | None
) -> tuple[list[RoleTurn], list[ResultWarning]]:
    """Keep whole turns in a zero-based slice or overlapping a time range.

    Untimed turns are kept alongside timed turns; a fully untimed transcript rejects time
    ranges. A missing end timestamp falls back to the start timestamp.
    """
    if coded_span is None:
        return list(turns), []
    span = select_coded_span(Transcript(turns=[rt.turn for rt in turns]), "", coded_span).coded_span
    if span.start_turn is not None:
        return turns[span.start_turn:span.end_turn], []
    kept = []
    for rt in turns:
        start = rt.turn.start_ms
        if start is None:
            kept.append(rt)
            continue
        end = rt.turn.end_ms if rt.turn.end_ms is not None else start
        if start < span.end_ms and end > span.start_ms:
            kept.append(rt)
    if not kept:
        raise InvalidCodedSpan("invalid_coded_span: time range selects no turns")
    return kept, []


def _spaceless_script(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]

    def relevant(c: str) -> bool:
        n = ord(c)
        return (
            0x0E00 <= n <= 0x0E7F  # Thai
            or 0x3040 <= n <= 0x30FF  # Hiragana / Katakana
            or 0x31F0 <= n <= 0x31FF  # Katakana extensions
            or 0xFF66 <= n <= 0xFF9D  # half-width Katakana
            or unicodedata.name(c, "").startswith(
                ("CJK UNIFIED IDEOGRAPH", "CJK COMPATIBILITY IDEOGRAPH")
            )
        )
    return bool(letters) and sum(relevant(c) for c in letters) * 2 >= len(letters)


def _size(text: str) -> tuple[int, bool]:
    spaceless = _spaceless_script(text)
    return (sum(not c.isspace() for c in text) if spaceless else _words(text)), spaceless


def _asks_question(text: str) -> bool:
    # A short tail after the final question is still a direct question (R1).
    text = text.rstrip()
    while text and (text[-1] in "\"'" or unicodedata.category(text[-1]) in {"Pe", "Pf"}):
        text = text[:-1].rstrip()
    last = max(text.rfind(marker) for marker in ("?", "？", "؟"))
    if last < 0:
        return False
    tail = text[last + 1:].strip()
    size, spaceless = _size(tail)
    return size <= (6 if spaceless else 3)


def build_volleys(turns: list[RoleTurn], volley_cfg: dict[str, Any]) -> list[Volley]:
    """Keep facilitative client input within a clinician volley (manual pp.13, 15–16).

    Size thresholds are engineering approximations; answers to a direct question
    always break. Client turns stay in Prepared.turns, never in codable volley turns.
    """
    min_words = int(volley_cfg.get("min_other_words", 3))
    min_chars = int(volley_cfg.get("min_other_chars", 6))
    volleys: list[Volley] = []
    current: list[Turn] = []
    prev_other: Turn | None = None
    current_prev: Turn | None = None

    def flush() -> None:
        nonlocal current
        if current:
            volleys.append(Volley(f"v{len(volleys) + 1}", current, current_prev))
            current = []

    for rt in turns:
        if rt.role == SUBJECT:
            if not current:
                current_prev = prev_other
            current.append(rt.turn)
        else:
            prev_other = rt.turn
            size, spaceless = _size(rt.turn.text)
            if size >= (min_chars if spaceless else min_words) or (
                current and _asks_question(current[-1].text)
            ):
                flush()
    flush()
    return volleys


def _duration_ms(
    transcript: Transcript, turns: list[RoleTurn], coded_span: dict[str, Any] | None
) -> int | None:
    """Measure the selected portion, using the header only for an untimed whole session."""
    return selected_duration_ms(transcript, [rt.turn for rt in turns], coded_span)


def run_input_checks(
    turns: list[RoleTurn], params: dict[str, Any], duration_ms: int | None
) -> list[ResultWarning]:
    """MITI `input_checks`: severity `error` raises `InputError`, `warn` returns a warning."""
    warnings: list[ResultWarning] = []
    n_subject = sum(rt.role == SUBJECT for rt in turns)
    n_other = len(turns) - n_subject
    for chk in miti.MITI.data.get("input_checks", []):
        kind, value = chk["kind"], chk["value"]
        code = "short_session"
        if kind == "duration_max":
            bad = duration_ms is not None and duration_ms > value * 60_000
            msg = f"session longer than {value} min; supply a narrower coded_span"
            code = "session_too_long"
        elif kind == "duration_min":
            bad = duration_ms is not None and duration_ms < value * 60_000
            msg = f"session shorter than {value} min"
        elif kind == "param_required":
            bad = params.get(value) in (None, "")
            msg = f"parameter '{value}' is required"
            code = "missing_param"
        elif kind == "min_subject_turns":
            bad = n_subject < value
            msg = f"fewer than {value} subject turns ({n_subject})"
        else:  # min_other_turns
            bad = n_other < value
            msg = f"fewer than {value} other-speaker turns ({n_other})"
        if not bad:
            continue
        if chk["severity"] == "error":
            error = SessionTooLong if code == "session_too_long" else InputError
            raise error(f"{chk['id']}: {msg}")
        warnings.append(ResultWarning(code=code, detail=f"{chk['id']}: {msg}"))
    return warnings


def _coerce(w: Any) -> ResultWarning:
    return w if isinstance(w, ResultWarning) else ResultWarning(**w)


def prepare(
    transcript: Transcript,
    params: dict[str, Any],
    coded_span: CodedSpan | dict[str, Any] | None = None,
) -> Prepared:
    """Roles -> select by span -> input checks (+ rules.check_input) -> volleys.
    Checks run on the selected turns, so a short span counts as a short session.
    An explicit keyword overrides params["coded_span"]; absent means the whole transcript."""
    speaker_map = params.get("speaker_map") or {}
    role_turns, warnings = mark_roles(transcript, speaker_map)
    if coded_span is None:
        coded_span = params.get("coded_span")
    choice = select_coded_span(transcript, "", coded_span)
    coded_span = choice.coded_span.model_dump(exclude_none=True) if choice.coded_span else None
    selected, span_warn = select_turns(role_turns, coded_span)
    warnings += span_warn
    duration = _duration_ms(transcript, selected, coded_span)
    validate_portion_limits([rt.turn for rt in selected], duration, max_duration_ms=None)
    warnings += run_input_checks(selected, params, duration)
    extra = rules.check_input(CheckInput(selected, params, duration), miti.MITI.data) or []
    warnings += [_coerce(w) for w in extra]
    volleys = build_volleys(selected, miti.MITI.data["volley"])
    return Prepared(selected, volleys, warnings, duration)
