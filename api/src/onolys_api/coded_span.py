"""Validate selection and engine limits before reserving a run or calling a model."""

from onolys_engine_core.errors import InvalidCodedSpan, SessionTooLong
from onolys_miti import miti
from onolys_miti.prepare import RoleTurn, _duration_ms, select_turns
from onolys_miti.result import CodedSpan
from onolys_miti.span import select_coded_span
from onolys_miti.transcript import Transcript

from onolys_api.adapters.error_map import PUBLIC_MESSAGES
from onolys_api.errors import ApiError


def validate_coded_input(transcript: Transcript, span: CodedSpan | None) -> None:
    # Input-quality/role checks remain the engine's responsibility; these checks need
    # neither a confirmed clinician nor a goal, so upload can reject a bad span early.
    try:
        choice = select_coded_span(transcript, "", span)
        bounds = choice.coded_span.model_dump(exclude_none=True) if choice.coded_span else None
        turns, _ = select_turns([RoleTurn(t, "other") for t in transcript.turns], bounds)
        duration = _duration_ms(transcript, turns, bounds)
        too_long = sum(len(rt.turn.text.split()) for rt in turns) > 6000
        for check in miti.MITI.data.get("input_checks", []):
            if check["kind"] == "duration_max" and duration is not None:
                too_long |= duration > check["value"] * 60_000
        if too_long:
            raise SessionTooLong("session_too_long")
    except (InvalidCodedSpan, SessionTooLong) as exc:
        raise ApiError.of(422, exc.code, PUBLIC_MESSAGES[exc.code]) from None
