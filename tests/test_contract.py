from __future__ import annotations

from pathlib import Path

import pytest

from pyspec_contract.compile import ContractError, audit_cases, author_from_source, compile_author, compile_source, validate_against_schema
from pyspec_contract.io import read_yaml, write_yaml
from pyspec_contract.paths import COMPILED_SPEC_PATH, SOURCE_SPEC_PATH
from pyspec_contract.validate import validate_project
from tests.helpers import EXAMPLE_ROOT, copy_project_tree

ROOT = EXAMPLE_ROOT


def _basis(text: str = "test contract declaration") -> str:
    return text


def P(name: str) -> dict[str, str]:
    return {"primitive": name}


def M(name: str) -> dict[str, str]:
    return {"model": name}


def A(item: dict) -> dict:
    return {"array": item}


def E(*values: str) -> dict[str, list[str]]:
    return {"enum": list(values)}


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
    state = _item(author, "fsms", "state_machine.project.list")["states"]["loading"]
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
    assert author["events"] == {
        "event.project.approved": {
            "basis": "Approval events carry the reviewer and project identity needed by notification workflows.",
            "payload": M("ProjectApproved"),
        }
    }
    assert "refs" not in author
    assert "transition" not in author["capabilities"]["operation.project.submit"]
    assert author["scenarios"]["scenario.project.approve.success"]["given"]["facts"] == [{"use": "fact.project.submitted"}]
    assert compile_author(author) == read_yaml(ROOT / COMPILED_SPEC_PATH)


def test_named_fact_expands_into_compiled_scenario() -> None:
    author = _author()
    contract = compile_author(author)
    fact = contract["facts"]["fact.project.submitted"]
    scenario_fact = contract["scenarios"]["scenario.project.approve.success"]["arrange"]["facts"][0]
    assert "use" not in scenario_fact
    assert scenario_fact == {"present": fact["present"]}
    assert audit_cases(contract)["state_machine.project.board.ready.ready_selected.audit"]["facts"] == [
        {"use": "fact.project.submitted"},
        {"use": "fact.project.draft"},
    ]


def test_unknown_fact_use_is_rejected() -> None:
    author = _author()
    author["scenarios"]["scenario.project.approve.success"]["given"]["facts"] = [{"use": "fact.project.missing"}]
    with pytest.raises(ContractError, match=r"Scenario scenario.project\.approve\.success references unknown fact fact\.project\.missing"):
        compile_author(author)


def test_duplicate_fact_use_in_one_scenario_is_rejected() -> None:
    author = _author()
    author["scenarios"]["scenario.project.approve.success"]["given"]["facts"] = [
        {"use": "fact.project.submitted"},
        {"use": "fact.project.submitted"},
    ]
    with pytest.raises(ContractError, match=r"Scenario scenario.project\.approve\.success uses fact fact\.project\.submitted more than once"):
        compile_author(author)


def test_unknown_audit_case_fact_use_is_rejected() -> None:
    author = _author()
    author["fsms"]["state_machine.project.board"]["states"]["ready"]["audit"]["ready_selected"]["facts"] = [{"use": "fact.project.missing"}]
    with pytest.raises(ContractError, match=r"Audit case state_machine\.project\.board\.ready\.ready_selected\.audit references unknown fact fact\.project\.missing"):
        compile_author(author)


def test_duplicate_audit_case_fact_use_is_rejected() -> None:
    author = _author()
    author["fsms"]["state_machine.project.board"]["states"]["ready"]["audit"]["ready_selected"]["facts"] = [
        {"use": "fact.project.submitted"},
        {"use": "fact.project.submitted"},
    ]
    with pytest.raises(ContractError, match=r"Audit case state_machine\.project\.board\.ready\.ready_selected\.audit uses fact fact\.project\.submitted more than once"):
        compile_author(author)


