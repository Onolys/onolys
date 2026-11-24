"""Limit accounting at run end (03-failure-policy R5, D5).

Only a user/file fault after the model started is ever counted; interview-linked runs are never
counted (they are created `counted=False`, so a release never gives anything back for them).
`should_refund` and `release_once` are the public helpers SP04 reuses; both are run-end only.
"""

from onolys_api.repo.base import NotFoundError
from onolys_api.repo.limits import decide_cancel

__all__ = ["decide_cancel", "release_failed_run", "release_once", "should_refund"]


def should_refund(kind: str, llm_started: bool) -> bool:
    """A system failure (`transient`, `permanent_internal`) always refunds, whether or not the
    model was called. A `user_file` failure refunds only if no attempt called the evaluation
    (`llm_started` on the run doc, persisted across attempts)."""
    if kind == "user_file":
        return not llm_started
    return True


def release_once(
    repo, uid: str, sid: str, run_id: str, refund: bool, date: str | None
) -> bool | None:
    """Hand the cap slot back at most once per run: one repo transaction checks and sets the
    `released` flag and moves the counters, so a crash or a concurrent caller can neither leak
    the slot nor refund twice. Returns whether a unit of the user's limit was kept (the run was
    counted and not refunded; stored on the run doc, so a repeat call answers the same), or None
    when the run is gone or was released before this field existed."""
    try:
        repo.release_run_slot(uid, sid, run_id, refund, date)
        return repo.get_run(uid, sid, run_id).unit_kept
    except NotFoundError:  # session deleted under the run: the delete already freed the slot
        return None


def release_failed_run(repo, uid: str, sid: str, run_id: str, kind: str, date: str | None):
    """Release a run that ended in a failure of `kind`, refunding per `should_refund`."""
    try:
        llm_started = repo.get_run(uid, sid, run_id).llm_started
    except NotFoundError:
        return None  # nothing to refund on a vanished run
    return release_once(repo, uid, sid, run_id, should_refund(kind, llm_started), date)
