from __future__ import annotations

from pathlib import Path

import pytest

from pyspec_contract.compile import ContractError, author_from_source, compile_author, compile_source, validate_against_schema
from pyspec_contract.io import read_yaml, write_yaml
from pyspec_contract.paths import COMPILED_SPEC_PATH, SOURCE_SPEC_PATH
from pyspec_contract.validate import validate_project
from tests.helpers import EXAMPLE_ROOT, copy_project_tree

ROOT = EXAMPLE_ROOT


def _basis(text: str = "test contract declaration") -> str:
    return text


def _author() -> dict:
    return read_yaml(ROOT / SOURCE_SPEC_PATH)


def _item(author: dict, section: str, item_id: str) -> dict:
    return author[section][item_id]


def _first_item(author: dict, section: str) -> dict:
    return next(iter(author[section].values()))


def test_project_validates() -> None:
    validate_project(ROOT)




def test_yaml_writer_never_emits_anchors_or_aliases(tmp_path: Path) -> None:
    shared = {"text": "shared basis"}
    path = tmp_path / "spec.yaml"
    write_yaml(path, {"first": shared, "second": shared})
    text = path.read_text(encoding="utf-8")
    assert "&id" not in text
    assert "*id" not in text
    assert text.count("shared basis") == 2


def test_yaml_reader_treats_on_as_a_string_key(tmp_path: Path) -> None:
    path = tmp_path / "spec.yaml"
    write_yaml(path, {"transition": {"on": "data.ready", "required": True}}, sort_keys=False)

    text = path.read_text(encoding="utf-8")
    data = read_yaml(path)

    assert "  on: data.ready" in text
    assert "'on':" not in text
    assert data["transition"]["on"] == "data.ready"
    assert True not in data["transition"]
    assert data["transition"]["required"] is True


def test_checked_in_yaml_has_no_anchors_or_aliases() -> None:
    yaml_paths = [ROOT / SOURCE_SPEC_PATH] + sorted((ROOT / "spec" / "generated").rglob("*.yaml"))
    offenders = []
    for path in yaml_paths:
        text = path.read_text(encoding="utf-8")
        if "&id" in text or "*id" in text:
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []



def test_validation_rejects_hand_edited_yaml_anchors(tmp_path: Path) -> None:
    project = tmp_path / "project"
    copy_project_tree(ROOT, project)
    contract_path = project / SOURCE_SPEC_PATH
    text = contract_path.read_text(encoding="utf-8")
    contract_path.write_text(text.replace("project: project_dispatch_board", "project: &id001 project_dispatch_board", 1), encoding="utf-8")
    with pytest.raises(ContractError, match="Generated YAML must not contain anchors or aliases"):
        validate_project(project)

def test_release_gate_requires_final_content_resolvers() -> None:
    with pytest.raises(ContractError, match="Release gate requires final content resolvers"):
        validate_project(ROOT, release=True)


def test_state_pattern_is_not_a_contract_concept() -> None:
    author = _author()
    state = _item(author, "panels", "panel.project.list")["states"]["loading"]
    state["pattern"] = "loading"
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)


def test_contract_schema_rejects_meta_root_fields() -> None:
    for key, value in [("version", 1), ("status", "draft"), ("review_flags", [{"id": "x"}])]:
        contract = read_yaml(ROOT / COMPILED_SPEC_PATH)
        contract[key] = value
        with pytest.raises(ContractError, match="Schema validation failed"):
            validate_against_schema(contract, "spec.schema.json")


def test_author_schema_rejects_meta_root_fields() -> None:
    for key, value in [("version", 1), ("status", "draft"), ("review_flags", [{"id": "x"}])]:
        author = read_yaml(ROOT / SOURCE_SPEC_PATH)
        author[key] = value
        with pytest.raises(ContractError, match="Schema validation failed"):
            validate_against_schema(author, "author.schema.json")


def test_author_yaml_is_direct_source() -> None:
    author = read_yaml(ROOT / SOURCE_SPEC_PATH)
    assert compile_author(author) == read_yaml(ROOT / COMPILED_SPEC_PATH)


