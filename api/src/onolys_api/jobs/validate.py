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
import tempfile
from collections.abc import Callable
from pathlib import Path

from onolys_api.audio import (
    CANONICAL_TYPES,
    DEFAULT_MAX_DURATION_S,
    MIN_DURATION_S,
    SHORT_RECORDING_S,
    UNKNOWN_DURATION_MARGIN_S,
    AudioTools,
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
from onolys_api.repo.models import RecordingDoc
from onolys_api.storage.base import MAX_UPLOAD_BYTES, BlobNotFoundError, BlobStore

SHORT_WARNING = "short_recording"
SHORT_INTERVIEW_WARNING = "short_interview"  # replaces `short_recording` for AI interviews


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

    def _matches_relay(ctx: TaskContext, session, seconds: float) -> bool:
        try:
            recorded = ctx.repo.get_interview(ctx.uid, session.interview_id).duration_s
        except NotFoundError:
            return False
        return recorded is not None and abs(seconds - recorded) <= cfg.ai_tolerance_seconds

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
            # A10: the free first run is only for the interview's own recording: the uploaded
            # audio must last as long as the relay recorded (within the tolerance)
            ctx.repo.update_session(
                uid, sid, {"free_run_void": not _matches_relay(ctx, session, seconds)}
            )
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
