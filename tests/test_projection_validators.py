from __future__ import annotations

import copy
import shutil
from pathlib import Path

import pytest

from pm_contract.compile import ContractError
from pm_contract.io import read_json, read_yaml
from pm_contract.projection_validators import (
    validate_asyncapi,
    validate_fixtures_and_scenarios,
    validate_openapi,
    validate_panels_json,
    validate_panel_css,
    validate_panels_html,
    validate_textual_contract,
    validate_workflows,
)

ROOT = Path(__file__).resolve().parents[1]


def _contract(root: Path = ROOT) -> dict:
    return read_yaml(root / "contract.yaml")


def test_openapi_validator_rejects_response_schema_drift() -> None:
    contract = _contract()
    openapi = read_yaml(ROOT / "generated" / "openapi.yaml")
    mutated = copy.deepcopy(openapi)
    op = mutated["paths"]["/workspaces/{workspace_id}/projects"]["post"]
    op["responses"]["200"]["content"]["application/json"]["schema"] = {"type": "string"}
    with pytest.raises(ContractError, match="response schema"):
        validate_openapi(contract, mutated)


def test_openapi_validator_rejects_unresolved_component_ref() -> None:
    contract = _contract()
    openapi = read_yaml(ROOT / "generated" / "openapi.yaml")
    mutated = copy.deepcopy(openapi)
    mutated["paths"]["/workspaces/{workspace_id}/projects"]["post"]["responses"]["200"]["content"]["application/json"]["schema"] = {"$ref": "#/components/schemas/Missing"}
    with pytest.raises(ContractError, match="response schema"):
        validate_openapi(contract, mutated)


def test_asyncapi_validator_rejects_wrong_channel_message_binding() -> None:
    contract = _contract()
    asyncapi = read_yaml(ROOT / "generated" / "asyncapi.yaml")
    mutated = copy.deepcopy(asyncapi)
    first_channel = next(value for value in mutated["channels"].values() if isinstance(value, dict) and "messages" in value)
    first_channel["messages"] = {"message_drift": {"$ref": "#/components/messages/message_drift"}}
    with pytest.raises(ContractError, match="message binding"):
        validate_asyncapi(contract, mutated)


def test_workflow_validator_rejects_unknown_cwl_step_target() -> None:
    contract = _contract()
    cwl = read_yaml(ROOT / "generated" / "workflows.cwl.yaml")
    mutated = copy.deepcopy(cwl)
    workflow = next(item for item in mutated["$graph"] if item["class"] == "Workflow")
    first_step = next(iter(workflow["steps"].values()))
    first_step["run"] = "#missing_tool"
    with pytest.raises(ContractError, match="unknown run"):
        validate_workflows(contract, mutated)


def test_html_validator_rejects_undeclared_copy_ref() -> None:
    contract = _contract()
    html = (ROOT / "generated" / "panels.html").read_text(encoding="utf-8")
    mutated = html.replace("copy.project.list.empty.heading", "copy.project.list.empty.subtitle", 1)
    with pytest.raises(ContractError, match="undeclared copy refs|missing copy slot"):
        validate_panels_html(contract, mutated)


def test_css_validator_rejects_unresolved_contract_token() -> None:
    contract = _contract()
    css = (ROOT / "generated" / "panel_styles.css").read_text(encoding="utf-8")
    mutated = css.replace("var(--gap)", "token.gap", 1)
    with pytest.raises(ContractError, match="unresolved"):
        validate_panel_css(contract, mutated)


def test_textual_validator_rejects_broken_generated_python(tmp_path: Path) -> None:
    project = tmp_path / "project"
    shutil.copytree(ROOT, project, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.pyc", "node_modules"))
    path = project / "generated" / "textual_contract.py"
    path.write_text(path.read_text(encoding="utf-8") + "\nthis is not python\n", encoding="utf-8")
    with pytest.raises(ContractError, match="not importable"):
        validate_textual_contract(project, _contract())


def test_scenario_validator_rejects_freeform_generated_gherkin(tmp_path: Path) -> None:
    project = tmp_path / "project"
    shutil.copytree(ROOT, project, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.pyc", "node_modules"))
    feature = next((project / "generated" / "features").glob("*.feature"))
    text = feature.read_text(encoding="utf-8")
    feature.write_text(text.replace("    Then ", "    And freeform agent prose\n    Then ", 1), encoding="utf-8")
    with pytest.raises(ContractError, match="non-canonical BDD conjunction|canonical When/Then"):
        validate_fixtures_and_scenarios(project, _contract())


def test_panels_json_validator_rejects_missing_composition() -> None:
    contract = _contract()
    panels = read_json(ROOT / "generated" / "panels.json")
    mutated = copy.deepcopy(panels)
    mutated["compositions"] = []
    with pytest.raises(ContractError, match="panels.json"):
        validate_panels_json(contract, mutated)


def test_html_validator_rejects_wrong_composed_panel_instance() -> None:
    contract = _contract()
    html = (ROOT / "generated" / "panels.html").read_text(encoding="utf-8")
    mutated = html.replace('data-panel-source="panel.project.list"', 'data-panel-source="panel.project.ghost"', 1)
    with pytest.raises(ContractError, match="wrong source/initial"):
        validate_panels_html(contract, mutated)
