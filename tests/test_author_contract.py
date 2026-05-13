from __future__ import annotations

import copy
from pathlib import Path

import pytest

from pm_contract.compile import ContractError, author_from_patch, compile_patch, compile_source, validate_against_schema
from pm_contract.io import read_yaml
from pm_contract.paths import SOURCE_CONTRACT_PATH

ROOT = Path(__file__).resolve().parents[1]


def test_author_contract_schema_validates() -> None:
    validate_against_schema(read_yaml(ROOT / SOURCE_CONTRACT_PATH), "author.schema.json")


def test_author_contract_compiles_to_same_machine_contract_as_patch() -> None:
    author = read_yaml(ROOT / SOURCE_CONTRACT_PATH)
    patch = read_yaml(ROOT / "pm.patch.yaml")
    assert compile_source(author) == compile_patch(patch)


def test_patch_operations_can_create_authored_contract() -> None:
    patch = read_yaml(ROOT / "pm.patch.yaml")
    assert author_from_patch(patch) == read_yaml(ROOT / SOURCE_CONTRACT_PATH)


def test_author_contract_can_be_minimal_and_surface_invisible() -> None:
    author = {
        "project": "minimal_author",
        "resources": {
            "Project": {
                "basis": "Minimal product resource for an API-free contract.",
                "kind": "aggregate",
                "fields": {"id": "ID", "title": "Text"},
            }
        },
    }
    contract = compile_source(author, layers={"core"})
    assert contract["resources"]["Project"]["fields"]["title"] == "Text"
    assert contract["panels"] == {}
    assert contract["views"] == {}
    assert contract["entries"] == {}
    assert contract["refs"] == {}


def test_author_contract_reuses_layer_guardrails() -> None:
    author = {
        "project": "blocked_author",
        "copies": {
            "copy.project.empty.heading": {
                "basis": "UI copy is not part of a core-only source.",
                "placeholder": "No projects",
            }
        },
    }
    with pytest.raises(ContractError, match="outside active authoring layers"):
        compile_source(author, layers={"core"})


def test_author_schema_rejects_meta_root_fields() -> None:
    author = copy.deepcopy(read_yaml(ROOT / SOURCE_CONTRACT_PATH))
    author["status"] = "draft"
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)
