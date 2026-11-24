"""Worker endpoint Cloud Tasks calls: POST /tasks/{kind}. Not in the public schema.

Auth: a Google-signed OIDC token whose audience is the worker URL and whose email is the
tasks-invoker SA (Cloud Run IAM already requires the SA; this checks the audience too).
Bypassed only when ENV is local or test.
`POST /tasks/sweep` is the Cloud Scheduler entry (no payload): see `jobs/sweep.py`.
"""

from fastapi import APIRouter, Header, Request, Response

from onolys_api.auth.idtoken import InvalidToken
from onolys_api.config import LOCAL_ENVS
from onolys_api.errors import ApiError
from onolys_api.jobs.queue import KINDS, TaskPayload
from onolys_api.jobs.sweep import run_sweep
from onolys_api.jobs.worker import TaskRunner

router = APIRouter(include_in_schema=False)


def _unauthenticated() -> ApiError:
    return ApiError.of(401, "unauthenticated", "Authentication required.")


def check_oidc(request: Request, authorization: str | None) -> None:
    if request.app.state.settings.env in LOCAL_ENVS:
        return
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise _unauthenticated()
    try:
        request.app.state.oidc.verify(token)
    except InvalidToken:
        raise _unauthenticated() from None


@router.post("/tasks/sweep")
def run_sweep_route(
    request: Request, authorization: str | None = Header(default=None)
) -> dict[str, int]:
    """The periodic server sweep (Cloud Scheduler, same OIDC as the task routes): settle stale
    sessions, resume stuck deletions, repair leaked run slots. Bounded and idempotent."""
    check_oidc(request, authorization)
    state = request.app.state
    return run_sweep(state.repo, state.blobs, state.settings, state.clock()).as_dict()


@router.post("/tasks/{kind}")
def run_task(
    kind: str,
    payload: TaskPayload,
    request: Request,
    authorization: str | None = Header(default=None),
    x_cloudtasks_taskretrycount: str | None = Header(default=None),
) -> Response:
    check_oidc(request, authorization)
    if kind not in KINDS:
        raise ApiError.of(404, "not_found", "Resource not found.")
    if payload.kind != kind:
        raise ApiError.of(422, "invalid_parameters", "kind: does not match the path")
    try:
        retry = max(0, int(x_cloudtasks_taskretrycount or 0))
    except ValueError:
        retry = 0
    runner: TaskRunner = request.app.state.runner
    result = runner.handle(payload, retry)
    return Response(status_code=result.status_code, content=result.outcome)
