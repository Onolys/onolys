"""Typed errors shared by all engines. SP02/SP04 map them to results/HTTP."""


class OnolysError(Exception):
    """Base class for all Onolys errors."""


class RunAborted(Exception):
    """Raised by a progress callback to stop a run on purpose (e.g. the user cancelled).

    Engines must let it propagate out of the callback; every other callback error is ignored.
    Deliberately not an `OnolysError`: it is a stop signal, not a failure to map."""


class InputError(OnolysError):
    """The caller supplied invalid input (bad transcript, unknown preset, ...)."""


class ConfigError(OnolysError):
    """Deployment configuration is invalid (bad routes file, unset API-key variable)."""


class InvalidCodedSpan(InputError):
    """An explicit coded span cannot be applied to this transcript."""

    code = "invalid_coded_span"


class SessionTooLong(InputError):
    """The selected portion exceeds the engine's coding limits."""

    code = "session_too_long"
