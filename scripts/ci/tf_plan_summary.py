#!/usr/bin/env python3
"""Concise, public-safe Markdown summary of a Terraform plan (docs/reference/infra-pipeline.md).

The repository and its Actions logs are public, so the summary lists only resource addresses and actions plus the NAMES of
changed outputs. It never prints attribute values, output values or the plan text; sensitive values are not read at all.
Remaining defence in depth: credential-looking strings are redacted from anything echoed (error excerpts).

Usage: tf_plan_summary.py --env NAME --status ok|failed|unconfigured [--plan-json F] [--log F] [--max-lines N] > summary.md
"""
from __future__ import annotations

import argparse
import json
import re
import sys

MAX_COMMENT_CHARS = 60000  # GitHub comment limit is 65536; leave room for the wrapper
REDACT = [
    re.compile(r"AIza[0-9A-Za-z_\-]{30,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*", re.S),
    re.compile(r"\b(?:ghp|gho|ghs|ghu|github_pat)_[0-9A-Za-z_]{20,}"),
    re.compile(r"\bya29\.[0-9A-Za-z_\-]{20,}"),
    re.compile(r"(?i)(private_key|client_secret|api[_-]?key|token|password|secret)(\"?\s*[:=]\s*\"?)[^\s\",]{8,}"),
]
ORDER = {"delete": 0, "replace": 1, "forget": 2, "update": 3, "create": 4, "read": 5}
KNOWN_COUNTS = ("create", "update", "delete", "replace", "forget")


def redact(text: str) -> str:
    for rx in REDACT:
        if rx.groups >= 2:
            text = rx.sub(lambda m: f"{m.group(1)}{m.group(2)}[redacted]", text)
        else:
            text = rx.sub("[redacted]", text)
    return text


def classify(actions: list[str]) -> str | None:
    if actions == ["no-op"]:
        return None
    if actions in (["delete", "create"], ["create", "delete"], ["forget", "create"], ["create", "forget"]):
        return "replace"
    if actions == ["read"]:
        return "read"
    return actions[0]


def summarize_plan(plan: dict, max_lines: int) -> tuple[str, dict]:
    counts = {k: 0 for k in KNOWN_COUNTS}
    rows: list[tuple[int, str, str]] = []
    for rc in plan.get("resource_changes", []):
        kind = classify(rc["change"]["actions"])
        if kind is None or kind == "read":
            continue
        counts[kind] = counts.get(kind, 0) + 1  # unknown future action kinds must never crash the summary
        rows.append((ORDER.get(kind, 2), rc["address"], kind))
    rows.sort()
    out_names = sorted(k for k, v in (plan.get("output_changes") or {}).items() if classify(v["actions"]))
    lines = [f"- `{kind}` {addr}" for _, addr, kind in rows[:max_lines]]
    if len(rows) > max_lines:
        lines.append(f"- ... and {len(rows) - max_lines} more (truncated; run the plan locally for the full list)")
    head = (f"**{counts['create']} to add, {counts['update']} to change, {counts['replace']} to replace, "
            f"{counts['delete']} to destroy")
    if counts["forget"]:
        head += f", {counts['forget']} to forget (removed from state, not destroyed)"
    extra = {k: v for k, v in counts.items() if k not in KNOWN_COUNTS}
    if extra:
        head += ", " + ", ".join(f"{v} {k}" for k, v in sorted(extra.items()))
    head += "**"
    parts = [head]
    if counts["delete"] or counts["replace"]:
        parts.append("Destructive changes present: review the `delete` and `replace` lines first.")
    if lines:
        parts.append("\n".join(lines))
    else:
        parts.append("No resource changes.")
    if out_names:
        parts.append("Output changes (names only): " + ", ".join(f"`{n}`" for n in out_names))
    return "\n\n".join(parts), counts


def error_excerpt(log: str, limit: int = 30) -> str:
    keep, grab = [], False
    for line in log.splitlines():
        if line.startswith("Error:") or "Error:" in line[:12]:
            grab = True
        if grab:
            keep.append(line.lstrip("│ ").rstrip())
        if len(keep) >= limit:
            break
    return redact("\n".join(keep) if keep else "\n".join(log.splitlines()[-limit:]))


def render(env: str, status: str, plan: dict | None, log: str, max_lines: int) -> str:
    title = f"#### Terraform plan: `{env}`"
    if status == "unconfigured":
        body = "Not configured yet: repo variables for this environment are unset (pipeline not bootstrapped). Skipped."
    elif status == "failed":
        body = "**Plan failed.** Excerpt (redacted):\n\n```\n" + error_excerpt(log) + "\n```"
    else:
        body, _ = summarize_plan(plan or {}, max_lines)
    return redact(f"{title}\n\n{body}\n")[:MAX_COMMENT_CHARS]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", required=True)
    ap.add_argument("--status", choices=["ok", "failed", "unconfigured"], required=True)
    ap.add_argument("--plan-json")
    ap.add_argument("--log")
    ap.add_argument("--max-lines", type=int, default=80)
    a = ap.parse_args()
    plan = json.load(open(a.plan_json, encoding="utf-8")) if a.plan_json else None
    log = open(a.log, encoding="utf-8", errors="replace").read() if a.log else ""
    sys.stdout.write(render(a.env, a.status, plan, log, a.max_lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