def test_author_contract_is_sparse_source() -> None:
    author = read_yaml(ROOT / SOURCE_SPEC_PATH)
    assert "events" not in author
    assert "refs" not in author
    assert "transition" not in author["capabilities"]["project.submit"]
    assert author["scenarios"]["project.approve.success"]["given"]["facts"] == [{"use": "fact.project.submitted"}]
    assert compile_author(author) == read_yaml(ROOT / COMPILED_SPEC_PATH)


def test_named_fact_expands_into_compiled_scenario() -> None:
    author = _author()
    contract = compile_author(author)
    fact = contract["facts"]["fact.project.submitted"]
    scenario_fact = contract["scenarios"]["project.approve.success"]["arrange"]["facts"][0]
    assert "use" not in scenario_fact
    assert scenario_fact == {"present": fact["present"]}
    assert contract["render_cases"]["project.board.ready_selected.audit"]["facts"] == [
        {"use": "fact.project.submitted"},
        {"use": "fact.project.draft"},
    ]


def test_unknown_fact_use_is_rejected() -> None:
    author = _author()
    author["scenarios"]["project.approve.success"]["given"]["facts"] = [{"use": "fact.project.missing"}]
    with pytest.raises(ContractError, match=r"Scenario project\.approve\.success references unknown fact fact\.project\.missing"):
        compile_author(author)


def test_duplicate_fact_use_in_one_scenario_is_rejected() -> None:
    author = _author()
    author["scenarios"]["project.approve.success"]["given"]["facts"] = [
        {"use": "fact.project.submitted"},
        {"use": "fact.project.submitted"},
    ]
    with pytest.raises(ContractError, match=r"Scenario project\.approve\.success uses fact fact\.project\.submitted more than once"):
        compile_author(author)


def test_unknown_render_case_fact_use_is_rejected() -> None:
    author = _author()
    author["render_cases"]["project.board.ready_selected.audit"]["facts"] = [{"use": "fact.project.missing"}]
    with pytest.raises(ContractError, match=r"Render case project\.board\.ready_selected\.audit references unknown fact fact\.project\.missing"):
        compile_author(author)


def test_duplicate_render_case_fact_use_is_rejected() -> None:
    author = _author()
    author["render_cases"]["project.board.ready_selected.audit"]["facts"] = [
        {"use": "fact.project.submitted"},
        {"use": "fact.project.submitted"},
    ]
    with pytest.raises(ContractError, match=r"Render case project\.board\.ready_selected\.audit uses fact fact\.project\.submitted more than once"):
        compile_author(author)


def test_unused_fact_is_rejected() -> None:
    author = _author()
    author["facts"]["fact.project.unused"] = {
        "present": {
            "resource": "Project",
            "values": {
                "id": "project_unused_1",
                "status": "submitted",
                "title": "Unused project",
                "workspace_id": "$fixture.workspace.id",
            },
        },
        "basis": "Unused facts are dead setup, so they should be removed.",
    }
    with pytest.raises(ContractError, match=r"Unused facts: fact\.project\.unused"):
        compile_author(author)


def test_fact_use_requires_declared_fixture_namespace() -> None:
    author = _author()
    author["scenarios"]["project.approve.success"]["given"]["fixtures"] = []
    with pytest.raises(
        ContractError,
        match=r"Scenario project\.approve\.success fixture ref \$fixture\.workspace\.id cannot resolve at workspace",
    ):
        compile_author(author)


def test_fact_template_fields_must_belong_to_resource() -> None:
    author = _author()
    author["facts"]["fact.project.submitted"]["present"]["values"]["unknown_field"] = "nope"
    with pytest.raises(ContractError, match=r"Fact fact\.project\.submitted seeds unknown Project fields: \['unknown_field'\]"):
        compile_author(author)


