"""Shared STT base class, `transcribe()` helper and `words_to_turns`."""

import asyncio
from abc import ABC, abstractmethod

from onolys_engine import Transcript, Turn, log_event

from onolys_api.transcription import AudioRef, SttCompletion, SttParams, SttRun, Word

DEFAULT_MAX_GAP_MS = 2000


def _turn_end(words: list[Word]) -> int | None:
    """Latest observed time in the turn; None when no word has a valid end."""
    ends = [w.end_ms for w in words if w.end_ms is not None]
    if not ends:
        return None
    return max(ends + [w.start_ms for w in words])


def _last_seen(word: Word) -> int:
    return max(word.start_ms, word.end_ms) if word.end_ms is not None else word.start_ms


def words_to_turns(words: list[Word], max_gap_ms: int = DEFAULT_MAX_GAP_MS) -> list[Turn]:
    """Group words into turns: new turn on speaker change or a gap above `max_gap_ms`.

    Speaker labels are normalised to S1..Sn by first appearance.
    Missing provider labels use the explicit uncertainty marker `unknown`.
    """
    turns: list[Turn] = []
    labels: dict[str, str] = {}
    cur: list[Word] = []

    def flush() -> None:
        if not cur:
            return
        raw = cur[0].speaker
        speaker = "unknown" if raw is None else labels.setdefault(raw, f"S{len(labels) + 1}")
        turns.append(
            Turn(
                id=f"t{len(turns) + 1}",
                speaker=speaker,
                text=" ".join(w.text for w in cur),
                start_ms=cur[0].start_ms,
                end_ms=_turn_end(cur),
            )
        )
        cur.clear()

    # Register labels in order of first appearance even when turns flush later.
    for w in words:
        if w.speaker is not None:
            labels.setdefault(w.speaker, f"S{len(labels) + 1}")
        if cur and (
            w.speaker != cur[-1].speaker
            or w.start_ms - _last_seen(cur[-1]) > max_gap_ms
        ):
            flush()
        cur.append(w)
    flush()
    return turns


def _audio_ms(words: list[Word]) -> int | None:
    return max((w.end_ms for w in words if w.end_ms is not None), default=None)


class BaseSttAdapter(ABC):
    """Adapters implement `_submit`/`_fetch` and return words only; `poll` builds turns."""

    max_gap_ms: int = DEFAULT_MAX_GAP_MS

    @abstractmethod
    async def _submit(self, audio: AudioRef, params: SttParams) -> str:
        """Submit the job; return an opaque, JSON-serialisable handle."""

    @abstractmethod
    async def _fetch(self, handle: str) -> tuple[list[Word], SttRun] | None:
        """Return (words, run), or None while still running. Must not re-submit."""

    async def start(self, audio: AudioRef, params: SttParams) -> str:
        handle = await self._submit(audio, params)
        log_event(
            "stt_submit",
            step="submit",
            stt_provider=params.provider,
            stt_model=params.model,
            language=params.language,
            audio_ms=audio.duration_ms,
            job_id=handle,
        )
        return handle

    async def poll(self, handle: str) -> SttCompletion | None:
        got = await self._fetch(handle)
        if got is None:
            log_event("stt_poll", step="poll", status="running", job_id=handle)
            return None
        words, run = got
        turns = words_to_turns(words, self.max_gap_ms)
        log_event(
            "stt_done",
            step="done",
            status="done",
            job_id=handle,
            stt_provider=run.provider,
            stt_model=run.model,
            language=run.language_detected or run.language_requested,
            speakers=len({w.speaker for w in words if w.speaker is not None}),
            audio_ms=_audio_ms(words),
        )
        return SttCompletion(
            transcript=Transcript(
                turns=turns,
                # Undetected language stays unknown; never defaulted to English.
                language=run.language_detected
                or (None if run.language_requested == "auto" else run.language_requested),
                duration_ms=_audio_ms(words),
            ),
            run=run,
        )


async def transcribe(
    adapter,
    audio: AudioRef,
    params: SttParams,
    *,
    interval_s: float = 1.0,
    max_polls: int | None = None,
) -> Transcript:
    """Start, then poll until done."""
    handle = await adapter.start(audio, params)
    polls = 0
    while True:
        result = await adapter.poll(handle)
        if result is not None:
            return result.transcript
        polls += 1
        if max_polls is not None and polls >= max_polls:
            raise TimeoutError(f"STT job {handle!r} not finished after {polls} polls")
        await asyncio.sleep(interval_s)
