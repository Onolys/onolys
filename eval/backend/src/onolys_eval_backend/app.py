"""Eval app factory: CORS -> user/task auth -> routes, with injectable services."""

import os
from collections.abc import Mapping

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from onolys_admin_auth import ConfigError

from onolys_eval_backend.auth import EvalAuthMiddleware, TokenVerifier
from onolys_eval_backend.config import EvalConfig


def parse_cors_origins(raw: str) -> list[str]:
    origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
    if any("*" in origin or origin == "null" for origin in origins):
        raise ConfigError("ADMIN_CORS_ORIGINS must list exact origins (no wildcards)")
    return origins


def create_app(
    env: Mapping[str, str] | None = None,
    verifier: TokenVerifier | None = None,
    *,
    task_verifier: TokenVerifier | None = None,
    services: object | None = None,
) -> FastAPI:
    env = os.environ if env is None else env
    config = EvalConfig.from_env(env)
    origins = parse_cors_origins(env.get("ADMIN_CORS_ORIGINS", ""))
    app = FastAPI(title="Onolys eval backend", docs_url=None, redoc_url=None, openapi_url=None)
    # Routers access these through request.app.state; construction performs no cloud I/O.
    # Later services can be supplied as a bundle of repository/storage/queue fakes.
    app.state.config = config
    app.state.services = services

    @app.get("/v1/me")
    async def me() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/healthz")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/internal/tasks/unit")
    @app.post("/internal/tasks/transcribe")
    async def task_placeholder() -> JSONResponse:
        # Do not acknowledge/discard queued work until the task executors are implemented.
        return JSONResponse({"error": {"code": "not_implemented"}}, status_code=501)

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
