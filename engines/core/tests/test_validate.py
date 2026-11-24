import json

import pytest

from onolys_engine_core.validate import (
    MAX_ISSUE_LENGTH,
    MAX_ISSUES,
    SCHEMA_CONFORMANCE_INSTRUCTION,
    build_feedback,
    validate_output,
)


def test_valid_output_has_no_issues():
    assert validate_output({"count": 2}, {"properties": {"count": {"type": "integer"}}}) == []


def test_issues_include_known_fields_and_array_indices_without_values():
    schema = {"properties": {"items": {"type": "array", "items": {"properties": {"score": {"type": "integer"}}}}}}
    issues = validate_output({"items": [{"score": "PRIVATE_VALUE"}]}, schema)
    assert len(issues) == 1
    assert "items" in issues[0].path and "0" in issues[0].path and "score" in issues[0].path
    assert "type" in issues[0].message.lower()
    assert "PRIVATE_VALUE" not in repr(issues)


@pytest.mark.parametrize("constraint", [
    {"type": "integer"}, {"enum": [1, 2]}, {"const": 1}, {"pattern": "^public$"},
    {"maxLength": 1}, {"anyOf": [{"type": "integer"}, {"type": "boolean"}]},
    {"not": {"type": "string"}},
])
def test_validation_messages_never_echo_instance_values(constraint):
    issues = validate_output({"answer": "PATIENT_SECRET"}, {"properties": {"answer": constraint}})
    assert issues
    assert "PATIENT_SECRET" not in build_feedback(issues)


@pytest.mark.parametrize("schema,output", [
    ({"additionalProperties": False}, {"PATIENT_SECRET": "PRIVATE_VALUE"}),
    ({"additionalProperties": {"type": "integer"}}, {"PATIENT_SECRET": "PRIVATE_VALUE"}),
    ({"patternProperties": {".*": {"type": "integer"}}}, {"PATIENT_SECRET": "PRIVATE_VALUE"}),
    ({"propertyNames": {"pattern": "^public$"}}, {"PATIENT_SECRET": "PRIVATE_VALUE"}),
    ({"additionalProperties": {"required": ["present"]}}, {"PATIENT_SECRET": {}}),
    ({"properties": {"known": {"additionalProperties": {"type": "integer"}}}}, {"known": {"PATIENT_SECRET": "PRIVATE_VALUE"}}),
])
def test_unknown_property_paths_and_property_errors_are_sanitized(schema, output):
    issues = validate_output(output, schema)
    assert issues
    rendered = repr(issues) + build_feedback(issues)
    assert "PATIENT_SECRET" not in rendered and "PRIVATE_VALUE" not in rendered


def test_required_message_is_fixed_and_does_not_echo_property_names():
    issues = validate_output({}, {"required": ["PATIENT_SECRET"]})
    assert len(issues) == 1
    assert "PATIENT_SECRET" not in build_feedback(issues)


def test_issue_count_and_each_field_length_are_capped():
    name = "known" * MAX_ISSUE_LENGTH
    schema = {"properties": {name: {"type": "array", "items": {"type": "integer"}}}}
    issues = validate_output({name: ["PRIVATE_VALUE"] * (MAX_ISSUES + 10)}, schema)
    assert len(issues) == MAX_ISSUES
    assert all(len(issue.path) <= MAX_ISSUE_LENGTH and len(issue.message) <= MAX_ISSUE_LENGTH for issue in issues)
    assert "PRIVATE_VALUE" not in repr(issues)


def test_local_refs_keep_known_paths_safe():
    schema = {"$defs": {"entry": {"properties": {"score": {"type": "integer"}}}}, "properties": {"entry": {"$ref": "#/$defs/entry"}}}
    issue = validate_output({"entry": {"score": "PRIVATE_VALUE"}}, schema)[0]
    assert "entry" in issue.path and "score" in issue.path
    assert "PRIVATE_VALUE" not in json.dumps(issue.__dict__)


def test_feedback_contains_fixed_instruction_and_sanitized_issues():
    issues = validate_output({"score": "PRIVATE_VALUE"}, {"properties": {"score": {"type": "integer"}}})
    feedback = build_feedback(issues)
    assert SCHEMA_CONFORMANCE_INSTRUCTION in feedback
    assert issues[0].path in feedback and issues[0].message in feedback
    assert "PRIVATE_VALUE" not in feedback
    assert build_feedback([]) == SCHEMA_CONFORMANCE_INSTRUCTION


def test_integral_float_is_not_an_integer():
    schema = {"properties": {"n": {"type": "integer"}}}
    assert validate_output({"n": 1}, schema) == []
    assert validate_output({"n": 1.0}, schema) != []
    assert validate_output({"n": True}, schema) != []