def test_transition_capability_derives_state_change_from_resource_lifecycle() -> None:
    author = {
        "project": "derived_transition",
        "resources": {
            "Ticket": {
                "kind": "aggregate",
                "fields": {"id": "ID", "status": "TicketStatus"},
                "lifecycle": {
                    "field": "status",
                    "initial": "draft",
                    "states": ["draft", "submitted"],
                    "transitions": [{"by": "ticket.submit", "from": "draft", "to": "submitted"}],
                },
                "basis": "Ticket lifecycle owns state transitions.",
            }
        },
        "capabilities": {
            "ticket.submit": {
                "archetype": "transition",
                "resource": "Ticket",
                "input": {"ticket_id": "ID"},
                "output": "Ticket",
                "basis": "Submitting moves a draft ticket forward.",
            }
        },
    }
    contract = compile_author(author)
    assert contract["capabilities"]["ticket.submit"]["transition"] == {
        "field": "status",
        "from": "draft",
        "to": "submitted",
    }


def test_author_contract_can_omit_absent_sections() -> None:
    author = {
        "project": "author_core",
        "resources": {
            "Ticket": {
                "kind": "aggregate",
                "fields": {"id": "ID", "title": "Text"},
            }
        },
        "capabilities": {
            "ticket.create": {
                "archetype": "create",
                "resource": "Ticket",
                "input": {"title": "Text"},
                "output": "Ticket",
                "why": "Members can create tickets.",
            }
        },
    }
    contract = compile_author(author)
    assert set(contract["resources"]) == {"Ticket"}
    assert contract["entries"] == {}
    assert contract["panels"] == {}
    assert contract["refs"]["policy"] == ["policy.ticket.create"]
    assert contract["resources"]["Ticket"]["basis"] == "Declared resource Ticket."
    assert contract["capabilities"]["ticket.create"]["basis"] == "Members can create tickets."


def test_author_panel_defaults_empty_collections() -> None:
    from pyspec_contract.layers import parse_layers

    author = {
        "project": "author_ui",
        "resources": {
            "Ticket": {
                "kind": "aggregate",
                "fields": {"id": "ID", "title": "Text"},
                "basis": "Ticket is the product work item.",
            }
        },
        "audit_profiles": {
            "default": {
                "html": {"breakpoints": {"compact": {"width": 320, "height": 480}}},
                "basis": "Single breakpoint covers the tiny authored example.",
            }
        },
        "panels": {
            "panel.ticket.empty": {
                "resource": "Ticket",
                "initial": "empty",
                "states": {"empty": {}},
                "basis": "Panel can start as a minimal empty-state FSM.",
            }
        },
    }
    contract = compile_author(author, layers=parse_layers("core,ui,web"))
    panel = contract["panels"]["panel.ticket.empty"]
    assert panel["context"] == {}
    assert panel["data"] == []
    assert panel["messages"] == {"accepts": {}, "emits": {}}
    assert panel["transitions"] == []
    assert "kind" not in panel


def test_panel_empty_message_directions_can_be_omitted() -> None:
    author = _author()
    activity = _item(author, "panels", "panel.project.activity")

    assert "emits" not in activity["messages"]
    contract = compile_source(author)

    assert contract["panels"]["panel.project.activity"]["messages"]["emits"] == {}


def test_author_source_prunes_empty_message_directions() -> None:
    author = _author()
    activity = _item(author, "panels", "panel.project.activity")
    activity["messages"]["emits"] = {}

    pruned = author_from_source(author)

    assert "emits" not in pruned["panels"]["panel.project.activity"]["messages"]


def test_empty_panel_message_payloads_can_be_omitted() -> None:
    author = _author()
    activity = _item(author, "panels", "panel.project.activity")

    assert activity["messages"]["accepts"]["selection.cleared"] == {}
    contract = compile_source(author)

    assert contract["panels"]["panel.project.activity"]["messages"]["accepts"]["selection.cleared"]["payload"] == {}


def test_author_source_prunes_empty_message_payloads() -> None:
    author = _author()
    activity = _item(author, "panels", "panel.project.activity")
    activity["messages"]["accepts"]["selection.cleared"]["payload"] = {}

    pruned = author_from_source(author)

    assert pruned["panels"]["panel.project.activity"]["messages"]["accepts"]["selection.cleared"] == {}


