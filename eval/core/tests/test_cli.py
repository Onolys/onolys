import subprocess
import sys

import pytest


@pytest.mark.parametrize("command", [[], ["fetch"], ["convert"], ["upload"], ["run"]])
def test_module_help(command):
    result = subprocess.run(
        [sys.executable, "-m", "onolys_eval", *command, "--help"],
        check=False, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout
    if not command:
        for name in ("fetch", "convert", "upload", "run"):
            assert name in result.stdout


def test_console_entry_point_help():
    result = subprocess.run(["onolys-eval", "--help"], check=False, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "fetch" in result.stdout
