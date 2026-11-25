"""Eval run creation: import sessions once, write the grouping doc, enqueue tick 1; cancel."""

import logging
import os
import re
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from onolys_api.engines import eval_snapshot
from onolys_api.jobs.transcribe import TRANSCRIPT_ID
from onolys_api.repo.base import NotFoundError
from onolys_api.storage.base import BlobNotFoundError
from onolys_engine_core.errors import ConfigError, InputError
from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

from onolys_eval_backend.catalog import _IDENTIFIER, read_dataset
from onolys_eval_backend.eval_group import build_group_doc, session_entry
from onolys_eval_backend.eval_sessions import SessionImportError, SessionSource, ensure_session
from onolys_eval_backend.matrix import (
    RunTooLarge,
    SelectionError,
    combo_key,
    plan_units,
    validate_selection,
)

router = APIRouter()
logger = logging.getLogger(__name__)


def now():
    return datetime.now(UTC).isoformat()


class InputRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dataset_id: str | None = None
    session_ids: list[str] | None = None
    upload_id: str | None = None

    @model_validator(mode="after")
    def one_source(self):
        if self.upload_id is not None:
            if (
                not re.fullmatch(r"[A-Za-z0-9_-]+", self.upload_id)
                or self.dataset_id is not None
                or self.session_ids is not None
            ):
                raise ValueError("Invalid input reference")
        elif (
            not self.dataset_id
            or not _IDENTIFIER.fullmatch(self.dataset_id)
            or not self.session_ids
            or len(set(self.session_ids)) != len(self.session_ids)
        ):
            raise ValueError("Invalid input reference")
        return self


class Selection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    models: list[str] = Field(default_factory=list)
    tiers: list[str] = Field(default_factory=list)
    efforts: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique(self):
        if any(len(set(v)) != len(v) for v in (self.models, self.tiers, self.efforts)):
            raise ValueError("Invalid run selection")
        return self


class RunMetadata(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=4000)


class RunRequest(RunMetadata):
    model_config = ConfigDict(extra="forbid")
    input: InputRef
    engines: list[str] = Field(min_length=1)
    selection: Selection = Field(default_factory=Selection)
    repeats: StrictInt = 1
    change_goal: str | None = Field(default=None, min_length=1, max_length=4000)
    language: str | None = Field(default=None, min_length=1, max_length=64)
    coded_span: dict | None = None

    @model_validator(mode="after")
    def check_selection(self):
        if self.repeats not in (1, 3) or len(set(self.engines)) != len(self.engines):
            raise ValueError("Invalid run selection")
        if self.input.dataset_id and self.coded_span is not None:
            raise ValueError("Dataset spans come from the manifest")
        return self


class RunInputError(ValueError):
    """A client-fixable input problem whose message is safe to show."""


def _git_sha():
    # Deploy builds inject GIT_SHA; source checkouts resolve git without a shell.
    value = os.environ.get("GIT_SHA") or os.environ.get("COMMIT_SHA")
    if value:
        return value
    import subprocess

    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL, timeout=2
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


class SavedInputUnavailable(Exception):
    """A rerun's pinned session is gone or no longer matches what was saved (HTTP 409)."""


def _dataset_sources(services, body, engines):
    ref = body.input
    manifest = read_dataset(services.datasets, ref.dataset_id)
    sessions = {s.session_id: s for s in manifest.sessions}
    if any(sid not in sessions for sid in ref.session_ids):
        raise ValueError("Unknown dataset session")
    sources = []
    for sid in ref.session_ids:
        session = sessions[sid]
        base = f"datasets/{ref.dataset_id}/{sid}"
        has_gold = f"{base}/gold.json" in services.datasets.list(f"{base}/gold.json")
        sources.append(
            (
                SessionSource(
                    dataset_id=ref.dataset_id,
                    dataset_session_id=sid,
                    source="dataset",
                    title=session.title,
                    transcript_path=f"{base}/transcript.json",
                    gold_path=f"{base}/gold.json" if has_gold else None,
                    change_goal=session.change_goal,
                    coded_span=session.coded_span.model_dump() if session.coded_span else None,
                    language=body.language,
                ),
                has_gold,
            )
        )
    return sources


