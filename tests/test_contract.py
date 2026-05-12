from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from pm_contract.compile import ContractError, compile_patch
from pm_contract.io import read_yaml
from pm_contract.validate import validate_project

ROOT = Path(__file__).resolve().parents[1]


def _basis(text: str = "test patch operation") -> dict[str, str]:
    return {"kind": "explicit", "confidence": "high", "text": text}


def _change(patch: dict, target: str, item_id: str | None = None) -> dict:
    for change in patch["changes"]:
        if change.get("target") == target and change.get("op") in {"add", "replace"}:
            if item_id is None or change.get("id") == item_id:
                return change
    raise AssertionError(f"missing {target} change {item_id or ''}")


def _first_spec(patch: dict, target: str) -> dict:
    return _change(patch, target)["spec"]


def test_project_validates() -> None:
    validate_project(ROOT)


def test_release_gate_blocks_starter_draft() -> None:
    with pytest.raises(ContractError, match="Release gate requires status: approved"):
        validate_project(ROOT, release=True)


def test_pm_patch_schema_rejects_unknown_fields() -> None:
    patch = read_yaml(ROOT / "pm.patch.yaml")
    patch["changes"][0]["invented_by_agent"] = True
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_patch(patch)


def test_generated_tree_is_closed(tmp_path: Path) -> None:
    project = tmp_path / "project"
    ignore = shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.pyc", "node_modules")
    shutil.copytree(ROOT, project, ignore=ignore)
    rogue = project / "generated" / "agent_invented.feature"
    rogue.write_text("Feature: Drift\n", encoding="utf-8")
    with pytest.raises(ContractError, match="Generated file set drift"):
        validate_project(project)


def test_unknown_fixture_is_rejected() -> None:
    patch = read_yaml(ROOT / "pm.patch.yaml")
    scenario = _first_spec(patch, "scenario")
    scenario["given"]["fixtures"] = ["fixture.workspace.ghost"]
    with pytest.raises(ContractError, match="unknown fixture"):
        compile_patch(patch)


def test_unresolved_fixture_reference_is_rejected() -> None:
    patch = read_yaml(ROOT / "pm.patch.yaml")
    scenario = _first_spec(patch, "scenario")
    _, body = next(iter(scenario["when"].items()))
    body.setdefault("params", {})["workspace_id"] = "$fixture.workspace.missing"
    with pytest.raises(ContractError, match="cannot resolve"):
        compile_patch(patch)


def test_prod_harness_cannot_import_spec_fake(tmp_path: Path) -> None:
    project = tmp_path / "project"
    ignore = shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.pyc", "node_modules")
    shutil.copytree(ROOT, project, ignore=ignore)
    prod_driver = project / "tests" / "prod_bdd" / "driver.py"
    prod_driver.write_text(
        "from pm_contract.reference_driver import ReferenceSpecDriver\n"
        "class ProdDriver(ReferenceSpecDriver):\n"
        "    pass\n",
        encoding="utf-8",
    )
    with pytest.raises(ContractError, match="Prod harness must be real/no-fake"):
        validate_project(project)


def test_presentation_rejects_undeclared_css_slot() -> None:
    patch = read_yaml(ROOT / "pm.patch.yaml")
    view = _change(patch, "view", "project.board")["spec"]
    view["layout"]["css"]["rules"].append({"selector": "slot.ghost", "declarations": {"display": "block"}})
    with pytest.raises(ContractError, match="undeclared layout slot"):
        compile_patch(patch)


def test_presentation_rejects_undeclared_textual_action() -> None:
    patch = read_yaml(ROOT / "pm.patch.yaml")
    state = _change(patch, "panel", "panel.project.list")["spec"]["states"]["ready"]
    state["presentation"] = {
        "textual": {
            "screen_class": "ProjectListState",
            "widgets": [{"id": "delete", "kind": "Button", "bind": {"action": "project.delete"}}],
        }
    }
    with pytest.raises(ContractError, match="action bind is not declared"):
        compile_patch(patch)


