from __future__ import annotations
from pathlib import Path

import pytest

from pyspec_contract.audit import _render_graphviz_svg, audit_expected_files, composition_dot, composition_file, panel_fsm_dot, panel_fsm_file, panel_state_root, render_case_file
from pyspec_contract.compile import ContractError, compile_source
from pyspec_contract.io import read_yaml
from pyspec_contract.paths import COMPILED_SPEC_PATH, SOURCE_SPEC_PATH
from pyspec_contract.projection_validators import validate_audit_outputs
from tests.helpers import EXAMPLE_ROOT, copy_project_tree

ROOT = EXAMPLE_ROOT
PNG_HEADER = bytes([137, 80, 78, 71, 13, 10, 26, 10])


def _contract(root: Path = ROOT) -> dict:
    return read_yaml(root / COMPILED_SPEC_PATH)


def test_audit_outputs_cover_full_contract() -> None:
    contract = _contract()
    expected = audit_expected_files(contract)
    assert "spec/generated/audit_evidence/panels/panel_project_list/fsm.svg" in expected
    assert "spec/generated/audit_evidence/composed_views/project_board/composition.svg" in expected
    assert any(path.startswith("spec/generated/audit_evidence/panels/") and "/states/" in path and path.endswith("/copy.yaml") for path in expected)
    assert any(path.startswith("spec/generated/audit_evidence/panels/") and "/states/" in path and "/renders/" in path and path.endswith(".png") for path in expected)
    assert any(path.startswith("spec/generated/audit_evidence/composed_views/") and "/cases/" in path and "/renders/" in path and path.endswith(".html") for path in expected)
    assert any(path.startswith("spec/generated/audit_evidence/composed_views/") and "/cases/" in path and "/renders/" in path and path.endswith(".svg") for path in expected)
    assert render_case_file("project.board", "project.board.ready_selected.audit", "default", "wide", "html").endswith("/renders/html.default.wide.source.html")
    assert render_case_file("project.board", "project.board.ready_selected.audit", "default", "wide", "png").endswith("/renders/html.default.wide.screenshot.png")
    assert render_case_file("project.board", "project.board.ready_selected.audit", "default", "wide", "py").endswith("/renders/textual.default.wide.source.py")
    assert render_case_file("project.board", "project.board.ready_selected.audit", "default", "wide", "svg").endswith("/renders/textual.default.wide.capture.svg")
    validate_audit_outputs(ROOT, contract)


def test_audit_flowcharts_use_graphviz_dot_sources() -> None:
    contract = _contract()
    fsm = panel_fsm_dot("panel.project.list", contract["panels"]["panel.project.list"], contract)
    composition = composition_dot("project.board", contract["views"]["project.board"], contract)
    assert fsm.startswith("digraph ")
    assert composition.startswith("digraph ")
    assert "stateDiagram" not in fsm
    assert "flowchart" not in composition
    assert "on data.ready" in fsm
    assert "copy.project.list.ready.heading" in fsm
    assert "asset.project.list.empty.illustration" in fsm
    assert "emit project.selected" in fsm
    assert "<B>projection:</B>" not in fsm
    assert "<B>load:</B>&#160;&#160;project.list" in fsm
    assert "<B>query:</B>&#160;&#160;query.project.list.list" in fsm
    assert "<B>input:</B>&#160;&#160;workspace_id: ID" in fsm
    assert fsm.index("<B>input:</B>&#160;&#160;workspace_id: ID") < fsm.index("<B>query:</B>&#160;&#160;query.project.list.list")
    assert fsm.index("<B>query:</B>&#160;&#160;query.project.list.list") < fsm.index("<B>load:</B>&#160;&#160;project.list")
    detail_transition = panel_fsm_dot("panel.project.detail", contract["panels"]["panel.project.detail"], contract)
    selection_card = detail_transition[detail_transition.index("on project.selection_changed") :]
    assert selection_card.index("<B>input:</B>&#160;&#160;project_id: ID") < selection_card.index("<B>query:</B>&#160;&#160;query.project.detail.read")
    assert selection_card.index("<B>query:</B>&#160;&#160;query.project.detail.read") < selection_card.index("<B>load:</B>&#160;&#160;project.read")
    assert "<B>Project fields</B>" in fsm
    assert fsm.count("query.project.list.list") == 4
    assert "<B>resource:</B>" not in fsm
    assert "<B>context:</B>" not in fsm
    assert "$event." not in fsm
    assert "emitted message" in composition
    assert "sent message" in composition
    assert "message route" in composition
    assert "project.select (ready to ready)" in composition
    assert "selected state:" not in composition
    assert "<B>data:</B>&#160;&#160;project_id" in composition
    assert "selected_project_id &lt;- project_id" in composition
    assert "$event." not in composition
    assert "$view." not in composition
    assert "<B>from:</B>" not in composition
    assert "<B>do:</B>" not in composition
    assert "Layout / mounted panels" not in composition
    assert "Message routing" not in composition
    assert "Sync rules" not in composition
    assert "<B>region:</B>" in composition
    assert "<B>region:</B>&#160;&#160;nav" in composition
    assert "<B>region:</B>&#160;&#160;main" in composition
    assert "<B>causes:</B>&#160;&#160;to loading" in composition
    assert "context binding" in composition
    assert "panel context" not in composition
    assert "order:" not in composition
    assert "element:" not in composition
    assert "role:" not in composition
    assert "required:" not in composition
    assert "layout_region_nav" not in composition
    assert "fontcolor" not in composition
    for graph_id, dot_source in {"panel_project_list": fsm, "project_board": composition}.items():
        svg = _render_graphviz_svg(dot_source, graph_id)
        assert svg.lstrip().startswith("<svg")
        assert "</svg>" in svg


