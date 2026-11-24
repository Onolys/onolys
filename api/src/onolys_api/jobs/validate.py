"""The `validate` step (PRD R3, D5): bytes in safely, one canonical format out.

Checks in order: object size, magic bytes, ffprobe (audio stream, no video, 1 s to the
STT provider's `max_audio_s`, 20 min for Chirp 3).
A passing upload moves to `{uid}/{sid}/audio/original.{ext}`, is transcoded to
`canonical.flac` (16 kHz mono), the staged object is deleted, the recording doc is written,
and `transcribe` is enqueued. A failure removes every object of the session's audio and
records the public code. Idempotent: a redelivery after the move resumes from the original.
Logs carry codes only, never file names or content.
"""

import hashlib
import logging
import tempfile
from collections.abc import Callable
from pathlib import Path

from onolys_api import logs
from onolys_api.audio import (
    CANONICAL_TYPES,
    DEFAULT_MAX_DURATION_S,
    MIN_DURATION_S,
    SHORT_RECORDING_S,
    UNKNOWN_DURATION_MARGIN_S,
    AudioTools,
    ProbeResult,
    ToolError,
    canonical_key,
    original_key,
    sniff,
    staging_key,
)
from onolys_api.config import Settings
from onolys_api.jobs.alive import ensure_alive as _ensure_alive
from onolys_api.jobs.machine import advance
from onolys_api.jobs.queue import TaskPayload
from onolys_api.jobs.worker import Handler, PermanentError, TaskContext
from onolys_api.repo.base import NotFoundError
from onolys_api.repo.models import ClientInfo, InterviewDoc, RecordingDoc
from onolys_api.storage.base import MAX_UPLOAD_BYTES, BlobNotFoundError, BlobStore

SHORT_WARNING = "short_recording"
SHORT_INTERVIEW_WARNING = "short_interview"  # replaces `short_recording` for AI interviews

AUDIO_CHECK_EVENT = "interview_audio_check"
AUDIO_CHECK_RESULTS = ("ok", "mismatch", "skipped_no_relay_duration", "skipped_no_interview")


def _r1(value: float | None) -> float | None:
    return None if value is None else round(value, 1)


