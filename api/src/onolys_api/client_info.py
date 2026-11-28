"""Build the `client` info stored on sessions and interviews.

`web_version` comes from the `X-Client-Version` value `RequestIdMiddleware` validated and bound and
falls back to the body; `user_agent` from the `User-Agent` header; `recorder_mime` and
`audio_engine` only from the optional body object. Nothing here ever rejects a request.
"""

from fastapi import Request

from onolys_api.logs import snapshot
from onolys_api.repo.models import ClientInfo


def client_info(request: Request, reported: ClientInfo | None = None) -> ClientInfo:
    body = reported or ClientInfo()
    bound = snapshot().get("client_version")  # validated and bound by RequestIdMiddleware
    return ClientInfo(
        web_version=bound or body.web_version,
        user_agent=request.headers.get("user-agent") or body.user_agent,
        recorder_mime=body.recorder_mime,
        audio_engine=body.audio_engine,
    )
