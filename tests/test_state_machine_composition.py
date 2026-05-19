from __future__ import annotations

from pathlib import Path

import pytest

from pyspec_contract.compile import ContractError, compile_source
from pyspec_contract.io import read_json, read_yaml
from pyspec_contract.paths import SOURCE_SPEC_PATH
from tests.helpers import EXAMPLE_ROOT

ROOT = EXAMPLE_ROOT


def _author() -> dict:
    return read_yaml(ROOT / SOURCE_SPEC_PATH)


def _item(author: dict, section: str, item_id: str) -> dict:
    return author[section][item_id]


def test_composed_state_machine_contract_is_closed_and_projected() -> None:
    contract = compile_source(_author())
    list_state_machine = contract["state_machines"]["state_machine.project.list"]
    assert set(list_state_machine) == {"entity_type", "context_schema", "query_bindings", "local_signals", "initial_state", "states", "transitions", "rationale"}
    assert list_state_machine["initial_state"] == "loading"
    assert set(list_state_machine["query_bindings"]) == {"list_projects"}
    assert list_state_machine["query_bindings"]["list_projects"]["query"] == "query.project.list"
    assert list_state_machine["states"]["ready"]["fields"] == ["title", "customer", "priority", "status"]
    detail_state_machine = contract["state_machines"]["state_machine.project.detail"]
    assert detail_state_machine["query_bindings"] == {}
    assert detail_state_machine["states"]["loading"]["query_bindings"]["read_project"]["query"] == "query.project.read"
    assert contract["state_machines"]["state_machine.project.activity"]["states"]["ready"]["query_bindings"]["read_activity"]["query"] == "query.project.read"

    state_machine = contract["state_machines"]["state_machine.project.board"]["states"]["ready"]
    assert set(state_machine["renderers"]["html"]["layout"]["regions"]) == {"nav", "main", "aside"}
    assert set(state_machine["renderers"]["textual"]["layout"]["containers"]) == {"nav", "main", "aside"}
    assert [(item["id"], item["state_machine"], item["html_region"], item["textual_container"], item["initial_state"]) for item in state_machine["child_state_machines"]] == [
        ("list", "state_machine.project.list", "nav", "nav", "loading"),
        ("detail", "state_machine.project.detail", "main", "main", "none"),
        ("activity", "state_machine.project.activity", "aside", "aside", "empty"),
    ]

    generated = read_json(ROOT / "spec" / "generated" / "product_interfaces" / "html.state_machines.json")
    composition = next(item for item in generated["compositions"] if item["id"] == "state_machine.project.board.ready")
    assert composition["child_state_machines"] == state_machine["child_state_machines"]
    assert composition["local_signal_sync_rules"] == state_machine["local_signal_sync_rules"]


def test_state_machine_composition_rejects_unknown_html_region() -> None:
    author = _author()
    state_machine = _item(author, "state_machines", "state_machine.project.board")["states"]["ready"]
    state_machine["child_state_machines"]["list"]["html_region"] = "ghost"
    with pytest.raises(ContractError, match="undeclared HTML region"):
        compile_source(author)


def test_state_machine_composition_rejects_context_binding_drift() -> None:
    author = _author()
    state_machine = _item(author, "state_machines", "state_machine.project.board")["states"]["ready"]
    del state_machine["child_state_machines"]["list"]["context_bindings"]["workspace_id"]
    with pytest.raises(ContractError, match="context bindings must satisfy state machine context"):
        compile_source(author)


def test_state_machine_composition_rejects_sync_local_signal_not_emitted_by_source_instance() -> None:
    author = _author()
    state_machine = _item(author, "state_machines", "state_machine.project.board")["states"]["ready"]
    state_machine["local_signal_sync_rules"]["select_project_updates_state_machines"]["trigger"]["local_signal"] = "unannounced"
    with pytest.raises(ContractError, match="sync listens for signal the source does not emit"):
        compile_source(author)


def test_composed_behavior_scenario_rejects_unknown_state_machine_state() -> None:
    author = _author()
    behavior_scenario = _item(author, "behavior_scenarios", "behavior_scenario.project.board.ready")
    behavior_scenario["then"]["state_machine"]["instances"]["detail"]["state"] = "ghost"
    with pytest.raises(ContractError, match="unknown state machine state"):
        compile_source(author)
