"""Bounded output validation suitable for logs and model feedback.

jsonschema's messages and instance paths can contain transcript text. Only fixed
messages and explicitly declared schema property names may cross this boundary.
"""

from dataclasses import dataclass
from itertools import islice

from jsonschema.validators import validator_for

MAX_ISSUES = 20
MAX_ISSUE_LENGTH = 200
SCHEMA_CONFORMANCE_INSTRUCTION = (
    "Your last answer did not match the schema. Return the complete JSON object; "
    "every required field present, no extra fields, exact enum values"
)


@dataclass(frozen=True)
class ValidationIssue:
    path: str
    message: str


# Never interpolate ValidationError.message, instance values, or schema constraint
# values (enum/const/required/pattern) into feedback.
_MESSAGES = {
    "type": "Value has an incorrect type.",
    "required": "A required property is missing.",
    "additionalProperties": "Unexpected properties are not allowed.",
    "unevaluatedProperties": "Unexpected properties are not allowed.",
    "enum": "Value is not one of the allowed choices.",
    "const": "Value does not match the required constant.",
    "pattern": "String does not match the required pattern.",
    "format": "String does not match the required format.",
    "minLength": "String is shorter than allowed.",
    "maxLength": "String is longer than allowed.",
    "minimum": "Number is below the allowed minimum.",
    "maximum": "Number is above the allowed maximum.",
    "exclusiveMinimum": "Number must exceed the allowed minimum.",
    "exclusiveMaximum": "Number must be below the allowed maximum.",
    "multipleOf": "Number is not an allowed multiple.",
    "minItems": "Array has too few items.",
    "maxItems": "Array has too many items.",
    "uniqueItems": "Array items must be unique.",
    "minProperties": "Object has too few properties.",
    "maxProperties": "Object has too many properties.",
}


def _property_names(schema: dict | bool) -> set[str]:
    """Collect declared names, visiting schema positions only, never const/enum data."""
    if not isinstance(schema, dict) or not schema:
        return set()
    names = set(schema.get("properties", {}))
    for keyword in (
        "properties", "patternProperties", "$defs", "definitions", "dependentSchemas",
    ):
        for child in schema.get(keyword, {}).values():
            names.update(_property_names(child))
    for keyword in ("allOf", "anyOf", "oneOf", "prefixItems"):
        for child in schema.get(keyword, []):
            names.update(_property_names(child))
    for keyword in (
        "additionalProperties", "unevaluatedProperties", "items", "additionalItems",
        "unevaluatedItems", "contains", "not", "if", "then", "else", "propertyNames",
    ):
        child = schema.get(keyword, {})
        # Draft 7 and earlier permit a tuple schema in items.
        for item in child if isinstance(child, list) else [child]:
            names.update(_property_names(item))
    return names


def validate_output(output: dict, schema: dict) -> list[ValidationIssue]:
    """Return at most MAX_ISSUES issues with bounded, value-free fields.

    Unknown object keys become a fixed placeholder; numeric array indices and
    schema-declared property names remain useful for locating the problem.
    """
    known_names = _property_names(schema)
    errors = validator_for(schema)(schema).iter_errors(output)
    issues = []
    for error in islice(errors, MAX_ISSUES):
        parts = ["$"]
        for part in error.absolute_path:
            if isinstance(part, int):
                parts.append(f"[{part}]")
            elif part in known_names:
                parts.append(f".{part}")
            else:
                parts.append(".[unknown]")
        issues.append(ValidationIssue(
            path="".join(parts)[:MAX_ISSUE_LENGTH],
            message=_MESSAGES.get(error.validator, "Value does not conform to the schema.")
            [:MAX_ISSUE_LENGTH],
        ))
    return issues


def build_feedback(issues: list[ValidationIssue]) -> str:
    """Build model feedback from sanitized validation issues only."""
    details = "\n".join(f"{issue.path}: {issue.message}" for issue in issues[:MAX_ISSUES])
    return f"{SCHEMA_CONFORMANCE_INSTRUCTION}\n{details}" if details else (
        SCHEMA_CONFORMANCE_INSTRUCTION
    )
