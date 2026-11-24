"""Guard for tasks that write blobs: no audio or artifact may outlive a session delete, and no
task keeps working on a cancelled session.

`DELETE` marks the session `deleting` first and sweeps the blobs afterwards. A task calls
`ensure_active` right after its writes: a write before the mark is swept by the delete, and one
after it is removed here (the task then answers `gone`), so nothing survives either order.
A `cancelled` session raises `Cancelled` and purges nothing: cancel keeps the data (04-cancel R5).
"""

from onolys_api.jobs.worker import Cancelled
from onolys_api.repo.base import NotFoundError, Repo
from onolys_api.storage.base import BlobStore


def ensure_active(repo: Repo, blobs: BlobStore, uid: str, sid: str) -> None:
    """Raise Cancelled (purging nothing) if the session is cancelled; raise NotFoundError (and
    purge every session prefix) if it is gone or deleting."""
    try:
        state = repo.get_session(uid, sid).state
        if state == "cancelled":
            raise Cancelled()
        if state != "deleting":
            return
    except NotFoundError:
        pass
    blobs.delete_prefix(f"{uid}/{sid}/")
    blobs.delete_prefix(f"uploads/{uid}/{sid}/")
    raise NotFoundError()
