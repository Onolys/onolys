"""Eval app factory: CORS -> user/task auth -> routes, with injectable services."""

import os
from collections.abc import Mapping
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from onolys_engine_core.errors import ConfigError
from onolys_engine_core.json_logging import configure_logging

from onolys_eval_backend.allowlist import ClaimsVerifier
from onolys_eval_backend.auth import EvalAuthMiddleware, TokenVerifier
from onolys_eval_backend.catalog import router as catalog_router
from onolys_eval_backend.config import EvalConfig
from onolys_eval_backend.read_runs import router as read_runs_router
from onolys_eval_backend.runs import _git_sha
from onolys_eval_backend.runs import router as runs_router
from onolys_eval_backend.services import EvalServices
from onolys_eval_backend.uploads import install_error_handler
from onolys_eval_backend.uploads import router as uploads_router


def parse_cors_origins(raw: str) -> list[str]:
    origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
    if any("*" in origin or origin == "null" for origin in origins):
        raise ConfigError("CORS_ORIGINS must list exact origins (no wildcards)")
    return origins


def create_app(
    env: Mapping[str, str] | None = None,
    verifier: ClaimsVerifier | None = None,
    *,
    task_verifier: TokenVerifier | None = None,
    services: object | None = None,
) -> FastAPI:
    env = os.environ if env is None else env
    config = EvalConfig.from_env(env)
    # One JSON handler on root; configure_logging never imports litellm.
    configure_logging(SimpleNamespace(git_sha=_git_sha()))
    origins = parse_cors_origins(env.get("CORS_ORIGINS", ""))
    app = FastAPI(title="Onolys eval backend", docs_url=None, redoc_url=None, openapi_url=None)
    # Routers access these through request.app.state; construction performs no cloud I/O.
    # Later services can be supplied as a bundle of repository/storage/queue fakes.
    app.state.config = config
    app.state.catalog = EvalServices(config)
    app.state.services = services if services is not None else app.state.catalog
    app.include_router(catalog_router)
    app.include_router(uploads_router)
    app.include_router(runs_router)
    app.include_router(read_runs_router)
    install_error_handler(app)

    @app.get("/v1/me")
    async def me() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/healthz")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.add_middleware(
        EvalAuthMiddleware, config=config, verifier=verifier, task_verifier=task_verifier
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["authorization", "content-type"],
        allow_credentials=False,
    )
    return app
