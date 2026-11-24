"""The `run` task (PRD R4 Run, R5, R6, D2, D12, D17): the whole evaluation as one task.

The handler calls the `Evaluation` adapter in-process. `progress_cb(stage, status)` writes
`session_status.step` (the stage last `started`) and adds a finished stage's weight to `progress`
(a failed stage counts too); the value is `45 + sum(weights of finished stages)`, capped at 99 and
never lower than what is already shown, so a retry (which re-runs everything) stays flat until it
catches up. 100 belongs to `report_ready`.

Outcome: the report is validated against the report schema, stored verbatim (the repo moves it to
GCS above 500 KB) under a deterministic report id (= run id), the run artifacts go to
`{uid}/{sid}/runs/{run_id}/{code,tips}.json`, and the session moves to `report_ready`
with the new `latest_report_version`. A code failure fails the run and the session; tips
failures arrive as report warnings and still ship (the adapter handles them). A redelivered or
retried task finds the stored report and only finishes the bookkeeping: one report per run.

Cap slot: every run is released exactly once (`released` flag on the run record), when the run
ends for good: success or failure (refunded per `charging.should_refund`: a system failure
always, a user/file fault only if no attempt called the evaluation, `llm_started` on the run
record), but not on a retryable failure with an attempt left. The refund runs here, before the
worker's `_fail`, which reads the outcome (`unit_kept`) into `SessionError.counted`.
"""

import json
import logging
import time
from collections.abc import Callable
from typing import Any

from onolys_engine_core.context import RunContext
from onolys_engine_core.validated_run import OutputInvalid

from onolys_api import logs
from onolys_api.adapters.base import Evaluation
from onolys_api.adapters.error_map import kind_for_code, to_public
from onolys_api.adapters.validated import evaluate_validated
from onolys_api.jobs.alive import ensure_active
from onolys_api.jobs.charging import release_failed_run, release_once
from onolys_api.jobs.machine import (
    RUN_START_PROGRESS,
    STAGE_WEIGHTS,
    STAGES,
    advance,
    stage_fields,
    transition_plan,
)
from onolys_api.jobs.queue import MAX_ATTEMPTS
from onolys_api.jobs.transcribe import TRANSCRIPT_ID
from onolys_api.jobs.transcribe import _run as run_coro
from onolys_api.jobs.worker import (
    Cancelled,
    Handler,
    PermanentError,
    TaskContext,
    TaskError,
)
from onolys_api.repo.base import NotFoundError
from onolys_api.repo.models import ReportDoc, utcnow
from onolys_api.storage.base import BlobStore

ARTIFACTS = ("code", "tips")
MAX_PROGRESS = 99  # same as `progress.MAX_PROGRESS`


def artifact_key(uid: str, sid: str, run_id: str, name: str) -> str:
    return f"{uid}/{sid}/runs/{run_id}/{name}.json"


def _dumps(obj: Any) -> bytes:
    return json.dumps(obj, ensure_ascii=False, default=str).encode()


def make_run_handler(
    blobs: BlobStore, get_evaluation: Callable[[], Evaluation], settings=None
) -> Handler:
    """Register with `HandlerSpec(fn, scope="run")` (claim on the run record)."""

    def run(ctx: TaskContext) -> None:
        uid, sid, run_id = ctx.uid, ctx.sid, ctx.payload.run_id
        assert run_id
        repo = ctx.repo
        run_doc = repo.get_run(uid, sid, run_id)
        date = run_doc.cap_date
        try:
            _execute(ctx, blobs, get_evaluation(), run_doc)
        except Cancelled:
            raise  # the cancel already released the slot (released=true) and marked the run
        except (TaskError, TimeoutError) as e:
            retryable = isinstance(e, TimeoutError) or e.retryable
            if not retryable or ctx.attempt >= MAX_ATTEMPTS:
                code = e.code if isinstance(e, TaskError) else "deadline_exceeded"
                release_failed_run(repo, uid, sid, run_id, kind_for_code(code), date)
            raise
        except Exception as e:
            if isinstance(e, OutputInvalid):
                fields = {"validation": e.validation}
                if e.usage is not None:
                    fields["run_info"] = {"usage": e.usage.model_dump(mode="json")}
                repo.update_run(uid, sid, run_id, fields)
            code, retryable = to_public(e, ctx.attempt)
            if not retryable or ctx.attempt >= MAX_ATTEMPTS:
                release_failed_run(repo, uid, sid, run_id, kind_for_code(code), date)
            raise
        release_once(repo, uid, sid, run_id, False, date)

    return run


