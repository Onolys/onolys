"""The one transcript write: pack + build + `transition_session`, shared by the public upload
route and the eval session import. Prod behaviour is unchanged; the route keeps
`maybe_start_first_run`."""

from uuid import uuid4

from onolys_engine_core.transcript import Transcript

from onolys_api.jobs.machine import transition_plan
from onolys_api.jobs.transcribe import TRANSCRIPT_ID
from onolys_api.repo import large
from onolys_api.repo.models import SessionDoc, TranscriptDoc


def session_language(session_language: str, transcript_language: str | None) -> str:
    """A language the user chose stays; only `auto` takes the transcript's, else `en`."""
    if session_language not in ("", "auto"):
        return session_language
    return transcript_language or "en"


def store_transcript(
    repo, blobs, uid: str, sid: str, session: SessionDoc, transcript: Transcript,
    clinician: str | None,
) -> None:  # fmt: skip
    """Synchronous storage/Firestore sequence; call from a worker thread when on the event loop."""
    # ONE transaction: the `created` check, the transcript doc and the move to
    # `awaiting_input` commit together, so two concurrent PUTs cannot both write.
    pointer = large.pack(
        blobs, f"{uid}/{sid}/transcripts/{uuid4().hex}.json",
        transcript.model_dump(mode="json"),
    )  # a unique key: the losing PUT must not overwrite the winner's blob
    language = session_language(session.language, transcript.language)
    tdoc = TranscriptDoc.build(transcript, pointer, language)
    try:
        repo.transition_session(
            uid, sid,
            transition_plan(
                to="awaiting_input", step=None, only_from=("created",),
                flags={"transcript_ready": True, "speaker_confirmed": clinician is not None},
                extra_fields={
                    "clinician_speaker": clinician, "stt": None,
                    "language": language,
                },
            ),
            children=((f"transcripts/{TRANSCRIPT_ID}", tdoc.to_store(), False),),
        )  # fmt: skip
    except Exception:
        if pointer is not None:
            blobs.delete(pointer.key)
        raise
