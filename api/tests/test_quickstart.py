"""AC17: the quickstart's curl sequence (extracted from the OpenAPI description) runs against a
real `SERVICE_MODE=combined` server with stub adapters."""

import json
import re
import shutil

import pytest

from onolys_api import openapi

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not all(shutil.which(t) for t in ("ffmpeg", "curl", "jq", "bash")),
        reason="ffmpeg/curl/jq missing",
    ),
]


def quickstart_script() -> str:
    desc = json.loads(openapi.render())["info"]["description"]
    blocks = re.findall(r"```bash\n(.*?)```", desc, re.S)
    assert blocks, "no bash block in the description"
    return "\n".join(blocks)


def test_quickstart_put_sends_every_required_header():
    """Staging: the signed URL also signs `x-goog-content-length-range`; sending only
    Content-Type gives 400 MalformedSecurityHeader. The PUT must send all required_headers."""
    script = quickstart_script()
    put = script.split("# 2.")[1].split("# 3.")[0]
    assert "required_headers | to_entries" in put
    assert 'required_headers["Content-Type"]' not in put
