"""JSON/OIDC Cloud Tasks dispatch, with no SDK or credentials at import time."""

import json
from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Protocol

from onolys_eval_backend.config import EvalConfig


class TaskQueue(Protocol):
    def enqueue(self, kind: str, payload: dict, *, delay_seconds: int = 0) -> None: ...


class InMemoryTaskQueue:
    def __init__(self):
        self.tasks: list[dict] = []

    def enqueue(self, kind, payload, *, delay_seconds=0):
        self.tasks.append(
            {"kind": kind, "payload": deepcopy(payload), "delay_seconds": delay_seconds}
        )


class CloudTasksQueue:
    def __init__(self, config: EvalConfig, client, *, now: Callable = lambda: datetime.now(UTC)):
        self.config, self.client, self.now = config, client, now

    def enqueue(self, kind, payload, *, delay_seconds=0):
        if kind not in {"unit", "transcribe"}:
            raise ValueError("Unknown task kind")
        task = {
            "http_request": {
                "http_method": "POST",
                "url": f"{self.config.service_url}/internal/tasks/{kind}",
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps(payload, allow_nan=False).encode(),
                "oidc_token": {
                    "service_account_email": self.config.tasks_sa,
                    "audience": self.config.task_audience,
                },
            },
            "dispatch_deadline": {"seconds": 900},
        }
        if delay_seconds:
            task["schedule_time"] = self.now() + timedelta(seconds=delay_seconds)
        self.client.create_task(parent=self.config.tasks_queue, task=task)
