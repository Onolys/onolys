"""Private eval upload validation and persisted asynchronous STT poll chains."""

import json
from datetime import UTC, datetime
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
MAX_AUDIO_BYTES = 300 * 1024 * 1024
MAX_BODY_BYTES = MAX_AUDIO_BYTES + MAX_GOLD_BYTES + 65536
_AUDIO_TYPES = {
    ".mp3": {"audio/mpeg", "audio/mp3", "audio/x-mp3", "audio/mpeg3"},
    ".wav": {"audio/wav", "audio/x-wav", "audio/wave", "audio/vnd.wave"},
    ".m4a": {"audio/mp4", "audio/x-m4a", "audio/m4a"},
    ".webm": {"audio/webm"},
    ".ogg": {"audio/ogg", "application/ogg"},
}


def error(status, code, message):
    raise HTTPException(status, detail={"code": code, "message": message})


def bundle(request):
    return request.app.state.services


def read_upload(request, upload_id):
    saved = bundle(request).repository.get_upload(upload_id)
    if saved is None:
        error(404, "not_found", "Upload not found.")
    return saved


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
        raw = await file.read((MAX_AUDIO_BYTES if is_audio else MAX_TRANSCRIPT_BYTES) + 1)
        if len(raw) > (MAX_AUDIO_BYTES if is_audio else MAX_TRANSCRIPT_BYTES):
            error(413, "upload_too_large", "Input file exceeds the size limit.")
        if not raw:
            error(422, "upload_invalid", "The input file is empty.")
        change_goal, language = form.get("change_goal", ""), form.get("language", "en")
        if (
            not isinstance(change_goal, str)
            or not isinstance(language, str)
            or len(change_goal) > 10000
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
        services.bucket.write_bytes(saved["input_path"], raw, content_type=saved["content_type"])
        if gold:
            services.bucket.write_json(
                saved["gold_path"], gold.model_dump(mode="json", by_alias=True)
            )
        if transcript:
            services.bucket.write_json(saved["transcript_path"], transcript.model_dump(mode="json"))
        services.repository.create_upload(uid, saved)
        if is_audio:
            services.queue.enqueue("transcribe", {"upload_id": uid})
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


@router.get("/v1/uploads/{upload_id}")
async def get_upload(upload_id: str, request: Request):
    return response(upload_id, read_upload(request, upload_id))


@router.post("/v1/uploads/{upload_id}/speakers")
async def pick_speaker(upload_id: str, request: Request):
    saved = read_upload(request, upload_id)
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
    transcript = validate_transcript_input(services.bucket.read_json(saved["transcript_path"]))
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
    services.bucket.write_json(saved["transcript_path"], transcript.model_dump(mode="json"))
    services.repository.update_upload(upload_id, metadata)
    return response(upload_id, {**saved, **metadata})


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
    saved = services.repository.get_upload(uid)
    if saved is None or saved["status"] != "transcribing":
        return {"status": "ok"}
    try:
        params = SttParams.model_validate(saved["stt_params"])
        adapter = (
            services.stt if hasattr(services, "stt") else services.stt_factory(params.provider)
        )
        handle = saved.get("stt_handle")
        if not handle:
            handle = await adapter.start(
                AudioRef(
                    uri=f"gs://{request.app.state.config.bucket}/{saved['input_path']}",
                    mime=saved["content_type"],
                ),
                params,
            )
            services.repository.update_upload(uid, {"stt_handle": handle})
        else:
            complete = await adapter.poll(handle)
            if complete is not None:
                transcript = validate_transcript_input(complete.transcript.model_dump(mode="json"))
                validate_span(transcript, saved.get("coded_span"))
                if saved["has_gold"]:
                    validate_gold(
                        Gold.model_validate(services.bucket.read_json(saved["gold_path"])),
                        transcript,
                    )
                metadata = transcript_metadata(transcript)
                services.bucket.write_json(
                    saved["transcript_path"], transcript.model_dump(mode="json")
                )
                services.repository.update_upload(
                    uid, {**metadata, "stt_run": complete.run.model_dump(mode="json")}
                )
                return {"status": "ok"}
    except Exception:
        services.repository.update_upload(
            uid,
            {
                "status": "failed",
                "error": {"code": "transcription_failed", "message": "Transcription failed."},
            },
        )
        return {"status": "ok"}
    # Queue failures remain 5xx so Cloud Tasks retries the persisted handle.
    services.queue.enqueue("transcribe", {"upload_id": uid}, delay_seconds=15)
    return {"status": "ok"}


def install_error_handler(app):
    @app.exception_handler(HTTPException)
    async def public_error(request, exc):
        if isinstance(exc.detail, dict) and "code" in exc.detail:
            return JSONResponse({"error": exc.detail}, status_code=exc.status_code)
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