def test_panel_accepted_messages_must_be_used_by_transition() -> None:
    author = _author()
    activity = _item(author, "panels", "panel.project.activity")
    activity["messages"]["accepts"]["unused.message"] = {}
    with pytest.raises(ContractError, match=r"Panel panel\.project\.activity declares accepted message without transition: .*unused\.message"):
        compile_source(author)


def test_panel_transition_messages_must_be_declared_as_accepted() -> None:
    author = _author()
    activity = _item(author, "panels", "panel.project.activity")
    del activity["messages"]["accepts"]["selection.cleared"]
    with pytest.raises(ContractError, match=r"Panel panel\.project\.activity transition message references undeclared panel message: selection\.cleared"):
        compile_source(author)


def test_panel_data_events_require_data_binding() -> None:
    author = _author()
    detail = _item(author, "panels", "panel.project.detail")
    detail["states"]["loading"]["data"] = []
    detail["states"]["ready"].pop("field_slots")
    with pytest.raises(ContractError, match=r"Panel panel\.project\.detail transition uses data message without panel or source-state data: data\.ready"):
        compile_source(author)


def test_panel_transition_requires_basis_when_audit_card_would_be_empty() -> None:
    author = _author()
    activity = _item(author, "panels", "panel.project.activity")
    cleared = next(transition for transition in activity["transitions"] if transition["on"] == "selection.cleared")
    cleared.pop("effects")
    with pytest.raises(
        ContractError,
        match=r"Panel panel\.project\.activity transition selection\.cleared from ready to empty must declare basis, data, or effects",
    ):
        compile_source(author)


def test_panel_transition_basis_can_explain_otherwise_empty_audit_card() -> None:
    author = _author()
    activity = _item(author, "panels", "panel.project.activity")
    cleared = next(transition for transition in activity["transitions"] if transition["on"] == "selection.cleared")
    cleared.pop("effects")
    cleared["basis"] = "Clearing the selection returns the activity panel to its empty state."
    contract = compile_source(author)
    compiled = next(
        transition
        for transition in contract["panels"]["panel.project.activity"]["transitions"]
        if transition["on"] == "selection.cleared"
    )
    assert compiled["basis"] == "Clearing the selection returns the activity panel to its empty state."


def test_panel_data_inputs_must_come_from_context() -> None:
    author = _author()
    panel = _item(author, "panels", "panel.project.list")
    del panel["context"]["workspace_id"]
    with pytest.raises(
        ContractError,
        match=r"Panel panel\.project\.list data capability project\.list input not provided by context: .*workspace_id",
    ):
        compile_source(author)


def test_panel_field_slots_require_data_source() -> None:
    author = _author()
    activity = _item(author, "panels", "panel.project.activity")
    del activity["states"]["ready"]["data"]
    with pytest.raises(
        ContractError,
        match=r"Panel panel\.project\.activity\.ready declares field slots without data source",
    ):
        compile_source(author)


def test_panel_data_source_must_be_query_like_capability() -> None:
    author = _author()
    activity = _item(author, "panels", "panel.project.activity")
    activity["states"]["ready"]["data"] = ["project.submit"]
    with pytest.raises(
        ContractError,
        match=r"Panel panel\.project\.activity\.ready data capability must be read, list, or query: project\.submit",
    ):
        compile_source(author)


def test_basis_is_plain_bounded_text() -> None:
    author = _author()
    assert isinstance(author["resources"]["Project"]["basis"], str)
    bad = _author()
    bad["resources"]["Project"]["basis"] = {"text": "object basis", "kind": "explicit", "confidence": "high"}
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(bad)
    bad = _author()
    bad["resources"]["Project"]["basis"] = "x" * 281
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(bad)


def test_generated_tree_is_closed(tmp_path: Path) -> None:
    project = tmp_path / "project"
    copy_project_tree(ROOT, project)
    rogue = project / "spec" / "generated" / "agent_invented.feature"
    rogue.write_text("Feature: Drift\n", encoding="utf-8")
    with pytest.raises(ContractError, match="Generated file set drift"):
        validate_project(project)


