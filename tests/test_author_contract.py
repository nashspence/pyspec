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


def test_author_data_loaders_must_be_non_empty_when_present() -> None:
    author = copy.deepcopy(read_yaml(ROOT / SOURCE_SPEC_PATH))
    author["state_machines"]["state_machine.project.activity"]["data_loaders"] = {}
    with pytest.raises(ContractError, match="Schema validation failed"):
        validate_against_schema(author, "author.schema.json")

    author = copy.deepcopy(read_yaml(ROOT / SOURCE_SPEC_PATH))
    author["state_machines"]["state_machine.project.detail"]["view_states"]["loading"]["data_loaders"] = {}
    with pytest.raises(ContractError, match="Schema validation failed"):
        validate_against_schema(author, "author.schema.json")


def test_author_state_machine_context_uses_explicit_field_schema() -> None:
    author = copy.deepcopy(read_yaml(ROOT / SOURCE_SPEC_PATH))
    author["state_machines"]["state_machine.project.list"]["context"]["workspace_id"] = P("ID")
    with pytest.raises(ContractError, match="Schema validation failed"):
        validate_against_schema(author, "author.schema.json")

    author["state_machines"]["state_machine.project.list"]["context"]["workspace_id"] = F(P("ID"))
    validate_against_schema(author, "author.schema.json")


def test_author_query_result_binding_uses_data_key() -> None:
    author = copy.deepcopy(read_yaml(ROOT / SOURCE_SPEC_PATH))
    route = author["state_machines"]["state_machine.project.board"]["data_loaders"]["list_board"]["outcome_routes"]["listed"]
    route["result_binding"]["field"] = route["result_binding"].pop("data_key")
    with pytest.raises(ContractError, match="Schema validation failed"):
        validate_against_schema(author, "author.schema.json")

    author = copy.deepcopy(read_yaml(ROOT / SOURCE_SPEC_PATH))
    route = author["state_machines"]["state_machine.project.board"]["data_loaders"]["list_board"]["outcome_routes"]["listed"]
    route["result_binding"] = {"data_key": "projects", "from": {"from": "$outcome.result"}}
    validate_against_schema(author, "author.schema.json")


def test_author_query_conditional_routes_and_result_scope_validate() -> None:
    author = copy.deepcopy(read_yaml(ROOT / SOURCE_SPEC_PATH))
    invocation = author["state_machines"]["state_machine.project.list"]["data_loaders"]["list_projects"]
    assert invocation["result_scope"] == "local"
    route = invocation["outcome_routes"]["listed"]
    assert {next(iter(branch["when"])) for branch in route["conditional_routes"]} == {"result_empty", "result_non_empty"}
    validate_against_schema(author, "author.schema.json")

    route["conditional_routes"][0]["when"] = {"result_empty": False}
    with pytest.raises(ContractError, match="Schema validation failed"):
        validate_against_schema(author, "author.schema.json")


def test_author_value_maps_require_tagged_literals_or_runtime_sources() -> None:
    author = copy.deepcopy(read_yaml(ROOT / SOURCE_SPEC_PATH))
    body = author["test_cases"]["test_case.project.board.empty"]["when"]["open_entry_point"]
    body["input"]["workspace_id"] = "$fixture.workspace.id"
    with pytest.raises(ContractError, match="Schema validation failed"):
        validate_against_schema(author, "author.schema.json")

    body["input"]["workspace_id"] = {"from": "$fixture.workspace.id"}
    body["input"]["literal_dollar"] = {"value": "$literal"}
    validate_against_schema(author, "author.schema.json")


def test_author_no_signal_reasons_are_closed_vocabulary() -> None:
    author = copy.deepcopy(read_yaml(ROOT / SOURCE_SPEC_PATH))
    route = author["state_machines"]["state_machine.project.list"]["view_states"]["ready"]["action_bindings"]["create"]["outcome_routes"]["validation_failed"]
    route["no_signal"]["reason"] = "ignored"
    with pytest.raises(ContractError, match="Schema validation failed"):
        validate_against_schema(author, "author.schema.json")


def test_author_async_adapters_use_ingress_responses() -> None:
    author = copy.deepcopy(read_yaml(ROOT / SOURCE_SPEC_PATH))
    worker = author["entry_points"]["entry_point.worker.project.approval_notice"]["adapter"]["worker"]
    worker["responses"] = worker.pop("ingress_responses")
    with pytest.raises(ContractError, match="Schema validation failed"):
        validate_against_schema(author, "author.schema.json")


def test_author_contract_compiles_to_checked_in_machine_contract() -> None:
    author = read_yaml(ROOT / SOURCE_SPEC_PATH)
    assert compile_source(author) == read_yaml(ROOT / "spec" / "generated" / "compiled" / "spec.yaml")


def test_author_contract_can_be_minimal_and_renderer_invisible() -> None:
    author = {
        "project": "minimal_author",
        "models": {
            "Project": {
                "rationale": "Minimal product model for an API-free contract.",
                "fields": {"id": F(P("ID")), "title": F(P("Text"))},
            }
        },
    }
    contract = compile_source(author, layers={"core"})
    assert contract["models"]["Project"]["fields"]["title"] == F(P("Text"))
    assert contract["state_machines"] == {}
    assert contract["entry_points"] == {}
    assert contract["refs"] == {}


def test_author_contract_reuses_layer_guardrails() -> None:
    author = {
        "project": "blocked_author",
        "text_resources": {
            "text.project.empty.heading": {
                "rationale": "UI text is not part of a core-only source.",
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
