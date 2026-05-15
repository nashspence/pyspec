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
    "operation",
    "entry",
    "event",
    "fixture",
    "fsm",
    "model",
    "scenario",
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
    "model_id",
    "type_map",
    "type_name",
    "audit_profile_item",
    "textual_viewport",
}
DEPRECATED_TOP_LEVEL_PROPERTIES = {
    "audit_profiles",
    "copies",
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


def test_spec_ontology_rejects_deprecated_reference_terminology() -> None:
    text = DOC_PATH.read_text(encoding="utf-8")
    deprecated_terms = sorted(
        term
        for term in DEPRECATED_REFERENCE_DEFINITION_NAMES | DEPRECATED_TOP_LEVEL_PROPERTIES | {"capability", "capabilities", "fsm", "fsms"}
        if term in text
    )
    assert deprecated_terms == []
