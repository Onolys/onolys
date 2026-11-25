"""Interactive API documentation is available only on local/test services."""
from dataclasses import replace

import httpx
import pytest

from onolys_api.app import create_app
from onolys_api.repo.fake import FakeRepo


@pytest.mark.parametrize("env", ["staging", "prod"])
async def test_hosted_docs_and_schema_are_not_served(settings, blobs, env):
    app = create_app(
        replace(settings, env=env, auth_mode="idp", service_mode="api", auth_project="test"),
        repo=FakeRepo(blobs), blobs=blobs,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        for path in ("/v1/docs", "/v1/docs/redoc.standalone.js", "/v1/openapi.json"):
            response = await client.get(path)
            assert response.status_code == 404, path
            assert response.headers["content-type"].startswith("application/json")
            assert response.json()["status"] == 404
        assert (await client.get("/v1/healthz")).status_code == 200
    # The internal generator can still inspect hosted app instances in-process.
    assert "/v1/sessions" in app.openapi()["paths"]


@pytest.mark.parametrize("env", ["local", "test"])
async def test_local_docs_and_schema_remain_available(settings, blobs, env):
    app = create_app(replace(settings, env=env), repo=FakeRepo(blobs), blobs=blobs)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        for path in ("/v1/docs", "/v1/docs/redoc.standalone.js", "/v1/openapi.json"):
            assert (await client.get(path)).status_code == 200