def test_unknown_fixture_is_rejected() -> None:
    author = _author()
    scenario = _first_item(author, "scenarios")
    scenario["given"]["fixtures"] = ["fixture.workspace.ghost"]
    with pytest.raises(ContractError, match="unknown fixture"):
        compile_source(author)


def test_unresolved_fixture_reference_is_rejected() -> None:
    author = _author()
    scenario = _item(author, "scenarios", "project.board.empty")
    _, body = next(iter(scenario["when"].items()))
    body.setdefault("params", {})["workspace_id"] = "$fixture.workspace.missing"
    with pytest.raises(ContractError, match="cannot resolve"):
        compile_source(author)


def test_prod_harness_cannot_import_spec_fake(tmp_path: Path) -> None:
    project = tmp_path / "project"
    copy_project_tree(ROOT, project)
    prod_driver = project / "tests" / "prod_bdd" / "driver.py"
    prod_driver.write_text(
        "from pyspec_contract.reference_driver import ReferenceSpecDriver\n"
        "class ProdDriver(ReferenceSpecDriver):\n"
        "    pass\n",
        encoding="utf-8",
    )
    with pytest.raises(ContractError, match="Prod harness must be real/no-fake"):
        validate_project(project)


def test_presentation_rejects_undeclared_css_region() -> None:
    author = _author()
    view = _item(author, "views", "project.board")
    view["layout"]["html"]["css"]["rules"].append({"selector": "region.ghost", "declarations": {"display": "block"}})
    with pytest.raises(ContractError, match="undeclared layout region"):
        compile_source(author)


def test_presentation_rejects_undeclared_textual_action() -> None:
    author = _author()
    state = _item(author, "panels", "panel.project.list")["states"]["ready"]
    state["presentation"] = {
        "textual": {
            "screen_class": "ProjectListState",
            "widgets": [{"id": "delete", "kind": "Button", "bind": {"action": "project.delete"}}],
        }
    }
    with pytest.raises(ContractError, match="action bind is not declared"):
        compile_source(author)


def test_missing_referenced_capability_is_rejected() -> None:
    author = _author()
    del author["capabilities"]["project.create"]
    with pytest.raises(ContractError, match="unknown capability|action references"):
        compile_source(author)


def test_composed_view_rejects_unknown_included_panel() -> None:
    author = _author()
    view = _item(author, "views", "project.board")
    view["includes"][0]["panel"] = "panel.project.ghost"
    with pytest.raises(ContractError, match="includes unknown panel"):
        compile_source(author)


def test_composed_view_rejects_unknown_sync_target_message() -> None:
    author = _author()
    view = _item(author, "views", "project.board")
    for effect in view["sync"][0]["do"]:
        if "send" in effect:
            effect["send"]["message"] = "project.ghost_message"
            break
    with pytest.raises(ContractError, match="sync sends message the target does not accept"):
        compile_source(author)


def test_panel_emit_data_must_exactly_match_emitted_message_payload() -> None:
    author = _author()
    transition = _item(author, "panels", "panel.project.list")["transitions"][-1]
    transition["effects"][0]["emit"]["data"] = {}
    with pytest.raises(ContractError, match=r"transition emit project\.selected data must exactly match payload fields: missing: project_id"):
        compile_source(author)


def test_sync_send_data_must_exactly_match_target_message_payload() -> None:
    author = _author()
    view = _item(author, "views", "project.board")
    send = next(effect["send"] for effect in view["sync"][0]["do"] if "send" in effect)
    send["data"] = {}
    with pytest.raises(ContractError, match=r"sync send project\.selection_changed to detail data must exactly match payload fields: missing: project_id"):
        compile_source(author)


def test_sync_send_data_must_match_target_message_payload_type() -> None:
    author = _author()
    view = _item(author, "views", "project.board")
    send = next(effect["send"] for effect in view["sync"][0]["do"] if "send" in effect)
    send["data"]["project_id"] = 1
    with pytest.raises(ContractError, match=r"sync send project\.selection_changed to detail data\.project_id type mismatch: expected ID, got Int"):
        compile_source(author)


