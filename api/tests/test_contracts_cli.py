"""`python -m onolys_api.contracts`: write mode, --check mode, staleness detection."""

import json

import pytest
from onolys_api import contracts

pytestmark = pytest.mark.unit


@pytest.fixture
def out(tmp_path, monkeypatch):
    monkeypatch.setattr(contracts, "OUT_DIR", tmp_path)
    return tmp_path


def test_write_mode_emits_one_schema_per_model(out):
    assert contracts.main([]) == 0
    names = {p.name for p in out.iterdir()}
    assert names == {f"{stem}.schema.json" for stem in contracts.MODELS}
    doc = json.loads((out / "run-request.schema.json").read_text())
    assert doc["$id"] == "run-request.schema.json"
    assert doc["$schema"].endswith("2020-12/schema")


def test_check_passes_right_after_write(out):
    contracts.main([])
    assert contracts.main(["--check"]) == 0


def test_check_reports_missing_and_modified_files(out, capsys):
    contracts.main([])
    (out / "run-view.schema.json").write_text("{}\n")
    (out / "rating-view.schema.json").unlink()
    assert contracts.main(["--check"]) == 1
    err = capsys.readouterr().err
    assert "run-view.schema.json" in err and "rating-view.schema.json" in err
    assert "session-list.schema.json" not in err


def test_check_does_not_write(out):
    assert contracts.main(["--check"]) == 1  # everything missing
    assert list(out.iterdir()) == []


def test_render_is_deterministic():
    assert contracts.render_all() == contracts.render_all()


@pytest.mark.filterwarnings("ignore:.*found in sys.modules:RuntimeWarning")
def test_module_entrypoint_exits_with_main_status(out, monkeypatch):
    import runpy
    import sys

    monkeypatch.setattr(sys, "argv", ["onolys_api.contracts", "--check"])
    # runpy re-executes the module, so patching OUT_DIR on the old module does not apply;
    # the committed files must be fresh for this to exit 0 (also what CI asserts).
    with pytest.raises(SystemExit) as e:
        runpy.run_module("onolys_api.contracts", run_name="__main__")
    assert e.value.code == 0
