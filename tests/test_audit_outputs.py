from __future__ import annotations
from pathlib import Path

import pytest

from pm_contract.audit import _render_graphviz_svg, audit_expected_files, composition_dot, panel_fsm_dot
from pm_contract.compile import ContractError, compile_patch
from pm_contract.io import read_yaml
from pm_contract.paths import COMPILED_CONTRACT_PATH
from pm_contract.projection_validators import validate_audit_outputs
from tests.helpers import copy_project_tree

ROOT = Path(__file__).resolve().parents[1]
PNG_HEADER = bytes([137, 80, 78, 71, 13, 10, 26, 10])


def _contract(root: Path = ROOT) -> dict:
    return read_yaml(root / COMPILED_CONTRACT_PATH)


def _first_change(patch: dict, target: str) -> dict:
    for change in patch["changes"]:
        if change.get("target") == target and change["op"] in {"add", "replace"}:
            return change
    raise AssertionError(f"missing {target} change")


def test_audit_outputs_cover_full_contract() -> None:
    contract = _contract()
    expected = audit_expected_files(contract)
    assert "generated/audit/copy.yaml" in expected
    assert any(path.startswith("generated/audit/fsm/") and path.endswith(".svg") for path in expected)
    assert any(path.startswith("generated/audit/composition/") and path.endswith(".svg") for path in expected)
    assert any(path.startswith("generated/audit/html/panels/") and path.endswith(".png") for path in expected)
    assert any(path.startswith("generated/audit/html/views/") and path.endswith(".html") for path in expected)
    assert any(path.startswith("generated/audit/textual/views/") and path.endswith(".svg") for path in expected)
    validate_audit_outputs(ROOT, contract)


def test_audit_flowcharts_use_graphviz_dot_sources() -> None:
    contract = _contract()
    fsm = panel_fsm_dot("panel.project.list", contract["panels"]["panel.project.list"], contract)
    composition = composition_dot("project.board", contract["views"]["project.board"])
    assert fsm.startswith("digraph ")
    assert composition.startswith("digraph ")
    assert "stateDiagram" not in fsm
    assert "flowchart" not in composition
    assert "on data.ready" in fsm
    assert "copy.project.list.ready.heading" in fsm
    assert "asset.project.list.empty.illustration" in fsm
    assert "emit project.selected" in fsm
    assert "<B>data:</B>&#160;&#160;project.list" in fsm
    assert "<B>query:</B>&#160;&#160;query.project.list.list" in fsm
    assert "<B>input:</B>&#160;&#160;workspace_id: ID" in fsm
    assert "<B>Project fields</B>" in fsm
    assert fsm.count("query.project.list.list") == 4
    assert "<B>resource:</B>" not in fsm
    assert "<B>context:</B>" not in fsm
    assert "selected state: loading" in composition
    assert "send project.selection_changed to detail" in composition
    for graph_id, dot_source in {"panel_project_list": fsm, "project_board": composition}.items():
        svg = _render_graphviz_svg(dot_source, graph_id)
        assert svg.lstrip().startswith("<svg")
        assert "</svg>" in svg


def test_generated_flowchart_svgs_include_contract_audit_details() -> None:
    list_fsm = (ROOT / "generated" / "audit" / "fsm" / "panel_project_list.svg").read_text(encoding="utf-8")
    detail_fsm = (ROOT / "generated" / "audit" / "fsm" / "panel_project_detail.svg").read_text(encoding="utf-8")
    activity_fsm = (ROOT / "generated" / "audit" / "fsm" / "panel_project_activity.svg").read_text(encoding="utf-8")
    composition = (ROOT / "generated" / "audit" / "composition" / "project_board.svg").read_text(encoding="utf-8")
    assert "on data.ready" in list_fsm
    assert "copy.project.list.ready.heading" in list_fsm
    assert "asset.project.list.empty.illustration" in list_fsm
    assert "emit project.selected" in list_fsm
    assert "capability: project.list" not in list_fsm
    assert "query.project.list.list" in list_fsm
    assert "workspace_id: ID" in list_fsm
    assert "Project fields" in list_fsm
    assert "resource:" not in list_fsm
    assert "context:" not in list_fsm
    assert "&#45; data.ready" not in list_fsm
    assert "&#45; copy.project" not in list_fsm
    assert "&#45; none" not in list_fsm
    assert ">basis<" not in list_fsm
    assert "loading &#45;&gt; empty" not in list_fsm
    assert "(initial)" not in list_fsm
    assert "initial:" not in list_fsm
    assert "FSM panel" not in list_fsm
    assert "declared, no arrow" not in list_fsm
    assert "transition events" not in list_fsm
    assert "emitted events" not in list_fsm
    assert "panel.project.detail.ready" in detail_fsm
    assert "project.approve" in detail_fsm
    assert "query.project.detail.read" in detail_fsm
    assert "project_id: ID" in detail_fsm
    assert "capability: project.read" not in detail_fsm
    assert "data.ready" not in activity_fsm
    assert "selected state: loading" in composition
    assert "send project.selection_changed to detail" in composition