def test_panel_message_payloads_must_be_consistent_across_panels() -> None:
    author = _author()
    activity = _item(author, "panels", "panel.project.activity")
    activity["messages"]["accepts"]["project.selection_changed"]["payload"]["project_id"] = "Text"
    with pytest.raises(ContractError, match=r"Panel message project\.selection_changed payload differs"):
        compile_source(author)


def test_panel_message_direction_must_be_unambiguous() -> None:
    author = _author()
    panel = _item(author, "panels", "panel.project.list")
    panel["messages"]["emits"]["project.select"] = {"payload": {"project_id": "ID"}}
    with pytest.raises(ContractError, match=r"declares message as both accepted and emitted: .*project\.select"):
        compile_source(author)


def test_composed_scenario_rejects_unknown_panel_instance() -> None:
    author = _author()
    scenario = _item(author, "scenarios", "project.board.ready")
    scenario["then"]["view"]["panels"]["ghost"] = {"state": "ready"}
    with pytest.raises(ContractError, match="unknown panel instance"):
        compile_source(author)


def _api_only_author() -> dict:
    return {
        "project": "api_only",
        "resources": {
            "Ticket": {
                "kind": "aggregate",
                "fields": {"id": "ID", "title": "Text"},
                "basis": _basis("ticket resource"),
            }
        },
        "capabilities": {
            "ticket.create": {
                "archetype": "create",
                "resource": "Ticket",
                "input": {"title": "Text"},
                "output": "Ticket",
                "basis": _basis("create ticket"),
            }
        },
        "entries": {
            "api.ticket.create": {
                "surface": "api",
                "method": "POST",
                "path": "/tickets",
                "target": {"capability": "ticket.create"},
                "basis": _basis("HTTP create ticket entry"),
            }
        },
    }


def test_authoring_layers_allow_api_only_contract_and_graph_driven_projections() -> None:
    from pyspec_contract.layers import parse_layers
    from pyspec_contract.project import projection_paths

    contract = compile_author(_api_only_author(), layers=parse_layers("core,http"))
    paths = set(projection_paths(contract))
    assert "spec/generated/product_interfaces/http.openapi.yaml" in paths
    assert "spec/generated/persistence.sql" not in paths
    assert "spec/generated/persistence.json" not in paths
    assert "spec/generated/product_interfaces/web.panels.preview.html" not in paths
    assert "spec/generated/product_interfaces/web.panels.preview.css" not in paths
    assert "spec/generated/product_interfaces/textual.projection.py" not in paths
    assert "spec/generated/product_interfaces/events.asyncapi.yaml" not in paths
    assert "spec/generated/product_interfaces/workflow.cwl.yaml" not in paths


def test_authoring_layers_reject_irrelevant_ui_targets() -> None:
    from pyspec_contract.layers import parse_layers

    author = _api_only_author()
    author["panels"] = {
        "panel.ticket.list": {
            "resource": "Ticket",
            "context": {},
            "data": [],
            "initial": "empty",
            "states": {"empty": {}},
            "transitions": [],
            "basis": _basis("UI panel is not part of this API layer"),
        }
    }
    with pytest.raises(ContractError, match="outside active authoring layers"):
        compile_author(author, layers=parse_layers("core,http"))


def test_authoring_layers_reject_wrong_entry_surface() -> None:
    from pyspec_contract.layers import parse_layers

    author = _api_only_author()
    del author["entries"]["api.ticket.create"]
    author["entries"]["web.ticket.create"] = {"surface": "web", "path": "/tickets", "target": {"view": {"name": "ticket.list", "surface": "html"}}}
    with pytest.raises(ContractError, match="entry surface web requires web"):
        compile_author(author, layers=parse_layers("core,http"))


def test_cli_view_entry_must_provide_required_view_context_args() -> None:
    author = _author()
    del author["entries"]["cli.project.board"]["args"]
    with pytest.raises(ContractError, match=r"Entry cli\.project\.board args must include required view context inputs: \['workspace_id'\]"):
        compile_source(author)


def test_entry_rejects_surface_irrelevant_fields() -> None:
    author = _author()
    author["entries"]["web.project.board"]["args"] = {"workspace_id": "ID"}
    with pytest.raises(ContractError, match=r"Entry web\.project\.board surface web has unsupported fields: \['args'\]"):
        compile_source(author)


