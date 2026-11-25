"""RunDoc.eval: optional write-once provenance block (SP04 R1)."""

import pytest

from onolys_api.repo.fake import FakeRepo
from onolys_api.repo.models import EvalRunInfo, RunDoc
from onolys_api.storage.fake import FakeBlobStore

BASE = dict(
    uid="u",
    session_id="s",
    run_id="r",
    change_goal="g",
    clinician_speaker="S1",
    language="auto",
    transcript_sha256="h",
)
INFO = dict(
    eval_run_id="e1",
    combo_key="miti|openai|gpt|low|high",
    repeat=0,
    engine="oneshot:miti",
    route_override={"provider": "openai", "model": "gpt", "tier": "low", "effort": "high"},
    resolved_route={"litellm_id": "openai/gpt", "effort": "high", "max_output_tokens": 100,
                    "context_tokens": 1000, "supports_temperature": False,
                    "caching_mode": "auto"},
    engine_version="v1",
)  # fmt: skip


def test_run_without_eval_loads_and_stays_absent():
    run = RunDoc(**BASE)
    assert run.eval is None
    assert RunDoc(**run.to_store()).eval is None


def test_run_with_eval_round_trips():
    run = RunDoc(**BASE, eval=EvalRunInfo(**INFO))
    back = RunDoc(**run.to_store())
    assert back.eval == run.eval
    assert back.eval.engine == "oneshot:miti"


def test_miti_engine_without_override():
    info = EvalRunInfo(**{**INFO, "engine": "miti", "route_override": None})
    assert info.route_override is None


@pytest.mark.parametrize("field", ["eval", "eval.engine", "eval.route_override.model"])
def test_update_run_cannot_touch_eval(tmp_path, field):
    repo = FakeRepo(FakeBlobStore(tmp_path / "b", bucket="t"))
    repo._put("sessions/s", {"uid": "u"})
    repo._put("sessions/s/runs/r", RunDoc(**BASE, eval=EvalRunInfo(**INFO)).to_store())
    with pytest.raises(ValueError, match="write-once"):
        repo.update_run("u", "s", "r", {field: None})
    repo.update_run("u", "s", "r", {"stage": "x"})
    assert RunDoc(**repo._get("sessions/s/runs/r")).eval == EvalRunInfo(**INFO)
