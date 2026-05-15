from __future__ import annotations

import copy
from pathlib import Path

import pytest

from pyspec_contract.compile import ContractError
from pyspec_contract.io import read_json, read_yaml
from pyspec_contract.paths import COMPILED_SPEC_PATH
from pyspec_contract.projection_validators import (
    validate_asyncapi,
    validate_fixtures_and_scenarios,
    validate_openapi,
    validate_fsms_json,
    validate_textual_contract,
    validate_workflows,
)
from tests.helpers import EXAMPLE_ROOT, copy_project_tree

ROOT = EXAMPLE_ROOT


def _contract(root: Path = ROOT) -> dict:
    return read_yaml(root / COMPILED_SPEC_PATH)


def test_openapi_validator_rejects_response_schema_drift() -> None:
    contract = _contract()
    openapi = read_yaml(ROOT / "spec" / "generated" / "product_interfaces" / "http.openapi.yaml")
    mutated = copy.deepcopy(openapi)
    op = mutated["paths"]["/workspaces/{workspace_id}/projects"]["post"]
    op["responses"]["201"]["content"]["application/json"]["schema"] = {"type": "string"}
    with pytest.raises(ContractError, match="response schema"):
        validate_openapi(contract, mutated)


def test_openapi_validator_rejects_unresolved_component_ref() -> None:
    contract = _contract()
    openapi = read_yaml(ROOT / "spec" / "generated" / "product_interfaces" / "http.openapi.yaml")
    mutated = copy.deepcopy(openapi)
    mutated["paths"]["/workspaces/{workspace_id}/projects"]["post"]["responses"]["201"]["content"]["application/json"]["schema"] = {"$ref": "#/components/schemas/Missing"}
    with pytest.raises(ContractError, match="response schema"):
        validate_openapi(contract, mutated)


def test_asyncapi_validator_rejects_wrong_channel_message_binding() -> None:
    contract = _contract()
    asyncapi = read_yaml(ROOT / "spec" / "generated" / "product_interfaces" / "events.asyncapi.yaml")
    mutated = copy.deepcopy(asyncapi)
    first_channel = next(value for value in mutated["channels"].values() if isinstance(value, dict) and "messages" in value)
    first_channel["messages"] = {"message_drift": {"$ref": "#/components/messages/message_drift"}}
    with pytest.raises(ContractError, match="message binding"):
        validate_asyncapi(contract, mutated)


def test_workflow_validator_rejects_unknown_cwl_step_target() -> None:
    contract = _contract()
    cwl = read_yaml(ROOT / "spec" / "generated" / "product_interfaces" / "workflow.cwl.yaml")
    mutated = copy.deepcopy(cwl)
    workflow = next(item for item in mutated["$graph"] if item["class"] == "Workflow")
    first_step = next(iter(workflow["steps"].values()))
    first_step["run"] = "#missing_tool"
    with pytest.raises(ContractError, match="unknown run"):
        validate_workflows(contract, mutated)


def test_textual_validator_rejects_broken_generated_python(tmp_path: Path) -> None:
    project = tmp_path / "project"
    copy_project_tree(ROOT, project)
    path = project / "spec" / "generated" / "product_interfaces" / "textual.projection.py"
    path.write_text(path.read_text(encoding="utf-8") + "\nthis is not python\n", encoding="utf-8")
    with pytest.raises(ContractError, match="not importable"):
        validate_textual_contract(project, _contract())


def test_scenario_validator_rejects_freeform_generated_gherkin(tmp_path: Path) -> None:
    project = tmp_path / "project"
    copy_project_tree(ROOT, project)
    feature = next((project / "spec" / "generated" / "test_adapters" / "pytest_bdd_features").glob("*.feature"))
    text = feature.read_text(encoding="utf-8")
    feature.write_text(text.replace("    Then ", "    And freeform agent prose\n    Then ", 1), encoding="utf-8")
    with pytest.raises(ContractError, match="non-canonical BDD conjunction|canonical When/Then"):
        validate_fixtures_and_scenarios(project, _contract())


def test_fsms_json_validator_rejects_missing_composition() -> None:
    contract = _contract()
    fsms = read_json(ROOT / "spec" / "generated" / "product_interfaces" / "web.fsms.json")
    mutated = copy.deepcopy(fsms)
    mutated["compositions"] = []
    with pytest.raises(ContractError, match="fsms.json"):
        validate_fsms_json(contract, mutated)
