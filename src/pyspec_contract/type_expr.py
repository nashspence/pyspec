from __future__ import annotations

import copy
import json
from typing import Any, Iterable, Mapping


PRIMITIVES: dict[str, dict[str, Any]] = {
    "ID": {"type": "string"},
    "Text": {"type": "string"},
    "Markdown": {"type": "string"},
    "Date": {"type": "string", "format": "date"},
    "Timestamp": {"type": "string", "format": "date-time"},
    "Bool": {"type": "boolean"},
    "Int": {"type": "integer"},
    "Decimal": {"type": "number"},
    "JSON": {"type": "object", "additionalProperties": True},
}


class TypeExpressionError(ValueError):
    pass


def primitive(name: str) -> dict[str, str]:
    return {"primitive": name}


def model(name: str) -> dict[str, str]:
    return {"model": name}


def array_of(item: Any) -> dict[str, Any]:
    return {"array": normalize_type_expr(item)}


def normalize_type_expr(expr: Any) -> dict[str, Any]:
    """Return the canonical structured form for a contract type expression.

    The string branch is only a migration/interop shim for older in-memory tests
    and hand-built values. The JSON Schemas require structured expressions.
    """
    if isinstance(expr, str):
        if expr.startswith("list[") and expr.endswith("]"):
            return {"array": normalize_type_expr(expr[5:-1])}
        if expr in PRIMITIVES:
            return {"primitive": expr}
        return {"model": expr}
    if not isinstance(expr, Mapping):
        raise TypeExpressionError(f"Type expression must be an object: {expr!r}")
    if len(expr) != 1:
        raise TypeExpressionError(f"Type expression must have exactly one kind: {expr!r}")
    kind, value = next(iter(expr.items()))
    if kind == "primitive":
        if value not in PRIMITIVES:
            raise TypeExpressionError(f"Unknown primitive type: {value!r}")
        return {"primitive": value}
    if kind in {"model", "contract"}:
        if not isinstance(value, str):
            raise TypeExpressionError(f"{kind} type must name a reusable contract")
        return {kind: value}
    if kind in {"array", "map", "nullable", "optional"}:
        return {kind: normalize_type_expr(value)}
    if kind == "enum":
        if not isinstance(value, list) or not value or not all(isinstance(item, str) for item in value):
            raise TypeExpressionError("Enum type must declare one or more string values")
        if len(value) != len(set(value)):
            raise TypeExpressionError(f"Enum type contains duplicate values: {value!r}")
        return {"enum": list(value)}
    if kind == "object":
        if not isinstance(value, Mapping):
            raise TypeExpressionError("Inline object type must declare an object schema")
        return {"object": normalize_object_schema(value)}
    raise TypeExpressionError(f"Unsupported type expression kind: {kind}")


def normalize_type_map(fields: Mapping[str, Any] | None) -> dict[str, dict[str, Any]]:
    return {name: normalize_type_expr(type_expr) for name, type_expr in (fields or {}).items()}


def normalize_field_schema(field: Any) -> dict[str, Any]:
    """Normalize a field declaration to explicit presence/nullability metadata.

    The non-``type`` branch keeps older in-memory field maps readable while the
    authored/compiled schemas require the explicit object form.
    """
    if isinstance(field, Mapping) and "type" in field:
        unknown = set(field) - {"type", "required", "nullable"}
        if unknown:
            raise TypeExpressionError(f"Field schema has unsupported keys: {sorted(unknown)}")
        required = field.get("required", True)
        nullable = field.get("nullable", False)
        type_expr = normalize_type_expr(field["type"])
    else:
        required = True
        nullable = False
        type_expr = normalize_type_expr(field)

    if not isinstance(required, bool):
        raise TypeExpressionError("Field schema required must be a boolean")
    if not isinstance(nullable, bool):
        raise TypeExpressionError("Field schema nullable must be a boolean")

    while "optional" in type_expr or "nullable" in type_expr:
        if "optional" in type_expr:
            required = False
            type_expr = normalize_type_expr(type_expr["optional"])
        else:
            nullable = True
            type_expr = normalize_type_expr(type_expr["nullable"])
    return {"type": type_expr, "required": required, "nullable": nullable}


def normalize_field_map(fields: Mapping[str, Any] | None) -> dict[str, dict[str, Any]]:
    return {name: normalize_field_schema(field) for name, field in (fields or {}).items()}


