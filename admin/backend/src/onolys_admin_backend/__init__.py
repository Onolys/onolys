"""Admin shell: auth middleware + CORS in front of GET /v1/me."""

from onolys_admin_backend.app import create_app, parse_cors_origins

__all__ = ["create_app", "parse_cors_origins"]