def test_unused_fact_is_rejected() -> None:
    author = _author()
    author["facts"]["fact.project.unused"] = {
        "present": {
            "model": "Project",
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
    author["scenarios"]["scenario.project.approve.success"]["given"]["fixtures"] = []
    with pytest.raises(
        ContractError,
        match=r"Scenario scenario.project\.approve\.success fixture ref \$fixture\.workspace\.id cannot resolve at workspace",
    ):
        compile_author(author)


def test_fact_template_fields_must_belong_to_model() -> None:
    author = _author()
    author["facts"]["fact.project.submitted"]["present"]["values"]["unknown_field"] = "nope"
    with pytest.raises(ContractError, match=r"Fact fact\.project\.submitted seeds unknown Project fields: \['unknown_field'\]"):
        compile_author(author)


def test_transition_capability_derives_state_change_from_model_lifecycle() -> None:
    author = {
        "project": "derived_transition",
        "models": {
            "Ticket": {
                "kind": "aggregate",
                "fields": {"id": P("ID"), "status": E("draft", "submitted")},
                "lifecycle": {
                    "field": "status",
                    "initial": "draft",
                    "states": ["draft", "submitted"],
                    "transitions": [{"by": "operation.ticket.submit", "from": "draft", "to": "submitted"}],
                },
                "basis": "Ticket lifecycle owns state transitions.",
            }
        },
        "capabilities": {
            "operation.ticket.submit": {
                "archetype": "transition",
                "input": {"ticket_id": P("ID")},
                "outcomes": {
                    "submitted": {"kind": "success", "result": M("Ticket")},
                    "invalid_state": {"kind": "failure", "result": M("Problem")},
                },
                "basis": "Submitting moves a draft ticket forward.",
            }
        },
    }
    contract = compile_author(author)
    assert contract["capabilities"]["operation.ticket.submit"]["transition"] == {
        "model": "Ticket",
        "field": "status",
        "from": "draft",
        "to": "submitted",
    }


def test_capability_rejects_primary_model_field() -> None:
    author = _author()
    author["capabilities"]["operation.project.create"]["model"] = "Project"
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)


def test_create_capability_requires_created_model_relationship() -> None:
    author = _author()
    del author["capabilities"]["operation.project.create"]["creates"]
    with pytest.raises(ContractError, match=r"Capability operation.project\.create archetype create must declare creates"):
        compile_source(author)


def test_fsm_data_capability_must_read_fsm_model() -> None:
    author = _author()
    author["models"]["Workspace"] = {
        "kind": "entity",
        "fields": {"id": P("ID"), "name": P("Text")},
        "basis": "Workspace is a separate model used to prove data bindings are model-aware.",
    }
    author["capabilities"]["operation.project.read"]["archetype"] = "query"
    author["capabilities"]["operation.project.read"]["reads"] = ["Workspace"]
    with pytest.raises(ContractError, match=r"FSM state_machine\.project\.activity\.ready data capability operation.project\.read must read model Project"):
        compile_source(author)


def test_command_capability_does_not_need_model_relationship() -> None:
    contract = compile_source(_author())
    assert "creates" not in contract["capabilities"]["operation.project.send_approval_notice"]
    assert "reads" not in contract["capabilities"]["operation.project.send_approval_notice"]
    assert "updates" not in contract["capabilities"]["operation.project.send_approval_notice"]
    assert "deletes" not in contract["capabilities"]["operation.project.send_approval_notice"]


def test_author_contract_can_omit_absent_sections() -> None:
    author = {
        "project": "author_core",
        "models": {
            "Ticket": {
                "kind": "aggregate",
                "fields": {"id": P("ID"), "title": P("Text")},
            }
        },
        "capabilities": {
            "operation.ticket.create": {
                "archetype": "create",
                "creates": ["Ticket"],
                "input": {"title": P("Text")},
                "outcomes": {
                    "created": {"kind": "success", "result": M("Ticket")},
                    "validation_failed": {"kind": "failure", "result": M("Problem")},
                },
                "why": "Members can create tickets.",
            }
        },
    }
    contract = compile_author(author)
    assert set(contract["models"]) == {"Ticket"}
    assert contract["entries"] == {}
    assert contract["fsms"] == {}
    assert contract["refs"]["policy"] == ["policy.ticket.create"]
    assert contract["models"]["Ticket"]["basis"] == "Declared model Ticket."
    assert contract["capabilities"]["operation.ticket.create"]["basis"] == "Members can create tickets."


def test_author_fsm_defaults_empty_collections() -> None:
    from pyspec_contract.layers import parse_layers

    author = {
        "project": "author_ui",
        "models": {
            "Ticket": {
                "kind": "aggregate",
                "fields": {"id": P("ID"), "title": P("Text")},
                "basis": "Ticket is the product work item.",
            }
        },
        "audit_profiles": {
            "default": {
                "html": {"breakpoints": {"compact": {"width": 320, "height": 480}}},
                "basis": "Single breakpoint covers the tiny authored example.",
            }
        },
        "fsms": {
            "state_machine.ticket.empty": {
                "model": "Ticket",
                "initial": "empty",
                "states": {"empty": {}},
                "basis": "FSM can start as a minimal empty-state.",
            }
        },
    }
    contract = compile_author(author, layers=parse_layers("core,ui,web"))
    fsm = contract["fsms"]["state_machine.ticket.empty"]
    assert fsm["context"] == {}
    assert fsm["data"] == []
    assert fsm["messages"] == {"accepts": {}, "emits": {}}
    assert fsm["transitions"] == []
    assert "kind" not in fsm


def test_fsm_empty_message_directions_can_be_omitted() -> None:
    author = _author()
    activity = _item(author, "fsms", "state_machine.project.activity")

    assert "emits" not in activity["messages"]
    contract = compile_source(author)

    assert contract["fsms"]["state_machine.project.activity"]["messages"]["emits"] == {}


def test_author_source_prunes_empty_message_directions() -> None:
    author = _author()
    activity = _item(author, "fsms", "state_machine.project.activity")
    activity["messages"]["emits"] = {}

    pruned = author_from_source(author)

    assert "emits" not in pruned["fsms"]["state_machine.project.activity"]["messages"]


def test_empty_fsm_message_payloads_can_be_omitted() -> None:
    author = _author()
    activity = _item(author, "fsms", "state_machine.project.activity")

    assert activity["messages"]["accepts"]["message.selection.cleared"] == {}
    contract = compile_source(author)

    assert contract["fsms"]["state_machine.project.activity"]["messages"]["accepts"]["message.selection.cleared"]["payload"] == {}


def test_author_source_prunes_empty_message_payloads() -> None:
    author = _author()
    activity = _item(author, "fsms", "state_machine.project.activity")
    activity["messages"]["accepts"]["message.selection.cleared"]["payload"] = {}

    pruned = author_from_source(author)

    assert pruned["fsms"]["state_machine.project.activity"]["messages"]["accepts"]["message.selection.cleared"] == {}


def test_fsm_accepted_messages_must_be_used_by_transition() -> None:
    author = _author()
    activity = _item(author, "fsms", "state_machine.project.activity")
    activity["messages"]["accepts"]["message.unused"] = {}
    with pytest.raises(ContractError, match=r"FSM state_machine\.project\.activity declares accepted message without transition: .*message\.unused"):
        compile_source(author)


def test_fsm_transition_messages_must_be_declared_as_accepted() -> None:
    author = _author()
    activity = _item(author, "fsms", "state_machine.project.activity")
    del activity["messages"]["accepts"]["message.selection.cleared"]
    with pytest.raises(ContractError, match=r"FSM state_machine\.project\.activity transition message references undeclared FSM message: message\.selection\.cleared"):
        compile_source(author)


def test_fsm_data_events_require_data_binding() -> None:
    author = _author()
    detail = _item(author, "fsms", "state_machine.project.detail")
    detail["states"]["loading"]["data"] = []
    detail["states"]["ready"].pop("field_slots")
    with pytest.raises(ContractError, match=r"FSM state_machine\.project\.detail transition uses data message without FSM or source-state data: data\.ready"):
        compile_source(author)


def test_fsm_transition_requires_basis_when_audit_card_would_be_empty() -> None:
    author = _author()
    activity = _item(author, "fsms", "state_machine.project.activity")
    cleared = next(transition for transition in activity["transitions"] if transition["on"] == "message.selection.cleared")
    cleared.pop("effects")
    with pytest.raises(
        ContractError,
            match=r"FSM state_machine\.project\.activity transition message\.selection\.cleared from ready to empty must declare basis, data, or effects",
    ):
        compile_source(author)


def test_fsm_transition_basis_can_explain_otherwise_empty_audit_card() -> None:
    author = _author()
    activity = _item(author, "fsms", "state_machine.project.activity")
    cleared = next(transition for transition in activity["transitions"] if transition["on"] == "message.selection.cleared")
    cleared.pop("effects")
    cleared["basis"] = "Clearing the selection returns the activity FSM to its empty state."
    contract = compile_source(author)
    compiled = next(
        transition
        for transition in contract["fsms"]["state_machine.project.activity"]["transitions"]
        if transition["on"] == "message.selection.cleared"
    )
    assert compiled["basis"] == "Clearing the selection returns the activity FSM to its empty state."


def test_fsm_data_inputs_must_come_from_context() -> None:
    author = _author()
    fsm = _item(author, "fsms", "state_machine.project.list")
    del fsm["context"]["workspace_id"]
    board = _item(author, "fsms", "state_machine.project.board")
    for mount in board["states"]["ready"]["mounts"]:
        if mount["fsm"] == "state_machine.project.list":
            mount["context"].pop("workspace_id", None)
    with pytest.raises(
        ContractError,
        match=r"FSM state_machine\.project\.list data capability operation.project\.list input not provided by context: .*workspace_id",
    ):
        compile_source(author)


def test_fsm_field_slots_require_data_source() -> None:
    author = _author()
    activity = _item(author, "fsms", "state_machine.project.activity")
    del activity["states"]["ready"]["data"]
    with pytest.raises(
        ContractError,
        match=r"FSM state_machine\.project\.activity\.ready declares field slots without data source",
    ):
        compile_source(author)


def test_fsm_data_source_must_be_query_like_capability() -> None:
    author = _author()
    activity = _item(author, "fsms", "state_machine.project.activity")
    activity["states"]["ready"]["data"] = ["operation.project.submit"]
    with pytest.raises(
        ContractError,
        match=r"FSM state_machine\.project\.activity\.ready data capability must be read, list, or query: operation.project.submit",
    ):
        compile_source(author)


def test_basis_is_plain_bounded_text() -> None:
    author = _author()
    assert isinstance(author["models"]["Project"]["basis"], str)
    bad = _author()
    bad["models"]["Project"]["basis"] = {"text": "object basis", "kind": "explicit", "confidence": "high"}
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(bad)
    bad = _author()
    bad["models"]["Project"]["basis"] = "x" * 281
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
    scenario = _item(author, "scenarios", "scenario.project.board.empty")
    _, body = next(iter(scenario["when"].items()))
    body.setdefault("input", {})["workspace_id"] = "$fixture.workspace.missing"
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
    fsm = _item(author, "fsms", "state_machine.project.board")["states"]["ready"]
    fsm["layout"]["html"]["css"]["rules"].append({"selector": "region.ghost", "declarations": {"display": "block"}})
    with pytest.raises(ContractError, match="undeclared layout region"):
        compile_source(author)


def test_presentation_rejects_undeclared_textual_action() -> None:
    author = _author()
    state = _item(author, "fsms", "state_machine.project.list")["states"]["ready"]
    state["presentation"] = {
        "textual": {
            "screen_class": "ProjectListState",
            "widgets": [{"id": "delete", "kind": "Button", "bind": {"action": "operation.project.delete"}}],
        }
    }
    with pytest.raises(ContractError, match="action bind is not declared"):
        compile_source(author)


def test_missing_referenced_capability_is_rejected() -> None:
    author = _author()
    del author["capabilities"]["operation.project.create"]
    with pytest.raises(ContractError, match="unknown capability|action references"):
        compile_source(author)


def test_fsm_composition_rejects_unknown_mounted_fsm() -> None:
    author = _author()
    fsm = _item(author, "fsms", "state_machine.project.board")["states"]["ready"]
    fsm["mounts"][0]["fsm"] = "state_machine.project.ghost"
    with pytest.raises(ContractError, match="mounts unknown FSM"):
        compile_source(author)


def test_fsm_composition_rejects_unknown_sync_target_message() -> None:
    author = _author()
    fsm = _item(author, "fsms", "state_machine.project.board")["states"]["ready"]
    for effect in fsm["sync"][0]["do"]:
        if "send" in effect:
            effect["send"]["message"] = "message.project.ghost_message"
            break
    with pytest.raises(ContractError, match="sync sends message the target does not accept"):
        compile_source(author)


def test_fsm_emit_data_must_exactly_match_emitted_message_payload() -> None:
    author = _author()
    transition = _item(author, "fsms", "state_machine.project.list")["transitions"][-1]
    transition["effects"][0]["emit"]["data"] = {}
    with pytest.raises(ContractError, match=r"transition emit message.project\.selected data must exactly match payload fields: missing: project_id"):
        compile_source(author)


def test_sync_send_data_must_exactly_match_target_message_payload() -> None:
    author = _author()
    fsm = _item(author, "fsms", "state_machine.project.board")["states"]["ready"]
    send = next(effect["send"] for effect in fsm["sync"][0]["do"] if "send" in effect)
    send["data"] = {}
    with pytest.raises(ContractError, match=r"sync send message.project\.selection_changed to detail data must exactly match payload fields: missing: project_id"):
        compile_source(author)


def test_sync_send_data_must_match_target_message_payload_type() -> None:
    author = _author()
    fsm = _item(author, "fsms", "state_machine.project.board")["states"]["ready"]
    send = next(effect["send"] for effect in fsm["sync"][0]["do"] if "send" in effect)
    send["data"]["project_id"] = 1
    with pytest.raises(ContractError, match=r"sync send message.project\.selection_changed to detail data\.project_id type mismatch: expected ID, got Int"):
        compile_source(author)


def test_fsm_message_payloads_must_be_consistent_across_fsms() -> None:
    author = _author()
    activity = _item(author, "fsms", "state_machine.project.activity")
    activity["messages"]["accepts"]["message.project.selection_changed"]["payload"]["project_id"] = P("Text")
    with pytest.raises(ContractError, match=r"sync send message.project\.selection_changed to activity data\.project_id type mismatch"):
        compile_source(author)


def test_fsm_message_direction_must_be_unambiguous() -> None:
    author = _author()
    fsm = _item(author, "fsms", "state_machine.project.list")
    fsm["messages"]["emits"]["message.project.select"] = {"payload": {"project_id": P("ID")}}
    with pytest.raises(ContractError, match=r"declares message as both accepted and emitted: .*project\.select"):
        compile_source(author)


def test_composed_scenario_rejects_unknown_fsm_instance() -> None:
    author = _author()
    scenario = _item(author, "scenarios", "scenario.project.board.ready")
    scenario["then"]["fsm"]["instances"]["ghost"] = {"state": "ready"}
    with pytest.raises(ContractError, match="unknown FSM instance"):
        compile_source(author)


def _api_only_author() -> dict:
    return {
        "project": "api_only",
        "models": {
            "Ticket": {
                "kind": "aggregate",
                "fields": {"id": P("ID"), "title": P("Text")},
                "basis": _basis("ticket model"),
            }
        },
        "capabilities": {
            "operation.ticket.create": {
                "archetype": "create",
                "creates": ["Ticket"],
                "input": {"title": P("Text")},
                "outcomes": {
                    "created": {"kind": "success", "result": M("Ticket")},
                    "validation_failed": {"kind": "failure", "result": M("Problem")},
                },
                "basis": _basis("create ticket"),
            }
        },
        "entries": {
            "entry_point.api.ticket.create": {
                "surface": "api",
                "method": "POST",
                "path": "/tickets",
                "input": {"body": {"title": P("Text")}},
                "target": {"capability": "operation.ticket.create", "with": {"title": "$input.body.title"}},
                "responses": {
                    "created": {"status": 201, "body": {"type": M("Ticket"), "from": "$outcome.result"}},
                    "validation_failed": {"status": 422, "body": {"type": M("Problem"), "from": "$outcome.result"}},
                },
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
    assert "spec/generated/product_interfaces/web.fsms.preview.html" not in paths
    assert "spec/generated/product_interfaces/web.fsms.preview.css" not in paths
    assert "spec/generated/product_interfaces/textual.projection.py" not in paths
    assert "spec/generated/product_interfaces/events.asyncapi.yaml" not in paths
    assert "spec/generated/product_interfaces/workflow.cwl.yaml" not in paths


def test_authoring_layers_reject_irrelevant_ui_targets() -> None:
    from pyspec_contract.layers import parse_layers

    author = _api_only_author()
    author["fsms"] = {
        "state_machine.ticket.list": {
            "model": "Ticket",
            "context": {},
            "data": [],
            "initial": "empty",
            "states": {"empty": {}},
            "transitions": [],
            "basis": _basis("UI FSM is not part of this API layer"),
        }
    }
    with pytest.raises(ContractError, match="outside active authoring layers"):
        compile_author(author, layers=parse_layers("core,http"))


def test_authoring_layers_reject_wrong_entry_surface() -> None:
    from pyspec_contract.layers import parse_layers

    author = _api_only_author()
    del author["entries"]["entry_point.api.ticket.create"]
    author["entries"]["entry_point.web.ticket.create"] = {
        "surface": "web",
        "path": "/tickets",
        "target": {"fsm": {"name": "state_machine.ticket.list", "surface": "html"}},
    }
    with pytest.raises(ContractError, match="entry surface web requires web"):
        compile_author(author, layers=parse_layers("core,http"))


def test_cli_fsm_entry_must_provide_required_context_args() -> None:
    author = _author()
    del author["entries"]["entry_point.cli.project.board"]["input"]["args"]
    with pytest.raises(ContractError, match=r"Entry entry_point.cli\.project\.board input\.args must include required FSM context inputs: \['workspace_id'\]"):
        compile_source(author)


def test_entry_rejects_surface_irrelevant_fields() -> None:
    author = _author()
    author["entries"]["entry_point.web.project.board"]["input"]["args"] = {"workspace_id": P("ID")}
    with pytest.raises(ContractError, match=r"Entry entry_point.web\.project\.board surface web has unsupported input sections: \['args'\]"):
        compile_source(author)


def test_textual_is_not_an_entrypoint_surface() -> None:
    author = _author()
    author["entries"]["textual.project.board"] = {
        "basis": _basis("Textual is a render surface, not an entrypoint surface."),
        "command": "project board",
        "surface": "textual",
        "target": {"fsm": {"name": "state_machine.project.board", "surface": "textual"}},
    }
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)


def test_cli_entry_args_must_exactly_match_capability_input() -> None:
    author = _author()
    del author["entries"]["entry_point.cli.project.approve"]["input"]["args"]
    with pytest.raises(ContractError, match=r"Entry entry_point.cli\.project\.approve input\.args must exactly match target input: missing: approved_by, project_id"):
        compile_source(author)


def test_entry_target_bindings_must_exactly_match_target_input() -> None:
    author = _author()
    del author["entries"]["entry_point.api.project.create"]["target"]["with"]["title"]
    with pytest.raises(ContractError, match=r"Entry entry_point.api\.project\.create target\.with must exactly bind target input: missing: title"):
        compile_source(author)


def test_entry_response_must_match_surface_contract() -> None:
    author = _author()
    author["entries"]["entry_point.api.project.create"]["responses"]["created"]["body"]["type"] = P("Text")
    with pytest.raises(ContractError, match=r"API entry entry_point.api\.project\.create response created\.body must expose \$outcome\.result as Project"):
        compile_source(author)


def test_capability_outcomes_must_have_one_success_and_real_failure_result() -> None:
    author = _author()
    author["capabilities"]["operation.project.create"]["outcomes"]["validation_failed"]["kind"] = "success"
    with pytest.raises(ContractError, match=r"Capability operation.project\.create must declare exactly one success outcome"):
        compile_source(author)

    author = _author()
    author["capabilities"]["operation.project.create"]["outcomes"]["validation_failed"]["result"] = M("Project")
    with pytest.raises(ContractError, match=r"failure outcome validation_failed result must be Problem"):
        compile_source(author)


def test_event_emits_must_map_declared_payload() -> None:
    author = _author()
    author["capabilities"]["operation.project.approve"]["outcomes"]["approved"]["emits"][0]["with"]["approved_by"] = "$outcome.result"
    with pytest.raises(ContractError, match=r"emit event.project\.approved mapping approved_by source \$outcome\.result type must be ID"):
        compile_source(author)


def test_runtime_references_are_context_scoped() -> None:
    author = _author()
    author["entries"]["entry_point.api.project.create"]["target"]["with"]["title"] = "$trigger.payload.title"
    with pytest.raises(ContractError, match=r"target\.with\.title references unavailable runtime root: \$trigger"):
        compile_source(author)


def test_runtime_references_validate_declared_fields() -> None:
    author = _author()
    author["workflows"]["workflow.project.approval_notice"]["steps"][0]["with"]["project_id"] = "$trigger.payload.missing"
    with pytest.raises(ContractError, match=r"input project_id references unknown ProjectApproved field: missing"):
        compile_source(author)


def test_entry_responses_must_map_all_capability_outcomes() -> None:
    author = _author()
    del author["entries"]["entry_point.api.project.create"]["responses"]["validation_failed"]
    with pytest.raises(ContractError, match=r"Entry entry_point.api\.project\.create responses must exactly map capability outcomes: missing: validation_failed"):
        compile_source(author)


def test_cli_failure_response_must_use_nonzero_exit_and_stderr() -> None:
    author = _author()
    author["entries"]["entry_point.cli.project.approve"]["responses"]["invalid_state"]["exit_code"] = 0
    with pytest.raises(ContractError, match=r"CLI entry entry_point.cli\.project\.approve failure response invalid_state exit_code must be nonzero"):
        compile_source(author)


def test_fsm_entry_must_not_declare_output() -> None:
    author = _author()
    entry = author["entries"]["entry_point.web.project.board"]
    entry["output"] = {"status": 200}
    with pytest.raises(ContractError, match=r"Schema validation failed"):
        compile_source(author)


def test_worker_entry_payload_must_match_trigger_event_payload() -> None:
    author = _author()
    author["entries"]["entry_point.worker.project.approval_notice"]["input"]["payload"] = M("NoticeResult")
    with pytest.raises(ContractError, match=r"Entry entry_point.worker\.project\.approval_notice input\.payload must be ProjectApproved, got NoticeResult"):
        compile_source(author)


def test_worker_entry_must_declare_realistic_dispositions() -> None:
    author = _author()
    author["entries"]["entry_point.worker.project.approval_notice"]["responses"] = {"accepted": {"disposition": "ack"}}
    with pytest.raises(ContractError, match=r"Entry entry_point.worker\.project\.approval_notice must declare at least one non-ack disposition"):
        compile_source(author)


def test_workflow_steps_must_route_all_capability_outcomes() -> None:
    author = _author()
    del author["workflows"]["workflow.project.approval_notice"]["steps"][0]["on"]["delivery_failed"]
    with pytest.raises(ContractError, match=r"Workflow workflow.project\.approval_notice step send_notice on must exactly map capability outcomes: missing: delivery_failed"):
        compile_source(author)


def test_workflow_failure_routes_must_declare_retry_or_dead_letter() -> None:
    author = _author()
    del author["workflows"]["workflow.project.approval_notice"]["steps"][0]["on"]["delivery_failed"]["retry"]
    with pytest.raises(ContractError, match=r"Workflow workflow.project\.approval_notice step send_notice failure route delivery_failed must declare retry or dead_letter"):
        compile_source(author)


def test_cli_entry_cannot_target_raw_event() -> None:
    author = _author()
    author["entries"]["entry_point.cli.project.event"] = {
        "basis": _basis("CLI event publishing is intentionally not modeled"),
        "command": "project event",
        "surface": "cli",
        "target": {"event": "event.project.approved"},
    }
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)


def test_fsm_entry_target_must_declare_render_surface() -> None:
    author = _author()
    author["entries"]["entry_point.cli.project.board"]["target"] = {"fsm": "state_machine.project.board"}
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)


def test_web_fsm_entry_must_target_html_surface() -> None:
    author = _author()
    author["entries"]["entry_point.web.project.board"]["target"]["fsm"]["surface"] = "textual"
    with pytest.raises(ContractError, match=r"Entry entry_point.web\.project\.board cannot target FSM surface 'textual'"):
        compile_source(author)


def test_cli_fsm_entry_surface_must_be_declared_by_fsm() -> None:
    author = _author()
    del author["fsms"]["state_machine.project.board"]["states"]["ready"]["layout"]["textual"]
    with pytest.raises(ContractError, match=r"Entry entry_point.cli\.project\.board targets FSM state_machine\.project\.board surface textual but that FSM does not declare it"):
        compile_source(author)


def test_cli_fsm_entry_can_launch_html_surface() -> None:
    author = _author()
    author["entries"]["entry_point.cli.project.board"]["target"]["fsm"]["surface"] = "html"
    compile_source(author)


def test_workflow_entry_target_must_declare_trigger() -> None:
    author = _author()
    author["entries"]["entry_point.worker.project.approval_notice"]["target"] = {"workflow": "workflow.project.approval_notice"}
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)