def normalize_object_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    if "fields" in schema:
        unknown = set(schema) - {"fields"}
        if unknown:
            raise TypeExpressionError(f"Object schema has unsupported keys: {sorted(unknown)}")
        fields = schema["fields"]
    else:
        fields = schema
    if not isinstance(fields, Mapping):
        raise TypeExpressionError("Object schema fields must be a field map")
    return {"fields": normalize_field_map(fields)}


def effective_field_type(field: Any) -> dict[str, Any]:
    normalized = normalize_field_schema(field)
    type_expr = normalized["type"]
    if normalized["nullable"]:
        type_expr = {"nullable": type_expr}
    if not normalized["required"]:
        type_expr = {"optional": type_expr}
    return normalize_type_expr(type_expr)


def effective_type_map(fields: Mapping[str, Any] | None) -> dict[str, dict[str, Any]]:
    return {name: effective_field_type(field) for name, field in (fields or {}).items()}


def type_equals(left: Any, right: Any) -> bool:
    return normalize_type_expr(left) == normalize_type_expr(right)


def type_key(expr: Any) -> str:
    return json.dumps(normalize_type_expr(expr), sort_keys=True, separators=(",", ":"))


def type_display(expr: Any) -> str:
    expr = normalize_type_expr(expr)
    kind, value = next(iter(expr.items()))
    if kind in {"primitive", "model", "contract"}:
        return value
    if kind == "array":
        return f"array<{type_display(value)}>"
    if kind == "map":
        return f"map<{type_display(value)}>"
    if kind == "nullable":
        return f"nullable<{type_display(value)}>"
    if kind == "optional":
        return f"optional<{type_display(value)}>"
    if kind == "enum":
        return "enum<" + "|".join(value) + ">"
    if kind == "object":
        fields = ", ".join(
            f"{name}: {type_display(effective_field_type(child))}"
            for name, child in sorted(normalize_object_schema(value)["fields"].items())
        )
        return "object{" + fields + "}"
    raise TypeExpressionError(f"Unsupported type expression kind: {kind}")


def unwrap_optional(expr: Any) -> dict[str, Any]:
    expr = normalize_type_expr(expr)
    return normalize_type_expr(expr["optional"]) if "optional" in expr else expr


def unwrap_nullable_optional(expr: Any) -> dict[str, Any]:
    expr = normalize_type_expr(expr)
    while "optional" in expr or "nullable" in expr:
        expr = normalize_type_expr(expr.get("optional", expr.get("nullable")))
    return expr


def is_optional(expr: Any) -> bool:
    return "optional" in normalize_type_expr(expr)


def model_name(expr: Any) -> str | None:
    expr = unwrap_nullable_optional(expr)
    if "model" in expr:
        return expr["model"]
    if "contract" in expr:
        return expr["contract"]
    return None


def base_model_name(expr: Any) -> str | None:
    expr = unwrap_nullable_optional(expr)
    if "array" in expr:
        return model_name(expr["array"])
    return model_name(expr)


def is_array_of_model(expr: Any, model_id: str) -> bool:
    expr = unwrap_nullable_optional(expr)
    return "array" in expr and model_name(expr["array"]) == model_id


def is_problem_type(expr: Any) -> bool:
    name = base_model_name(expr)
    return bool(name and (name == "Problem" or name.endswith("Problem")))


def object_fields_for_type(contract: Mapping[str, Any] | None, expr: Any) -> dict[str, Any] | None:
    expr = unwrap_nullable_optional(expr)
    if "object" in expr:
        return effective_type_map(expr["object"]["fields"])
    name = model_name(expr)
    if name and contract and name in contract.get("models", {}):
        return effective_type_map(contract["models"][name]["fields"])
    return None


def dereference_type(contract: Mapping[str, Any] | None, expr: Any, path: Iterable[str], source: str) -> dict[str, Any]:
    current = normalize_type_expr(expr)
    for segment in path:
        fields = object_fields_for_type(contract, current)
        if fields is None:
            raise TypeExpressionError(f"cannot dereference non-object field: {source}")
        if segment not in fields:
            container = model_name(current) or "inline object"
            raise TypeExpressionError(f"unknown {container} field: {segment}")
        current = fields[segment]
    return normalize_type_expr(current)


