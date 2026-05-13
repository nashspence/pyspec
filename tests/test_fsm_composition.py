from __future__ import annotations

from pathlib import Path

import pytest

from pm_contract.compile import ContractError, compile_patch
from pm_contract.io import read_json, read_yaml

ROOT = Path(__file__).resolve().parents[1]


def _patch() -> dict:
    return read_yaml(ROOT / "pm.patch.yaml")


def _change(patch: dict, target: str, item_id: str) -> dict:
    for change in patch["changes"]:
        if change.get("target") == target and change.get("id") == item_id:
            return change
    raise AssertionError(f"Missing {target} patch: {item_id}")


def test_composed_fsm_contract_is_closed_and_projected() -> None:
    contract = compile_patch(_patch())
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

    generated = read_json(ROOT / "generated" / "panels.json")
    composition = next(item for item in generated["compositions"] if item["id"] == "project.board")
    assert composition["instances"] == view["includes"]
    assert composition["sync"] == view["sync"]


def test_composed_view_rejects_unknown_layout_region() -> None:
    patch = _patch()
    view = _change(patch, "view", "project.board")["spec"]
    view["includes"][0]["region"] = "ghost"
    with pytest.raises(ContractError, match="undeclared region"):
        compile_patch(patch)


def test_composed_view_rejects_context_binding_drift() -> None:
    patch = _patch()
    view = _change(patch, "view", "project.board")["spec"]
    del view["includes"][0]["context"]["selected_project_id"]
    with pytest.raises(ContractError, match="context keys"):
        compile_patch(patch)


def test_composed_view_rejects_sync_event_not_emitted_by_source_panel() -> None:
    patch = _patch()
    view = _change(patch, "view", "project.board")["spec"]
    view["sync"][0]["when"]["emits"] = "project.unannounced"
    with pytest.raises(ContractError, match="undeclared panel event"):
        compile_patch(patch)


def test_composed_scenario_rejects_unknown_panel_state() -> None:
    patch = _patch()
    scenario = _change(patch, "scenario", "project.board.ready")["spec"]
    scenario["then"]["view"]["panels"]["detail"]["state"] = "ghost"
    with pytest.raises(ContractError, match="unknown panel state"):
        compile_patch(patch)
