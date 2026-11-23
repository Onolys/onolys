# syntax=docker/dockerfile:1
# One image for api, worker and combined mode (PRD D6). Build from the REPO ROOT:
#   docker build -f api/Dockerfile --build-arg GIT_SHA=$(git rev-parse HEAD) -t onolys-api .
#   docker run --rm -p 8080:8080 -e ENV=local -e SERVICE_MODE=combined onolys-api
# Cloud Run (infra/modules/environment/services.tf) sets PORT, SERVICE_MODE and the rest of the env.

FROM python:3.12-slim-bookworm AS build
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv PIP_DISABLE_PIP_VERSION_CHECK=1
RUN pip install --no-cache-dir uv==0.13.4
WORKDIR /src
# Dependency layer: manifests only (every workspace member's pyproject must exist for uv).
COPY pyproject.toml uv.lock ./
COPY engines/core/pyproject.toml engines/core/pyproject.toml
COPY eval/core/pyproject.toml eval/core/pyproject.toml
COPY engines/miti/pyproject.toml engines/miti/pyproject.toml
COPY api/pyproject.toml api/pyproject.toml
COPY admin/auth/pyproject.toml admin/auth/pyproject.toml
COPY admin/backend/pyproject.toml admin/backend/pyproject.toml
RUN uv sync --frozen --no-dev --package onolys-api --no-install-workspace
# Source: core, miti (schemas and fixtures in its wheel), and api (vendored Redoc in static/).
# Eval needs only a manifest for workspace resolution; no eval source or datasets ship.
COPY engines/core engines/core
COPY engines/miti engines/miti
COPY api/src api/src
RUN uv sync --frozen --no-dev --no-editable --package onolys-api

FROM python:3.12-slim-bookworm
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 10001 --create-home onolys
COPY --from=build /opt/venv /opt/venv
COPY config /app/config
COPY api/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
ARG GIT_SHA=dev
ENV PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1 PORT=8080 GIT_SHA=${GIT_SHA}
WORKDIR /app
USER onolys
EXPOSE 8080
ENTRYPOINT ["docker-entrypoint.sh"]
