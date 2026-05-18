from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from pyspec_contract.compile import ROOT


DOC_PATH = ROOT.parents[1] / "docs" / "spec-ontology.md"
SCHEMA_ROOT = ROOT / "schemas"
DEPRECATED_DEFINITION_NAMES = {
    "capability",
    "application_action",
    "entry",
    "event",
    "fixture",
    "fsm",
    "entity_type",
    "scenario",
    "behavior_scenario",
    "workflow",
}
DEPRECATED_REFERENCE_DEFINITION_NAMES = {
    "asset_id",
    "audit_expected_artifacts",
    "audit_profile_id",
    "audit_profile_ref",
    "authored_audit_profile",
    "content_case_id",
    "content_resolver_id",
    "authored_copy",
    "copy_item",
    "copy_id",
    "dotted_id",
    "fact_id",
    "fixture_id",
    "fsm_id",
    "entity_type_id",
    "scenario_ref",
    "type_map",
    "type_name",
    "audit_profile_item",
}
DEPRECATED_TOP_LEVEL_PROPERTIES = {
    "audit_profiles",
    "copies",
    "scenarios",
}
DEPRECATED_PROPERTY_NAMES = {
    "basis",
    "why",
    "with",
    "do",
    "ran",
    "complete",
    "fail",
    "next",
}
def _former_name(prefix: str, suffix: str) -> str:
    return prefix + suffix


STALE_SCHEMA_DEFINITION_NAMES = {
    "entry_bindings",
    "expression_map",
    _former_name("layout_", "container"),
    _former_name("layout_", "region"),
    _former_name("layout_", "root"),
    "entity_type_refs",
    "action_emit_bindings",
    "action_emit_source",
    "state_name",
    _former_name("state_machine_", "audit_case"),
    "target",
    "workflow_input_bindings",
    "workflow_source",
    "workflow_trigger_target",
}
ALLOWED_DUPLICATE_DEFINITION_GROUPS = {
    frozenset({"instance_id", "view_state_name"}),
    frozenset({"entity_type_ref", "python_class_name"}),
}
ALLOWED_ANY_OF_PATHS_BY_SCHEMA = {
    "author.schema.json": {
        "$defs.authored_child_state_machine.anyOf",
        "$defs.authored_render_profile.anyOf",
        "$defs.schema.properties.anyOf",
        "$defs.state_machine_query_conditional_effect.anyOf",
        "$defs.state_machine_data_loader_outcome_effect.anyOf",
    },
    "spec.schema.json": {
        "$defs.child_state_machine_item.anyOf",
        "$defs.render_profile_item.anyOf",
        "$defs.schema.properties.anyOf",
        "$defs.state_machine_query_conditional_effect.anyOf",
        "$defs.state_machine_data_loader_outcome_effect.anyOf",
    },
}
ALLOWED_ONE_OF_WITHOUT_OBJECT_DISCRIMINATORS = {
    "$defs.authored_content_case.properties.ref.oneOf",
    "$defs.content_case_item.properties.ref.oneOf",
    "$defs.content_source_ref.oneOf",
    "$defs.given.properties.preconditions.items.oneOf",
    "$defs.json_value.oneOf",
    "$defs.schema.properties.additionalProperties.oneOf",
    "$defs.schema.properties.oneOf",
    "$defs.schema.properties.type.oneOf",
    "$defs.state_machine_signals.properties.accepts.propertyNames.oneOf",
    "$defs.state_machine_signal_trigger.oneOf",
    "$defs.then.properties.postconditions.items.oneOf",
}
JSON_SCHEMA_KEYWORD_PROPERTY_NAMES = {
    "$defs",
    "$id",
    "$ref",
    "$schema",
    "additionalProperties",
    "allOf",
    "anyOf",
    "const",
    "default",
    "description",
    "else",
    "enum",
    "examples",
    "format",
    "if",
    "items",
    "maxItems",
    "maxLength",
    "maxProperties",
    "maximum",
    "minItems",
    "minLength",
    "minProperties",
    "minimum",
    "not",
    "oneOf",
    "pattern",
    "properties",
    "propertyNames",
    "required",
    "then",
    "title",
    "type",
    "uniqueItems",
}
ALLOWED_JSON_SCHEMA_KEYWORD_PROPERTIES = {
    ("authored_behavior_scenario", "then"),
    ("authored_behavior_scenario", "title"),
    ("entry_point_response_value", "type"),
    ("schema", "$ref"),
    ("schema", "additionalProperties"),
    ("schema", "allOf"),
    ("schema", "anyOf"),
    ("schema", "const"),
    ("schema", "enum"),
    ("schema", "format"),
    ("schema", "items"),
    ("schema", "oneOf"),
    ("schema", "properties"),
    ("schema", "required"),
    ("schema", "type"),
    ("behavior_scenario_item", "then"),
    ("behavior_scenario_item", "title"),
}


