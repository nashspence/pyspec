from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from pm_contract.compile import ContractError, compile_patch
from pm_contract.io import read_yaml, write_yaml
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




def test_yaml_writer_never_emits_anchors_or_aliases(tmp_path: Path) -> None:
    shared = {"confidence": "high", "kind": "explicit", "text": "shared basis"}
    path = tmp_path / "contract.yaml"
    write_yaml(path, {"first": shared, "second": shared})
    text = path.read_text(encoding="utf-8")
    assert "&id" not in text
    assert "*id" not in text
    assert text.count("shared basis") == 2


def test_checked_in_yaml_has_no_anchors_or_aliases() -> None:
    yaml_paths = [ROOT / "contract.yaml"] + sorted((ROOT / "generated").rglob("*.yaml"))
    offenders = []
    for path in yaml_paths:
        text = path.read_text(encoding="utf-8")
        if "&id" in text or "*id" in text:
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []



def test_validation_rejects_hand_edited_yaml_anchors(tmp_path: Path) -> None:
    project = tmp_path / "project"
    ignore = shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.pyc", "node_modules")
    shutil.copytree(ROOT, project, ignore=ignore)
    contract_path = project / "contract.yaml"
    text = contract_path.read_text(encoding="utf-8")
    contract_path.write_text(text.replace("status: draft", "status: &id001 draft", 1), encoding="utf-8")
    with pytest.raises(ContractError, match="Generated YAML must not contain anchors or aliases"):
        validate_project(project)

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


def _api_only_patch() -> dict:
    return {
        "version": 1,
        "project": "api_only",
        "status": "draft",
        "changes": [
            {
                "op": "add",
                "target": "resource",
                "id": "Ticket",
                "spec": {"kind": "aggregate", "fields": {"id": "ID", "title": "Text"}},
                "basis": _basis("ticket resource"),
            },
            {
                "op": "add",
                "target": "capability",
                "id": "ticket.create",
                "spec": {
                    "archetype": "create",
                    "resource": "Ticket",
                    "input": {"title": "Text"},
                    "output": "Ticket",
                },
                "basis": _basis("create ticket"),
            },
            {
                "op": "add",
                "target": "entry",
                "id": "api.ticket.create",
                "spec": {
                    "surface": "api",
                    "method": "POST",
                    "path": "/tickets",
                    "target": {"capability": "ticket.create"},
                },
                "basis": _basis("HTTP create ticket entry"),
            },
        ],
    }


def test_authoring_layers_allow_api_only_contract_and_graph_driven_projections() -> None:
    from pm_contract.layers import parse_layers
    from pm_contract.project import projection_paths

    contract = compile_patch(_api_only_patch(), layers=parse_layers("core,http"))
    paths = set(projection_paths(contract))
    assert "generated/openapi.yaml" in paths
    assert "generated/persistence.sql" not in paths
    assert "generated/persistence.json" not in paths
    assert "generated/panels.html" not in paths
    assert "generated/textual_contract.py" not in paths
    assert "generated/asyncapi.yaml" not in paths
    assert "generated/workflows.cwl.yaml" not in paths


def test_authoring_layers_reject_irrelevant_ui_targets() -> None:
    from pm_contract.layers import parse_layers

    patch = _api_only_patch()
    patch["changes"].append(
        {
            "op": "add",
            "target": "panel",
            "id": "panel.ticket.list",
            "spec": {
                "kind": "fsm",
                "resource": "Ticket",
                "context": {},
                "data": [],
                "events": [],
                "initial": "empty",
                "states": {"empty": {"pattern": "empty"}},
                "transitions": [],
            },
            "basis": _basis("UI panel is not part of this API layer"),
        }
    )
    with pytest.raises(ContractError, match="outside active authoring layers"):
        compile_patch(patch, layers=parse_layers("core,http"))


def test_authoring_layers_reject_wrong_entry_surface() -> None:
    from pm_contract.layers import parse_layers

    patch = _api_only_patch()
    for change in patch["changes"]:
        if change["target"] == "entry":
            change["id"] = "web.ticket.create"
            change["spec"] = {"surface": "web", "path": "/tickets", "target": {"view": "ticket.list"}}
            break
    with pytest.raises(ContractError, match="entry surface web requires web"):
        compile_patch(patch, layers=parse_layers("core,http"))


def test_layer_pruned_schema_hides_irrelevant_targets() -> None:
    from pm_contract.layers import parse_layers, schema_for_layers

    schema = schema_for_layers(parse_layers("core,http"))
    refs = [item["$ref"] for item in schema["properties"]["changes"]["items"]["oneOf"]]
    assert any(ref.endswith("add_entry") for ref in refs)
    assert any(ref.endswith("add_resource") for ref in refs)
    assert not any(ref.endswith("add_panel") for ref in refs)
    assert not any(ref.endswith("add_render_case") for ref in refs)


def test_pm_contract_rejects_scenario_harness_routing() -> None:
    patch = read_yaml(ROOT / "pm.patch.yaml")
    scenario = _first_spec(patch, "scenario")
    scenario["harnesses"] = ["spec", "prod"]
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_patch(patch)


def test_pm_contract_rejects_storage_implementation_details_on_resource() -> None:
    patch = read_yaml(ROOT / "pm.patch.yaml")
    resource = _first_spec(patch, "resource")
    resource["persistence"] = {"dialect": "sqlite", "table": "projects"}
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_patch(patch)


def test_generated_gherkin_is_single_corpus() -> None:
    features = ROOT / "generated" / "features"
    assert features.exists()
    assert not (features / "spec").exists()
    assert not (features / "prod").exists()
    assert sorted(path.name for path in features.glob("*.feature"))
