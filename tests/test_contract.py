from __future__ import annotations

from pathlib import Path

import pytest

from pyspec_contract.compile import ContractError, compile_author, compile_source, validate_against_schema
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
    assert panel["events"] == []
    assert panel["transitions"] == []
    assert "kind" not in panel


def test_panel_events_must_be_used_by_transition_or_emit() -> None:
    author = _author()
    activity = _item(author, "panels", "panel.project.activity")
    activity["events"].append("unused.event")
    with pytest.raises(ContractError, match=r"Panel panel\.project\.activity declares event without transition or emit: .*unused\.event"):
        compile_source(author)


def test_panel_transition_events_must_be_declared() -> None:
    author = _author()
    activity = _item(author, "panels", "panel.project.activity")
    activity["events"].remove("selection.cleared")
    with pytest.raises(ContractError, match=r"Panel panel\.project\.activity uses event without declaring it: .*selection\.cleared"):
        compile_source(author)


def test_panel_data_events_require_data_binding() -> None:
    author = _author()
    detail = _item(author, "panels", "panel.project.detail")
    detail["states"]["loading"]["data"] = []
    detail["states"]["ready"].pop("field_slots")
    with pytest.raises(ContractError, match=r"Panel panel\.project\.detail transition uses data event without panel or source-state data: data\.ready"):
        compile_source(author)


def test_panel_transition_requires_basis_when_audit_card_would_be_empty() -> None:
    author = _author()
    activity = _item(author, "panels", "panel.project.activity")
    cleared = next(transition for transition in activity["transitions"] if transition["event"] == "selection.cleared")
    cleared.pop("effects")
    with pytest.raises(
        ContractError,
        match=r"Panel panel\.project\.activity transition selection\.cleared from ready to empty must declare basis, data, or effects",
    ):
        compile_source(author)


def test_panel_transition_basis_can_explain_otherwise_empty_audit_card() -> None:
    author = _author()
    activity = _item(author, "panels", "panel.project.activity")
    cleared = next(transition for transition in activity["transitions"] if transition["event"] == "selection.cleared")
    cleared.pop("effects")
    cleared["basis"] = "Clearing the selection returns the activity panel to its empty state."
    contract = compile_source(author)
    compiled = next(
        transition
        for transition in contract["panels"]["panel.project.activity"]["transitions"]
        if transition["event"] == "selection.cleared"
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


def test_composed_view_rejects_unknown_sync_target_event() -> None:
    author = _author()
    view = _item(author, "views", "project.board")
    for effect in view["sync"][0]["do"]:
        if "send" in effect:
            effect["send"]["event"] = "project.ghost_event"
            break
    with pytest.raises(ContractError, match="sync sends undeclared target event"):
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
            "events": [],
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
    author["entries"]["web.ticket.create"] = {"surface": "web", "path": "/tickets", "target": {"view": "ticket.list"}}
    with pytest.raises(ContractError, match="entry surface web requires web"):
        compile_author(author, layers=parse_layers("core,http"))


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