def _json_without_duplicate_keys(path: Path) -> dict[str, Any]:
    def object_pairs_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        keys = [key for key, _ in pairs]
        duplicates = sorted(key for key, count in Counter(keys).items() if count > 1)
        assert duplicates == [], f"{path} contains duplicate JSON keys: {duplicates}"
        return dict(pairs)

    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=object_pairs_hook)


def _schemas() -> list[tuple[Path, dict[str, Any]]]:
    return [(path, _json_without_duplicate_keys(path)) for path in sorted(SCHEMA_ROOT.glob("**/*.schema.json"))]


def _walk(node: Any, trail: tuple[str, ...] = ()) -> list[tuple[tuple[str, ...], Any]]:
    nodes = [(trail, node)]
    if isinstance(node, dict):
        for key, value in node.items():
            nodes.extend(_walk(value, (*trail, key)))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            nodes.extend(_walk(value, (*trail, str(index))))
    return nodes


def _path(trail: tuple[str, ...]) -> str:
    return ".".join(trail)


def _definition_refs(node: Any) -> set[str]:
    refs: set[str] = set()
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/$defs/"):
            refs.add(ref.removeprefix("#/$defs/"))
        for value in node.values():
            refs.update(_definition_refs(value))
    elif isinstance(node, list):
        for value in node:
            refs.update(_definition_refs(value))
    return refs


def _reachable_definitions(schema: dict[str, Any]) -> set[str]:
    defs = schema.get("$defs", {})
    root_schema = {key: value for key, value in schema.items() if key != "$defs"}
    pending = list(_definition_refs(root_schema))
    reachable: set[str] = set()
    while pending:
        name = pending.pop()
        if name in reachable:
            continue
        reachable.add(name)
        if name in defs:
            pending.extend(_definition_refs(defs[name]) - reachable)
    return reachable


def _schema_definition_names() -> set[str]:
    names: set[str] = set()
    for _, schema in _schemas():
        names.update(schema.get("$defs", {}))
    return names


def _schema_top_level_properties() -> set[str]:
    names: set[str] = set()
    for _, schema in _schemas():
        names.update(schema.get("properties", {}))
    return names


def _markers(kind: str) -> Counter[str]:
    text = DOC_PATH.read_text(encoding="utf-8")
    return Counter(re.findall(rf"<!--\s*{re.escape(kind)}:([A-Za-z0-9_]+)\s*-->", text))


def _assert_inventory_matches(kind: str, expected: set[str]) -> None:
    markers = _markers(kind)
    duplicates = sorted(name for name, count in markers.items() if count > 1)
    documented = set(markers)
    assert duplicates == [], f"Duplicate {kind} documentation markers: {duplicates}"
    assert documented == expected, (
        f"{kind} documentation inventory mismatch; "
        f"missing={sorted(expected - documented)}, extra={sorted(documented - expected)}"
    )


def test_spec_ontology_documents_every_schema_definition() -> None:
    _assert_inventory_matches("schema-def", _schema_definition_names())


def test_spec_ontology_documents_every_top_level_property() -> None:
    _assert_inventory_matches("top-level", _schema_top_level_properties())