def test_composition_dot_routes_messages_generically() -> None:
    view = {
        "archetype": "workspace",
        "resource": "generic.resource",
        "context": {"selected_id": "ID", "workspace_id": "ID"},
        "data": [],
        "layout": {
            "html": {
                "regions": {
                    "target": {"order": 10, "element": "aside", "role": "complementary"},
                    "source": {"order": 20, "element": "main", "role": "main", "required": True},
                    "unused": {"order": 30, "element": "footer", "role": "contentinfo"},
                }
            }
        },
        "includes": [
            {"id": "publisher", "region": "source", "panel": "panel.alpha", "initial": "idle", "context": {}},
            {"id": "receiver", "region": "target", "panel": "panel.beta", "initial": "waiting", "context": {"item_id": "$view.selected_id"}},
        ],
        "sync": [
            {
                "id": "route_alpha_beta",
                "when": {"panel": "publisher", "emits": "alpha.ready"},
                "do": [
                    {"send": {"panel": "receiver", "event": "beta.consume", "data": {"item_id": "$event.id"}}},
                    {"set": {"context": "selected_id", "from": "$event.id"}},
                ],
            }
        ],
    }
    contract = {
        "panels": {
            "panel.alpha": {
                "events": {
                    "alpha.ready": {"payload": {"id": "ID"}},
                    "alpha.submit": {"payload": {"id": "ID"}},
                },
                "transitions": [
                    {
                        "event": "alpha.submit",
                        "from": "idle",
                        "to": "ready",
                        "effects": [{"emit": {"event": "alpha.ready", "data": {"id": "$event.id"}}}],
                    }
                ]
            },
            "panel.beta": {
                "events": {
                    "beta.consume": {"payload": {"item_id": "ID"}},
                },
                "transitions": [
                    {
                        "event": "beta.consume",
                        "from": "waiting",
                        "to": "consumed",
                    }
                ]
            }
        }
    }

    composition = composition_dot("generic.view", view, contract)

    assert "emitted message" in composition
    assert "sent message" in composition
    assert "message route" in composition
    assert "alpha.submit (idle to ready)" in composition
    assert "beta.consume" in composition
    assert "<B>causes:</B>&#160;&#160;to consumed" in composition
    assert "<B>data:</B>&#160;&#160;id" in composition
    assert "selected_id &lt;- id" in composition
    assert "item_id &lt;- id" in composition
    assert "item_id &lt;- view.selected_id" in composition
    assert "$event." not in composition
    assert "$view." not in composition
    assert "<B>target:</B>" not in composition
    assert "<B>from:</B>" not in composition
    assert "<B>do:</B>" not in composition
    assert '"message_effect_route_alpha_beta_0" -> "panel_instance_receiver"' in composition
    assert '#fff7ed' in composition
    assert '#fdf2f8' in composition
    assert "No mounted panels" not in composition
    assert "<B>region:</B>&#160;&#160;source" in composition
    assert "<B>region:</B>&#160;&#160;target" in composition
    assert "unused" not in composition
    assert "order:" not in composition
    assert "element:" not in composition
    assert "role:" not in composition
    assert "required:" not in composition
    assert "layout_instance" not in composition
    assert "layout_region_empty" not in composition
    assert "project.board" not in composition
    assert "panel.project" not in composition
    svg = _render_graphviz_svg(composition, "generic_composition")
    assert svg.lstrip().startswith("<svg")


def test_audit_transition_basis_renders_for_otherwise_sparse_card() -> None:
    author = read_yaml(ROOT / SOURCE_SPEC_PATH)
    activity = author["panels"]["panel.project.activity"]
    cleared = next(transition for transition in activity["transitions"] if transition["event"] == "selection.cleared")
    cleared.pop("effects")
    cleared["basis"] = "Clearing the selection returns the activity panel to its empty state."
    contract = compile_source(author)

    fsm = panel_fsm_dot("panel.project.activity", contract["panels"]["panel.project.activity"], contract)

    assert "Clearing the selection returns the activity panel" in fsm
    assert "to its empty state." in fsm


