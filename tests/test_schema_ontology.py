from __future__ import annotations

import re
from typing import Any

import pytest

from pyspec_contract.compile import ROOT
from pyspec_contract.io import read_json
from pyspec_contract.layers import COMMON_LAYER_SETS, author_schema_for_layers


COLLECTION_SECTIONS = {
    "access_policies": "access_policy",
    "media_assets": "media_asset",
    "viewport_profiles": "viewport_profile",
    "commands": "command",
    "queries": "query",
    "content_examples": "content_example",
    "text_resources": "text_resource",
    "external_interfaces": "external_interface",
    "domain_events": "domain_event",
    "preconditions": "precondition",
    "assertions": "assertion",
    "fixtures": "fixture",
    "state_machines": "state_machine",
    "entity_types": "entity_type",
    "schemas": "schema",
    "behavior_scenarios": "behavior_scenario",
    "workflows": "workflow",
}


def _authored_schema_cases() -> list[Any]:
    schemas = [
        pytest.param(
            "author.schema.json",
            read_json(ROOT / "schemas" / "author.schema.json"),
            id="author.schema.json",
        )
    ]
    schemas.extend(
        pytest.param(
            f"generated:{name}.author.schema.json",
            author_schema_for_layers(layers),
            id=f"generated:{name}.author.schema.json",
        )
        for name, layers in sorted(COMMON_LAYER_SETS.items())
    )
    return schemas


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


@pytest.mark.parametrize("schema_name,schema", _authored_schema_cases())
def test_authored_schemas_only_use_authored_source_collection_defs(schema_name: str, schema: dict[str, Any]) -> None:
    defs = schema["$defs"]
    legacy = sorted(name for name in defs if name.endswith(("_author", "_item", "_spec")))
    assert legacy == [], schema_name

    refs = _definition_refs(schema)
    assert sorted(refs - set(defs)) == [], schema_name

    for section, singular in COLLECTION_SECTIONS.items():
        if section in schema["properties"]:
            assert schema["properties"][section]["additionalProperties"]["$ref"] == f"#/$defs/authored_{singular}"


def test_compiled_schema_uses_item_defs_for_compiled_collections() -> None:
    schema = read_json(ROOT / "schemas" / "spec.schema.json")
    defs = schema["$defs"]
    legacy = sorted(name for name in defs if name.endswith(("_author", "_spec")))
    assert legacy == []
    assert sorted(name for name in defs if name in COLLECTION_SECTIONS.values() and name != "schema") == []

    refs = _definition_refs(schema)
    assert sorted(refs - set(defs)) == []

    for section, singular in COLLECTION_SECTIONS.items():
        assert schema["properties"][section]["additionalProperties"]["$ref"] == f"#/$defs/{singular}_item"


def test_entity_type_ref_allows_dotted_domain_segments() -> None:
    schema_cases: list[tuple[str, dict[str, Any]]] = [
        ("author.schema.json", read_json(ROOT / "schemas" / "author.schema.json")),
        ("spec.schema.json", read_json(ROOT / "schemas" / "spec.schema.json")),
    ]
    schema_cases.extend(
        (f"generated:{name}.author.schema.json", author_schema_for_layers(layers))
        for name, layers in sorted(COMMON_LAYER_SETS.items())
    )

    for schema_name, schema in schema_cases:
        pattern = schema["$defs"]["entity_type_ref"]["pattern"]
        assert re.fullmatch(pattern, "entity_type.project"), schema_name
        assert re.fullmatch(pattern, "entity_type.billing.invoice"), schema_name
        assert not re.fullmatch(pattern, "entity_type."), schema_name
        assert not re.fullmatch(pattern, "entity_type.billing."), schema_name
        assert not re.fullmatch(pattern, "entity_type.billing..invoice"), schema_name


def test_binding_expression_restricts_root_vocabulary() -> None:
    schema_cases: list[tuple[str, dict[str, Any]]] = [
        ("author.schema.json", read_json(ROOT / "schemas" / "author.schema.json")),
        ("spec.schema.json", read_json(ROOT / "schemas" / "spec.schema.json")),
    ]
    schema_cases.extend(
        (f"generated:{name}.author.schema.json", author_schema_for_layers(layers))
        for name, layers in sorted(COMMON_LAYER_SETS.items())
    )

    valid = [
        "$fixture.workspace.id",
        "$state_machine.selected_project_id",
        "$trigger.payload.project_id",
        "$state_context.workspace_id",
        "$principal.roles[*]",
        "$adapter_input.body.title",
        "$command_input.project_id",
        "$command_outcome.result.message",
        "$query_outcome.result",
        "$invocation_outcome.result",
        "$command_binding.input.project_id",
        "$query_binding.input.workspace_id",
        "$adapter_response.body.message",
        "$workflow_input.payload.project_id",
        "$activity_outcome.send_notice.sent.result",
    ]
    invalid = [
        "$message.payload.project_id",
        "$operation_input.project_id",
        "$domain_event.payload.project_id",
        "$state.context",
        "$adapter.input.body.title",
    ]

    for schema_name, schema in schema_cases:
        pattern = schema["$defs"]["binding_expression"]["pattern"]
        for expression in valid:
            assert re.fullmatch(pattern, expression), f"{schema_name} should accept {expression}"
        for expression in invalid:
            assert not re.fullmatch(pattern, expression), f"{schema_name} should reject {expression}"


