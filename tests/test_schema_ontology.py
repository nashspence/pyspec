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