def test_generated_flowchart_svgs_include_contract_audit_details() -> None:
    list_fsm = (ROOT / panel_fsm_file("panel.project.list")).read_text(encoding="utf-8")
    detail_fsm = (ROOT / panel_fsm_file("panel.project.detail")).read_text(encoding="utf-8")
    activity_fsm = (ROOT / panel_fsm_file("panel.project.activity")).read_text(encoding="utf-8")
    composition = (ROOT / composition_file("project.board")).read_text(encoding="utf-8")
    assert "on data.ready" in list_fsm
    assert "copy.project.list.ready.heading" in list_fsm
    assert "asset.project.list.empty.illustration" in list_fsm
    assert "emit project.selected" in list_fsm
    assert "capability: project.list" not in list_fsm
    assert "query.project.list.list" in list_fsm
    assert "workspace_id: ID" in list_fsm
    assert "Project fields" in list_fsm
    assert "projection:" not in list_fsm
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
    assert "$event." not in list_fsm
    assert "copy.project.detail.ready.heading" in detail_fsm
    assert "project.approve" in detail_fsm
    assert "input:" in detail_fsm
    assert "query.project.detail.read" in detail_fsm
    assert "project_id: ID" in detail_fsm
    assert "capability: project.read" not in detail_fsm
    assert "project_id &lt;&#45; null" in detail_fsm
    assert "select_project_updates_panels" not in detail_fsm
    assert "data.ready" not in activity_fsm
    assert "input:" in activity_fsm
    assert "query.project.activity.read" in activity_fsm
    assert "project_id: ID" in activity_fsm
    assert "project_id &lt;&#45; null" in activity_fsm
    assert "emitted message" in composition
    assert "sent message" in composition
    assert "project.select" in composition
    assert "project.selection_changed" in composition
    assert "to loading" in composition
    assert "to ready" in composition
    assert "none to loading" not in composition
    assert "empty to ready" not in composition
    assert "selected state:" not in composition
    assert "selected_project_id &lt;&#45; project_id" in composition
    assert "context binding" in composition
    assert "panel context" not in composition
    assert "$event." not in composition
    assert "$view." not in composition
    assert "region:" in composition
    assert "target:" not in composition
    assert "from:" not in composition
    assert "do:" not in composition
    assert "Layout / mounted panels" not in composition
    assert "Message routing" not in composition
    assert "Sync rules" not in composition
    assert "region" in composition
    assert "nav" in composition
    assert "main" in composition
    assert "aside" in composition
    assert "order:" not in composition
    assert "element:" not in composition
    assert "role:" not in composition
    assert "required:" not in composition


def test_audit_html_sources_render_copy_assets_and_fixture_fields() -> None:
    ready = ROOT / render_case_file("project.board", "project.board.ready_selected.audit", "default", "wide", "html")
    text = ready.read_text(encoding="utf-8")
    assert "Dispatch queue" in text
    assert "Replace rooftop condenser fan · Atlas Foods" in text
    assert "Latest activity" in text
    assert "High priority" in text
    assert "Replace rooftop condenser fan" in text
    assert "Atlas Foods" in text
    assert "fixture.projects.audit_records" not in text
    assert "data-audit" not in text

    empty = ROOT / render_case_file("project.board", "project.board.empty.audit", "default", "compact", "html")
    empty_text = empty.read_text(encoding="utf-8")
    assert "No dispatch projects yet" in empty_text
    assert "asset.project.list.empty.illustration" in empty_text
    assert "data:image/svg+xml;base64" in empty_text


def test_audit_asset_placeholder_is_generic_and_not_named() -> None:
    asset = ROOT / panel_state_root("panel.project.list", "empty") / "assets" / "asset_project_list_empty_illustration.svg"
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
    author = read_yaml(ROOT / SOURCE_SPEC_PATH)
    copy_id = next(iter(author["copies"]))
    del author["copies"][copy_id]
    with pytest.raises(ContractError, match="copy placeholders drift"):
        compile_source(author)


def test_asset_placeholder_schema_rejects_missing_visual_intent() -> None:
    author = read_yaml(ROOT / SOURCE_SPEC_PATH)
    asset_id = next(iter(author["assets"]))
    del author["assets"][asset_id]["placeholder"]
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)


def test_render_case_coverage_is_required() -> None:
    author = read_yaml(ROOT / SOURCE_SPEC_PATH)
    author.pop("render_cases")
    with pytest.raises(ContractError, match="At least one render_case|Missing render_case coverage"):
        compile_source(author)


def test_audit_validator_rejects_corrupt_html_png(tmp_path: Path) -> None:
    project = tmp_path / "project"
    copy_project_tree(ROOT, project)
    contract = read_yaml(project / COMPILED_SPEC_PATH)
    png = next(project / path for path in audit_expected_files(contract) if path.endswith(".png"))
    png.write_bytes(b"not-a-png")
    with pytest.raises(ContractError, match="not PNG"):
        validate_audit_outputs(project, contract)


def test_audit_validator_rejects_missing_fsm_svg(tmp_path: Path) -> None:
    project = tmp_path / "project"
    copy_project_tree(ROOT, project)
    contract = read_yaml(project / COMPILED_SPEC_PATH)
    svg = next(project / path for path in audit_expected_files(contract) if path.startswith("spec/generated/audit_evidence/panels/") and path.endswith("/fsm.svg"))
    svg.unlink()
    with pytest.raises(ContractError, match="audit generated files"):
        validate_audit_outputs(project, contract)
