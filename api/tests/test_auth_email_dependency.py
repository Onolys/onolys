from typing import Annotated

import httpx
import pytest
from fastapi import Depends
from test_auth import KID, OTHER_PRIV, PROJECT, PUB, bearer, mint

from onolys_api.app import create_app
from onolys_api.auth import deps
from onolys_api.auth.idtoken import IdTokenVerifier, InvalidToken
from onolys_api.config import Settings
from onolys_api.repo.fake import FakeRepo

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "kwargs", [{"priv": OTHER_PRIV}, {"aud": "other"}, {"iss": "bad"}, {"uid": ""}]
)
def test_unverified_flag_does_not_skip_token_security(kwargs):
    verifier = IdTokenVerifier(PROJECT, fetch_certs=lambda: {KID: PUB})
    with pytest.raises(InvalidToken):
        verifier.verify(mint(verified=False, **kwargs), allow_unverified=True)


async def test_unverified_dependency_is_token_only_and_existing_guard_unchanged(blobs):
    verifier = IdTokenVerifier(PROJECT, fetch_certs=lambda: {KID: PUB})
    app = create_app(
        Settings(env="staging", auth_mode="idp", service_mode="api", auth_project=PROJECT),
        repo=FakeRepo(blobs),
        blobs=blobs,
        token_verifier=verifier,
    )

    @app.get("/unverified-probe")
    def probe(user: Annotated[deps.AuthUser, Depends(deps.current_user_unverified_ok)]):
        return {"uid": user.uid}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        token = mint(verified=False)
        assert (await client.get("/unverified-probe", headers=bearer(token))).json() == {
            "uid": "u1"
        }
        old = await client.get("/v1/api-key", headers=bearer(token))
        assert old.status_code == 403
        assert old.json()["details"][0]["code"] == "email_unverified"
        assert (await client.get("/unverified-probe")).status_code == 401
        assert (
            await client.get("/unverified-probe", headers={"X-API-Key": "any"})
        ).status_code == 403
        assert (
            await client.get("/unverified-probe", headers=bearer(mint(verified=False, aud="bad")))
        ).status_code == 401
        assert (
            await client.get(
                "/unverified-probe", headers=bearer(mint(verified=False, priv=OTHER_PRIV))
            )
        ).status_code == 401
