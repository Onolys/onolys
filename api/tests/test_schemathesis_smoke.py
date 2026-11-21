"""Bounded schemathesis smoke: every documented operation, a few examples each, in-process ASGI app
on the FakeRepo (no emulator, no ports: xdist-safe). Only `not_a_server_error`; the full run (all
checks, stateful, Firestore) is manual/nightly: see docs/testing/fuzz-and-mutation.md.
Known 500s are excluded by name here and covered by strict xfails in test_fuzz_review.py.
"""

import tempfile
from pathlib import Path

import pytest
import schemathesis
from hypothesis import HealthCheck, settings
from schemathesis.checks import not_a_server_error

from onolys_api.app import create_app
from onolys_api.config import Settings
from onolys_api.repo.fake import FakeRepo
from onolys_api.storage.fake import FakeBlobStore

pytestmark = pytest.mark.integration


def _build():
    blobs = FakeBlobStore(Path(tempfile.mkdtemp(prefix="onolys-st-")))
    return create_app(
        Settings(
            env="test",
            service_mode="combined",
            auth_mode="fake",
            git_sha="x",
            cors_origins=("https://app.onolys.com",),
        ),
        repo=FakeRepo(blobs),
        blobs=blobs,
    )


APP = _build()
# GET /v1/sessions: cursor 500s are tracked by test_list_cursor_never_5xx (F4).
schema = schemathesis.openapi.from_asgi("/v1/openapi.json", APP).exclude(
    method="GET", path="/v1/sessions"
)


@schema.parametrize()
@settings(
    max_examples=1,
    deadline=None,
    derandomize=True,
    suppress_health_check=list(HealthCheck),
)
def test_no_server_errors(case):
    response = case.call(headers={"Authorization": "Bearer test:alice", "X-API-Key": "x"})
    case.validate_response(response, checks=[not_a_server_error])