def test_audit_html_sources_render_copy_assets_and_fixture_fields() -> None:
    ready = ROOT / "generated" / "audit" / "html" / "views" / "project_board" / "default.wide.project_board_ready_selected_audit.html"
    text = ready.read_text(encoding="utf-8")
    assert "Dispatch queue" in text
    assert "Replace rooftop condenser fan · Atlas Foods" in text
    assert "Latest activity" in text
    assert "High priority" in text
    assert "Replace rooftop condenser fan" in text
    assert "Atlas Foods" in text
    assert "fixture.projects.audit_records" not in text
    assert "data-audit" not in text

    empty = ROOT / "generated" / "audit" / "html" / "views" / "project_board" / "default.compact.project_board_empty_audit.html"
    empty_text = empty.read_text(encoding="utf-8")
    assert "No dispatch projects yet" in empty_text
    assert "asset.project.list.empty.illustration" in empty_text
    assert "data:image/svg+xml;base64" in empty_text


def test_audit_asset_placeholder_is_generic_and_not_named() -> None:
    asset = ROOT / "generated" / "audit" / "assets" / "asset_project_list_empty_illustration.svg"
    text = asset.read_text(encoding="utf-8")
    assert text.lstrip().startswith("<svg")
    assert "asset.project.list.empty.illustration" not in text
    assert "<text" not in text
    assert "Empty dispatch queue illustration" in text


def test_audit_pngs_are_real_pngs() -> None:
    contract = _contract()
    pngs = [ROOT / path for path in audit_expected_files(contract) if path.endswith(".png")]
    assert pngs
    for path in pngs:
        assert path.read_bytes().startswith(PNG_HEADER), path


def test_copy_placeholder_is_required_for_used_copy_ref() -> None:
    patch = read_yaml(ROOT / "pm.patch.yaml")
    change = _first_change(patch, "copy")
    patch["changes"].remove(change)
    with pytest.raises(ContractError, match="copy placeholders drift"):
        compile_patch(patch)


def test_asset_placeholder_schema_rejects_missing_visual_intent() -> None:
    patch = read_yaml(ROOT / "pm.patch.yaml")
    change = _first_change(patch, "asset")
    del change["spec"]["placeholder"]
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_patch(patch)


def test_render_case_coverage_is_required() -> None:
    patch = read_yaml(ROOT / "pm.patch.yaml")
    patch["changes"] = [change for change in patch["changes"] if change.get("target") != "render_case"]
    with pytest.raises(ContractError, match="At least one render_case|Missing render_case coverage"):
        compile_patch(patch)


def test_audit_validator_rejects_corrupt_html_png(tmp_path: Path) -> None:
    project = tmp_path / "project"
    copy_project_tree(ROOT, project)
    contract = read_yaml(project / COMPILED_CONTRACT_PATH)
    png = next(project / path for path in audit_expected_files(contract) if path.endswith(".png"))
    png.write_bytes(b"not-a-png")
    with pytest.raises(ContractError, match="not PNG"):
        validate_audit_outputs(project, contract)


def test_audit_validator_rejects_missing_fsm_svg(tmp_path: Path) -> None:
    project = tmp_path / "project"
    copy_project_tree(ROOT, project)
    contract = read_yaml(project / COMPILED_CONTRACT_PATH)
    svg = next(project / path for path in audit_expected_files(contract) if "/fsm/" in path)
    svg.unlink()
    with pytest.raises(ContractError, match="audit generated files"):
        validate_audit_outputs(project, contract)