def log_interview_audio_check(
    *,
    session_id: str,
    interview_id: str,
    uploaded_s: float,
    relay_s: float | None,
    threshold_s: float,
    result: str,
    audio_format: str | None,
    probe: ProbeResult | None,
    session_client: ClientInfo | None,
    interview: InterviewDoc | None,
) -> None:
    """Emit the ONE `interview_audio_check` line of an interview-linked validation (02-logging
    R12/R13). The caller decides `result` (one of `AUDIO_CHECK_RESULTS`) and `threshold_s`; this
    only reports, so the mismatch rule can change without touching the line. INFO for `ok`,
    WARNING otherwise. Sources that are not there are omitted (absent), never an error.
    Numbers are rounded to 0.1 s. Carries ids, numbers and build/format names only."""
    iv_client = interview.client if interview else None
    relay = interview.relay if interview else None

    def client(name: str) -> str | None:  # the interview's own value wins over the session's
        return getattr(iv_client, name, None) or getattr(session_client, name, None)

    up, rel = _r1(uploaded_s), _r1(relay_s)
    logs.emit(
        AUDIO_CHECK_EVENT,
        logging.INFO if result == "ok" else logging.WARNING,
        session_id=session_id,
        interview_id=interview_id,
        uploaded_s=up,
        relay_s=rel,
        diff_s=None if relay_s is None else _r1(abs(uploaded_s - relay_s)),
        threshold_s=_r1(threshold_s),
        result=result,
        relay_version=relay.relay_version if relay else None,
        relay_revision=relay.relay_revision if relay else None,
        web_version=client("web_version"),
        user_agent=client("user_agent"),
        recorder_mime=client("recorder_mime"),
        audio_engine=client("audio_engine"),
        audio_format=audio_format,
        audio_codec=probe.codec_name if probe else None,
        audio_streams=probe.audio_streams if probe else None,
    )


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def make_validate_handler(
    blobs: BlobStore,
    tools: AudioTools,
    max_audio_s: Callable[[str | None, str | None], float] | None = None,
    settings: Settings | None = None,
) -> Handler:
    """`max_audio_s(provider, model)` gives the longest accepted audio for the session's STT.
    `settings` carries the AI interview bounds (`AI_MAX_SECONDS` + `AI_TOLERANCE_SECONDS`
    longest, `AI_MIN_SECONDS` shortest before a warning) used when the session has `interview_id`.
    """
    cfg = settings or Settings()

    def purge(uid: str, sid: str) -> None:
        blobs.delete_prefix(f"uploads/{uid}/{sid}/")
        blobs.delete_prefix(f"{uid}/{sid}/audio/")

    def ensure_alive(ctx: TaskContext) -> None:
        _ensure_alive(ctx.repo, blobs, ctx.uid, ctx.sid)

    def fail(ctx: TaskContext, code: str) -> PermanentError:
        purge(ctx.uid, ctx.sid)
        return PermanentError(code)

    def find_source(ctx: TaskContext, upload_id: str | None) -> tuple[str, bool] | None:
        """(key, already_moved): an original left by an earlier attempt, else the staged object.
        The validated original wins: a later PUT to the (still signed) staging URL must not
        replace audio that already passed."""
        for fmt in CANONICAL_TYPES:
            key = original_key(ctx.uid, ctx.sid, fmt)
            if blobs.exists(key):
                return key, True
        if upload_id:
            staged = staging_key(ctx.uid, ctx.sid, upload_id)
            if blobs.exists(staged):
                return staged, False
        return None

    def check_duration(
        ctx: TaskContext, seconds: float, limit: float, too_long: str = "audio_too_long"
    ) -> None:
        if seconds > limit:
            raise fail(ctx, too_long)
        if seconds < MIN_DURATION_S:
            raise fail(ctx, "audio_unreadable")

    def _matches_relay(
        ctx: TaskContext, session, seconds: float, fmt: str, probe: ProbeResult
    ) -> bool:
        """True when the upload matches the relay duration; logs the one audio-check line."""
        threshold = float(cfg.ai_tolerance_seconds)
        try:
            iv = ctx.repo.get_interview(ctx.uid, session.interview_id)
        except NotFoundError:
            iv = None
        recorded = iv.duration_s if iv else None
        if iv is None:
            result = "skipped_no_interview"
        elif recorded is None:
            result = "skipped_no_relay_duration"
        else:
            result = "ok" if abs(seconds - recorded) <= threshold else "mismatch"
        log_interview_audio_check(
            session_id=ctx.sid, interview_id=session.interview_id, uploaded_s=seconds,
            relay_s=recorded, threshold_s=threshold, result=result, audio_format=fmt,
            probe=probe, session_client=session.client, interview=iv,
        )  # fmt: skip
        return result == "ok"

    def validate(ctx: TaskContext) -> None:
        uid, sid = ctx.uid, ctx.sid
        session = ctx.repo.get_session(uid, sid)
        source = find_source(ctx, session.upload.upload_id if session.upload else None)
        if source is None:
            raise fail(ctx, "audio_unreadable")
        src_key, moved = source
        stt = session.stt
        limit = (
            max_audio_s(stt.provider, stt.model) if max_audio_s and stt else DEFAULT_MAX_DURATION_S
        )

        too_long = "audio_too_long"
        if session.interview_id:  # an AI interview recording: its own, tighter ceiling
            interview_limit = float(cfg.ai_max_seconds + cfg.ai_tolerance_seconds)
            if interview_limit <= limit:
                limit, too_long = interview_limit, "interview_too_long"

        size = blobs.size(src_key)
        if size is None:
            raise fail(ctx, "audio_unreadable")
        if size > MAX_UPLOAD_BYTES:
            raise fail(ctx, "audio_too_large")

        with tempfile.TemporaryDirectory(prefix="onolys-validate-") as tmp:
            local = Path(tmp) / "in.bin"
            flac = Path(tmp) / "canonical.flac"
            blobs.download_to(src_key, local)
            ctx.check_deadline()

            with local.open("rb") as f:
                fmt = sniff(f.read(64))
            if fmt is None:
                raise fail(ctx, "unsupported_audio")

            try:
                probe = tools.probe(local, fmt)
            except ToolError:
                raise fail(ctx, "audio_unreadable") from None
            if probe.video_streams > 0:
                raise fail(ctx, "unsupported_audio")
            if probe.audio_streams < 1:
                raise fail(ctx, "audio_unreadable")
            seconds = probe.duration_s
            if seconds is not None:
                check_duration(ctx, seconds, limit, too_long)

            try:
                cap = None if seconds is not None else limit + UNKNOWN_DURATION_MARGIN_S
                tools.to_flac(local, flac, cap, fmt)
                if seconds is None:  # header carried no duration: measure the transcoded file
                    seconds = tools.probe(flac).duration_s
            except ToolError:
                raise fail(ctx, "audio_unreadable") from None
            if seconds is None:
                raise fail(ctx, "audio_unreadable")
            check_duration(ctx, seconds, limit, too_long)
            ctx.check_deadline()

            orig = original_key(uid, sid, fmt)
            digest, nbytes = _sha256(local), local.stat().st_size
            ensure_alive(ctx)
            try:
                blobs.upload_from(canonical_key(uid, sid), flac, "audio/flac")
                if moved:
                    if src_key != orig:  # sniffed format differs from the earlier attempt's
                        blobs.move(src_key, orig)
                else:
                    blobs.move(src_key, orig)  # also deletes the staged object
            except BlobNotFoundError:
                ensure_alive(ctx)  # the DELETE swept the staged object under us
                raise
            blobs.delete_prefix(f"uploads/{uid}/{sid}/")  # late PUTs and stale-URL strays
            ensure_alive(ctx)  # a DELETE during the writes above must not leave audio behind

        if session.interview_id:
            # interview sessions are never counted (03-failure-policy R5): the check only logs
            _matches_relay(ctx, session, seconds, fmt, probe)
        ctx.repo.add_recording(
            uid,
            sid,
            "original",
            RecordingDoc(
                gcs_uri=blobs.uri(orig),
                size=nbytes,
                duration_ms=round(seconds * 1000),
                format=fmt,
                sha256=digest,
            ),
        )
        short = (
            (SHORT_INTERVIEW_WARNING, seconds < cfg.ai_min_seconds)
            if session.interview_id
            else (SHORT_WARNING, seconds < SHORT_RECORDING_S)
        )
        if short[1] and short[0] not in session.warnings:
            ctx.repo.update_session(uid, sid, {"warnings": [*session.warnings, short[0]]})
        if session.state == "validating":
            advance(ctx.repo, uid, sid, to="transcribing", step="transcribe")
        ctx.enqueue(TaskPayload(kind="transcribe", uid=uid, sid=sid))

    return validate
