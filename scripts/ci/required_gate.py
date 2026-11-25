#!/usr/bin/env python3
"""Fail closed on missing selected checks and on a PR execution path over 300s."""
from __future__ import annotations

import datetime as dt
import json
import os
import urllib.request

JOB_FLAGS = {
    "engine-core": "core", "oneshot": "oneshot", "miti": "miti",
    "eval-core": "eval", "eval-backend": "eval-backend", "eval-web": "eval-web",
    "api-unit": "api", "api-emulator": "api", "api-coverage": "api",
    "api-flaky": "api", "api-rules": "api", "api-image": "api",
    "frontend": "frontend", "web": "web", "web-e2e": "web", "infra": "infra",
}


def validate(needs: dict, event: str, elapsed: float) -> list[str]:
    errors = []
    for name in ("changes", "guards"):
        if needs.get(name, {}).get("result") != "success":
            errors.append(f"{name} must succeed")
    flags = needs.get("changes", {}).get("outputs", {})
    for name, flag in JOB_FLAGS.items():
        if flags.get(flag) not in ("true", "false"):
            errors.append(f"missing/invalid routing flag: {flag}")
        if event != "pull_request" and flags.get(flag) != "true":
            errors.append(f"exact-candidate check must select {flag}")
        selected = flags.get(flag) == "true"
        if event == "pull_request" and name in ("api-image", "api-flaky"):
            selected = False
        result = needs.get(name, {}).get("result")
        if result != "success" and (selected or result != "skipped"):
            errors.append(f"{name}: {result} (selected={selected})")
    # Reserve ten seconds for validation, log upload and the final runner teardown.
    if event == "pull_request" and elapsed + 10 > 300:
        errors.append(f"PR execution budget exceeded: {elapsed:.1f}s + 10s reserve > 300s")
    return errors


def elapsed_from_jobs(data: dict, now: dt.datetime) -> float:
    if data["total_count"] > 100 or data["total_count"] != len(data["jobs"]):
        raise RuntimeError("incomplete job list; cannot verify execution budget")
    starts = []
    for job in data["jobs"]:
        if job["status"] not in ("queued", "waiting", "pending", "in_progress", "completed"):
            raise RuntimeError("unknown job status; cannot verify execution budget")
        if job["status"] not in ("in_progress", "completed") or job["conclusion"] == "skipped":
            continue
        if not job["started_at"]:
            raise RuntimeError("running/completed job lacks start timestamp")
        starts.append(dt.datetime.fromisoformat(job["started_at"]))
    if not starts:
        raise RuntimeError("no started jobs; cannot verify execution budget")
    elapsed = (now - min(starts)).total_seconds()
    if elapsed < 0:
        raise RuntimeError("job start timestamp is in the future")
    return elapsed


def main() -> int:
    needs = json.loads(os.environ["CI_NEEDS"])
    event = os.environ["CI_EVENT"]
    elapsed = 0.0
    if event == "pull_request":
        # Include checkout, setup, all serial tails and runner handoffs. Queue time before
        # the first job starts is excluded. API/auth failures fail this check, never pass it.
        url = (f"https://api.github.com/repos/{os.environ['GH_REPO']}/actions/runs/"
               f"{os.environ['GH_RUN_ID']}/jobs?per_page=100&filter=latest")
        request = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {os.environ['GH_TOKEN']}",
            "Accept": "application/vnd.github+json",
        })
        with urllib.request.urlopen(request, timeout=15) as response:
            data = json.load(response)
        elapsed = elapsed_from_jobs(data, dt.datetime.now(dt.UTC))
        print(f"PR required path so far: {elapsed:.1f}s + 10s completion reserve "
              "(target 270s, limit 300s)")
    errors = validate(needs, event, elapsed)
    for error in errors:
        print(f"::error::{error}")
    return bool(errors)


if __name__ == "__main__":
    raise SystemExit(main())
