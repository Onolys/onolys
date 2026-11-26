#!/usr/bin/env python3
"""Deploy-managed Terraform inputs, read from the live Cloud Run services (docs/reference/infra-pipeline.md).

Deploy workflows set GIT_SHA and LLM_PROVIDER/LLM_MODEL/LLM_EFFORT on the services on every deploy, and Terraform owns the
same env vars from the git_sha / llm_* variables (docs/reference/infra.md "Terraform drift"). The ops machine keeps
them in ignored tfvars; CI reads the live values so a plan/apply never rewrites a deployed commit or LLM selection.

Usage: tf_live_inputs.py --root legacy|isolated --env prod|staging|eval --project P [--region R] --out FILE.auto.tfvars.json
Only reads (gcloud run services describe). Values are non-secret env vars; secret references are never emitted.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys

LLM = {"LLM_PROVIDER": "llm_provider", "LLM_MODEL": "llm_model", "LLM_EFFORT": "llm_effort"}
NOT_FOUND = re.compile(r"not.?found|could not be found|cannot find", re.I)


def env_values(service: dict | None) -> dict[str, str]:
    """Plain `value` env entries of the first container (Knative v1 or Cloud Run v2 JSON shape)."""
    if not service:
        return {}
    tmpl = service.get("spec", {}).get("template", {})
    containers = tmpl.get("spec", {}).get("containers") or service.get("template", {}).get("containers") or []
    out: dict[str, str] = {}
    for entry in (containers[0].get("env") or []) if containers else []:
        if "valueFrom" not in entry and "valueSource" not in entry:
            out[entry["name"]] = entry.get("value", "")  # gcloud omits an empty value
    return out


def build(root: str, worker: dict | None, api: dict | None) -> tuple[dict, list[str]]:
    warnings: list[str] = []
    wenv, aenv = env_values(worker), env_values(api)
    out: dict = {}
    sha = wenv.get("GIT_SHA")
    if sha is not None:
        if aenv.get("GIT_SHA") not in (None, sha):
            warnings.append("api and worker GIT_SHA differ; using the worker value (the plan will show the api drift)")
        out["git_sha"] = {"prod": sha} if root == "legacy" else sha
    for env_name, var in LLM.items():
        if env_name in aenv:
            out[var] = aenv[env_name]
    return out, warnings


def describe(name: str, project: str, region: str) -> dict | None:
    proc = subprocess.run(
        ["gcloud", "run", "services", "describe", name, "--project", project, "--region", region, "--format=json"],
        capture_output=True, text=True, check=False)
    if proc.returncode == 0:
        return json.loads(proc.stdout)
    if NOT_FOUND.search(proc.stderr):
        return None  # not created yet: Terraform defaults apply to the first create
    raise SystemExit(f"gcloud run services describe {name} failed:\n{proc.stderr.strip()[-600:]}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", choices=["legacy", "isolated"], required=True)
    ap.add_argument("--env", choices=["prod", "staging", "eval"], required=True)
    ap.add_argument("--project", required=True)
    ap.add_argument("--region", default="us-central1")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    worker = describe(f"onolys-worker-{a.env}", a.project, a.region)
    api = describe(f"onolys-api-{a.env}", a.project, a.region) if a.env != "eval" else None
    values, warnings = build(a.root, worker, api)
    for w in warnings:
        print(f"::warning::{w}")
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(values, f, indent=2, sort_keys=True)
    print(f"live inputs for {a.env}: {sorted(values)} (written to {a.out})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
