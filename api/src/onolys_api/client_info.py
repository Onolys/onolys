"""Build the `client` info stored on sessions and interviews (02-logging R13).

`web_version` comes from the validated `X-Client-Version` header (set on every web request) and
falls back to the body; `user_agent` from the `User-Agent` header; `recorder_mime` and
`audio_engine` only from the optional body object. Nothing here ever rejects a request.
"""

import re

from fastapi import Request

from onolys_api.repo.models import ClientInfo

_VERSION_OK = re.compile(r"^[A-Za-z0-9._+-]{1,64}$")


def client_info(request: Request, reported: ClientInfo | None = None) -> ClientInfo:
    body = reported or ClientInfo()
    header = request.headers.get("x-client-version", "")
    return ClientInfo(
        web_version=header if _VERSION_OK.match(header) else body.web_version,
        user_agent=request.headers.get("user-agent") or body.user_agent,
        recorder_mime=body.recorder_mime,
        audio_engine=body.audio_engine,
    )
