import pytest

pytestmark = pytest.mark.unit


async def test_healthz(client):
    r = await client.get("/v1/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "service_mode": "combined", "code_version": "abc123"}
    assert r.headers["x-request-id"]


async def test_cors_allowed_origin_and_headers(client):
    r = await client.options(
        "/v1/healthz",
        headers={
            "Origin": "https://app.onolys.com",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization,X-API-Key,Idempotency-Key",
        },
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "https://app.onolys.com"


async def test_cors_allows_the_client_version_header(client):
    r = await client.options(
        "/v1/healthz",
        headers={
            "Origin": "https://app.onolys.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Authorization,X-Client-Version",
        },
    )
    assert r.status_code == 200
    assert "x-client-version" in r.headers["access-control-allow-headers"].lower()


def test_combined_has_queue_api_does_not(settings):
    from dataclasses import replace

    from onolys_api.app import create_app

    assert create_app(settings).state.queue is not None
    assert not hasattr(create_app(replace(settings, service_mode="api")).state, "queue")


H = {"Authorization": "Bearer test:u-hardening"}


async def test_api_responses_are_no_store_except_public_ones(client):
    """A12: PHI-bearing /v1 responses (and their errors) must never be cached."""
    for path, headers in (("/v1/sessions", H), ("/v1/sessions", {}), ("/v1/nope", H)):
        r = await client.get(path, headers=headers)
        assert "no-store" in r.headers["cache-control"], (path, r.status_code)
    assert "no-store" not in (await client.get("/v1/healthz")).headers.get("cache-control", "")
    assert "public" in (await client.get("/v1/docs/redoc.standalone.js")).headers["cache-control"]


async def test_oversized_json_body_is_413(client):
    """A13: JSON bodies are small (uploads use signed URLs); reject big ones before parsing."""
    big = b'{"title": "' + b"x" * (2 * 1024 * 1024) + b'"}'
    r = await client.post(
        "/v1/sessions", content=big, headers={**H, "Content-Type": "application/json"}
    )
    assert r.status_code == 413
    body = r.json()
    assert body["status"] == 413 and body["details"][0]["code"] == "body_too_large"
    assert r.headers["x-request-id"]

    async def chunks():  # no Content-Length: the stream itself is counted
        for _ in range(3):
            yield b"x" * (512 * 1024)

    r = await client.post(
        "/v1/sessions", content=chunks(), headers={**H, "Content-Type": "application/json"}
    )
    assert r.status_code == 413


async def test_normal_json_body_still_accepted(client):
    r = await client.post("/v1/sessions", json={"title": "ok"}, headers=H)
    assert r.status_code == 202


UPLOAD_PREFLIGHT = {
    "Origin": "https://app.onolys.com",
    "Access-Control-Request-Method": "PUT",
    "Access-Control-Request-Headers": "content-type,x-goog-content-length-range",
}


async def test_local_cors_allows_the_fake_blob_upload_headers(client):
    """E22: local Mode B PUTs the audio to the fake blob route with the signed upload headers."""
    r = await client.options("/v1/_fake_blob/k", headers=UPLOAD_PREFLIGHT)
    assert r.status_code == 200


async def test_deployed_cors_does_not_allow_the_upload_headers(settings, blobs):
    """The extra header is dev-only: GCS answers its own preflight; the API never needs it."""
    from dataclasses import replace

    import httpx

    from onolys_api.app import create_app
    from onolys_api.repo.fake import FakeRepo

    s = replace(settings, env="staging", auth_mode="firebase", uid_hmac_key="k", auth_project="p")
    app = create_app(s, repo=FakeRepo(blobs), blobs=blobs)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.options("/v1/healthz", headers=UPLOAD_PREFLIGHT)
    assert r.status_code == 400