def test_schema_inventory_rejects_deprecated_definition_terminology() -> None:
    names = _schema_definition_names()
    deprecated_suffixes = sorted(name for name in names if name.endswith(("_author", "_spec")))
    deprecated_bare_items = sorted(names & (DEPRECATED_DEFINITION_NAMES | DEPRECATED_REFERENCE_DEFINITION_NAMES))
    deprecated_capability_terms = sorted(name for name in names if "capability" in name)
    deprecated_top_level_properties = sorted(_schema_top_level_properties() & DEPRECATED_TOP_LEVEL_PROPERTIES)
    assert deprecated_suffixes == []
    assert deprecated_bare_items == []
    assert deprecated_capability_terms == []
    assert deprecated_top_level_properties == []

    for path, schema in _schemas():
        refs = re.findall(r"#/\$defs/([A-Za-z0-9_]+)", json.dumps(schema))
        deprecated_refs = sorted(
            ref
            for ref in refs
            if ref.endswith(("_author", "_spec"))
            or ref in DEPRECATED_DEFINITION_NAMES | DEPRECATED_REFERENCE_DEFINITION_NAMES
            or "capability" in ref
        )
        assert deprecated_refs == [], f"{path} contains deprecated schema refs: {deprecated_refs}"


def test_schema_lint_rejects_stale_definition_names() -> None:
    for path, schema in _schemas():
        defs = set(schema.get("$defs", {}))
        stale_defs = sorted(defs & STALE_SCHEMA_DEFINITION_NAMES)
        stale_refs = sorted(_definition_refs(schema) & STALE_SCHEMA_DEFINITION_NAMES)
        assert stale_defs == [], f"{path} contains stale schema definitions: {stale_defs}"
        assert stale_refs == [], f"{path} contains stale schema refs: {stale_refs}"


def test_schema_lint_rejects_unresolved_and_unused_definitions() -> None:
    for path, schema in _schemas():
        defs = set(schema.get("$defs", {}))
        refs = _definition_refs(schema)
        unresolved = sorted(refs - defs)
        unused = sorted(defs - _reachable_definitions(schema))
        assert unresolved == [], f"{path} contains unresolved $defs refs: {unresolved}"
        assert unused == [], f"{path} contains unused $defs: {unused}"


def test_schema_lint_rejects_empty_required_arrays() -> None:
    for path, schema in _schemas():
        empty_required = [
            _path(trail)
            for trail, node in _walk(schema)
            if isinstance(node, dict) and node.get("required") == []
        ]
        assert empty_required == [], f"{path} contains empty required arrays: {empty_required}"


def test_schema_lint_rejects_unapproved_duplicate_definition_bodies() -> None:
    for path, schema in _schemas():
        duplicates: dict[str, list[str]] = {}
        for name, definition in schema.get("$defs", {}).items():
            normalized = json.dumps(definition, sort_keys=True, separators=(",", ":"))
            duplicates.setdefault(normalized, []).append(name)

        duplicate_groups = [
            frozenset(names)
            for names in duplicates.values()
            if len(names) > 1
        ]
        unexpected = sorted(
            [sorted(group) for group in duplicate_groups if group not in ALLOWED_DUPLICATE_DEFINITION_GROUPS]
        )
        assert unexpected == [], f"{path} contains unapproved duplicate $defs: {unexpected}"


def test_schema_lint_documents_any_of_usage() -> None:
    for path, schema in _schemas():
        expected = ALLOWED_ANY_OF_PATHS_BY_SCHEMA[path.name]
        actual = {
            _path((*trail, "anyOf"))
            for trail, node in _walk(schema)
            if isinstance(node, dict) and "anyOf" in node
        }
        assert actual == expected, f"{path} has undocumented anyOf usage: {sorted(actual ^ expected)}"


def _resolve_ref(schema: dict[str, Any], branch: Any) -> Any:
    if isinstance(branch, dict) and set(branch) == {"$ref"}:
        ref = branch["$ref"]
        if isinstance(ref, str) and ref.startswith("#/$defs/"):
            return schema.get("$defs", {}).get(ref.removeprefix("#/$defs/"), branch)
    return branch


def _one_of_required_discriminator(branch: Any) -> frozenset[str] | None:
    if not isinstance(branch, dict):
        return None
    required = branch.get("required")
    if isinstance(required, list) and required:
        return frozenset(required)
    return None


