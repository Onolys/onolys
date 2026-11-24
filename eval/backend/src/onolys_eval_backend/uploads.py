"""Private eval upload validation and persisted asynchronous STT poll chains."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from onolys_engine_core.errors import InvalidCodedSpan, SessionTooLong
from onolys_engine_core.spans import (
    apply_coded_span,
    selected_duration_ms,
    validate_portion_limits,
)
from onolys_engine_core.transcript_input import (
    TranscriptInputError,
    inferred_clinician_speaker,
    validate_transcript_input,
)
from onolys_engine_core.transcript_txt import parse_transcript_txt
from onolys_eval.gold import Gold
from onolys_miti.stt import AudioRef, SttParams
from pydantic import ValidationError
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser

router = APIRouter()
MAX_TRANSCRIPT_BYTES = 1024 * 1024
MAX_GOLD_BYTES = 1024 * 1024
# Cloud Run (HTTP/1) rejects request bodies over 32 MiB before this app can answer, with a
# non-JSON response and no CORS headers. Multipart therefore stays well below that cap;
# larger recordings go straight to the bucket through a signed URL (see /v1/uploads/audio).
MAX_MULTIPART_AUDIO_BYTES = 25 * 1024 * 1024
MAX_AUDIO_BYTES = 300 * 1024 * 1024
MAX_BODY_BYTES = MAX_MULTIPART_AUDIO_BYTES + MAX_GOLD_BYTES + 65536
MAX_CHANGE_GOAL_CHARS = 4000  # same limit as RunRequest.change_goal
SIGNED_URL_TTL_S = 900
TRANSCRIBE_DEADLINE_S = 2 * 3600
_AUDIO_TYPES = {
    ".mp3": {"audio/mpeg", "audio/mp3", "audio/x-mp3", "audio/mpeg3"},
    ".wav": {"audio/wav", "audio/x-wav", "audio/wave", "audio/vnd.wave"},
    ".m4a": {"audio/mp4", "audio/x-m4a", "audio/m4a"},
    ".webm": {"audio/webm"},
    ".ogg": {"audio/ogg", "application/ogg"},
}


def _now():
    return datetime.now(UTC)


def error(status, code, message):
    raise HTTPException(status, detail={"code": code, "message": message})


def bundle(request):
    return request.app.state.services


async def read_upload(request, upload_id):
    saved = await asyncio.to_thread(bundle(request).repository.get_upload, upload_id)
    if saved is None:
        error(404, "not_found", "Upload not found.")
    return saved


def _transcribe_expired(saved):
    """Persisted poll budget: measured from when transcription was queued."""
    since = saved.get("transcribing_since") or saved.get("created_at")
    try:
        started = datetime.fromisoformat(since)
    except (TypeError, ValueError):
        return False
    return _now() - started > timedelta(seconds=TRANSCRIBE_DEADLINE_S)


TRANSCRIBE_TIMEOUT = {
    "status": "failed",
    "error": {"code": "transcription_timeout", "message": "Transcription timed out."},
}


# Provider submission can outlive a delivery; only its current owner may publish a handle.
STT_START_LEASE_S = 120


def _transcribe_match(saved):
    return {key: saved.get(key) for key in (
        "stt_handle", "transcribing_since", "created_at", "stt_start_owner", "stt_start_until",
    )}


async def _transcribe_transition(services, uid, saved, updates):
    return await asyncio.to_thread(
        services.repository.transition_upload, uid, "transcribing", updates,
        match=_transcribe_match(saved),
    )


async def _discard_candidate(bucket, path):
    # Only an unpublished, UUID-named candidate may be removed. Never remove a
    # published transcript: a run or concurrent reader may still reference it.
    delete = getattr(bucket, "delete", None)
    if delete is not None:
        try:
            await asyncio.to_thread(delete, path)
        except Exception:
            pass  # Best effort; cleanup must not turn a lost race into a user failure.


def response(upload_id, saved):
    data = {
        "upload_id": upload_id,
        "status": saved["status"],
        "has_gold": saved["has_gold"],
        "speakers": saved.get("speakers", []),
    }
    if saved.get("error"):
        data["error"] = saved["error"]
    return data


def transcript_metadata(transcript):
    clinician = inferred_clinician_speaker(transcript)
    speakers = {}
    for turn in transcript.turns:
        samples = speakers.setdefault(turn.speaker, [])
        if len(samples) < 3:
            samples.append(turn.text)
    return {
        "status": "ready" if clinician else "awaiting_speakers",
        "clinician_speaker": clinician,
        "speakers": [{"speaker": label, "samples": samples} for label, samples in speakers.items()],
    }


def validate_span(transcript, span):
    selected = apply_coded_span(transcript, span)
    validate_portion_limits(selected.turns, selected_duration_ms(transcript, selected.turns, span))


def validate_gold(gold, transcript):
    if transcript is None:
        return
    validate_span(transcript, gold.coded_span.model_dump() if gold.coded_span else None)
    ids = {turn.id for turn in transcript.turns}
    if any(row.turn_id not in ids for row in gold.utterance_codes or []):
        error(422, "gold_invalid", "Gold refers to an unknown transcript turn.")


def audio_matches(ext, head):
    return {
        ".wav": head[:4] == b"RIFF" and head[8:12] == b"WAVE",
        ".mp3": head[:3] == b"ID3" or (len(head) >= 2 and head[0] == 255 and head[1] & 224 == 224),
        ".m4a": head[4:8] == b"ftyp",
        ".webm": head[:4] == b"\x1aE\xdf\xa3",
        ".ogg": head[:4] == b"OggS",
    }.get(ext, False)


async def bounded_form(request):
    if not request.headers.get("content-type", "").lower().startswith("multipart/form-data;"):
        error(415, "unsupported_media_type", "Use multipart/form-data.")
    length = request.headers.get("content-length", "")
    if length.isdigit() and int(length) > MAX_BODY_BYTES:
        error(413, "upload_too_large", "Upload exceeds the size limit.")

    class BodyTooLarge(MultiPartException):
        pass

    async def bounded_stream():
        total = 0
        async for chunk in request.stream():
            total += len(chunk)
            if total > MAX_BODY_BYTES:
                # The parser closes its spooled files when this exception is raised.
                raise BodyTooLarge("Upload exceeds the size limit.")
            yield chunk

    try:
        return await MultiPartParser(
            request.headers, bounded_stream(), max_files=2, max_fields=3
        ).parse()
    except BodyTooLarge:
        error(413, "upload_too_large", "Upload exceeds the size limit.")
    except MultiPartException:
        error(400, "multipart_invalid", "Invalid multipart upload.")


@router.post("/v1/uploads")
async def upload(request: Request):
    form = await bounded_form(request)
    try:
        if len(form) != len(form.multi_items()) or set(form) - {
            "file",
            "gold",
            "change_goal",
            "language",
            "coded_span",
        }:
            error(422, "upload_invalid", "Invalid upload fields.")
        file, gold_file = form.get("file"), form.get("gold")
        if not isinstance(file, UploadFile) or (
            gold_file is not None and not isinstance(gold_file, UploadFile)
        ):
            error(422, "upload_invalid", "An input file is required.")
        ext = Path(file.filename or "").suffix.lower()
        media = (file.content_type or "").split(";", 1)[0].strip().lower()
        allowed = {".json": {"application/json"}, ".txt": {"text/plain"}, **_AUDIO_TYPES}
        if ext not in allowed or (media and media not in allowed[ext]):
            error(415, "unsupported_media_type", "Unsupported file type.")
        is_audio = ext in _AUDIO_TYPES
        limit = MAX_MULTIPART_AUDIO_BYTES if is_audio else MAX_TRANSCRIPT_BYTES
        raw = await file.read(limit + 1)
        if len(raw) > limit:
            error(
                413,
                "upload_too_large",
                "Input file exceeds the size limit."
                if not is_audio
                else "Recording is too large for this upload; use the direct upload.",
            )
        if not raw:
            error(422, "upload_invalid", "The input file is empty.")
        change_goal, language = form.get("change_goal", ""), form.get("language", "en")
        if (
            not isinstance(change_goal, str)
            or not isinstance(language, str)
            or len(change_goal) > MAX_CHANGE_GOAL_CHARS
            or not 1 <= len(language) <= 64
        ):
            error(422, "upload_invalid", "Invalid change goal or language.")
        span_value = form.get("coded_span")
        span = json.loads(span_value) if span_value else None
        # Validate shape now, and bounds against the real transcript before it is ready.
        if span is not None:
            from onolys_eval._contracts import CodedSpan
            from pydantic import TypeAdapter

            validated_span = TypeAdapter(CodedSpan).validate_python(span)
            span = validated_span.model_dump() if validated_span is not None else None
        transcript = None
        if not is_audio:
            transcript = (
                parse_transcript_txt(raw)
                if ext == ".txt"
                else validate_transcript_input(json.loads(raw))
            )
            validate_span(transcript, span)
            metadata = transcript_metadata(transcript)
        else:
            if not audio_matches(ext, raw[:16]):
                error(422, "audio_invalid", "Audio bytes do not match the file type.")
            metadata = {"status": "transcribing", "speakers": [], "clinician_speaker": None}
        gold = None
        if gold_file is not None:
            gold_raw = await gold_file.read(MAX_GOLD_BYTES + 1)
            if len(gold_raw) > MAX_GOLD_BYTES:
                error(413, "upload_too_large", "Gold file exceeds the size limit.")
            gold = Gold.model_validate_json(gold_raw)
            validate_gold(gold, transcript)
        services = bundle(request)
        params = services.stt_params(language) if is_audio else None
        uid = uuid4().hex
        prefix = f"uploads/{uid}"
        saved = {
            "name": Path(file.filename or "input").name,
            "kind": "audio" if is_audio else "transcript",
            "input_path": f"{prefix}/input{ext}",
            "transcript_path": f"{prefix}/transcript.json",
            "gold_path": f"{prefix}/gold.json" if gold else None,
            "has_gold": gold is not None,
            "change_goal": change_goal,
            "language": language,
            "coded_span": span,
            "content_type": media or sorted(allowed[ext])[0],
            "created_by": request.state.admin_claims["email"].strip().lower(),
            "created_at": datetime.now(UTC).isoformat(),
            **metadata,
        }
        if params:
            saved["stt_params"] = params.model_dump(mode="json")
        if is_audio:
            saved["transcribing_since"] = _now().isoformat()
        # Blocking client calls run off the event loop so other requests keep flowing.
        await asyncio.to_thread(
            services.bucket.write_bytes, saved["input_path"], raw,
            content_type=saved["content_type"]
        )
        if gold:
            await asyncio.to_thread(
                services.bucket.write_json,
                saved["gold_path"],
                gold.model_dump(mode="json", by_alias=True),
            )
        if transcript:
            await asyncio.to_thread(
                services.bucket.write_json,
                saved["transcript_path"],
                transcript.model_dump(mode="json"),
            )
        await asyncio.to_thread(services.repository.create_upload, uid, saved)
        if is_audio:
            await asyncio.to_thread(services.queue.enqueue, "transcribe", {"upload_id": uid})
        return response(uid, saved)
    except (
        TranscriptInputError,
        InvalidCodedSpan,
        SessionTooLong,
        ValidationError,
        ValueError,
        UnicodeDecodeError,
        RecursionError,
        TypeError,
    ):
        error(422, "upload_invalid", "Invalid transcript, gold, or coded span.")
    finally:
        await form.close()


@router.post("/v1/uploads/audio")
async def start_audio_upload(request: Request):
    """Direct-to-bucket recording upload: avoids Cloud Run's 32 MiB request cap and RAM use.

    JSON body: filename, content_type, size, optional change_goal, language, coded_span, gold.
    Returns a signed PUT target; the client then calls POST /v1/uploads/{id}/complete.
    """
    try:
        body = await request.json()
    except ValueError:
        error(422, "upload_invalid", "A JSON body is required.")
    if not isinstance(body, dict) or set(body) - {
        "filename", "content_type", "size", "change_goal", "language", "coded_span", "gold",
    }:
        error(422, "upload_invalid", "Invalid upload fields.")
    ext = Path(str(body.get("filename") or "")).suffix.lower()
    media = str(body.get("content_type") or "").split(";", 1)[0].strip().lower()
    if ext not in _AUDIO_TYPES or (media and media not in _AUDIO_TYPES[ext]):
        error(415, "unsupported_media_type", "Unsupported file type.")
    size = body.get("size")
    if not isinstance(size, int) or isinstance(size, bool) or size < 1:
        error(422, "upload_invalid", "The recording size is required.")
    if size > MAX_AUDIO_BYTES:
        error(413, "upload_too_large", "Input file exceeds the size limit.")
    change_goal, language = body.get("change_goal", ""), body.get("language", "en")
    if (
        not isinstance(change_goal, str)
        or not isinstance(language, str)
        or len(change_goal) > MAX_CHANGE_GOAL_CHARS
        or not 1 <= len(language) <= 64
    ):
        error(422, "upload_invalid", "Invalid change goal or language.")
    try:
        span = body.get("coded_span")
        if span is not None:
            from onolys_eval._contracts import CodedSpan
            from pydantic import TypeAdapter

            validated = TypeAdapter(CodedSpan).validate_python(span)
            span = validated.model_dump() if validated is not None else None
        gold = None
        if body.get("gold") is not None:
            if len(json.dumps(body["gold"])) > MAX_GOLD_BYTES:
                error(413, "upload_too_large", "Gold file exceeds the size limit.")
            gold = Gold.model_validate(body["gold"])
            validate_gold(gold, None)  # turn IDs are checked once the transcript exists
    except (ValidationError, ValueError, TypeError, RecursionError):
        error(422, "upload_invalid", "Invalid gold or coded span.")
    services = bundle(request)
    params = services.stt_params(language)
    uid = uuid4().hex
    prefix = f"uploads/{uid}"
    content_type = media or sorted(_AUDIO_TYPES[ext])[0]
    saved = {
        "name": Path(str(body["filename"])).name,
        "kind": "audio",
        "input_path": f"{prefix}/input{ext}",
        "transcript_path": f"{prefix}/transcript.json",
        "gold_path": f"{prefix}/gold.json" if gold else None,
        "has_gold": gold is not None,
        "change_goal": change_goal,
        "language": language,
        "coded_span": span,
        "content_type": content_type,
        "expected_size": size,
        "created_by": request.state.admin_claims["email"].strip().lower(),
        "created_at": _now().isoformat(),
        "status": "awaiting_upload",
        "speakers": [],
        "clinician_speaker": None,
        "stt_params": params.model_dump(mode="json"),
    }
    target = await asyncio.to_thread(
        services.bucket.signed_upload_url,
        saved["input_path"],
        content_type,
        expires_s=SIGNED_URL_TTL_S,
        max_bytes=MAX_AUDIO_BYTES,
    )
    if gold:
        await asyncio.to_thread(
            services.bucket.write_json, saved["gold_path"],
            gold.model_dump(mode="json", by_alias=True)
        )
    await asyncio.to_thread(services.repository.create_upload, uid, saved)
    return {**response(uid, saved), "upload": target}


async def _ensure_audio_dispatch(services, upload_id, saved):
    if saved.get("initial_task_enqueued"):
        return
    # A stable task id closes the enqueue/record window, including concurrent completes.
    await asyncio.to_thread(
        services.queue.enqueue, "transcribe", {"upload_id": upload_id},
        task_id=f"upload-{upload_id}",
    )
    await asyncio.to_thread(
        services.repository.update_upload, upload_id, {"initial_task_enqueued": True}
    )


@router.post("/v1/uploads/{upload_id}/complete")
async def complete_audio_upload(upload_id: str, request: Request):
    saved = await read_upload(request, upload_id)
    if saved["status"] != "awaiting_upload":
        # Idempotent: a repeated call after success reports the current state.
        if saved["status"] in {"transcribing", "awaiting_speakers", "ready"}:
            if saved["status"] == "transcribing":
                await _ensure_audio_dispatch(bundle(request), upload_id, saved)
            return response(upload_id, saved)
        error(409, "upload_not_ready", "This upload cannot be completed.")
    services = bundle(request)
    size = await asyncio.to_thread(services.bucket.size, saved["input_path"])
    if size is None:
        error(409, "upload_missing", "The recording has not been uploaded yet.")
    ext = Path(saved["input_path"]).suffix
    head = b""
    if 0 < size <= MAX_AUDIO_BYTES:
        head = await asyncio.to_thread(services.bucket.read_head, saved["input_path"], 16)
    if not 0 < size <= MAX_AUDIO_BYTES or not audio_matches(ext, head):
        failed = {
            "status": "failed",
            "error": {
                "code": "audio_invalid", "message": "Audio bytes do not match the file type."
            },
        }
        changed = await asyncio.to_thread(
            services.repository.transition_upload, upload_id, "awaiting_upload", failed
        )
        if not changed:
            return response(upload_id, await read_upload(request, upload_id))
        error(422, "audio_invalid", "Audio bytes do not match the file type.")
    updates = {"status": "transcribing", "transcribing_since": _now().isoformat()}
    transitioned = await asyncio.to_thread(
        services.repository.transition_upload, upload_id, "awaiting_upload", updates
    )
    if not transitioned:
        current = await read_upload(request, upload_id)
        if current["status"] == "transcribing":
            await _ensure_audio_dispatch(services, upload_id, current)
        return response(upload_id, current)
    await _ensure_audio_dispatch(services, upload_id, saved)
    return response(upload_id, {**saved, **updates})


@router.get("/v1/uploads/{upload_id}")
async def get_upload(upload_id: str, request: Request):
    saved = await read_upload(request, upload_id)
    if saved["status"] == "transcribing" and _transcribe_expired(saved):
        # Reconcile a chain whose last poll was lost: the budget, not a task, ends it.
        changed = await _transcribe_transition(
            bundle(request), upload_id, saved, TRANSCRIBE_TIMEOUT
        )
        saved = ({**saved, **TRANSCRIBE_TIMEOUT} if changed
                 else await read_upload(request, upload_id))
    return response(upload_id, saved)


@router.post("/v1/uploads/{upload_id}/speakers")
async def pick_speaker(upload_id: str, request: Request):
    saved = await read_upload(request, upload_id)
    if saved["status"] not in {"ready", "awaiting_speakers"}:
        error(409, "upload_not_ready", "Transcription is not ready.")
    try:
        body = await request.json()
    except ValueError:
        error(422, "speaker_invalid", "Choose an observed speaker.")
    speaker = body.get("clinician_speaker") if isinstance(body, dict) else None
    if not isinstance(speaker, str) or speaker not in {row["speaker"] for row in saved["speakers"]}:
        error(422, "speaker_invalid", "Choose an observed speaker.")
    services = bundle(request)
    transcript = validate_transcript_input(
        await asyncio.to_thread(services.bucket.read_json, saved["transcript_path"])
    )
    transcript = transcript.model_copy(
        update={
            "turns": [
                turn.model_copy(
                    update={"role": "clinician" if turn.speaker == speaker else "client"}
                )
                for turn in transcript.turns
            ]
        }
    )
    metadata = transcript_metadata(transcript)
    await asyncio.to_thread(
        services.bucket.write_json,
        path := f"uploads/{upload_id}/transcripts/{uuid4().hex}.json",
        transcript.model_dump(mode="json"),
    )
    metadata["transcript_path"] = path
    changed = await asyncio.to_thread(
        services.repository.transition_upload, upload_id, saved["status"], metadata,
        match={"transcript_path": saved["transcript_path"],
               "clinician_speaker": saved.get("clinician_speaker")},
    )
    if changed:
        return response(upload_id, {**saved, **metadata})
    await _discard_candidate(services.bucket, path)
    current = await read_upload(request, upload_id)
    if current["status"] == "ready" and current.get("clinician_speaker") == speaker:
        return response(upload_id, current)
    error(409, "speaker_conflict", "The speaker choice changed. Reload the upload and try again.")


@router.post("/internal/tasks/transcribe")
async def transcribe_task(request: Request):
    try:
        body = await request.json()
    except ValueError:
        error(422, "task_invalid", "An upload ID is required.")
    uid = body.get("upload_id") if isinstance(body, dict) else None
    if not isinstance(uid, str) or not uid:
        error(422, "task_invalid", "An upload ID is required.")
    services = bundle(request)
    saved = await asyncio.to_thread(services.repository.get_upload, uid)
    if saved is None or saved["status"] != "transcribing":
        return {"status": "ok"}
    if _transcribe_expired(saved):
        # Bounds the self-re-enqueueing poll chain: new tasks get fresh delivery retries.
        await _transcribe_transition(services, uid, saved, TRANSCRIBE_TIMEOUT)
        return {"status": "ok"}
    until = saved.get("stt_start_until")
    if not saved.get("stt_handle") and until is not None and datetime.fromisoformat(until) > _now():
        # Queue errors stay retryable; they are not transcription failures.
        await asyncio.to_thread(
            services.queue.enqueue, "transcribe", {"upload_id": uid}, delay_seconds=15
        )
        return {"status": "ok"}
    try:
        params = SttParams.model_validate(saved["stt_params"])
        adapter = (
            services.stt if hasattr(services, "stt") else services.stt_factory(params.provider)
        )
        handle = saved.get("stt_handle")
        if not handle:
            claim = {
                "stt_start_owner": uuid4().hex,
                "stt_start_until": (_now() + timedelta(seconds=STT_START_LEASE_S)).isoformat(),
            }
            if not await _transcribe_transition(services, uid, saved, claim):
                return {"status": "ok"}
            saved = {**saved, **claim}
            handle = await adapter.start(
                AudioRef(
                    uri=f"gs://{request.app.state.config.bucket}/{saved['input_path']}",
                    mime=saved["content_type"],
                ),
                params,
            )
            updates = {"stt_handle": handle, "stt_start_until": None}
            if not await _transcribe_transition(services, uid, saved, updates):
                return {"status": "ok"}
            saved = {**saved, **updates}
        else:
            complete = await adapter.poll(handle)
            if complete is not None:
                transcript = validate_transcript_input(complete.transcript.model_dump(mode="json"))
                validate_span(transcript, saved.get("coded_span"))
                if saved["has_gold"]:
                    validate_gold(
                        Gold.model_validate(
                            await asyncio.to_thread(services.bucket.read_json, saved["gold_path"])
                        ),
                        transcript,
                    )
                metadata = transcript_metadata(transcript)
                await asyncio.to_thread(
                    services.bucket.write_json,
                    path := f"uploads/{uid}/transcripts/{uuid4().hex}.json",
                    transcript.model_dump(mode="json"),
                )
                changed = await _transcribe_transition(
                    services, uid, saved,
                    {**metadata, "transcript_path": path,
                     "stt_run": complete.run.model_dump(mode="json")},
                )
                if not changed:
                    await _discard_candidate(services.bucket, path)
                return {"status": "ok"}
    except Exception:
        await _transcribe_transition(
            services, uid, saved,
            {
                "status": "failed",
                "error": {"code": "transcription_failed", "message": "Transcription failed."},
            },
        )
        return {"status": "ok"}
    # Queue failures remain 5xx so Cloud Tasks retries the persisted handle.
    await asyncio.to_thread(
        services.queue.enqueue, "transcribe", {"upload_id": uid}, delay_seconds=15
    )
    return {"status": "ok"}


def install_error_handler(app):
    @app.exception_handler(HTTPException)
    async def public_error(request, exc):
        if isinstance(exc.detail, dict) and "code" in exc.detail:
            return JSONResponse({"error": exc.detail}, status_code=exc.status_code)
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
