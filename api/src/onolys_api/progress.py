"""Progress numbers for the processing screen.

Pure tables and helpers, shared by `jobs.machine.advance`, the repo start/retry transactions and
the run worker, so the web only interpolates what the server publishes. Numbers and timestamps
only: no text reaches `session_status`. The expected durations are placeholders until real
timings exist; `STATE_PROGRESS` and `STAGE_WEIGHTS` keep their values.
"""

from collections.abc import Mapping
from datetime import datetime
from typing import Any

# progress table
STATE_PROGRESS: dict[str, int] = {
    "created": 0,
    "uploading": 5,
    "validating": 10,
    "transcribing": 20,
    "awaiting_input": 40,
    "running": 45,
    "report_ready": 100,
}
RUN_START_PROGRESS = STATE_PROGRESS["running"]
STAGE_WEIGHTS: dict[str, int] = {"code": 40, "tips": 8, "assemble": 3}
STAGES = tuple(STAGE_WEIGHTS)  # 45 + 51 = 96: under the 99 cap
MAX_PROGRESS = 99  # 100 belongs to `report_ready`

# the state a state hands over to (its bar segment ends at that state's base)
_NEXT_STATE = {
    "created": "uploading", "uploading": "validating", "validating": "transcribing",
    "transcribing": "awaiting_input", "awaiting_input": "running",
}  # fmt: skip

# the one server table of typical stage durations (seconds). Placeholders, except
# transcription, which scales with the recording (see `stage_expected_s`).
STAGE_EXPECTED_S: dict[str, int] = {
    "uploading": 30, "validating": 15,
    "code": 120, "tips": 40, "assemble": 15,
}  # fmt: skip
TRANSCRIBE_BASE_S, TRANSCRIBE_PER_AUDIO_S = 20, 0.2
TRANSCRIBE_MIN_S, TRANSCRIBE_MAX_S = 30, 600


def stage_expected_s(state: str, step: str | None, audio_s: float | None) -> int | None:
    """Typical duration (s) of the current stage; None for a state with no timed stage.
    Transcription: `clamp(20 + 0.2 x audio_s, 30, 600)`; an unknown `audio_s` counts as 0."""
    if state == "transcribing":
        raw = TRANSCRIBE_BASE_S + TRANSCRIBE_PER_AUDIO_S * max(0.0, audio_s or 0.0)
        return round(min(TRANSCRIBE_MAX_S, max(TRANSCRIBE_MIN_S, raw)))
    if state == "running":
        return STAGE_EXPECTED_S[step if step in STAGE_WEIGHTS else STAGES[0]]
    return STAGE_EXPECTED_S.get(state)


def progress_next(state: str, step: str | None) -> int | None:
    """Base % of the stage after the current one; the last stage (and `running` as a whole)
    caps at 99. None for a state with no next stage (done, failed, cancelled, deleting)."""
    if state == "running":
        stage = step if step in STAGE_WEIGHTS else STAGES[0]
        if stage == STAGES[-1]:
            return MAX_PROGRESS  # 100 is `report_ready`
        done = STAGES[: STAGES.index(stage) + 1]
        return RUN_START_PROGRESS + sum(STAGE_WEIGHTS[s] for s in done)
    nxt = _NEXT_STATE.get(state)
    return STATE_PROGRESS[nxt] if nxt else None


def stage_fields(state: str, step: str | None, audio_s: float | None) -> dict[str, Any]:
    return {
        "progress_next": progress_next(state, step),
        "stage_expected_s": stage_expected_s(state, step, audio_s),
    }


def _ms_between(start: datetime | None, end: datetime) -> int:
    return max(0, round((end - start).total_seconds() * 1000)) if start else 0


def timing_fields(
    prev_state: str,
    prev_entered: datetime | None,
    status: Mapping[str, Any],
    to: str,
    now: datetime,
) -> dict[str, Any]:
    """`stage_started_at`, plus `started_at` (first `uploading`, or a transcript upload leaving
    `created`; a re-run from `report_ready` restarts it and `waited_ms`) and `waited_ms` (grows
    when `awaiting_input` is left)."""
    out: dict[str, Any] = {"stage_started_at": now}
    waited = status.get("waited_ms") or 0
    if prev_state == "awaiting_input":
        waited += _ms_between(prev_entered, now)
    # first processing: audio enters `uploading`; a transcript goes `created` -> `awaiting_input`
    first = to == "uploading" or (prev_state == "created" and to == "awaiting_input")
    if first and not status.get("started_at"):
        out["started_at"] = now
    if to == "running" and prev_state == "report_ready":
        out["started_at"], waited = now, 0
    out["waited_ms"] = waited
    return out


def entry_fields(
    prev_state: str,
    prev_entered: datetime | None,
    status: Mapping[str, Any],
    to: str,
    step: str | None,
    now: datetime,
) -> dict[str, Any]:
    """Every progress field written when a session enters `to` (status doc only)."""
    return {
        **timing_fields(prev_state, prev_entered, status, to, now),
        **stage_fields(to, step, status.get("audio_s")),
    }
