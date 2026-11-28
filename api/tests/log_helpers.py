"""The JSON line the real log handler would produce for a record (tests assert on it)."""

import json
import logging

from onolys_api import logs


def render(record: logging.LogRecord) -> str:
    """Run `record` through the real handler's filters and `StructuredLogHandler` format."""
    handler = logs.make_handler()
    handler.filters = [f for f in handler.filters if not isinstance(f, logs.FirstPartyInfoFilter)]
    if not handler.filter(record):
        return ""
    return handler.format(record)


class Capture(logging.Handler):
    """Collects the parsed JSON lines the real handler would write (attach to the root logger)."""

    def __init__(self) -> None:
        super().__init__(logging.INFO)
        self._real = logs.make_handler()
        self.out: list[dict] = []

    def emit(self, record: logging.LogRecord) -> None:
        if self._real.filter(record):
            self.out.append(json.loads(self._real.format(record)))