def test_textual_is_not_an_entrypoint_surface() -> None:
    author = _author()
    author["entries"]["textual.project.board"] = {
        "basis": _basis("Textual is a render surface, not an entrypoint surface."),
        "command": "project board",
        "surface": "textual",
        "target": {"view": {"name": "project.board", "surface": "textual"}},
    }
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)


def test_cli_entry_args_must_exactly_match_capability_input() -> None:
    author = _author()
    del author["entries"]["cli.project.approve"]["args"]
    with pytest.raises(ContractError, match=r"Entry cli\.project\.approve args must exactly match target input: missing: project_id"):
        compile_source(author)


def test_cli_entry_cannot_target_raw_event() -> None:
    author = _author()
    author["entries"]["cli.project.event"] = {
        "basis": _basis("CLI event publishing is intentionally not modeled"),
        "command": "project event",
        "surface": "cli",
        "target": {"event": "project.approved"},
    }
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)


def test_view_entry_target_must_declare_render_surface() -> None:
    author = _author()
    author["entries"]["cli.project.board"]["target"] = {"view": "project.board"}
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)


def test_web_view_entry_must_target_html_surface() -> None:
    author = _author()
    author["entries"]["web.project.board"]["target"]["view"]["surface"] = "textual"
    with pytest.raises(ContractError, match=r"Entry web\.project\.board cannot target view surface 'textual'"):
        compile_source(author)


def test_cli_view_entry_surface_must_be_declared_by_view() -> None:
    author = _author()
    del author["views"]["project.board"]["layout"]["textual"]
    with pytest.raises(ContractError, match=r"Entry cli\.project\.board targets view project\.board surface textual but that view does not declare it"):
        compile_source(author)


def test_cli_view_entry_can_launch_html_view_surface() -> None:
    author = _author()
    author["entries"]["cli.project.board"]["target"]["view"]["surface"] = "html"
    compile_source(author)


def test_get_api_entry_must_provide_all_capability_input_as_params() -> None:
    author = _author()
    entry = author["entries"]["api.project.list"]
    entry["path"] = "/projects"
    entry.pop("params")
    with pytest.raises(ContractError, match=r"API entry api\.project\.list GET must declare all capability inputs as params: \['workspace_id'\]"):
        compile_source(author)


def test_authoring_layers_reject_html_layout_without_web_layer() -> None:
    from pyspec_contract.layers import parse_layers

    author = _api_only_author()
    author["views"] = {
        "ticket.board": {
            "archetype": "dashboard",
            "resource": "Ticket",
            "states": {"ready": {}},
            "layout": {"html": {"regions": {"main": {"required": True}}}},
            "basis": _basis("HTML layout is a web surface"),
        }
    }
    with pytest.raises(ContractError, match="view layout html requires web"):
        compile_author(author, layers=parse_layers("core,http,ui,textual"))


def test_layer_pruned_author_schema_hides_irrelevant_sections() -> None:
    from pyspec_contract.layers import author_schema_for_layers, parse_layers

    schema = author_schema_for_layers(parse_layers("core,http"))
    assert "entries" in schema["properties"]
    assert "resources" in schema["properties"]
    assert "panels" not in schema["properties"]
    assert "render_cases" not in schema["properties"]


def test_pyspec_contract_rejects_scenario_harness_routing() -> None:
    author = _author()
    scenario = _first_item(author, "scenarios")
    scenario["harnesses"] = ["spec", "prod"]
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)


def test_pyspec_contract_rejects_storage_implementation_details_on_resource() -> None:
    author = _author()
    resource = _first_item(author, "resources")
    resource["persistence"] = {"dialect": "sqlite", "table": "projects"}
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)


def test_generated_gherkin_is_single_corpus() -> None:
    features = ROOT / "spec" / "generated" / "test_adapters" / "pytest_bdd_features"
    assert features.exists()
    assert not (features / "spec").exists()
    assert not (features / "prod").exists()
    assert sorted(path.name for path in features.glob("*.feature"))
