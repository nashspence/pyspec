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
    list_panel = contract["panels"]["panel.project.list"]
    assert set(list_panel) == {"resource", "context", "data", "events", "initial", "states", "transitions", "basis"}
    assert list_panel["initial"] == "loading"
    assert list_panel["data"] == [{"query": "query.project.list.list", "capability": "project.list"}]
    assert list_panel["states"]["ready"]["fields"] == ["title", "customer", "priority", "status"]
    detail_panel = contract["panels"]["panel.project.detail"]
    assert detail_panel["data"] == []
    assert detail_panel["states"]["loading"]["data"] == [{"query": "query.project.detail.read", "capability": "project.read"}]
    assert contract["panels"]["panel.project.activity"]["states"]["ready"]["data"] == [
        {"query": "query.project.activity.read", "capability": "project.read"}
    ]

    view = contract["views"]["project.board"]
    assert set(view["layout"]["html"]["regions"]) == {"nav", "main", "aside"}
    assert set(view["layout"]["textual"]["containers"]) == {"nav", "main", "aside"}
    assert [(item["id"], item["panel"], item["region"], item["initial"]) for item in view["includes"]] == [
        ("list", "panel.project.list", "nav", "loading"),
        ("detail", "panel.project.detail", "main", "none"),
        ("activity", "panel.project.activity", "aside", "empty"),
    ]

    generated = read_json(ROOT / "spec" / "generated" / "panels.json")
    composition = next(item for item in generated["compositions"] if item["id"] == "project.board")
    assert composition["instances"] == view["includes"]
    assert composition["sync"] == view["sync"]


def test_composed_view_rejects_unknown_layout_region() -> None:
    author = _author()
    view = _item(author, "views", "project.board")
    view["includes"][0]["region"] = "ghost"
    with pytest.raises(ContractError, match="undeclared region"):
        compile_source(author)


def test_composed_view_rejects_context_binding_drift() -> None:
    author = _author()
    view = _item(author, "views", "project.board")
    del view["includes"][0]["context"]["selected_project_id"]
    with pytest.raises(ContractError, match="context keys"):
        compile_source(author)


def test_composed_view_rejects_sync_event_not_emitted_by_source_panel() -> None:
    author = _author()
    view = _item(author, "views", "project.board")
    view["sync"][0]["when"]["emits"] = "project.unannounced"
    with pytest.raises(ContractError, match="undeclared panel event"):
        compile_source(author)


def test_composed_scenario_rejects_unknown_panel_state() -> None:
    author = _author()
    scenario = _item(author, "scenarios", "project.board.ready")
    scenario["then"]["view"]["panels"]["detail"]["state"] = "ghost"
    with pytest.raises(ContractError, match="unknown panel state"):
        compile_source(author)