def _execute(ctx, blobs, evaluation, run_doc) -> None:
    uid, sid, run_id, repo = ctx.uid, ctx.sid, run_doc.run_id, ctx.repo
    session = repo.get_session(uid, sid)
    if session.state == "deleting":
        raise NotFoundError()
    if session.state == "cancelled":
        raise Cancelled()

    try:  # a retry or redelivery after the report was stored only finishes the bookkeeping
        existing = repo.get_report(uid, sid, run_id, resolve=False)
    except NotFoundError:
        existing = None
    if existing is None:
        _evaluate(ctx, blobs, evaluation, run_doc, session)  # publishes atomically (M-11)
        return

    # a report stored by an older build without its bookkeeping: only finish that
    repo.update_run(uid, sid, run_id, {"stage": None})
    if repo.get_session(uid, sid).state != "report_ready":
        advance(
            repo, uid, sid, to="report_ready", step=None,
            latest_report_version=existing.version,
        )  # fmt: skip


def _evaluate(ctx, blobs, evaluation, run_doc, session) -> None:
    uid, sid, run_id, repo = ctx.uid, ctx.sid, run_doc.run_id, ctx.repo
    if session.clinician_speaker is None:
        raise PermanentError("internal_error")
    transcript = repo.get_transcript(uid, sid, TRANSCRIPT_ID).transcript
    if transcript is None:
        raise PermanentError("internal_error")
    params = {
        "change_goal": session.change_goal or "",
        "seed": sid,
        "coded_span": (
            run_doc.coded_span.model_dump(exclude_none=True) if run_doc.coded_span else None
        ),
        "language": transcript.language or session.language,
        "n_runs": run_doc.n_runs,
        "preset": run_doc.preset,
        "code_version": run_doc.code_version,
        "stt_run": session.stt.run.model_dump() if session.stt and session.stt.run else None,
        "stub_title": session.title or "",  # real adapters ignore it
    }
    done: set[str] = set()

    def progress_cb(stage: str, status: str) -> None:
        if stage not in STAGE_WEIGHTS:
            return
        try:
            ensure_active(repo, blobs, uid, sid)  # stage boundary: stop when cancelled/deleted
            if status == "started":
                repo.update_session(
                    uid, sid, {"step": stage},
                    status={
                        "step": stage,
                        "stage_started_at": utcnow(),  # web interpolates from here
                        **stage_fields("running", stage, None),
                    },
                )
            elif stage not in done:
                done.add(stage)
                total = RUN_START_PROGRESS + sum(STAGE_WEIGHTS[s] for s in done)
                shown = repo.get_status(uid, sid).progress
                after = STAGES[STAGES.index(stage) + 1 :][:1]  # the stage that starts next
                repo.update_session(
                    uid, sid, {},
                    status={
                        "progress": max(shown, min(MAX_PROGRESS, total)),
                        "stage_started_at": utcnow(),
                        **stage_fields("running", after[0] if after else stage, None),
                    },
                )
        except (NotFoundError, Cancelled):
            raise
        except Exception as e:  # progress is best effort: never fail the run for it
            logs.emit(
                "progress_write_failed",
                logging.WARNING,
                session_id=sid,
                run_id=run_id,
                exc_class=type(e).__name__,
            )

    rctx = RunContext(
        llm=None, metrics=None, request_id=ctx.request_id or "",
        deadline=time.monotonic() + max(0.0, ctx.remaining_s()),
    )  # fmt: skip
    repo.update_run(uid, sid, run_id, {"llm_started": True})  # survives retries: a unit is spent
    # no catch here: any engine exception reaches the worker, which maps it with `to_public`
    out = run_coro(
        evaluate_validated(
            evaluation, rctx, transcript, {"subject": session.clinician_speaker},
            params, progress_cb,
        )
    )  # fmt: skip

    prefix = f"{uid}/{sid}/runs/{run_id}/"
    for name in ARTIFACTS:
        if out.artifacts.get(name) is not None:
            blobs.put_bytes(artifact_key(uid, sid, run_id, name), _dumps(out.artifacts[name]),
                            "application/json")  # fmt: skip
    ensure_active(repo, blobs, uid, sid)  # a DELETE during the run must not leave artifacts
    # (and a cancel must not get a report: ensure_active raises Cancelled)
    doc = ReportDoc(
        version=0,  # assigned by `publish_report` inside its transaction
        run_id=run_id,
        report=out.report,
        report_schema_version=str(out.report.get("schema_version", "")),
    )
    # ONE transaction: report + run completion + `report_ready` + slot release, re-checking that
    # the session is still `running` (a cancel after the last `ensure_active` wins: no report).
    published = repo.publish_report(
        uid, sid, run_id, doc,
        {
            "stage": None,
            "run_info": out.run_info or out.report.get("run_info"),
            "validation": out.run_info.get("validation"),
            "artifacts_prefix": blobs.uri(prefix),
        },
        lambda version: transition_plan(
            to="report_ready", step=None, latest_report_version=version
        ),
        run_doc.cap_date,
    )  # fmt: skip
    if published is None:
        if repo.get_session(uid, sid).state == "cancelled":
            raise Cancelled()
        raise PermanentError("internal_error")
