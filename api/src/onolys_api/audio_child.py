"""Apply audio tool resource bounds in a fresh interpreter, safe for threaded callers."""

import os
import resource
import sys

_CPU_LIMIT_S = 600
_ADDRESS_SPACE_BYTES = 4 * 1024**3
_OUTPUT_FILE_BYTES = 2 * 1024**3
_OPEN_FILES = 256


def _limit_child() -> None:
    """Runs in a fresh interpreter before exec: cap CPU, memory, output, handles."""
    for which, value in (
        (resource.RLIMIT_CPU, _CPU_LIMIT_S),
        (resource.RLIMIT_AS, _ADDRESS_SPACE_BYTES),
        (resource.RLIMIT_FSIZE, _OUTPUT_FILE_BYTES),
        (resource.RLIMIT_NOFILE, _OPEN_FILES),
    ):
        resource.setrlimit(which, (value, value))


if __name__ == "__main__":
    _limit_child()
    os.execvp(sys.argv[1], sys.argv[1:])