def test_state_machine_media_asset_slot_vocabulary_is_canonical() -> None:
    authored_schema_cases: list[tuple[str, dict[str, Any]]] = [
        ("author.schema.json", read_json(ROOT / "schemas" / "author.schema.json")),
    ]
    authored_schema_cases.extend(
        (f"generated:{name}.author.schema.json", author_schema_for_layers(layers))
        for name, layers in sorted(COMMON_LAYER_SETS.items())
    )

    for schema_name, schema in authored_schema_cases:
        state_properties = schema["$defs"]["authored_state_machine_state"]["properties"]
        assert "media_asset_slots" in state_properties, schema_name
        assert "asset_slots" not in state_properties, schema_name

    for schema_name, schema in [
        *authored_schema_cases,
        ("spec.schema.json", read_json(ROOT / "schemas" / "spec.schema.json")),
    ]:
        required_keys = {
            tuple(branch.get("required", []))
            for branch in schema["$defs"]["slot_binding"]["oneOf"]
        }
        assert ("media_asset_slot",) in required_keys, schema_name
        assert ("asset_slot",) not in required_keys, schema_name


def test_authored_state_machine_states_require_content_or_explicit_empty_marker() -> None:
    schema_cases: list[tuple[str, dict[str, Any]]] = [
        ("author.schema.json", read_json(ROOT / "schemas" / "author.schema.json")),
    ]
    schema_cases.extend(
        (f"generated:{name}.author.schema.json", author_schema_for_layers(layers))
        for name, layers in sorted(COMMON_LAYER_SETS.items())
    )

    for schema_name, schema in schema_cases:
        state = schema["$defs"]["authored_state_machine_state"]
        assert state["minProperties"] == 1, schema_name
        assert state["properties"]["intentionally_empty"]["const"] is True, schema_name
        assert state["properties"]["rationale"]["$ref"] == "#/$defs/rationale", schema_name
        required_alternatives = {tuple(branch["required"]) for branch in state["anyOf"]}
        assert ("intentionally_empty",) in required_alternatives, schema_name
        assert ("text_slots",) in required_alternatives, schema_name
        assert state["allOf"][0]["then"]["required"] == ["rationale"], schema_name


def test_authored_local_id_collections_are_keyed_maps() -> None:
    schema_cases: list[tuple[str, dict[str, Any]]] = [
        ("author.schema.json", read_json(ROOT / "schemas" / "author.schema.json")),
    ]
    schema_cases.extend(
        (f"generated:{name}.author.schema.json", author_schema_for_layers(layers))
        for name, layers in sorted(COMMON_LAYER_SETS.items())
    )

    for schema_name, schema in schema_cases:
        state_properties = schema["$defs"]["authored_state_machine_state"]["properties"]
        child_state_machines = state_properties["child_state_machines"]
        assert child_state_machines["type"] == "object", schema_name
        assert child_state_machines["propertyNames"]["$ref"] == "#/$defs/instance_id", schema_name
        assert child_state_machines["additionalProperties"]["$ref"] == "#/$defs/authored_child_state_machine", schema_name

        local_signal_sync_rules = state_properties["local_signal_sync_rules"]
        assert local_signal_sync_rules["type"] == "object", schema_name
        assert local_signal_sync_rules["propertyNames"]["$ref"] == "#/$defs/local_signal_sync_rule_id", schema_name
        assert local_signal_sync_rules["additionalProperties"]["$ref"] == "#/$defs/local_signal_sync_rule", schema_name

        activities = schema["$defs"]["authored_workflow"]["properties"]["activities"]
        assert activities["type"] == "object", schema_name
        assert activities["propertyNames"]["$ref"] == "#/$defs/workflow_activity_id", schema_name
        assert activities["additionalProperties"]["$ref"] == "#/$defs/workflow_activity", schema_name
        assert activities["minProperties"] == 1, schema_name

        for definition_name in ("authored_child_state_machine", "local_signal_sync_rule", "workflow_activity"):
            definition = schema["$defs"][definition_name]
            assert "id" not in definition["properties"], f"{schema_name} {definition_name}"
            assert "id" not in definition.get("required", []), f"{schema_name} {definition_name}"