def _fixture_change(op: str, fixture_id: str, actor_id: str = "u1") -> dict[str, object]:
    return {
        "op": op,
        "target": "fixture",
        "id": fixture_id,
        "basis": _basis(f"{op} {fixture_id}"),
        "spec": {"values": {"actor": {"id": actor_id}}},
    }


def test_patch_operations_allow_add_replace_delete() -> None:
    patch = {
        "version": 1,
        "project": "patch_ops",
        "status": "draft",
        "changes": [
            _fixture_change("add", "fixture.actor", "u1"),
            _fixture_change("replace", "fixture.actor", "u2"),
            {"op": "delete", "target": "fixture", "id": "fixture.actor", "basis": _basis("delete fixture")},
            _fixture_change("add", "fixture.final", "u3"),
        ],
    }
    contract = compile_patch(patch)
    assert "fixture.actor" not in contract["fixtures"]
    assert contract["fixtures"]["fixture.final"]["values"]["actor"]["id"] == "u3"


def test_add_existing_item_is_rejected() -> None:
    patch = {"version": 1, "project": "patch_ops", "status": "draft", "changes": [_fixture_change("add", "fixture.actor", "u1"), _fixture_change("add", "fixture.actor", "u2")]}
    with pytest.raises(ContractError, match="Duplicate fixture"):
        compile_patch(patch)


def test_replace_missing_item_is_rejected() -> None:
    patch = {"version": 1, "project": "patch_ops", "status": "draft", "changes": [_fixture_change("replace", "fixture.missing", "u1")]}
    with pytest.raises(ContractError, match="replace missing fixture|Cannot replace missing fixture"):
        compile_patch(patch)


def test_delete_missing_item_is_rejected() -> None:
    patch = {"version": 1, "project": "patch_ops", "status": "draft", "changes": [{"op": "delete", "target": "fixture", "id": "fixture.missing", "basis": _basis()}]}
    with pytest.raises(ContractError, match="delete missing fixture"):
        compile_patch(patch)


def test_delete_with_remaining_references_is_rejected() -> None:
    patch = read_yaml(ROOT / "pm.patch.yaml")
    patch["changes"].append({"op": "delete", "target": "capability", "id": "project.create", "basis": _basis("delete referenced capability")})
    with pytest.raises(ContractError, match="unknown capability|action references"):
        compile_patch(patch)


def test_legacy_define_operations_are_schema_rejected() -> None:
    patch = {"version": 1, "project": "patch_ops", "status": "draft", "changes": [{"op": "define_fixture", "id": "fixture.actor", "values": {"actor": {"id": "u1"}}, "basis": _basis("legacy define operation")}]} 
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_patch(patch)


def test_nested_subject_mutations_are_schema_rejected() -> None:
    patch = {"version": 1, "project": "patch_ops", "status": "draft", "changes": [{"op": "add", "fixture": {"id": "fixture.actor", "values": {"actor": {"id": "u1"}}, "basis": _basis("nested old mutation shape")}}]}
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_patch(patch)


def test_composed_view_rejects_unknown_included_panel() -> None:
    patch = read_yaml(ROOT / "pm.patch.yaml")
    view = _change(patch, "view", "project.board")["spec"]
    view["includes"][0]["panel"] = "panel.project.ghost"
    with pytest.raises(ContractError, match="includes unknown panel"):
        compile_patch(patch)


def test_composed_view_rejects_unknown_sync_target_event() -> None:
    patch = read_yaml(ROOT / "pm.patch.yaml")
    view = _change(patch, "view", "project.board")["spec"]
    for effect in view["sync"][0]["do"]:
        if "send" in effect:
            effect["send"]["event"] = "project.ghost_event"
            break
    with pytest.raises(ContractError, match="sync sends undeclared target event"):
        compile_patch(patch)


def test_composed_scenario_rejects_unknown_panel_instance() -> None:
    patch = read_yaml(ROOT / "pm.patch.yaml")
    scenario = _change(patch, "scenario", "project.board.ready")["spec"]
    scenario["then"]["view"]["panels"]["ghost"] = {"state": "ready"}
    with pytest.raises(ContractError, match="unknown panel instance"):
        compile_patch(patch)
