from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from pyspec_contract.compile import ROOT
from pyspec_contract.io import read_json


COLLECTION_SECTIONS = {
    "assets": "asset",
    "render_profiles": "render_profile",
    "operations": "operation",
    "content_cases": "content_case",
    "text_resources": "text_resource",
    "entry_points": "entry_point",
    "events": "event",
    "facts": "fact",
    "fixtures": "fixture",
    "state_machines": "state_machine",
    "models": "model",
    "scenarios": "scenario",
    "workflows": "workflow",
}


def _schema_paths() -> list[Path]:
    schemas = [ROOT / "schemas" / "author.schema.json"]
    schemas.extend(sorted((ROOT / "schemas" / "layers").glob("*.author.schema.json")))
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


@pytest.mark.parametrize("path", _schema_paths(), ids=lambda path: path.name)
def test_authored_schemas_only_use_authored_source_collection_defs(path: Path) -> None:
    schema = read_json(path)
    defs = schema["$defs"]
    legacy = sorted(name for name in defs if name.endswith(("_author", "_item", "_spec")))
    assert legacy == []

    refs = _definition_refs(schema)
    assert sorted(refs - set(defs)) == []

    for section, singular in COLLECTION_SECTIONS.items():
        if section in schema["properties"]:
            assert schema["properties"][section]["additionalProperties"]["$ref"] == f"#/$defs/authored_{singular}"


def test_compiled_schema_uses_item_defs_for_compiled_collections() -> None:
    schema = read_json(ROOT / "schemas" / "spec.schema.json")
    defs = schema["$defs"]
    legacy = sorted(name for name in defs if name.endswith(("_author", "_spec")))
    assert legacy == []
    assert sorted(name for name in defs if name in COLLECTION_SECTIONS.values()) == []

    refs = _definition_refs(schema)
    assert sorted(refs - set(defs)) == []

    for section, singular in COLLECTION_SECTIONS.items():
        assert schema["properties"][section]["additionalProperties"]["$ref"] == f"#/$defs/{singular}_item"
