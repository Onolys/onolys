"""LiteLLM logging stays quiet and is never imported just to configure logging."""

import inspect
import subprocess
import sys

import pytest

pytestmark = pytest.mark.unit


def _run_py(code: str) -> str:
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def test_quiet_litellm_does_not_import_litellm():
    out = _run_py(
        "import sys\nfrom onolys_engine.llm.quiet import quiet_litellm\n"
        "quiet_litellm()\nprint('litellm' in sys.modules)"
    )
    assert out == "False"


def test_quiet_litellm_after_lazy_import_pins_warning_and_strips_handlers():
    out = _run_py(
        "import logging\n"
        "from onolys_engine.llm.quiet import quiet_litellm\n"
        "import litellm\nquiet_litellm()\nquiet_litellm()\n"
        "names = ('litellm', 'LiteLLM', 'LiteLLM Router', 'LiteLLM Proxy')\n"
        "print(all(logging.getLogger(n).level == logging.WARNING for n in names),\n"
        "      all(not logging.getLogger(n).handlers for n in names), litellm.suppress_debug_info)"
    )
    assert out == "True True True"


def test_litellm_client_lazy_sites_call_quiet_litellm():
    from onolys_engine.llm import litellm_client

    assert inspect.getsource(litellm_client).count("quiet_litellm()") >= 2
