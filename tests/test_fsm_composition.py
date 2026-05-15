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


def test_composed_fsm_contract_is_closed_and_projected() -> None:
    contract = compile_source(_author())
    list_fsm = contract["fsms"]["state_machine.project.list"]
    assert set(list_fsm) == {"model", "context", "data", "messages", "initial", "states", "transitions", "basis"}
    assert list_fsm["initial"] == "loading"
    assert list_fsm["data"] == [{"query": "query.project.list.list", "operation": "operation.project.list"}]
    assert list_fsm["states"]["ready"]["fields"] == ["title", "customer", "priority", "status"]
    detail_fsm = contract["fsms"]["state_machine.project.detail"]
    assert detail_fsm["data"] == []
    assert detail_fsm["states"]["loading"]["data"] == [{"query": "query.project.detail.read", "operation": "operation.project.read"}]
    assert contract["fsms"]["state_machine.project.activity"]["states"]["ready"]["data"] == [
        {"query": "query.project.activity.read", "operation": "operation.project.read"}
    ]

    fsm = contract["fsms"]["state_machine.project.board"]["states"]["ready"]
    assert set(fsm["layout"]["html"]["regions"]) == {"nav", "main", "aside"}
    assert set(fsm["layout"]["textual"]["containers"]) == {"nav", "main", "aside"}
    assert [(item["id"], item["fsm"], item["region"], item["initial"]) for item in fsm["mounts"]] == [
        ("list", "state_machine.project.list", "nav", "loading"),
        ("detail", "state_machine.project.detail", "main", "none"),
        ("activity", "state_machine.project.activity", "aside", "empty"),
    ]

    generated = read_json(ROOT / "spec" / "generated" / "product_interfaces" / "web.fsms.json")
    composition = next(item for item in generated["compositions"] if item["id"] == "state_machine.project.board.ready")
    assert composition["mounts"] == fsm["mounts"]
    assert composition["sync"] == fsm["sync"]


def test_fsm_composition_rejects_unknown_layout_region() -> None:
    author = _author()
    fsm = _item(author, "fsms", "state_machine.project.board")["states"]["ready"]
    fsm["mounts"][0]["region"] = "ghost"
    with pytest.raises(ContractError, match="undeclared region"):
        compile_source(author)


def test_fsm_composition_rejects_context_binding_drift() -> None:
    author = _author()
    fsm = _item(author, "fsms", "state_machine.project.board")["states"]["ready"]
    del fsm["mounts"][0]["context"]["selected_project_id"]
    with pytest.raises(ContractError, match="context keys"):
        compile_source(author)


def test_fsm_composition_rejects_sync_message_not_emitted_by_source_instance() -> None:
    author = _author()
    fsm = _item(author, "fsms", "state_machine.project.board")["states"]["ready"]
    fsm["sync"][0]["when"]["message"] = "message.project.unannounced"
    with pytest.raises(ContractError, match="sync listens for message the source does not emit"):
        compile_source(author)


def test_composed_scenario_rejects_unknown_fsm_state() -> None:
    author = _author()
    scenario = _item(author, "scenarios", "scenario.project.board.ready")
    scenario["then"]["fsm"]["instances"]["detail"]["state"] = "ghost"
    with pytest.raises(ContractError, match="unknown FSM state"):
        compile_source(author)
