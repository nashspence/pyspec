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
    "Boolean": {"type": "boolean"},
    "Integer": {"type": "integer"},
    "Decimal": {"type": "number"},
    "JSON": {"type": "object", "additionalProperties": True},
}


class TypeExpressionError(ValueError):
    pass


def primitive(name: str) -> dict[str, str]:
    return {"primitive": name}


def entity_type(name: str) -> dict[str, str]:
    return {"entity_type": name}


def array_of(item: Any) -> dict[str, Any]:
    return {"array": normalize_type_expr(item)}


def normalize_type_expr(expr: Any) -> dict[str, Any]:
    """Return the canonical structured form for a contract type expression."""
    if not isinstance(expr, Mapping):
        raise TypeExpressionError(f"Type expression must be an object: {expr!r}")
    if len(expr) != 1:
        raise TypeExpressionError(f"Type expression must have exactly one kind: {expr!r}")
    kind, value = next(iter(expr.items()))
    if kind == "primitive":
        if value not in PRIMITIVES:
            raise TypeExpressionError(f"Unknown primitive type: {value!r}")
        return {"primitive": value}
    if kind in {"entity_type", "data_contract"}:
        if not isinstance(value, str):
            raise TypeExpressionError(f"{kind} type must name a reusable contract")
        return {kind: value}
    if kind in {"array", "map", "nullable"}:
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
    """Normalize a field declaration to explicit presence/nullability metadata."""
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

    if "nullable" in type_expr:
        raise TypeExpressionError("Field schema type must not use nullable; use field_schema.nullable")
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
    return normalize_type_expr(type_expr)


def effective_type_map(fields: Mapping[str, Any] | None) -> dict[str, dict[str, Any]]:
    return {name: effective_field_type(field) for name, field in (fields or {}).items()}


def type_equals(left: Any, right: Any) -> bool:
    return normalize_type_expr(left) == normalize_type_expr(right)


def type_key(expr: Any) -> str:
    return json.dumps(normalize_type_expr(expr), sort_keys=True, separators=(",", ":"))


def entity_type_display_name(ref: str) -> str:
    if not ref.startswith("entity_type."):
        return ref
    return "".join(part.capitalize() for part in ref.removeprefix("entity_type.").split("_"))


def type_display(expr: Any) -> str:
    expr = normalize_type_expr(expr)
    kind, value = next(iter(expr.items()))
    if kind == "entity_type":
        return entity_type_display_name(value)
    if kind in {"primitive", "data_contract"}:
        return value
    if kind == "array":
        return f"array<{type_display(value)}>"
    if kind == "map":
        return f"map<{type_display(value)}>"
    if kind == "nullable":
        return f"nullable<{type_display(value)}>"
    if kind == "enum":
        return "enum<" + "|".join(value) + ">"
    if kind == "object":
        fields = ", ".join(
            f"{name}: {type_display(effective_field_type(child))}"
            for name, child in sorted(normalize_object_schema(value)["fields"].items())
        )
        return "object{" + fields + "}"
    raise TypeExpressionError(f"Unsupported type expression kind: {kind}")


def unwrap_nullable(expr: Any) -> dict[str, Any]:
    expr = normalize_type_expr(expr)
    while "nullable" in expr:
        expr = normalize_type_expr(expr["nullable"])
    return expr


def entity_type_id(expr: Any) -> str | None:
    expr = unwrap_nullable(expr)
    if "entity_type" in expr:
        return expr["entity_type"]
    return None


def data_contract_name(expr: Any) -> str | None:
    expr = unwrap_nullable(expr)
    if "data_contract" in expr:
        return expr["data_contract"]
    return None


def base_entity_type_id(expr: Any) -> str | None:
    expr = unwrap_nullable(expr)
    if "array" in expr:
        return entity_type_id(expr["array"])
    return entity_type_id(expr)


def is_array_of_entity_type(expr: Any, expected_entity_type_id: str) -> bool:
    expr = unwrap_nullable(expr)
    return "array" in expr and entity_type_id(expr["array"]) == expected_entity_type_id


