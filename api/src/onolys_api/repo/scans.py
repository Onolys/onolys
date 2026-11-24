"""Persistent, internal sweep scan position; no session data or TTL."""

ACTIVE_SCAN_PATH = "_maintenance/sweep_active_runs"


def active_cursor(data: dict) -> tuple[int, str] | None:
    """An absent or legacy/malformed checkpoint restarts the bounded scan safely."""
    count, uid = data.get("active_runs"), data.get("uid")
    if type(count) is int and count > 0 and isinstance(uid, str) and uid and "/" not in uid:
        return count, uid
    return None
