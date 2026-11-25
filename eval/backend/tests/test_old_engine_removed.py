"""Grep gate (05 R9): the eval-only unit pipeline is gone and nothing references it."""

import os
import re
from pathlib import Path

import pytest
from test_app import AUTH, ENV, client

from onolys_eval_backend import config as config_mod
from onolys_eval_backend import queue as queue_mod
from onolys_eval_backend import repository, runs, services, storage
from onolys_eval_backend.config import EvalConfig
from onolys_eval_backend.queue import CloudTasksQueue

SRC = Path(os.environ.get("EVAL_BACKEND_SRC_UNDER_TEST", Path(__file__).parents[1] / "src"))

REMOVED = (
    "_inputs", "_validate_sources", "_hash", "execute_unit", "finish_unit", "unit_task",
    "UnitTask", "_ExecutionConfigChanged", "is_retryable", "UNIT_BUDGET_S", "LEASE_S",
    "MAX_CLAIMS", "RETRY_DELAYS_S", "MIN_RETRY_BUDGET_S", "get_unit",
    "list_units", "update_unit", "transact_unit", "UnitMutation", "store_output",
    "load_output", "INLINE_OUTPUT_LIMIT", "_bound_engines", "_legacy_create_run",
    "_routes_for", "_combo_snapshot", "_has_gold",
)


def test_no_source_references_removed_names():
    found = []
    for path in sorted(SRC.rglob("*.py")):
        text = path.read_text()
        for name in REMOVED:
            if re.search(rf"(?<![\w]){re.escape(name)}(?![\w])", text):
                found.append(f"{path.name}: {name}")
        for pattern in (r"services\.engine\(", r"def engine\(", r"tasks/unit", r"/inputs/",
                        r"\.collection\(.units.\)", r"services\.bucket\b", r"config\.bucket\b"):
            if re.search(pattern, text):
                found.append(f"{path.name}: {pattern}")
    assert found == []


def test_removed_names_are_not_importable():
    for module in (runs, storage, repository, services):
        for name in REMOVED:
            assert not hasattr(module, name), f"{module.__name__}.{name}"
    assert not hasattr(services.EvalServices, "engine")
    assert not hasattr(services.EvalServices, "bucket")
    assert not hasattr(EvalConfig, "bucket")
    for cls in (repository.InMemoryEvalRepository, repository.FirestoreEvalRepository):
        assert not hasattr(cls, "create_run") and not hasattr(cls, "_unit")


def test_queue_kind_unit_is_gone_but_the_kept_kinds_remain():
    queue = CloudTasksQueue(EvalConfig.from_env(ENV), client=None)
    with pytest.raises(ValueError, match="Unknown task kind"):
        queue.enqueue("unit", {})
    assert queue_mod.InMemoryTaskQueue is not None and config_mod is not None


def test_no_unit_task_route():
    c = client()
    assert c.post("/internal/tasks/unit", headers=AUTH).status_code == 404
    for kept in ("tick", "delete", "transcribe"):
        assert c.post(f"/internal/tasks/{kept}", headers=AUTH).status_code == 422
