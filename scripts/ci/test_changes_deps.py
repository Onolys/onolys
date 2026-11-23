"""changes.sh's DEPS map must match the pyproject dependencies of the workspace packages."""

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = (ROOT / "scripts/ci/changes.sh").read_text()


def _array(name: str) -> list[str]:
    m = re.search(rf"^{name}=\(\n(.*?)^\)", SCRIPT, re.S | re.M)
    assert m, f"{name} array not found in changes.sh"
    return re.findall(r'"([^"]+)"', m.group(1))


def _req_name(req: str) -> str:
    return re.split(r"[\[<>=!~; ]", req.strip(), maxsplit=1)[0]


def test_core_package_is_registered() -> None:
    # Missing registration would hide all new core edges from the comparison below.
    assert "core:engines/core:python" in _array("PACKAGES")


def test_oneshot_package_is_registered() -> None:
    assert "oneshot:engines/oneshot:python" in _array("PACKAGES")


def test_oneshot_ci_job_is_offline() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    assert "oneshot: ${{ steps.flags.outputs.oneshot }}" in workflow
    match = re.search(r"^  oneshot:\n(.*?)(?=^  [a-z#]|\Z)", workflow, re.M | re.S)
    assert match, "Missing isolated oneshot job"
    job = match.group(1)
    for required in (
        "needs.changes.outputs.oneshot == 'true'",
        'LITELLM_LOCAL_MODEL_COST_MAP: "True"',
        'MITI_LLM_RECORD: "0"',
        "uv sync --frozen --package onolys-oneshot",
        "uv run --no-sync --package onolys-oneshot ruff check engines/oneshot",
        'uv run --no-sync --package onolys-oneshot pytest engines/oneshot -m "not live"',
    ):
        assert required in job, required
    assert "secrets." not in job


def test_eval_package_is_registered() -> None:
    # Without this assertion, the dependency check silently ignores a new package.
    assert "eval:eval/core:python" in _array("PACKAGES")


def test_eval_site_packages_and_offline_jobs() -> None:
    assert "eval-backend:eval/backend:python" in _array("PACKAGES")
    assert "eval-web:eval/web:node" in _array("PACKAGES")
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    for name in ("eval-backend", "eval-web"):
        assert f"{name}: ${{{{ steps.flags.outputs.{name} }}}}" in workflow
        match = re.search(rf"^  {name}:\n(.*?)(?=^  [a-z#]|\Z)", workflow, re.M | re.S)
        assert match, f"Missing isolated {name} job"
        job = match.group(1)
        assert f"needs.changes.outputs.{name} == 'true'" in job
        assert "secrets." not in job
        if name == "eval-backend":
            for required in (
                'LITELLM_LOCAL_MODEL_COST_MAP: "True"',
                'MITI_LLM_RECORD: "0"',
                "uv sync --frozen --package onolys-eval-backend",
                "uv run --no-sync --package onolys-eval-backend ruff check eval/backend",
                'uv run --no-sync --package onolys-eval-backend pytest eval/backend -m "not live"',
            ):
                assert required in job, required
        else:
            for required in (
                "working-directory: eval/web", "node-version: 22",
                "cache-dependency-path: eval/web/package-lock.json",
                "npm ci", "npm test", "npm run typecheck", "npm run lint", "npm run build",
            ):
                assert required in job, required


def test_deps_map_matches_pyproject_dependencies() -> None:
    packages = [e.split(":") for e in _array("PACKAGES")]
    project_of: dict[str, str] = {}  # CI name -> pyproject project name
    deps_of: dict[str, list[str]] = {}
    for name, d, kind in packages:
        if kind != "python" or not (ROOT / d / "pyproject.toml").exists():
            continue
        proj = tomllib.loads((ROOT / d / "pyproject.toml").read_text())["project"]
        project_of[name] = proj["name"]
        deps_of[name] = [_req_name(r) for r in proj.get("dependencies", [])]
    ci_name = {v: k for k, v in project_of.items()}
    expected = {
        n: sorted(ci_name[d] for d in deps if d in ci_name)
        for n, deps in deps_of.items()
        if any(d in ci_name for d in deps)
    }
    actual = {}
    for entry in _array("DEPS"):
        name, deps = entry.split(":")
        actual[name] = sorted(deps.split())
    assert actual == expected


if __name__ == "__main__":
    test_core_package_is_registered()
    test_oneshot_package_is_registered()
    test_oneshot_ci_job_is_offline()
    test_eval_package_is_registered()
    test_eval_site_packages_and_offline_jobs()
    test_deps_map_matches_pyproject_dependencies()
    print("ok   changes.sh DEPS map matches pyproject dependencies")
