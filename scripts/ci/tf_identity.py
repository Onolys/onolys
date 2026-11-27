#!/usr/bin/env python3
"""Derive the Terraform CI identities from the existing deploy WIF provider variable (docs/reference/infra-pipeline.md).

The deploy workflows already carry WIF_PROVIDER / STAGING_WIF_PROVIDER / EVAL_WIF_PROVIDER
(projects/<number>/locations/global/workloadIdentityPools/github/providers/github). The plan and apply identities live in the
same project in pools `github-plan` / `github-apply` (infra/modules/terraform-ci), so their provider names and service
accounts follow deterministically and need no repository variables of their own.

Usage: tf_identity.py --wif-provider P --project ID --kind plan|apply   (prints provider=... and sa=... lines)
"""
from __future__ import annotations

import argparse
import re
import sys

DEPLOY = re.compile(r"^(projects/[0-9]+/locations/global/workloadIdentityPools)/github/providers/github$")
PROJECT = re.compile(r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$")


def derive(wif_provider: str, project: str, kind: str) -> tuple[str, str]:
    m = DEPLOY.match(wif_provider.strip())
    if not m:
        raise ValueError("WIF provider variable must look like projects/<number>/locations/global/workloadIdentityPools/github/providers/github")
    if kind not in ("plan", "apply") or not PROJECT.match(project):
        raise ValueError("bad kind or project")
    return f"{m.group(1)}/github-{kind}/providers/github-{kind}", f"terraform-{kind}@{project}.iam.gserviceaccount.com"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wif-provider", required=True)
    ap.add_argument("--project", required=True)
    ap.add_argument("--kind", choices=["plan", "apply"], required=True)
    a = ap.parse_args()
    try:
        provider, sa = derive(a.wif_provider, a.project, a.kind)
    except ValueError as e:
        print(f"::error::{e}", file=sys.stderr)
        return 1
    print(f"provider={provider}\nsa={sa}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