def _upload_sources(services, body):
    ref = body.input
    upload = services.repository.get_upload(ref.upload_id)
    if upload is None:
        raise HTTPException(404, "Upload not found.")
    if upload.get("status") != "ready":
        raise HTTPException(409, "Upload is not ready.")
    has_gold = upload.get("has_gold") is True and bool(upload.get("gold_path"))
    return [
        (
            SessionSource(
                dataset_id=None,
                dataset_session_id=ref.upload_id,
                source="upload",
                title=upload.get("title") or ref.upload_id,
                transcript_path=upload["transcript_path"],
                gold_path=upload["gold_path"] if has_gold else None,
                change_goal=body.change_goal or upload.get("change_goal"),
                coded_span=body.coded_span
                if body.coded_span is not None
                else upload.get("coded_span"),
                language=body.language or upload.get("language"),
            ),
            has_gold,
        )
    ]


def _pinned_sessions(services, body, pinned):
    """Rerun: reuse the saved sids if each still exists with the same transcript hash."""
    ref = body.input
    entries = sorted(pinned.items(), key=lambda item: item[1]["order"])
    expected = ref.session_ids if ref.dataset_id else [ref.upload_id]
    if [entry["dataset_session_id"] for _, entry in entries] != expected:
        raise ValueError("Saved input sessions do not match input reference")
    uid = services.config.eval_owner_uid
    out = []
    for sid, entry in entries:
        try:
            session = services.repo.get_session(uid, sid)
            sha = services.repo.get_transcript(uid, sid, TRANSCRIPT_ID).sha256
        except (NotFoundError, BlobNotFoundError):
            raise SavedInputUnavailable(
                "A saved input session is no longer available. Create a new run."
            ) from None
        if sha != entry.get("transcript_sha256"):
            raise SavedInputUnavailable(
                "A saved input transcript has changed. Create a new run."
            )
        out.append((sid, entry["dataset_session_id"], sha, session.eval and session.eval.gold))
    return out


