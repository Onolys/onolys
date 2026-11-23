"""A small provider-compatible projection; final validation uses the original schema."""

from copy import deepcopy
from typing import Any

# Provider structured-output dialects support only a subset of JSON Schema.
_UNSUPPORTED = {
    "$schema",
    "$id",
    "$anchor",
    "$comment",
    "$defs",
    "definitions",
    "title",
    "default",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "multipleOf",
    "minLength",
    "maxLength",
    "pattern",
    "format",
    "minItems",
    "maxItems",
    "uniqueItems",
    "minProperties",
    "maxProperties",
    "examples",
    "readOnly",
    "writeOnly",
    "deprecated",
}
_SCHEMA_MAPS = {"properties", "patternProperties", "dependentSchemas"}


def to_provider_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Inline local refs and omit unsupported constraints without changing the source.

    Recursive/external references cannot be inlined; reject them explicitly rather than
    sending an incomplete schema. Property names and enum/const values are left intact.
    """

    def resolve(ref: str) -> Any:
        if not ref.startswith("#/"):
            raise ValueError("only local JSON Schema references can be inlined")
        value: Any = schema
        try:
            for part in ref[2:].split("/"):
                value = value[part.replace("~1", "/").replace("~0", "~")]
        except (KeyError, TypeError) as exc:
            raise ValueError("unresolved JSON Schema reference") from exc
        return value

    def visit(node: Any, refs: frozenset[str] = frozenset()) -> Any:
        if isinstance(node, list):
            return [visit(value, refs) for value in node]
        if not isinstance(node, dict):
            return node
        result = {}
        if "$ref" in node:
            ref = node["$ref"]
            if ref in refs:
                raise ValueError("recursive JSON Schema reference cannot be inlined")
            result.update(visit(resolve(ref), refs | {ref}))
        for key, value in node.items():
            if key in _UNSUPPORTED or key == "$ref":
                continue
            if key in _SCHEMA_MAPS:
                result[key] = {name: visit(child, refs) for name, child in value.items()}
            elif key in {"enum", "const"}:
                result[key] = deepcopy(value)
            else:
                result[key] = visit(value, refs)
        return result

    return visit(schema)
