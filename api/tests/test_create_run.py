"""04-eval-run-path Task 4 (R2): `create_run` is the one run-creation entry. `EvalDisabled` writes
nothing; eval starts from report_ready/failed outside the caps; misuse raises; `run_id` is optional.
"""

# ruff: noqa: F811

import logging
from types import SimpleNamespace

import pytest
from test_first_run import (
    RecordingQueue,
    make_client,
    mk_settings,
    new_session,
    repo,  # noqa: F401  (fixture)
)
from test_start_run import READY

from onolys_api.errors import ApiError
from onolys_api.repo.models import EvalRunInfo
from onolys_api.routes.runs import EvalDisabled, RunRequest, create_run

pytestmark = pytest.mark.unit
UID = "u-create-run"
INFO = EvalRunInfo(
    eval_run_id="e1", combo_key="c", repeat=0, engine="miti",
    resolved_route={"litellm_id": "x/y"}, engine_version="v1",
)  # fmt: skip


def setup(repo, state="awaiting_input", **kw):
    q = RecordingQueue()
    app = make_client(repo, mk_settings(**kw), q)
    sid = new_session(repo, UID, state=state, ready=True, **READY)
    return app, q, sid


def test_eval_disabled_writes_nothing(repo, caplog):
    app, q, sid = setup(repo, "report_ready")
    before = repo.get_session(UID, sid)
    with caplog.at_level(logging.WARNING), pytest.raises(EvalDisabled):
        create_run(app, UID, sid, RunRequest(), is_eval=True, eval_spec=INFO)
    assert repo.list_runs(UID, sid) == []
    assert repo.get_session(UID, sid) == before
    assert q.calls == []
    assert [r.getMessage() for r in caplog.records if r.name.endswith("runs")] == ["eval_disabled"]


@pytest.mark.parametrize("state", ["report_ready", "failed"])
def test_eval_on_writes_block_and_starts(repo, state):
    app, q, sid = setup(repo, state, eval_mode=True)
    out = create_run(app, UID, sid, RunRequest(), is_eval=True, eval_spec=INFO)
    run = repo.get_run(UID, sid, out.run_id)
    assert run.eval == INFO and run.counted is False
    assert repo.get_session(UID, sid).state == "running"
    assert [c.run_id for c in q.runs] == [out.run_id]


def test_misuse_raises(repo):
    app, q, sid = setup(repo, eval_mode=True)
    with pytest.raises(ValueError):  # eval_spec without is_eval
        create_run(app, UID, sid, RunRequest(), eval_spec=INFO)
    with pytest.raises(ValueError):  # is_eval without eval_spec
        create_run(app, UID, sid, RunRequest(), is_eval=True)
    assert repo.list_runs(UID, sid) == [] and q.calls == []


def test_prod_run_on_report_ready_still_refused_and_has_no_eval(repo):
    app, q, sid = setup(repo, "report_ready", eval_mode=True)
    with pytest.raises(ApiError):
        create_run(app, UID, sid, RunRequest())
    app, q, sid = setup(repo)
    out = create_run(app, UID, sid, RunRequest())
    assert repo.get_run(UID, sid, out.run_id).eval is None


def test_caller_run_id_and_deps_outside_a_request(repo):
    app, q, sid = setup(repo, "failed", eval_mode=True)
    deps = SimpleNamespace(state=app.state)
    out = create_run(deps, UID, sid, RunRequest(), is_eval=True, eval_spec=INFO, run_id="det1")
    assert out.run_id == "det1" and repo.get_run(UID, sid, "det1").eval == INFO