def is_problem_type(expr: Any) -> bool:
    name = base_entity_type_id(expr)
    return bool(name and (name == "entity_type.problem" or name.endswith(".problem")))


def object_fields_for_type(contract: Mapping[str, Any] | None, expr: Any) -> dict[str, Any] | None:
    expr = unwrap_nullable(expr)
    if "object" in expr:
        return effective_type_map(expr["object"]["fields"])
    name = entity_type_id(expr)
    if name and contract and name in contract.get("entity_types", {}):
        return effective_type_map(contract["entity_types"][name]["fields"])
    data_name = data_contract_name(expr)
    if data_name and contract and data_name in contract.get("data_contracts", {}):
        return effective_type_map(contract["data_contracts"][data_name]["fields"])
    return None


def dereference_type(contract: Mapping[str, Any] | None, expr: Any, path: Iterable[str], source: str) -> dict[str, Any]:
    current = normalize_type_expr(expr)
    for segment in path:
        fields = object_fields_for_type(contract, current)
        if fields is None:
            raise TypeExpressionError(f"cannot dereference non-object field: {source}")
        if segment not in fields:
            container = entity_type_id(current) or data_contract_name(current) or "inline object"
            raise TypeExpressionError(f"unknown {container} field: {segment}")
        current = fields[segment]
    return normalize_type_expr(current)


def referenced_named_types(expr: Any) -> set[str]:
    expr = normalize_type_expr(expr)
    kind, value = next(iter(expr.items()))
    if kind in {"entity_type", "data_contract"}:
        return {value}
    if kind in {"array", "map", "nullable"}:
        return referenced_named_types(value)
    if kind == "object":
        names: set[str] = set()
        for child in normalize_object_schema(value)["fields"].values():
            names.update(referenced_named_types(child["type"]))
        return names
    return set()


def literal_type_expr(value: Any) -> dict[str, str] | None:
    if isinstance(value, bool):
        return primitive("Boolean")
    if isinstance(value, int) and not isinstance(value, bool):
        return primitive("Integer")
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
    if kind == "entity_type":
        return {"$ref": f"#/components/schemas/{entity_type_display_name(value)}"}
    if kind == "data_contract":
        return {"$ref": f"#/components/schemas/{value}"}
    if kind == "array":
        return {"type": "array", "items": type_to_json_schema(value)}
    if kind == "map":
        return {"type": "object", "additionalProperties": type_to_json_schema(value)}
    if kind == "nullable":
        schema = type_to_json_schema(value)
        return {"anyOf": [schema, {"type": "null"}]}
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
        if value == "Boolean":
            return "boolean"
        if value == "Integer":
            return "int"
        if value == "Decimal":
            return "double"
        return "Any"
    if kind in {"entity_type", "data_contract", "enum", "object", "map"}:
        return "Any"
    if kind == "array":
        return {"type": "array", "items": type_to_cwl(value)}
    if kind == "nullable":
        return ["null", type_to_cwl(value)]
    raise TypeExpressionError(f"Unsupported type expression kind: {kind}")


def type_to_python(expr: Any) -> str:
    expr = normalize_type_expr(expr)
    kind, value = next(iter(expr.items()))
    if kind == "primitive":
        if value in {"ID", "Text", "Markdown", "Date", "Timestamp"}:
            return "str"
        if value == "Boolean":
            return "bool"
        if value == "Integer":
            return "int"
        if value == "Decimal":
            return "float"
        return "object"
    if kind in {"entity_type", "data_contract", "enum", "object"}:
        return "dict[str, object]" if kind == "object" else "str"
    if kind == "array":
        return f"list[{type_to_python(value)}]"
    if kind == "map":
        return f"dict[str, {type_to_python(value)}]"
    if kind == "nullable":
        return f"{type_to_python(value)} | None"
    raise TypeExpressionError(f"Unsupported type expression kind: {kind}")


def sample_value(expr: Any) -> Any:
    kind, value = next(iter(normalize_type_expr(expr).items()))
    if kind == "primitive":
        return {
            "Boolean": True,
            "Integer": 1,
            "Decimal": 1.0,
            "JSON": {},
        }.get(value, "sample")
    if kind in {"entity_type", "data_contract", "map"}:
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
