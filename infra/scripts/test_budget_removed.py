"""Terraform budget dropped; owner sets limits in consoles (PRD 03-eval-environment R15)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def all_tf():
    return "\n".join(p.read_text() for p in ROOT.rglob("*.tf") if ".terraform" not in p.parts)


def test_no_budget_resource_or_vars():
    tf = all_tf()
    assert not re.search(r'resource\s+"google_billing_budget"', tf)
    assert "monthly_budget_usd" not in tf
    assert "billing_account_id" not in tf


def test_root_project_data_source_gone():
    tf = "\n".join(p.read_text() for p in ROOT.glob("*.tf"))
    assert 'data "google_project" "this"' not in tf
    assert "data.google_project.this" not in tf


def test_removed_block_keeps_existing_budget():
    tf = all_tf()
    start = tf.index("removed {")
    body = tf[start:tf.index("\n}\n", start)]
    assert re.search(r"from\s*=\s*google_billing_budget\.monthly", body)
    assert re.search(r"destroy\s*=\s*false", body)


def test_owner_channel_still_used_by_alerts():
    main = (ROOT / "main.tf").read_text()
    assert 'resource "google_monitoring_notification_channel" "owner_email"' in all_tf()
    assert main.count("google_monitoring_notification_channel.owner_email.id") >= 2
    assert 'variable "alert_email"' in (ROOT / "variables.tf").read_text()
