"""The shared LLM implementation and packaged routes belong to core."""

import subprocess
import sys
from importlib import resources

from onolys_engine.config import locate_config_file
from onolys_engine.llm import FixtureClient, LLMConfig, make_client
from onolys_engine.llm.routes import routes_path


def test_shared_llm_and_routes_live_in_core(monkeypatch):
    monkeypatch.delenv("ROUTES_FILE", raising=False)
    assert FixtureClient.__module__ == "onolys_engine.llm.fixture_client"
    assert make_client(LLMConfig(llm_mode="stub")).__class__.__module__.startswith(
        "onolys_engine.llm."
    )
    assert routes_path() == resources.files("onolys_engine.llm").joinpath(
        "routes.default.yaml"
    )


def test_config_locator_prefers_routes_sibling(tmp_path, monkeypatch):
    monkeypatch.setenv("ROUTES_FILE", str(tmp_path / "routes.yaml"))
    sibling = tmp_path / "providers.yaml"
    sibling.write_text("providers: {}")
    assert locate_config_file(
        "providers.yaml", "routes.default.yaml", "onolys_engine.llm"
    ) == sibling
    sibling.unlink()
    assert locate_config_file(
        "providers.yaml", "routes.default.yaml", "onolys_engine.llm"
    ) == resources.files("onolys_engine.llm").joinpath("routes.default.yaml")


def test_shared_llm_imports_without_miti():
    code = (
        "import sys; import onolys_engine.llm; "
        "from onolys_engine.llm.routes import resolve_preset; "
        "assert 'miti_code' in resolve_preset()[0]; "
        "assert not any(m.split('.')[0] == 'onolys_miti' for m in sys.modules)"
    )
    result = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
