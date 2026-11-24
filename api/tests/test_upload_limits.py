"""GET /v1/upload-limits: server-published pre-check limits (SP03 R10, AC10)."""

import httpx
import pytest

from onolys_api import audio
from onolys_api.app import create_app
from onolys_api.config import Settings
from onolys_api.repo.fake import FakeRepo
from onolys_api.storage.base import MAX_UPLOAD_BYTES
from onolys_api.storage.fake import FakeBlobStore

A = {"Authorization": "Bearer test:alice"}


@pytest.fixture
async def ctx(tmp_path):
    settings = Settings(env="test", auth_mode="fake", service_mode="combined")
    app = create_app(
        settings, repo=FakeRepo(FakeBlobStore(tmp_path / "b")), blobs=FakeBlobStore(tmp_path / "b2")
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://t"
    ) as c:
        yield c, app, settings


async def test_values_match_constants(ctx):
    c, app, settings = ctx
    r = await c.get("/v1/upload-limits", headers=A)
    assert r.status_code == 200
    body = r.json()
    stt = app.state.presets.resolve(None, "en")[1]
    assert body["max_bytes"] == MAX_UPLOAD_BYTES
    assert body["max_duration_s"] == app.state.presets.max_audio_s(stt.provider, stt.model)
    assert (
        body["interview_max_duration_s"] == settings.ai_max_seconds + settings.ai_tolerance_seconds
    )
    assert body["short_warning_s"] == audio.SHORT_RECORDING_S
    assert set(body) == {
        "max_bytes", "max_duration_s", "interview_max_duration_s", "short_warning_s",
        "extensions", "mime_types",
    }  # fmt: skip


async def test_requires_auth(ctx):
    c, _, _ = ctx
    assert (await c.get("/v1/upload-limits")).status_code == 401


async def test_served_types_equal_what_sniff_accepts(ctx):
    """Drift guard: every served extension/MIME resolves to a format sniff can return,
    and every format sniff can return is served."""
    c, _, _ = ctx
    body = (await c.get("/v1/upload-limits", headers=A)).json()
    sniffable = {
        audio.sniff(h)
        for h in (
            b"RIFF\0\0\0\0WAVE", b"OggS", b"\x1a\x45\xdf\xa3", b"\0\0\0\0ftyp", b"ID3", b"\xff\xfb",
        )
    }  # fmt: skip
    assert None not in sniffable
    exts = {audio.resolve_format(None, e) for e in body["extensions"]}
    mimes = {audio.resolve_format(m, None) for m in body["mime_types"]}
    assert None not in exts | mimes
    assert exts == mimes == sniffable
    assert set(body["extensions"]) == set(audio.ACCEPTED_EXTENSIONS)
    assert set(body["mime_types"]) == set(audio.ACCEPTED_MIME_TYPES)