def create_run(
    services, config, body, created_by, *, registry=None, pinned=None, saved_config=None
):
    """Create the eval run's grouping doc and enqueue tick 1 (05 R5). No RunDoc is created.

    Sessions are imported once and shared (`ensure_session`); `pinned` (a rerun) is the saved
    `sessions` map whose sids are reused after a transcript-hash check. `saved_config` is the
    saved `{base_preset, resolved_combos}`: its preset is kept and any combo that has a saved
    snapshot must still resolve to the same one (the drift rule).
    """
    registry = registry or services.registry
    choices = {
        f"{info.name}:{v.id}" if v else info.name: info
        for info in registry.engines()
        for v in (info.variants or [None])
    }
    if any(e != "human" and e not in choices for e in body.engines):
        raise ValueError("Unknown engine")
    models = services.models
    engines = list(body.engines)
    ref = body.input

    # Pure and IO-free: an oversized run is rejected before anything is read or written.
    plan_units(
        [{"session_id": str(i)} for i in range(len(ref.session_ids or [ref.upload_id]))],
        engines,
        validate_selection(
            {m.id: {t.id: list(t.efforts) for t in m.tiers.values()} for m in models.values()},
            body.selection.model_dump(),
            any(e != "human" for e in engines),
        )[0],
        body.repeats,
    )

    sources = None
    if pinned is not None:
        sessions_in = _pinned_sessions(services, body, pinned)
        all_gold = all(gold is not None for *_, gold in sessions_in)
    else:
        sources = _dataset_sources(services, body, engines) if ref.dataset_id else (
            _upload_sources(services, body)
        )
        all_gold = all(has_gold for _, has_gold in sources)
    if ref.dataset_id and "human" not in engines and all_gold:
        # Gold is compared on read; sessions without gold simply run without a reference.
        engines.append("human")
    if "human" in engines and not all_gold:
        raise RunInputError("Human requires gold.")
    combos, dropped = validate_selection(
        {m.id: {t.id: list(t.efforts) for t in m.tiers.values()} for m in models.values()},
        body.selection.model_dump(),
        any(e != "human" for e in engines),
    )
    n_sessions = len(sources) if sources is not None else len(sessions_in)
    plan = plan_units([{"session_id": str(i)} for i in range(n_sessions)], engines, combos,
                      body.repeats)
    if sources is not None and any(e.startswith("oneshot") for e in engines):
        if any(not (src.change_goal or "").strip() for src, _ in sources):
            # The one-shot schema requires a non-empty change_goal; fail now, not per run.
            raise RunInputError("A change goal is required for the one-shot engine.")

    base = (saved_config or {}).get("base_preset") or config.default_preset
    unavailable = (
        "Saved configuration is unavailable or changed. "
        "Create a new run to use current settings."
    )
    first_ai = next((e for e in engines if e != "human"), None)
    try:
        # The worker's own snapshot function: the saved route must equal what it re-derives.
        resolved_combos = {
            combo_key(c): eval_snapshot(config.settings, base, first_ai, c)[0] for c in combos
        }
    except (ConfigError, InputError, ValueError, KeyError):
        if saved_config:
            raise HTTPException(409, unavailable) from None
        raise
    previous = (saved_config or {}).get("resolved_combos") or {}
    if any(combo_key(c) in previous for c in dropped) or any(
        previous[key] != snapshot for key, snapshot in resolved_combos.items() if key in previous
    ):
        raise HTTPException(409, unavailable)

    if sources is not None:
        sessions_in = []
        for source, _ in sources:
            sid = ensure_session(services, source)
            uid = services.config.eval_owner_uid
            session = services.repo.get_session(uid, sid)
            sha = services.repo.get_transcript(uid, sid, TRANSCRIPT_ID).sha256
            sessions_in.append((sid, source.dataset_session_id, sha, session.eval.gold))
        if "human" in engines and any(gold is None for *_, gold in sessions_in):
            raise RunInputError("Human requires gold.")

    rid = uuid4().hex
    human_units = n_sessions if "human" in engines else 0
    doc = build_group_doc(
        name=body.name,
        description=body.description,
        input=ref.model_dump(exclude_none=True),
        created_by=created_by,
        created_at=now(),
        engines=engines,
        selection=body.selection.model_dump(),
        combos=combos,
        repeats=body.repeats,
        base_preset=base,
        resolved_combos=resolved_combos,
        engine_versions={e: choices[e].version for e in engines if e != "human"},
        engine_git_sha=_git_sha(),
        change_goal=body.change_goal,
        language=body.language,
        coded_span=body.coded_span,
        sessions={
            sid: session_entry(dataset_session_id, order, sha)
            for order, (sid, dataset_session_id, sha, _) in enumerate(sessions_in)
        },
        total_units=len(plan),
        human_units=human_units,
    )
    services.repository.create_group(rid, doc)
    if doc["status"] != "done":
        try:
            services.queue.enqueue(
                "tick", {"eval_run_id": rid, "n": 1}, task_id=f"{rid}-tick-1"
            )
        except Exception:
            logger.exception("tick_enqueue_failed", extra={"eval_run_id": rid})
            services.repository.update_run(
                rid, {"status": "failed", "finished_at": now(), "error": {"code": "enqueue_failed"}}
            )
    return rid, services.repository.get_run(rid)["status"]


@router.post("/v1/runs")
def post_run(request: Request, body: RunRequest):
    services = request.app.state.services
    try:
        rid, status = create_run(
            services,
            request.app.state.config,
            body,
            request.state.user_email,
            registry=getattr(services, "registry", None) or request.app.state.catalog.registry,
        )
        return {
            "run_id": rid,
            "status": status,
            "engines": services.repository.get_run(rid)["engines"],
        }
    except HTTPException:
        raise
    except (SelectionError, RunTooLarge) as error:
        raise HTTPException(422, str(error)) from None
    except (RunInputError, SessionImportError) as error:
        raise HTTPException(422, str(error)) from None
    except SavedInputUnavailable as error:
        raise HTTPException(409, str(error)) from None
    except (ValueError, FileNotFoundError, InputError):
        raise HTTPException(422, "Invalid run selection or input.") from None
    except Exception:
        raise HTTPException(503, "Run creation unavailable.") from None


@router.post("/v1/runs/{run_id}/cancel")
def cancel_run(request: Request, run_id: str):
    """Stop new runs only (05 R7). Only the flags are written here, in one transaction; the tick
    marks unstarted cells `cancelled` (it owns every other write to the group doc, so a cancel
    cannot be lost to, or clobber, a concurrent tick). In-flight runs finish; idempotent; a
    terminal or already-cancelled run is a no-op (the repository ignores non-active runs)."""
    repository = request.app.state.services.repository
    if not repository.cancel_run(run_id, at=datetime.now(UTC).isoformat()):
        raise HTTPException(404, "Run not found.")
    run = repository.get_run(run_id)
    return {"run_id": run_id, "status": run["status"], "cancelled_at": run.get("cancelled_at")}
