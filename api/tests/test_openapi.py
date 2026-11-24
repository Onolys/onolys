import json

import pytest

from onolys_api import openapi

pytestmark = pytest.mark.unit


def test_openapi_deterministic_and_has_contract_components():
    a, b = openapi.render(), openapi.render()
    assert a == b and a.endswith("\n")
    doc = json.loads(a)
    assert doc["paths"]["/v1/healthz"]["get"]["operationId"] == "getHealthz"
    assert {"ErrorResponse", "Healthz"} <= set(doc["components"]["schemas"])
    assert a == json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def test_cli_stdout(capsys):
    assert openapi.main(["--out", "-"]) == 0
    assert capsys.readouterr().out == openapi.render()


def test_cli_writes_file(tmp_path):
    out = tmp_path / "o.json"
    openapi.main(["--out", str(out)])
    assert out.read_text() == openapi.render()


def test_authenticated_operations_document_email_verification_failure():
    doc = json.loads(openapi.render())
    for path, item in doc["paths"].items():
        for operation in item.values():
            if operation.get("security"):
                assert "403" in operation["responses"], path
