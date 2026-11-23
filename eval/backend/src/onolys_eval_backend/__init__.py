"""Staging eval backend, independent of the main API and its usage limits."""

from onolys_eval_backend.app import create_app
from onolys_eval_backend.config import EvalConfig

__all__ = ["EvalConfig", "create_app"]