def referenced_named_types(expr: Any) -> set[str]:
    expr = normalize_type_expr(expr)
    kind, value = next(iter(expr.items()))
    if kind in {"model", "contract"}:
        return {value}
    if kind in {"array", "map", "nullable", "optional"}:
        return referenced_named_types(value)
    if kind == "object":
        names: set[str] = set()
        for child in normalize_object_schema(value)["fields"].values():
            names.update(referenced_named_types(child["type"]))
        return names
    return set()


def literal_type_expr(value: Any) -> dict[str, str] | None:
    if isinstance(value, bool):
        return primitive("Bool")
    if isinstance(value, int) and not isinstance(value, bool):
        return primitive("Int")
    if isinstance(value, float):
        return primitive("Decimal")
    if isinstance(value, (dict, list)):
        return primitive("JSON")
    return None


def type_to_json_schema(expr: Any) -> dict[str, Any]:
    expr = normalize_type_expr(expr)
    kind, value = next(iter(expr.items()))
    if kind == "primitive":
        return copy.deepcopy(PRIMITIVES[value])
    if kind in {"model", "contract"}:
        return {"$ref": f"#/components/schemas/{value}"}
    if kind == "array":
        return {"type": "array", "items": type_to_json_schema(value)}
    if kind == "map":
        return {"type": "object", "additionalProperties": type_to_json_schema(value)}
    if kind == "nullable":
        schema = type_to_json_schema(value)
        return {"anyOf": [schema, {"type": "null"}]}
    if kind == "optional":
        return type_to_json_schema(value)
    if kind == "enum":
        return {"type": "string", "enum": value}
    if kind == "object":
        return object_to_json_schema(value)
    raise TypeExpressionError(f"Unsupported type expression kind: {kind}")


def object_to_json_schema(fields: Mapping[str, Any]) -> dict[str, Any]:
    normalized = normalize_object_schema(fields)["fields"]
    return {
        "type": "object",
        "additionalProperties": False,
        "required": sorted(name for name, field in normalized.items() if field["required"]),
        "properties": {
            name: type_to_json_schema({"nullable": field["type"]} if field["nullable"] else field["type"])
            for name, field in sorted(normalized.items())
        },
    }


def type_to_cwl(expr: Any) -> str | dict[str, Any] | list[Any]:
    expr = normalize_type_expr(expr)
    kind, value = next(iter(expr.items()))
    if kind == "primitive":
        if value in {"ID", "Text", "Markdown", "Date", "Timestamp"}:
            return "string"
        if value == "Bool":
            return "boolean"
        if value == "Int":
            return "int"
        if value == "Decimal":
            return "double"
        return "Any"
    if kind in {"model", "contract", "enum", "object", "map"}:
        return "Any"
    if kind == "array":
        return {"type": "array", "items": type_to_cwl(value)}
    if kind in {"nullable", "optional"}:
        return ["null", type_to_cwl(value)]
    raise TypeExpressionError(f"Unsupported type expression kind: {kind}")


def type_to_python(expr: Any) -> str:
    expr = normalize_type_expr(expr)
    kind, value = next(iter(expr.items()))
    if kind == "primitive":
        if value in {"ID", "Text", "Markdown", "Date", "Timestamp"}:
            return "str"
        if value == "Bool":
            return "bool"
        if value == "Int":
            return "int"
        if value == "Decimal":
            return "float"
        return "object"
    if kind in {"model", "contract", "enum", "object"}:
        return "dict[str, object]" if kind == "object" else "str"
    if kind == "array":
        return f"list[{type_to_python(value)}]"
    if kind == "map":
        return f"dict[str, {type_to_python(value)}]"
    if kind in {"nullable", "optional"}:
        return f"{type_to_python(value)} | None"
    raise TypeExpressionError(f"Unsupported type expression kind: {kind}")


def sample_value(expr: Any) -> Any:
    expr = unwrap_optional(expr)
    kind, value = next(iter(normalize_type_expr(expr).items()))
    if kind == "primitive":
        return {
            "Bool": True,
            "Int": 1,
            "Decimal": 1.0,
            "JSON": {},
        }.get(value, "sample")
    if kind in {"model", "contract", "map"}:
        return {}
    if kind == "object":
        return {
            name: sample_value(field["type"])
            for name, field in normalize_object_schema(value)["fields"].items()
            if field["required"]
        }
    if kind == "array":
        return []
    if kind == "nullable":
        return None
    if kind == "enum":
        return value[0]
    return "sample"