def test_workflow_entry_trigger_must_match_workflow_trigger() -> None:
    author = _author()
    author["entries"]["entry_point.worker.project.approval_notice"]["target"]["workflow"]["trigger"] = {"event": "event.project.created"}
    with pytest.raises(ContractError, match=r"Entry entry_point.worker\.project\.approval_notice workflow trigger must match workflow workflow.project\.approval_notice trigger"):
        compile_source(author)


def test_get_api_entry_must_provide_all_capability_input_as_params() -> None:
    author = _author()
    entry = author["entries"]["entry_point.api.project.list"]
    entry["path"] = "/projects"
    entry["input"].pop("params")
    entry["target"]["with"].pop("workspace_id")
    with pytest.raises(ContractError, match=r"API entry entry_point.api\.project\.list GET must declare all capability inputs as input\.params: \['workspace_id'\]"):
        compile_source(author)


def test_authoring_layers_reject_html_fsm_layout_without_web_layer() -> None:
    from pyspec_contract.layers import parse_layers

    author = _api_only_author()
    author["fsms"] = {
        "state_machine.ticket.board": {
            "archetype": "dashboard",
            "model": "Ticket",
            "initial": "ready",
            "states": {"ready": {"layout": {"html": {"regions": {"main": {"required": True}}}}}},
            "basis": _basis("HTML layout is a web surface"),
        }
    }
    with pytest.raises(ContractError, match="FSM state layout html requires web"):
        compile_author(author, layers=parse_layers("core,http,ui,textual"))


def test_layer_pruned_author_schema_hides_irrelevant_sections() -> None:
    from pyspec_contract.layers import author_schema_for_layers, parse_layers

    schema = author_schema_for_layers(parse_layers("core,http"))
    assert "entries" in schema["properties"]
    assert "models" in schema["properties"]
    assert "fsms" not in schema["properties"]
    assert "audit_cases" not in schema["properties"]


def test_pyspec_contract_rejects_scenario_harness_routing() -> None:
    author = _author()
    scenario = _first_item(author, "scenarios")
    scenario["harnesses"] = ["spec", "prod"]
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)


def test_pyspec_contract_rejects_storage_implementation_details_on_model() -> None:
    author = _author()
    model = _first_item(author, "models")
    model["persistence"] = {"dialect": "sqlite", "table": "projects"}
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)


def test_generated_gherkin_is_single_corpus() -> None:
    features = ROOT / "spec" / "generated" / "test_adapters" / "pytest_bdd_features"
    assert features.exists()
    assert not (features / "spec").exists()
    assert not (features / "prod").exists()
    assert sorted(path.name for path in features.glob("*.feature"))
