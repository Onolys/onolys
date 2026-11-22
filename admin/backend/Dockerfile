# syntax=docker/dockerfile:1
# Admin shell image: allowlist auth + CORS and GET /v1/me only. Contains python, admin/auth and
# admin/backend; no engines, protocols, config or contracts.
# Build from the REPO ROOT:
#   docker build -f admin/backend/Dockerfile -t onolys-admin-backend .
#   docker run --rm -p 8080:8080 -e ADMIN_ALLOWED_EMAILS=you@example.com \
#     -e ADMIN_AUTH_PROJECT=<gcp-project> onolys-admin-backend
# Safe defaults: ENV=prod and ADMIN_AUTH=on (auth enforced, ADMIN_AUTH=off refused, an empty allowlist
# refuses to start). Local no-auth needs an explicit -e ENV=local -e ADMIN_AUTH=off.
# No data baked in: no eval code, datasets or transcripts (also see .dockerignore).

FROM python:3.12-slim-bookworm AS build
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv PIP_DISABLE_PIP_VERSION_CHECK=1
RUN pip install --no-cache-dir uv==0.13.4
WORKDIR /src
# Dependency layer: manifests only. Every workspace member listed in the root pyproject
# (engines/*, api, admin/*) needs its pyproject present for uv to resolve the frozen lock;
# no member source other than admin/auth and admin/backend is copied.
COPY pyproject.toml uv.lock ./
COPY engines/miti/pyproject.toml engines/miti/pyproject.toml
COPY api/pyproject.toml api/pyproject.toml
COPY admin/auth/pyproject.toml admin/auth/pyproject.toml
COPY admin/backend/pyproject.toml admin/backend/pyproject.toml
RUN uv sync --frozen --no-dev --package onolys-admin-backend --no-install-workspace
# Only the packages the admin shell needs.
COPY admin/auth admin/auth
COPY admin/backend admin/backend
RUN uv sync --frozen --no-dev --no-editable --package onolys-admin-backend

FROM python:3.12-slim-bookworm
RUN useradd --system --uid 10001 --create-home onolys
COPY --from=build /opt/venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1 PORT=8080 ENV=prod ADMIN_AUTH=on
WORKDIR /app
USER onolys
EXPOSE 8080
CMD ["sh", "-c", "exec uvicorn --factory onolys_admin_backend.app:create_app --host 0.0.0.0 --port ${PORT} --no-access-log --proxy-headers --forwarded-allow-ips='*'"]
