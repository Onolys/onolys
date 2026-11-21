"""Doc consistency (11-usage-limits T9): the removed `DAILY_RUN_CAP` is gone from current docs, and
the infra runbook and public API doc both list the three cap codes and the limits runbook."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INFRA = ROOT / "docs/reference/infra.md"
PUBLIC_API = ROOT / "docs/reference/public-api.md"
CODES = ("daily_cap_reached", "monthly_cap_reached", "interview_cap_reached")
STALE = ("DAILY_RUN_CAP", "daily_run_cap", "runs_today")


def _current_docs() -> list[Path]:
    """Every doc except historical PRDs/plans (docs/agent_files) and ADRs (docs/decisions)."""
    skip = (ROOT / "docs/agent_files", ROOT / "docs/decisions")
    return [
        p
        for p in (ROOT / "docs").rglob("*")
        if p.is_file() and p.suffix in {".md", ".json"} and not any(s in p.parents for s in skip)
    ]


def test_removed_daily_run_cap_is_gone_from_current_docs():
    hits = [
        f"{p.relative_to(ROOT)}: {word}"
        for p in _current_docs()
        for word in STALE
        if word in p.read_text()
    ]
    assert not hits, hits


def test_infra_and_public_api_list_the_three_cap_codes():
    for doc in (INFRA, PUBLIC_API):
        text = doc.read_text()
        for code in CODES:
            assert f"`{code}`" in text, f"{doc.name} misses {code}"


def test_infra_has_limits_runbook_and_new_env_vars():
    text = INFRA.read_text()
    assert "## Per-user limits (Firebase console)" in text
    for var in ("EVAL_CAP_DAY", "EVAL_CAP_MONTH", "AI_CAP_DAY", "AI_CAP_MONTH"):
        assert f"`{var}`" in text, var
    assert "`users/{uid}`" in text and "`limits`" in text and "`usage`" in text


def test_public_api_documents_usage_shape_and_period():
    text = PUBLIC_API.read_text()
    assert "`resets_at`" in text and "`period`" in text and "`interview`" in text
