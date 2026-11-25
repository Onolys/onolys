"""Import a dataset session or ready upload as ONE shared prod session (05 R3).

`sid = fingerprint[:32]`: the same inputs reuse the session, a changed transcript/goal/span
makes a new one. Gold is copied once to `gold/<sha256>.json` in the audio bucket (content
addressed, never under the auto-deleting `eval-uploads/` prefix).
"""

import hashlib
import json
from dataclasses import dataclass

from onolys_api.repo.base import ConflictError
from onolys_api.repo.models import (
    EvalGold,
    EvalSessionInfo,
    SessionDoc,
    SessionStatusDoc,
)
from onolys_api.transcript_store import store_transcript
from onolys_engine_core.transcript_input import (
    inferred_clinician_speaker,
    validate_transcript_input,
)
from onolys_eval.gold import Gold

from onolys_eval_backend.uploads import validate_gold, validate_span


class SessionImportError(ValueError):
    """A client-fixable input problem with a message safe to show."""


def canonical_sha256(obj) -> str:
    """Canonical JSON sha256, identical to prod `transcript_sha256`."""
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


@dataclass(frozen=True)
class SessionSource:
    dataset_id: str | None
    dataset_session_id: str  # the dataset session id, or the upload id
    source: str  # "dataset" | "upload"
    title: str | None
    transcript_path: str
    gold_path: str | None
    change_goal: str | None
    coded_span: dict | None
    language: str | None = None


def _reader(services, source: SessionSource):
    return services.datasets if source.source == "dataset" else services.audio_bucket


def ensure_session(services, source: SessionSource) -> str:
    """Validate, copy gold, create-or-reuse the session; returns its sid."""
    reader = _reader(services, source)
    transcript = validate_transcript_input(reader.read_json(source.transcript_path))
    clinician = inferred_clinician_speaker(transcript)
    clients = {t.speaker for t in transcript.turns if t.role == "client"}
    if clinician is None or not clients:
        raise SessionImportError("Unresolved speakers")
    validate_span(transcript, source.coded_span)

    gold_info = None
    gold_data = None
    if source.gold_path:
        try:
            gold = Gold.model_validate(reader.read_json(source.gold_path))
        except FileNotFoundError:
            gold = None
        if gold is not None:
            validate_gold(gold, transcript)
            if source.dataset_id and (
                gold.dataset_id != source.dataset_id
                or gold.session_id != source.dataset_session_id
            ):
                raise SessionImportError("Gold identity mismatch")
            gold_data = gold.model_dump(mode="json", by_alias=True)
            sha = canonical_sha256(gold_data)
            gold_info = EvalGold(sha256=sha, path=f"gold/{sha}.json")

    transcript_sha = canonical_sha256(transcript.model_dump(mode="json"))
    language = source.language or transcript.language
    fingerprint = canonical_sha256(
        {
            "dataset_id": source.dataset_id,
            "dataset_session_id": source.dataset_session_id,
            "transcript_sha256": transcript_sha,
            "change_goal": source.change_goal,
            "language": language,
            "coded_span": source.coded_span,
            "clinician_speaker": clinician,
        }
    )
    sid = fingerprint[:32]

    if gold_info is not None:
        _copy_gold(services.blobs, gold_info, gold_data)

    uid = services.config.eval_owner_uid
    repo = services.repo
    session = SessionDoc(
        uid=uid,
        title=source.title,
        language=language or "auto",
        change_goal=source.change_goal,
        coded_span=source.coded_span,
        n_runs=1,
        preset=services.config.default_preset,
        eval=EvalSessionInfo(
            dataset_id=source.dataset_id,
            dataset_session_id=source.dataset_session_id,
            source=source.source,
            gold=gold_info,
        ),
    )
    try:
        repo.create_session(uid, sid, session, SessionStatusDoc(uid=uid))
    except ConflictError:
        existing = repo.get_session(uid, sid)
        if existing.state != "created":
            return sid  # already imported (or racing and finished): reuse
        session = existing  # a crash left it before the transcript write: finish it
    # `only_from=("created",)`: a concurrent finisher makes this a no-op.
    store_transcript(repo, services.blobs, uid, sid, session, transcript, clinician)
    return sid


def _copy_gold(blobs, info: EvalGold, data) -> None:
    payload = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    if blobs.exists(info.path):
        try:
            if blobs.get_bytes(info.path) == payload:
                return
        except Exception:  # noqa: BLE001 - unreadable: rewrite the content-addressed object
            pass
    blobs.put_bytes(info.path, payload, "application/json")
