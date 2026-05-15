from __future__ import annotations

import copy
from pathlib import Path

import pytest

from pyspec_contract.compile import ContractError, compile_source, validate_against_schema
from pyspec_contract.io import read_yaml
from pyspec_contract.paths import SOURCE_SPEC_PATH
from tests.helpers import EXAMPLE_ROOT

ROOT = EXAMPLE_ROOT


def P(name: str) -> dict[str, str]:
    return {"primitive": name}


def F(type_expr: dict, *, required: bool = True, nullable: bool = False) -> dict:
    return {"type": type_expr, "required": required, "nullable": nullable}


def test_author_contract_schema_validates() -> None:
    validate_against_schema(read_yaml(ROOT / SOURCE_SPEC_PATH), "author.schema.json")


def test_author_contract_compiles_to_checked_in_machine_contract() -> None:
    author = read_yaml(ROOT / SOURCE_SPEC_PATH)
    assert compile_source(author) == read_yaml(ROOT / "spec" / "generated" / "compiled" / "spec.yaml")


def test_author_contract_can_be_minimal_and_surface_invisible() -> None:
    author = {
        "project": "minimal_author",
        "models": {
            "Project": {
                "basis": "Minimal product model for an API-free contract.",
                "fields": {"id": F(P("ID")), "title": F(P("Text"))},
            }
        },
    }
    contract = compile_source(author, layers={"core"})
    assert contract["models"]["Project"]["fields"]["title"] == F(P("Text"))
    assert contract["fsms"] == {}
    assert contract["entries"] == {}
    assert contract["refs"] == {}


def test_author_contract_reuses_layer_guardrails() -> None:
    author = {
        "project": "blocked_author",
        "copies": {
            "text.project.empty.heading": {
                "basis": "UI copy is not part of a core-only source.",
                "placeholder": "No projects",
            }
        },
    }
    with pytest.raises(ContractError, match="outside active authoring layers"):
        compile_source(author, layers={"core"})


def test_author_schema_rejects_meta_root_fields() -> None:
    author = copy.deepcopy(read_yaml(ROOT / SOURCE_SPEC_PATH))
    author["status"] = "draft"
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)
