# syntax=docker/dockerfile:1
# Build from repo root. Dockerfile.dockerignore admits only runtime source/manifests.
FROM python:3.12-slim-bookworm AS build
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv PIP_DISABLE_PIP_VERSION_CHECK=1
RUN pip install --no-cache-dir uv==0.13.4
WORKDIR /src
# All workspace manifests are needed for the frozen lock, even unused packages.
COPY pyproject.toml uv.lock ./
COPY engines/core/pyproject.toml engines/core/pyproject.toml
COPY engines/miti/pyproject.toml engines/miti/pyproject.toml
COPY engines/oneshot/pyproject.toml engines/oneshot/pyproject.toml
COPY api/pyproject.toml api/pyproject.toml
COPY eval/auth/pyproject.toml eval/auth/pyproject.toml
COPY eval/core/pyproject.toml eval/core/pyproject.toml
COPY eval/backend/pyproject.toml eval/backend/pyproject.toml
RUN uv sync --frozen --no-dev --package onolys-eval-backend --no-install-workspace
COPY engines/core/src engines/core/src
COPY engines/miti/src engines/miti/src
COPY engines/oneshot/src engines/oneshot/src
COPY eval/auth/src eval/auth/src
COPY eval/core/src eval/core/src
COPY eval/backend/src eval/backend/src
COPY eval/backend/prices.yaml eval/backend/prices.yaml
RUN uv sync --frozen --no-dev --no-editable --package onolys-eval-backend

FROM python:3.12-slim-bookworm
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 10001 --create-home onolys
COPY --from=build /opt/venv /opt/venv
COPY config /app/config
ARG GIT_SHA=dev
ENV PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1 PORT=8080 ENV=staging \
    ADMIN_AUTH=on GIT_SHA=${GIT_SHA} \
    LITELLM_LOCAL_MODEL_COST_MAP=True
WORKDIR /app
USER onolys
EXPOSE 8080
CMD ["sh", "-c", "exec uvicorn --factory onolys_eval_backend.app:create_app --host 0.0.0.0 --port ${PORT} --no-access-log --proxy-headers --forwarded-allow-ips='*'"]
