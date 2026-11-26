"""Contract: every Python version a workflow asks uv for must satisfy the API's `requires-python`.

`uv sync --frozen` refuses an interpreter outside `requires-python` (error: "The requested interpreter resolved to
Python 3.14.4, which is incompatible with the project's Python requirement"), so a 3.13/3.14 matrix fails the
Nightly api-emulator-matrix job in ~10s. Fail here, offline, instead.
"""
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"


def _minor(version: str) -> tuple[int, int]:
    major, minor = re.match(r"(\d+)\.(\d+)", str(version)).groups()
    return int(major), int(minor)


def _allowed(spec: str, version: str) -> bool:
    """Supports the `>=a.b`, `>a.b`, `<=a.b`, `<a.b`, `==a.b[.*]` comma lists used in pyproject.toml."""
    v = _minor(version)
    for clause in (c.strip() for c in spec.split(",")):
        op, bound = re.match(r"(>=|<=|==|>|<)\s*(.+)", clause).groups()
        b = _minor(bound)
        if not {">=": v >= b, "<=": v <= b, "==": v == b, ">": v > b, "<": v < b}[op]:
            return False
    return True


def _requires_python() -> str:
    text = (ROOT / "api" / "pyproject.toml").read_text()
    return re.search(r'^requires-python\s*=\s*"([^"]+)"', text, re.M)[1]


def _requested_versions():
    """Yield (workflow:job, version) for matrix `python` values and any literal `python-version` in a job."""
    for wf in sorted(WORKFLOWS.glob("*.yml")):
        jobs = (yaml.safe_load(wf.read_text()) or {}).get("jobs") or {}
        for name, job in jobs.items():
            matrix = (job.get("strategy") or {}).get("matrix") or {}
            for v in matrix.get("python", []) if isinstance(matrix, dict) else []:
                yield f"{wf.name}:{name}", str(v)
            for step in job.get("steps") or []:
                v = (step.get("with") or {}).get("python-version")
                if v is not None and "${{" not in str(v):
                    yield f"{wf.name}:{name}", str(v)


def _violations():
    spec = _requires_python()
    return [f"{where} requests Python {v}, outside requires-python {spec}" for where, v in _requested_versions() if not _allowed(spec, v)]


def test_workflow_python_versions_satisfy_requires_python():
    assert _violations() == []


def test_matcher_rejects_out_of_range():
    assert _allowed(">=3.12,<3.13", "3.12")
    assert not _allowed(">=3.12,<3.13", "3.13")
    assert not _allowed(">=3.12,<3.13", "3.14")


if __name__ == "__main__":
    test_matcher_rejects_out_of_range()
    test_workflow_python_versions_satisfy_requires_python()
    print("ok   workflow Python versions satisfy requires-python")
