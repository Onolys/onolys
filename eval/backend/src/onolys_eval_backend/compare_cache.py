"""Bounded process-local projection LRU; only active groups expire with the clock."""
from collections import OrderedDict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from threading import RLock
from time import monotonic
from typing import Any

from onolys_eval_backend.eval_sessions import canonical_sha256

TERMINAL = frozenset({"done", "partial", "failed", "cancelled"})


def projection_key(eval_run_id: str, cells: Sequence[Mapping[str, Any]]) -> tuple[str, str]:
    stamp = sorted((c.get("run_id") or "", c.get("status") or "", c.get("ended") or "")
                   for c in cells)
    return eval_run_id, canonical_sha256(stamp)


@dataclass
class _Entry:
    value: Any
    status: str
    created: float


class CompareCache:
    def __init__(self, max_entries: int = 16, ttl: float = 10.0,
                 clock: Callable[[], float] = monotonic):
        if max_entries < 1 or ttl <= 0:
            raise ValueError("Cache size and TTL must be positive")
        self.max_entries, self.ttl, self.clock = max_entries, ttl, clock
        self._entries: OrderedDict[tuple[str, str], _Entry] = OrderedDict()
        self._lock = RLock()

    def get(self, eval_run_id: str, cells: Sequence[Mapping[str, Any]], status: str) -> Any:
        key = projection_key(eval_run_id, cells)
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if entry.status != status or (status not in TERMINAL
                                          and self.clock() - entry.created >= self.ttl):
                del self._entries[key]
                return None
            self._entries.move_to_end(key)
            return entry.value

    def put(self, eval_run_id: str, cells: Sequence[Mapping[str, Any]], status: str,
            value: Any) -> None:
        key = projection_key(eval_run_id, cells)
        with self._lock:
            # Keep only one generation for a group, so changing runs cannot fill the LRU.
            for old in list(self._entries):
                if old[0] == eval_run_id:
                    del self._entries[old]
            self._entries[key] = _Entry(value, status, self.clock())
            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)
