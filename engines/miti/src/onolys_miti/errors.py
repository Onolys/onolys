"""Typed errors shared by all engines. SP02/SP04 map them to results/HTTP."""


class OnolysError(Exception):
    """Base class for all Onolys errors."""


class InputError(OnolysError):
    """The caller supplied invalid input (bad transcript, unknown preset, ...)."""


class ConfigError(OnolysError):
    """Deployment configuration is invalid (bad routes file, unset API-key variable)."""
