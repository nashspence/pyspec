from __future__ import annotations

import copy
import json
from typing import Any, Iterable, Mapping


SCHEMA_ALIASES: dict[str, dict[str, Any]] = {
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


class SchemaExpressionError(ValueError):
    pass


JSON_SCHEMA_TYPES = {"array", "boolean", "integer", "null", "number", "object", "string"}
JSON_SCHEMA_KEYS = {
    "$ref",
    "additionalProperties",
    "allOf",
    "anyOf",
    "const",
    "enum",
    "format",
    "items",
    "oneOf",
    "properties",
    "required",
    "type",
}
EMPTY_OBJECT_SCHEMA: dict[str, Any] = {"type": "object", "properties": {}, "required": [], "additionalProperties": False}


def schema_alias(name: str) -> dict[str, Any]:
    if name not in SCHEMA_ALIASES:
        raise SchemaExpressionError(f"Unknown schema alias: {name!r}")
    return copy.deepcopy(SCHEMA_ALIASES[name])


def entity_type_ref(name: str) -> dict[str, str]:
    return {"$ref": name}


def array_of(item: Any) -> dict[str, Any]:
    return {"type": "array", "items": normalize_schema(item)}


def normalize_schema(expr: Any) -> dict[str, Any]:
    """Return the canonical JSON Schema form for a contract schema expression."""
    if not isinstance(expr, Mapping):
        raise SchemaExpressionError(f"Schema expression must be an object: {expr!r}")
    if not expr:
        return {}

    unknown = set(expr) - JSON_SCHEMA_KEYS
    if unknown:
        raise SchemaExpressionError(f"Schema has unsupported keys: {sorted(unknown)}")
    schema = copy.deepcopy(dict(expr))
    if "$ref" in schema:
        if set(schema) != {"$ref"} or not isinstance(schema["$ref"], str):
            raise SchemaExpressionError("$ref schema must contain only a string $ref")
        return schema
    if "type" in schema:
        schema["type"] = _normalize_json_type(schema["type"])
    if "properties" in schema:
        if schema.get("type") not in ("object", ["object"], ["object", "null"], ["null", "object"]):
            schema.setdefault("type", "object")
        if not isinstance(schema["properties"], Mapping):
            raise SchemaExpressionError("Object schema properties must be an object")
        schema["properties"] = {
            name: normalize_schema(child)
            for name, child in sorted(schema["properties"].items())
        }
        required = schema.get("required", [])
        if not isinstance(required, list) or not all(isinstance(item, str) for item in required):
            raise SchemaExpressionError("Object schema required must be a string array")
        missing = sorted(set(required) - set(schema["properties"]))
        if missing:
            raise SchemaExpressionError(f"Object schema required names are not properties: {missing}")
        schema["required"] = sorted(required)
        schema.setdefault("additionalProperties", False)
    if "items" in schema:
        schema["items"] = normalize_schema(schema["items"])
    if isinstance(schema.get("additionalProperties"), Mapping):
        schema["additionalProperties"] = normalize_schema(schema["additionalProperties"])
    for composition_key in ("anyOf", "oneOf", "allOf"):
        if composition_key in schema:
            members = schema[composition_key]
            if not isinstance(members, list) or not members:
                raise SchemaExpressionError(f"{composition_key} must declare one or more schemas")
            schema[composition_key] = [normalize_schema(member) for member in members]
    if "enum" in schema:
        if not isinstance(schema["enum"], list) or not schema["enum"]:
            raise SchemaExpressionError("Enum schema must declare one or more values")
        if len({json.dumps(item, sort_keys=True) for item in schema["enum"]}) != len(schema["enum"]):
            raise SchemaExpressionError(f"Enum schema contains duplicate values: {schema['enum']!r}")
    return schema


def _normalize_json_type(value: Any) -> str | list[str]:
    if isinstance(value, str):
        if value not in JSON_SCHEMA_TYPES:
            raise SchemaExpressionError(f"Unknown JSON Schema type: {value!r}")
        return value
    if isinstance(value, list) and value and all(isinstance(item, str) and item in JSON_SCHEMA_TYPES for item in value):
        if len(value) != len(set(value)):
            raise SchemaExpressionError(f"JSON Schema type array contains duplicates: {value!r}")
        return sorted(value)
    raise SchemaExpressionError(f"JSON Schema type must be a type name or type-name array: {value!r}")


def normalize_schema_map(fields: Mapping[str, Any] | None) -> dict[str, dict[str, Any]]:
    return {name: normalize_schema(schema) for name, schema in (fields or {}).items()}


def normalize_property_schema(field: Any) -> dict[str, Any]:
    return normalize_schema(field)


def normalize_property_map(fields: Mapping[str, Any] | None) -> dict[str, dict[str, Any]]:
    return {name: normalize_property_schema(field) for name, field in (fields or {}).items()}


def normalize_object_json_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    if not schema:
        return copy.deepcopy(EMPTY_OBJECT_SCHEMA)
    if not _looks_like_json_schema(schema) and all(isinstance(value, Mapping) for value in schema.values()):
        return {
            "type": "object",
            "properties": normalize_property_map(schema),
            "required": sorted(schema),
            "additionalProperties": False,
        }
    normalized = normalize_schema(schema)
    if normalized.get("type") != "object" and "object" not in (normalized.get("type") or []):
        raise SchemaExpressionError("Object schema must declare type: object")
    normalized.setdefault("properties", {})
    normalized.setdefault("required", [])
    normalized.setdefault("additionalProperties", False)
    return normalized


def _looks_like_json_schema(schema: Mapping[str, Any]) -> bool:
    return bool(set(schema) & JSON_SCHEMA_KEYS)


def schema_properties(schema: Mapping[str, Any] | None) -> dict[str, Any]:
    return dict(normalize_object_json_schema(schema or EMPTY_OBJECT_SCHEMA).get("properties", {}))


def schema_required(schema: Mapping[str, Any] | None) -> set[str]:
    return set(normalize_object_json_schema(schema or EMPTY_OBJECT_SCHEMA).get("required", []))


def schema_property_required(schema: Mapping[str, Any] | None, name: str) -> bool:
    return name in schema_required(schema)


def effective_property_schema(field: Any) -> dict[str, Any]:
    return normalize_property_schema(field)


def effective_schema_map(fields: Mapping[str, Any] | None) -> dict[str, dict[str, Any]]:
    return {name: effective_property_schema(field) for name, field in (fields or {}).items()}


def type_equals(left: Any, right: Any) -> bool:
    return normalize_schema(left) == normalize_schema(right)


def type_key(expr: Any) -> str:
    return json.dumps(normalize_schema(expr), sort_keys=True, separators=(",", ":"))


def entity_type_display_name(ref: str) -> str:
    if not ref.startswith("entity_type."):
        return ref
    return "".join(part.capitalize() for part in ref.removeprefix("entity_type.").split("_"))


def type_display(expr: Any) -> str:
    expr = normalize_schema(expr)
    if "$ref" in expr:
        ref = expr["$ref"]
        return entity_type_display_name(ref) if ref.startswith("entity_type.") else ref
    if "anyOf" in expr:
        members = expr["anyOf"]
        non_null = [member for member in members if member.get("type") != "null"]
        if len(non_null) == 1 and len(members) == 2:
            return f"{type_display(non_null[0])} | null"
        return " | ".join(type_display(member) for member in members)
    type_value = expr.get("type")
    if isinstance(type_value, list):
        non_null = [item for item in type_value if item != "null"]
        if len(non_null) == 1 and len(type_value) == 2:
            clone = dict(expr)
            clone["type"] = non_null[0]
            return f"{type_display(clone)} | null"
        return "|".join(type_value)
    if type_value == "array":
        return f"array<{type_display(expr.get('items', {}))}>"
    if type_value == "object":
        if "properties" in expr and expr["properties"]:
            fields = ", ".join(f"{name}: {type_display(child)}" for name, child in sorted(expr["properties"].items()))
            return "object{" + fields + "}"
        return "object"
    if "enum" in expr:
        return "enum<" + "|".join(str(item) for item in expr["enum"]) + ">"
    if "const" in expr:
        return f"const<{expr['const']}>"
    if type_value == "string" and expr.get("format"):
        return f"string:{expr['format']}"
    if isinstance(type_value, str):
        return type_value
    return "schema"


def schema_without_null(expr: Any) -> dict[str, Any]:
    expr = normalize_schema(expr)
    type_value = expr.get("type")
    if isinstance(type_value, list) and "null" in type_value:
        remaining = [item for item in type_value if item != "null"]
        clone = copy.deepcopy(expr)
        if len(remaining) == 1:
            clone["type"] = remaining[0]
        elif remaining:
            clone["type"] = remaining
        else:
            clone["type"] = "null"
        return clone
    if "anyOf" in expr:
        members = expr["anyOf"]
        non_null = [member for member in members if member.get("type") != "null"]
        if len(non_null) == 1 and len(members) == 2:
            return non_null[0]
    return expr


def entity_type_id(expr: Any) -> str | None:
    expr = schema_without_null(expr)
    if "$ref" in expr and expr["$ref"].startswith("entity_type."):
        return expr["$ref"]
    return None


def schema_ref(expr: Any) -> str | None:
    expr = schema_without_null(expr)
    if "$ref" in expr and expr["$ref"].startswith("schema."):
        return expr["$ref"]
    return None


def schema_name(expr: Any) -> str | None:
    return schema_ref(expr)


def base_entity_type_id(expr: Any) -> str | None:
    expr = schema_without_null(expr)
    if expr.get("type") == "array":
        return entity_type_id(expr.get("items", {}))
    return entity_type_id(expr)


def is_array_of_entity_type(expr: Any, expected_entity_type_id: str) -> bool:
    expr = schema_without_null(expr)
    return expr.get("type") == "array" and entity_type_id(expr.get("items", {})) == expected_entity_type_id


def is_problem_type(expr: Any) -> bool:
    name = base_entity_type_id(expr)
    return bool(name and (name == "entity_type.problem" or name.endswith(".problem")))


def object_fields_for_type(contract: Mapping[str, Any] | None, expr: Any) -> dict[str, Any] | None:
    expr = schema_without_null(expr)
    if expr.get("type") == "object" or "properties" in expr:
        return dict(expr.get("properties", {}))
    name = entity_type_id(expr)
    if name and contract and name in contract.get("entity_types", {}):
        return dict(normalize_object_json_schema(contract["entity_types"][name]["schema"]).get("properties", {}))
    schema_name = schema_ref(expr)
    if schema_name and contract and schema_name in contract.get("schemas", {}):
        return dict(normalize_object_json_schema(contract["schemas"][schema_name]["schema"]).get("properties", {}))
    return None


def dereference_type(contract: Mapping[str, Any] | None, expr: Any, path: Iterable[str], source: str) -> dict[str, Any]:
    current = normalize_schema(expr)
    for segment in path:
        fields = object_fields_for_type(contract, current)
        if fields is None:
            raise SchemaExpressionError(f"cannot dereference non-object field: {source}")
        if segment not in fields:
            container = entity_type_id(current) or schema_ref(current) or "inline object"
            raise SchemaExpressionError(f"unknown {container} field: {segment}")
        current = fields[segment]
    return normalize_schema(current)


def referenced_named_types(expr: Any) -> set[str]:
    expr = normalize_schema(expr)
    if "$ref" in expr:
        return {expr["$ref"]}
    names: set[str] = set()
    if "items" in expr:
        names.update(referenced_named_types(expr["items"]))
    for child in expr.get("properties", {}).values():
        names.update(referenced_named_types(child))
    additional = expr.get("additionalProperties")
    if isinstance(additional, Mapping):
        names.update(referenced_named_types(additional))
    for child in expr.get("anyOf", []) + expr.get("oneOf", []) + expr.get("allOf", []):
        names.update(referenced_named_types(child))
    return names


def literal_schema(value: Any) -> dict[str, str] | None:
    if isinstance(value, bool):
        return schema_alias("Boolean")
    if isinstance(value, int) and not isinstance(value, bool):
        return schema_alias("Integer")
    if isinstance(value, float):
        return schema_alias("Decimal")
    if isinstance(value, (dict, list)):
        return schema_alias("JSON")
    return None


def type_to_json_schema(expr: Any) -> dict[str, Any]:
    expr = normalize_schema(expr)
    if "$ref" in expr:
        ref = expr["$ref"]
        return {"$ref": f"#/components/schemas/{entity_type_display_name(ref) if ref.startswith('entity_type.') else ref}"}
    result = copy.deepcopy(expr)
    if "items" in result:
        result["items"] = type_to_json_schema(result["items"])
    if "properties" in result:
        result["properties"] = {name: type_to_json_schema(child) for name, child in result["properties"].items()}
    if isinstance(result.get("additionalProperties"), Mapping):
        result["additionalProperties"] = type_to_json_schema(result["additionalProperties"])
    for composition_key in ("anyOf", "oneOf", "allOf"):
        if composition_key in result:
            result[composition_key] = [type_to_json_schema(member) for member in result[composition_key]]
    return result


def object_to_json_schema(fields: Mapping[str, Any]) -> dict[str, Any]:
    normalized = normalize_object_json_schema(fields)
    return type_to_json_schema(normalized)


def type_to_cwl(expr: Any) -> str | dict[str, Any] | list[Any]:
    expr = normalize_schema(expr)
    if "$ref" in expr or "enum" in expr or expr.get("type") == "object":
        return "Any"
    type_value = expr.get("type")
    if isinstance(type_value, list):
        return ["null", type_to_cwl({**expr, "type": [item for item in type_value if item != "null"][0]})] if "null" in type_value and len(type_value) == 2 else "Any"
    if type_value == "string":
        return "string"
    if type_value == "boolean":
        return "boolean"
    if type_value == "integer":
        return "int"
    if type_value == "number":
        return "double"
    if type_value == "array":
        return {"type": "array", "items": type_to_cwl(expr.get("items", {}))}
    return "Any"


def type_to_python(expr: Any) -> str:
    expr = normalize_schema(expr)
    if "$ref" in expr or "enum" in expr:
        return "dict[str, object]"
    if expr.get("type") == "object":
        return "dict[str, object]"
    type_value = expr.get("type")
    if isinstance(type_value, list):
        non_null = [item for item in type_value if item != "null"]
        return f"{type_to_python({**expr, 'type': non_null[0]})} | None" if len(non_null) == 1 and "null" in type_value else "object"
    if type_value == "string":
        return "str"
    if type_value == "boolean":
        return "bool"
    if type_value == "integer":
        return "int"
    if type_value == "number":
        return "float"
    if type_value == "array":
        return f"list[{type_to_python(expr.get('items', {}))}]"
    return "object"


def sample_value(expr: Any) -> Any:
    schema = normalize_schema(expr)
    if "$ref" in schema:
        return {}
    type_value = schema.get("type")
    if isinstance(type_value, list) and "null" in type_value:
        return None
    if type_value == "boolean":
        return True
    if type_value == "integer":
        return 1
    if type_value == "number":
        return 1.0
    if type_value == "object":
        required = set(schema.get("required", []))
        return {name: sample_value(child) for name, child in schema.get("properties", {}).items() if name in required}
    if type_value == "array":
        return []
    if "enum" in schema:
        return schema["enum"][0]
    if "const" in schema:
        return schema["const"]
    return "sample"