def test_schema_lint_documents_one_of_exclusivity_strategy() -> None:
    for path, schema in _schemas():
        for trail, node in _walk(schema):
            if not isinstance(node, dict) or "oneOf" not in node:
                continue

            schema_path = _path((*trail, "oneOf"))
            branches = [_resolve_ref(schema, branch) for branch in node["oneOf"]]
            discriminators = [_one_of_required_discriminator(branch) for branch in branches]
            if any(discriminator is None for discriminator in discriminators):
                assert schema_path in ALLOWED_ONE_OF_WITHOUT_OBJECT_DISCRIMINATORS, (
                    f"{path} oneOf lacks required-key discriminators at {schema_path}"
                )
                continue

            required_sets = [discriminator for discriminator in discriminators if discriminator is not None]
            duplicate_sets = [
                sorted(required_set)
                for required_set in set(required_sets)
                if required_sets.count(required_set) > 1
            ]
            assert duplicate_sets == [], f"{path} oneOf has duplicate discriminator sets at {schema_path}: {duplicate_sets}"

            for index, required_set in enumerate(required_sets):
                others = set().union(*(set(other) for offset, other in enumerate(required_sets) if offset != index))
                assert set(required_set) - others, (
                    f"{path} oneOf branch {index} has no unique discriminator key at {schema_path}"
                )


def test_schema_lint_limits_json_schema_keyword_shadowing() -> None:
    for path, schema in _schemas():
        shadowed: list[str] = []
        for trail, node in _walk(schema):
            if not isinstance(node, dict):
                continue
            properties = node.get("properties")
            if not isinstance(properties, dict):
                continue
            definition_name = trail[1] if len(trail) >= 2 and trail[0] == "$defs" else "<root>"
            for property_name in sorted(set(properties) & JSON_SCHEMA_KEYWORD_PROPERTY_NAMES):
                if (definition_name, property_name) not in ALLOWED_JSON_SCHEMA_KEYWORD_PROPERTIES:
                    shadowed.append(_path((*trail, "properties", property_name)))
        assert shadowed == [], f"{path} contains undocumented JSON Schema keyword property names: {shadowed}"


def test_schema_inventory_rejects_deprecated_property_terminology() -> None:
    for path, schema in _schemas():
        deprecated: list[str] = []

        def visit(node: Any, trail: tuple[str, ...] = ()) -> None:
            if isinstance(node, dict):
                properties = node.get("properties")
                if isinstance(properties, dict):
                    for name in sorted(set(properties) & DEPRECATED_PROPERTY_NAMES):
                        deprecated.append(".".join((*trail, "properties", name)))
                for key, value in node.items():
                    visit(value, (*trail, key))
            elif isinstance(node, list):
                for index, value in enumerate(node):
                    visit(value, (*trail, str(index)))

        visit(schema)
        assert deprecated == [], f"{path} contains deprecated property names: {deprecated}"


def test_layout_contract_uses_must_render_flag() -> None:
    for path, schema in _schemas():
        defs = schema.get("$defs", {})
        for name in ("textual_layout_container", "html_layout_region"):
            layout_def = defs.get(name)
            if not layout_def:
                continue
            properties = layout_def.get("properties", {})
            assert "must_render" in properties, f"{path} {name} missing must_render"
            assert "required" not in properties, f"{path} {name} still uses layout required flag"


def test_spec_ontology_rejects_deprecated_reference_terminology() -> None:
    text = DOC_PATH.read_text(encoding="utf-8")
    deprecated_doc_terms = DEPRECATED_REFERENCE_DEFINITION_NAMES | (DEPRECATED_TOP_LEVEL_PROPERTIES - {"scenarios"}) | {
        "capability",
        "capabilities",
        "fsm",
        "fsms",
    }
    deprecated_terms = sorted(
        term
        for term in deprecated_doc_terms
        if re.search(rf"(?<![A-Za-z0-9_]){re.escape(term)}(?![A-Za-z0-9_])", text)
    )
    assert deprecated_terms == []
