"""OidcVerifier paths beyond test_worker.py: ctor guards, alg, key rotation, cert outage."""

import time
from unittest.mock import MagicMock

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from google.auth import crypt, jwt
from onolys_api.auth import oidc
from onolys_api.auth.idtoken import InvalidToken
from onolys_api.auth.oidc import OidcVerifier
from onolys_api.errors import ApiError

pytestmark = pytest.mark.unit
AUD = "https://worker.run.app"
SA = "tasks@proj.iam.gserviceaccount.com"


def _keypair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    pub = (
        key.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    return priv, pub


PRIV1, PUB1 = _keypair()
PRIV2, PUB2 = _keypair()


def _mint(priv, kid):
    now = int(time.time())
    claims = {"aud": AUD, "iss": "accounts.google.com", "email": SA, "email_verified": True,
              "sub": "1", "iat": now - 5, "exp": now + 600}  # fmt: skip
    return jwt.encode(crypt.RSASigner.from_string(priv, kid), claims, header={"kid": kid}).decode()


@pytest.mark.parametrize(("aud", "email"), [("", SA), (AUD, ""), ("", "")])
def test_requires_audience_and_invoker_email(aud, email):
    with pytest.raises(ValueError):
        OidcVerifier(aud, email, fetch_certs=dict)


def test_second_issuer_spelling_accepted():
    v = OidcVerifier(AUD, SA, fetch_certs=lambda: {"k1": PUB1})
    assert v.verify(_mint(PRIV1, "k1")) == SA  # iss "accounts.google.com" (no scheme)


def test_unsigned_alg_none_token_rejected():
    import base64
    import json

    def b64(o):
        return base64.urlsafe_b64encode(json.dumps(o).encode()).rstrip(b"=").decode()

    tok = f"{b64({'alg': 'none', 'kid': 'k1'})}.{b64({'aud': AUD, 'email': SA})}."
    v = OidcVerifier(AUD, SA, fetch_certs=lambda: {"k1": PUB1})
    with pytest.raises(InvalidToken):
        v.verify(tok)


def test_garbage_token_rejected():
    v = OidcVerifier(AUD, SA, fetch_certs=lambda: {"k1": PUB1})
    with pytest.raises(InvalidToken):
        v.verify("not-a-jwt")


def test_unknown_kid_triggers_one_cert_refresh_then_succeeds():
    calls = []

    def fetch():
        calls.append(1)
        return {"k1": PUB1} if len(calls) == 1 else {"k1": PUB1, "k2": PUB2}

    v = OidcVerifier(AUD, SA, fetch_certs=fetch)
    assert v.verify(_mint(PRIV1, "k1")) == SA
    assert v.verify(_mint(PRIV2, "k2")) == SA  # rotated key: forced refetch
    assert len(calls) == 2


def test_unknown_kid_after_refresh_still_rejected():
    fetch = MagicMock(return_value={"k1": PUB1})
    v = OidcVerifier(AUD, SA, fetch_certs=fetch)
    with pytest.raises(InvalidToken):
        v.verify(_mint(PRIV2, "k-unknown"))
    assert fetch.call_count == 2  # initial + one forced refresh, no loop


def test_cert_fetch_failure_is_503_not_invalid_token():
    def boom():
        raise OSError("network down")

    v = OidcVerifier(AUD, SA, fetch_certs=boom)
    with pytest.raises(ApiError) as e:
        v.verify(_mint(PRIV1, "k1"))
    assert e.value.status == 503


def test_fetch_oidc_certs_requests_google_url_and_returns_json(monkeypatch):
    import requests

    resp = MagicMock()
    resp.json.return_value = {"k": "pem"}
    get = MagicMock(return_value=resp)
    monkeypatch.setattr(requests, "get", get)
    assert oidc.fetch_oidc_certs() == {"k": "pem"}
    get.assert_called_once_with(oidc.OIDC_CERTS_URL, timeout=5)
    resp.raise_for_status.assert_called_once_with()


def test_fetch_oidc_certs_propagates_http_errors(monkeypatch):
    import requests

    resp = MagicMock()
    resp.raise_for_status.side_effect = requests.HTTPError("500")
    monkeypatch.setattr(requests, "get", MagicMock(return_value=resp))
    with pytest.raises(requests.HTTPError):
        oidc.fetch_oidc_certs()
