"""JSON/OIDC Cloud Tasks dispatch, with no SDK or credentials at import time."""

import json
from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Protocol

from onolys_eval_backend.config import EvalConfig


class TaskQueue(Protocol):
    def enqueue(
        self, kind: str, payload: dict, *, delay_seconds: int = 0, task_id: str | None = None
    ) -> None: ...


class InMemoryTaskQueue:
    def __init__(self):
        self.tasks: list[dict] = []
        self._task_ids: set[str] = set()

    def enqueue(self, kind, payload, *, delay_seconds=0, task_id=None):
        if task_id is not None:
            if task_id in self._task_ids:
                return
            self._task_ids.add(task_id)
        self.tasks.append(
            {"kind": kind, "payload": deepcopy(payload), "delay_seconds": delay_seconds}
        )


class CloudTasksQueue:
    def __init__(self, config: EvalConfig, client, *, now: Callable = lambda: datetime.now(UTC)):
        self.config, self.client, self.now = config, client, now

    @property
    def queue_path(self) -> str:
        """Deployed TASKS_QUEUE is the bare queue name; Cloud Tasks needs the full resource path."""
        queue = self.config.tasks_queue
        if "/" in queue:
            return queue
        region = self.config.settings.region
        return f"projects/{self.config.project}/locations/{region}/queues/{queue}"

    def enqueue(self, kind, payload, *, delay_seconds=0, task_id=None):
        if kind not in {"transcribe", "tick", "delete"}:
            raise ValueError("Unknown task kind")
        parent = self.queue_path
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
        if task_id is not None:
            task["name"] = f"{parent}/tasks/{task_id}"
        from google.api_core.exceptions import AlreadyExists

        try:
            self.client.create_task(parent=parent, task=task)
        except AlreadyExists:
            if task_id is None:
                raise
