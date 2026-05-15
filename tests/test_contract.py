from __future__ import annotations

from pathlib import Path

import pytest

from pyspec_contract.compile import ContractError, audit_cases, author_from_source, compile_author, compile_source, validate_against_schema
from pyspec_contract.io import read_yaml, write_yaml
from pyspec_contract.paths import COMPILED_SPEC_PATH, SOURCE_SPEC_PATH
from pyspec_contract.validate import validate_project
from tests.helpers import EXAMPLE_ROOT, copy_project_tree

ROOT = EXAMPLE_ROOT


def _rationale(text: str = "test contract declaration") -> str:
    return text


def P(name: str) -> dict[str, str]:
    return {"primitive": name}


def M(name: str) -> dict[str, str]:
    return {"model": name}


def D(name: str) -> dict[str, str]:
    return {"data_contract": name}


def A(item: dict) -> dict:
    return {"array": item}


def E(*values: str) -> dict[str, list[str]]:
    return {"enum": list(values)}


def F(type_expr: dict, *, required: bool = True, nullable: bool = False) -> dict:
    return {"type": type_expr, "required": required, "nullable": nullable}


def _author() -> dict:
    return read_yaml(ROOT / SOURCE_SPEC_PATH)


def _item(author: dict, section: str, item_id: str) -> dict:
    return author[section][item_id]


def _first_item(author: dict, section: str) -> dict:
    return next(iter(author[section].values()))


def test_project_validates() -> None:
    validate_project(ROOT)




def test_yaml_writer_never_emits_anchors_or_aliases(tmp_path: Path) -> None:
    shared = {"text": "shared rationale"}
    path = tmp_path / "spec.yaml"
    write_yaml(path, {"first": shared, "second": shared})
    text = path.read_text(encoding="utf-8")
    assert "&id" not in text
    assert "*id" not in text
    assert text.count("shared rationale") == 2


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
    state = _item(author, "state_machines", "state_machine.project.list")["view_states"]["loading"]
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
            "rationale": "Approval events carry the reviewer and project identity needed by notification workflows.",
            "payload_schema": D("data_contract.project.approved"),
        }
    }
    assert "refs" not in author
    assert "transition" not in author["operations"]["operation.project.submit"]
    assert author["test_cases"]["test_case.project.approve.success"]["given"]["domain_facts"] == [{"ref": "fact.project.submitted"}]
    assert compile_author(author) == read_yaml(ROOT / COMPILED_SPEC_PATH)


def test_named_fact_expands_into_compiled_test_case() -> None:
    author = _author()
    contract = compile_author(author)
    fact = contract["facts"]["fact.project.submitted"]
    test_case_fact = contract["test_cases"]["test_case.project.approve.success"]["given"]["domain_facts"][0]
    assert "ref" not in test_case_fact
    assert test_case_fact == {"present": fact["present"]}
    assert audit_cases(contract)["state_machine.project.board.ready.ready_selected.audit"]["facts"] == [
        {"ref": "fact.project.submitted"},
        {"ref": "fact.project.draft"},
    ]


def test_unknown_fact_use_is_rejected() -> None:
    author = _author()
    author["test_cases"]["test_case.project.approve.success"]["given"]["domain_facts"] = [{"ref": "fact.project.missing"}]
    with pytest.raises(ContractError, match=r"Test case test_case.project\.approve\.success references unknown fact fact\.project\.missing"):
        compile_author(author)


def test_duplicate_fact_use_in_one_test_case_is_rejected() -> None:
    author = _author()
    author["test_cases"]["test_case.project.approve.success"]["given"]["domain_facts"] = [
        {"ref": "fact.project.submitted"},
        {"ref": "fact.project.submitted"},
    ]
    with pytest.raises(ContractError, match=r"Test case test_case.project\.approve\.success uses fact fact\.project\.submitted more than once"):
        compile_author(author)


def test_unknown_audit_case_fact_use_is_rejected() -> None:
    author = _author()
    author["state_machines"]["state_machine.project.board"]["view_states"]["ready"]["audit"]["ready_selected"]["facts"] = [{"ref": "fact.project.missing"}]
    with pytest.raises(ContractError, match=r"Audit case state_machine\.project\.board\.ready\.ready_selected\.audit references unknown fact fact\.project\.missing"):
        compile_author(author)


def test_duplicate_audit_case_fact_use_is_rejected() -> None:
    author = _author()
    author["state_machines"]["state_machine.project.board"]["view_states"]["ready"]["audit"]["ready_selected"]["facts"] = [
        {"ref": "fact.project.submitted"},
        {"ref": "fact.project.submitted"},
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
        "rationale": "Unused facts are dead setup, so they should be removed.",
    }
    with pytest.raises(ContractError, match=r"Unused facts: fact\.project\.unused"):
        compile_author(author)


def test_fact_use_requires_declared_fixture_namespace() -> None:
    author = _author()
    author["test_cases"]["test_case.project.approve.success"]["given"]["seed_fixtures"] = []
    with pytest.raises(
        ContractError,
        match=r"Test case test_case.project\.approve\.success fixture ref \$fixture\.workspace\.id cannot resolve at workspace",
    ):
        compile_author(author)


def test_fact_template_fields_must_belong_to_model() -> None:
    author = _author()
    author["facts"]["fact.project.submitted"]["present"]["values"]["unknown_field"] = "nope"
    with pytest.raises(ContractError, match=r"Fact fact\.project\.submitted seeds unknown Project fields: \['unknown_field'\]"):
        compile_author(author)


def test_test_case_subject_ref_must_match_operation_under_test() -> None:
    author = _author()
    author["test_cases"]["test_case.project.approve.success"]["subject_ref"] = {"operation": "operation.project.create"}
    with pytest.raises(ContractError, match="subject_ref.operation must match the operation under test"):
        compile_author(author)


def test_model_exists_assertion_rejects_unknown_field() -> None:
    author = _author()
    exists = author["test_cases"]["test_case.project.approve.success"]["then"]["model"]["exists"]
    exists["where"]["ghost"] = "nope"
    with pytest.raises(ContractError, match=r"model\.exists filters unknown Project fields: \['ghost'\]"):
        compile_author(author)


def test_response_assertion_requires_call_entry() -> None:
    author = _author()
    author["test_cases"]["test_case.project.approve.success"]["then"]["response"] = {"status": 200}
    with pytest.raises(ContractError, match="response assertions require call_entry"):
        compile_author(author)


def test_invocation_assertion_must_follow_when() -> None:
    author = _author()
    author["test_cases"]["test_case.project.approve.success"]["then"]["invoked"].append("operation.project.create")
    with pytest.raises(ContractError, match="asserts operation invocations unrelated to when"):
        compile_author(author)


def test_named_assertion_fact_expands_into_compiled_test_case() -> None:
    author = _author()
    author["test_cases"]["test_case.project.approve.success"]["then"]["assertion_facts"] = [{"ref": "fact.project.submitted"}]
    contract = compile_author(author)
    fact = contract["facts"]["fact.project.submitted"]
    assert contract["test_cases"]["test_case.project.approve.success"]["then"]["assertion_facts"] == [
        {"present": fact["present"]}
    ]


def _derived_transition_author() -> dict:
    return {
        "project": "derived_transition",
        "models": {
            "Ticket": {
                "fields": {"id": F(P("ID")), "status": F(E("draft", "submitted"))},
                "lifecycle": {
                    "field": "status",
                    "initial": "draft",
                    "states": ["draft", "submitted"],
                    "transitions": [{"triggered_by": "operation.ticket.submit", "from": "draft", "to": "submitted"}],
                },
                "rationale": "Ticket lifecycle owns state transitions.",
            },
            "Problem": {
                "fields": {"code": F(P("Text")), "message": F(P("Text"))},
                "rationale": "Problem describes failed transitions.",
            },
        },
        "operations": {
            "operation.ticket.submit": {
                "operation_kind": "transition",
                "input": {"ticket_id": P("ID")},
                "outcomes": {
                    "submitted": {"kind": "success", "result": M("Ticket")},
                    "invalid_state": {"kind": "failure", "result": M("Problem")},
                },
                "rationale": "Submitting moves a draft ticket forward.",
            }
        },
    }


def test_transition_operation_derives_state_change_from_model_lifecycle() -> None:
    author = _derived_transition_author()
    contract = compile_author(author)
    assert contract["operations"]["operation.ticket.submit"]["transition"] == {
        "model": "Ticket",
        "field": "status",
        "from": "draft",
        "to": "submitted",
    }


def test_lifecycle_field_must_exist_on_model() -> None:
    author = _derived_transition_author()
    del author["models"]["Ticket"]["fields"]["status"]
    with pytest.raises(ContractError, match=r"Model Ticket lifecycle field is not a field: status"):
        compile_author(author)


def test_lifecycle_initial_state_must_be_declared() -> None:
    author = _derived_transition_author()
    author["models"]["Ticket"]["lifecycle"]["initial"] = "missing"
    with pytest.raises(ContractError, match=r"Model Ticket lifecycle initial state is not declared: missing"):
        compile_author(author)


def test_lifecycle_transition_states_must_be_declared() -> None:
    author = _derived_transition_author()
    author["models"]["Ticket"]["lifecycle"]["transitions"][0]["to"] = "missing"
    with pytest.raises(ContractError, match=r"Model Ticket lifecycle transition uses unknown state"):
        compile_author(author)


def test_lifecycle_transition_must_reference_transition_operation() -> None:
    author = _derived_transition_author()
    author["operations"]["operation.ticket.submit"]["operation_kind"] = "command"
    with pytest.raises(
        ContractError,
        match=r"Model Ticket lifecycle transition operation\.ticket\.submit must reference a transition operation",
    ):
        compile_author(author)


def test_lifecycle_transition_must_reference_known_operation() -> None:
    author = _derived_transition_author()
    author["models"]["Ticket"]["lifecycle"]["transitions"][0]["triggered_by"] = "operation.ticket.missing"
    with pytest.raises(
        ContractError,
        match=r"Model Ticket lifecycle transition references unknown operation operation\.ticket\.missing",
    ):
        compile_author(author)


def test_operation_rejects_primary_model_field() -> None:
    author = _author()
    author["operations"]["operation.project.create"]["model"] = "Project"
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)


def test_command_operation_allows_empty_crud_effects() -> None:
    author = _author()
    del author["operations"]["operation.project.create"]["creates"]
    author["entry_points"]["entry_point.api.project.create"]["adapter"]["http"]["responses"]["created"]["status"] = 200
    author["test_cases"]["test_case.project.create.api.success"]["then"]["response"]["status"] = 200
    contract = compile_source(author)
    assert contract["operations"]["operation.project.create"]["creates"] == []


def test_state_machine_data_operation_must_read_state_machine_model() -> None:
    author = _author()
    author["models"]["Workspace"] = {
        "fields": {"id": F(P("ID")), "name": F(P("Text"))},
        "rationale": "Workspace is a separate model used to prove data bindings are model-aware.",
    }
    author["operations"]["operation.project.read"]["operation_kind"] = "query"
    author["operations"]["operation.project.read"]["reads"] = ["Workspace"]
    author["operations"]["operation.project.read"]["outcomes"]["found"]["result"] = M("Workspace")
    with pytest.raises(ContractError, match=r"state machine state_machine\.project\.activity\.ready data operation operation.project\.read must read model Project"):
        compile_source(author)


def test_command_operation_does_not_need_model_relationship() -> None:
    contract = compile_source(_author())
    assert contract["operations"]["operation.project.send_approval_notice"]["creates"] == []
    assert contract["operations"]["operation.project.send_approval_notice"]["reads"] == []
    assert contract["operations"]["operation.project.send_approval_notice"]["updates"] == []
    assert contract["operations"]["operation.project.send_approval_notice"]["deletes"] == []


def test_author_contract_can_omit_absent_sections() -> None:
    author = {
        "project": "author_core",
        "models": {
            "Ticket": {
                "fields": {"id": F(P("ID")), "title": F(P("Text"))},
            },
            "Problem": {
                "fields": {"code": F(P("Text")), "message": F(P("Text"))},
            },
        },
        "operations": {
            "operation.ticket.create": {
                "operation_kind": "command",
                "creates": ["Ticket"],
                "input": {"title": P("Text")},
                "outcomes": {
                    "created": {"kind": "success", "result": M("Ticket")},
                    "validation_failed": {"kind": "failure", "result": M("Problem")},
                },
                "rationale": "Members can create tickets.",
            }
        },
    }
    contract = compile_author(author)
    assert set(contract["models"]) == {"Problem", "Ticket"}
    assert contract["entry_points"] == {}
    assert contract["state_machines"] == {}
    assert contract["policies"]["policy.ticket.create"]["targets"] == [{"operation": "operation.ticket.create"}, {"model": "Ticket"}]
    assert contract["operations"]["operation.ticket.create"]["authorization_policy"] == {"policy": "policy.ticket.create"}
    assert contract["refs"]["policy"] == ["policy.ticket.create"]
    assert contract["models"]["Ticket"]["rationale"] == "Declared model Ticket."
    assert contract["operations"]["operation.ticket.create"]["rationale"] == "Members can create tickets."


def test_author_state_machine_defaults_empty_collections() -> None:
    from pyspec_contract.layers import parse_layers

    author = {
        "project": "author_ui",
        "models": {
            "Ticket": {
                "fields": {"id": F(P("ID")), "title": F(P("Text"))},
                "rationale": "Ticket is the product work item.",
            }
        },
        "render_profiles": {
            "render_profile.default": {
                "html_viewports": {"compact": {"width": 320, "height": 480}},
                "rationale": "Single breakpoint covers the tiny authored example.",
            }
        },
        "state_machines": {
            "state_machine.ticket.empty": {
                "model": "Ticket",
                "initial_view_state": "empty",
                "view_states": {"empty": {}},
                "rationale": "state machine can start as a minimal empty-state.",
            }
        },
    }
    contract = compile_author(author, layers=parse_layers("core,ui,html"))
    state_machine = contract["state_machines"]["state_machine.ticket.empty"]
    assert state_machine["context"] == {}
    assert state_machine["data_dependencies"] == []
    assert state_machine["messages"] == {"accepts": {}, "emits": {}}
    assert state_machine["transitions"] == []
    assert "kind" not in state_machine


def test_state_machine_empty_message_directions_can_be_omitted() -> None:
    author = _author()
    activity = _item(author, "state_machines", "state_machine.project.activity")

    assert "emits" not in activity["messages"]
    contract = compile_source(author)

    assert contract["state_machines"]["state_machine.project.activity"]["messages"]["emits"] == {}


def test_author_source_prunes_empty_message_directions() -> None:
    author = _author()
    activity = _item(author, "state_machines", "state_machine.project.activity")
    activity["messages"]["emits"] = {}

    pruned = author_from_source(author)

    assert "emits" not in pruned["state_machines"]["state_machine.project.activity"]["messages"]


def test_empty_state_machine_message_payloads_can_be_omitted() -> None:
    author = _author()
    activity = _item(author, "state_machines", "state_machine.project.activity")

    assert activity["messages"]["accepts"]["message.selection.cleared"] == {}
    contract = compile_source(author)

    assert contract["state_machines"]["state_machine.project.activity"]["messages"]["accepts"]["message.selection.cleared"]["payload_schema"] == {}


def test_author_source_prunes_empty_message_payloads() -> None:
    author = _author()
    activity = _item(author, "state_machines", "state_machine.project.activity")
    activity["messages"]["accepts"]["message.selection.cleared"]["payload_schema"] = {}

    pruned = author_from_source(author)

    assert pruned["state_machines"]["state_machine.project.activity"]["messages"]["accepts"]["message.selection.cleared"] == {}


def test_state_machine_accepted_messages_must_be_used_by_transition() -> None:
    author = _author()
    activity = _item(author, "state_machines", "state_machine.project.activity")
    activity["messages"]["accepts"]["message.unused"] = {}
    with pytest.raises(ContractError, match=r"state machine state_machine\.project\.activity declares accepted state-machine message without transition: .*message\.unused"):
        compile_source(author)


def test_state_machine_transition_messages_must_be_declared_as_accepted() -> None:
    author = _author()
    activity = _item(author, "state_machines", "state_machine.project.activity")
    del activity["messages"]["accepts"]["message.selection.cleared"]
    with pytest.raises(ContractError, match=r"state machine state_machine\.project\.activity transition message references undeclared state-machine message: message\.selection\.cleared"):
        compile_source(author)


def test_state_machine_data_events_require_data_binding() -> None:
    author = _author()
    detail = _item(author, "state_machines", "state_machine.project.detail")
    detail["view_states"]["loading"]["data_dependencies"] = []
    detail["view_states"]["ready"].pop("field_slots")
    with pytest.raises(ContractError, match=r"state machine state_machine\.project\.detail transition uses data signal without state machine or source-state data: data\.ready"):
        compile_source(author)


def test_state_machine_transition_requires_rationale_when_audit_card_would_be_empty() -> None:
    author = _author()
    activity = _item(author, "state_machines", "state_machine.project.activity")
    cleared = next(transition for transition in activity["transitions"] if transition["on"] == "message.selection.cleared")
    cleared.pop("effects")
    with pytest.raises(
        ContractError,
            match=r"state machine state_machine\.project\.activity transition message\.selection\.cleared from ready to empty must declare rationale, data, or effects",
    ):
        compile_source(author)


def test_state_machine_transition_rationale_can_explain_otherwise_empty_audit_card() -> None:
    author = _author()
    activity = _item(author, "state_machines", "state_machine.project.activity")
    cleared = next(transition for transition in activity["transitions"] if transition["on"] == "message.selection.cleared")
    cleared.pop("effects")
    cleared["rationale"] = "Clearing the selection returns the activity state machine to its empty state."
    contract = compile_source(author)
    compiled = next(
        transition
        for transition in contract["state_machines"]["state_machine.project.activity"]["transitions"]
        if transition["on"] == "message.selection.cleared"
    )
    assert compiled["rationale"] == "Clearing the selection returns the activity state machine to its empty state."


def test_state_machine_data_inputs_must_come_from_context() -> None:
    author = _author()
    state_machine = _item(author, "state_machines", "state_machine.project.list")
    del state_machine["context"]["workspace_id"]
    board = _item(author, "state_machines", "state_machine.project.board")
    for mount in board["view_states"]["ready"]["child_state_machines"]:
        if mount["state_machine"] == "state_machine.project.list":
            mount["context_bindings"].pop("workspace_id", None)
    with pytest.raises(
        ContractError,
        match=r"state machine state_machine\.project\.list data operation operation.project\.list input not provided by context: .*workspace_id",
    ):
        compile_source(author)


def test_state_machine_field_slots_require_data_source() -> None:
    author = _author()
    activity = _item(author, "state_machines", "state_machine.project.activity")
    del activity["view_states"]["ready"]["data_dependencies"]
    with pytest.raises(
        ContractError,
        match=r"state machine state_machine\.project\.activity\.ready declares field slots without data source",
    ):
        compile_source(author)


def test_state_machine_data_source_must_be_query_like_operation() -> None:
    author = _author()
    activity = _item(author, "state_machines", "state_machine.project.activity")
    activity["view_states"]["ready"]["data_dependencies"] = ["operation.project.submit"]
    with pytest.raises(
        ContractError,
        match=r"state machine state_machine\.project\.activity\.ready data operation must be query: operation.project.submit",
    ):
        compile_source(author)


def test_rationale_is_plain_bounded_text() -> None:
    author = _author()
    assert isinstance(author["models"]["Project"]["rationale"], str)
    bad = _author()
    bad["models"]["Project"]["rationale"] = {"text": "object rationale", "kind": "explicit", "confidence": "high"}
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(bad)
    bad = _author()
    bad["models"]["Project"]["rationale"] = "x" * 281
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
    test_case = _first_item(author, "test_cases")
    test_case["given"]["seed_fixtures"] = ["fixture.workspace.ghost"]
    with pytest.raises(ContractError, match="unknown seed fixture"):
        compile_source(author)


def test_unresolved_fixture_reference_is_rejected() -> None:
    author = _author()
    test_case = _item(author, "test_cases", "test_case.project.board.empty")
    _, body = next(iter(test_case["when"].items()))
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
    state_machine = _item(author, "state_machines", "state_machine.project.board")["view_states"]["ready"]
    state_machine["renderers"]["html"]["style"]["rules"].append({"selector": "region.ghost", "declarations": {"display": "block"}})
    with pytest.raises(ContractError, match="undeclared layout region"):
        compile_source(author)


def test_presentation_rejects_undeclared_textual_operation() -> None:
    author = _author()
    state = _item(author, "state_machines", "state_machine.project.list")["view_states"]["ready"]
    state["renderers"] = {
        "textual": {
            "presentation": {
                "widgets": [{"id": "delete", "widget_class": "Button", "binding": {"operation": "operation.project.delete"}}],
            }
        }
    }
    with pytest.raises(ContractError, match="operation binding is not declared"):
        compile_source(author)


def test_missing_referenced_operation_is_rejected() -> None:
    author = _author()
    del author["operations"]["operation.project.create"]
    with pytest.raises(ContractError, match="unknown operation|operation references"):
        compile_source(author)


def test_state_machine_composition_rejects_unknown_mounted_state_machine() -> None:
    author = _author()
    state_machine = _item(author, "state_machines", "state_machine.project.board")["view_states"]["ready"]
    state_machine["child_state_machines"][0]["state_machine"] = "state_machine.project.ghost"
    with pytest.raises(ContractError, match="mounts unknown state machine"):
        compile_source(author)


def test_state_machine_composition_rejects_unknown_sync_target_message() -> None:
    author = _author()
    state_machine = _item(author, "state_machines", "state_machine.project.board")["view_states"]["ready"]
    for effect in state_machine["message_sync_rules"][0]["effects"]:
        if "send" in effect:
            effect["send"]["message"] = "message.project.ghost_message"
            break
    with pytest.raises(ContractError, match="sync sends message the target does not accept"):
        compile_source(author)


def test_state_machine_emit_data_must_exactly_match_emitted_message_payload() -> None:
    author = _author()
    transition = _item(author, "state_machines", "state_machine.project.list")["transitions"][-1]
    transition["effects"][0]["emit"]["payload_bindings"] = {}
    with pytest.raises(ContractError, match=r"transition emit message.project\.selected payload_bindings must exactly match payload fields: missing: project_id"):
        compile_source(author)


def test_sync_send_data_must_exactly_match_target_message_payload() -> None:
    author = _author()
    state_machine = _item(author, "state_machines", "state_machine.project.board")["view_states"]["ready"]
    send = next(effect["send"] for effect in state_machine["message_sync_rules"][0]["effects"] if "send" in effect)
    send["payload_bindings"] = {}
    with pytest.raises(ContractError, match=r"sync send message.project\.selection_changed to detail payload_bindings must exactly match payload fields: missing: project_id"):
        compile_source(author)


def test_sync_send_data_must_match_target_message_payload_type() -> None:
    author = _author()
    state_machine = _item(author, "state_machines", "state_machine.project.board")["view_states"]["ready"]
    send = next(effect["send"] for effect in state_machine["message_sync_rules"][0]["effects"] if "send" in effect)
    send["payload_bindings"]["project_id"] = 1
    with pytest.raises(ContractError, match=r"Schema validation failed"):
        compile_source(author)


def test_state_machine_message_payloads_must_be_consistent_across_state_machines() -> None:
    author = _author()
    activity = _item(author, "state_machines", "state_machine.project.activity")
    activity["messages"]["accepts"]["message.project.selection_changed"]["payload_schema"]["project_id"] = P("Text")
    with pytest.raises(ContractError, match=r"sync send message.project\.selection_changed to activity payload_bindings\.project_id type mismatch"):
        compile_source(author)


def test_state_machine_message_direction_must_be_unambiguous() -> None:
    author = _author()
    state_machine = _item(author, "state_machines", "state_machine.project.list")
    state_machine["messages"]["emits"]["message.project.select"] = {"payload_schema": {"project_id": P("ID")}}
    with pytest.raises(ContractError, match=r"declares state-machine message as both accepted and emitted: .*project\.select"):
        compile_source(author)


def test_composed_test_case_rejects_unknown_state_machine_instance() -> None:
    author = _author()
    test_case = _item(author, "test_cases", "test_case.project.board.ready")
    test_case["then"]["state_machine"]["instances"]["ghost"] = {"view_state": "ready"}
    with pytest.raises(ContractError, match="unknown state machine instance"):
        compile_source(author)


def _api_only_author() -> dict:
    return {
        "project": "api_only",
        "models": {
            "Ticket": {
                "fields": {"id": F(P("ID")), "title": F(P("Text"))},
                "rationale": _rationale("ticket model"),
            },
            "Problem": {
                "fields": {"code": F(P("Text")), "message": F(P("Text"))},
                "rationale": _rationale("problem model"),
            },
        },
        "operations": {
            "operation.ticket.create": {
                "operation_kind": "command",
                "creates": ["Ticket"],
                "input": {"title": P("Text")},
                "outcomes": {
                    "created": {"kind": "success", "result": M("Ticket")},
                    "validation_failed": {"kind": "failure", "result": M("Problem")},
                },
                "rationale": _rationale("create ticket"),
            }
        },
        "entry_points": {
            "entry_point.api.ticket.create": {
                "adapter": {
                    "http": {
                        "method": "POST",
                        "path": "/tickets",
                        "input": {"body": {"title": P("Text")}},
                        "responses": {
                            "created": {"status": 201, "body": {"type": M("Ticket"), "from": "$outcome.result"}},
                            "validation_failed": {"status": 422, "body": {"type": M("Problem"), "from": "$outcome.result"}},
                        },
                    }
                },
                "target": {
                    "operation": {"ref": "operation.ticket.create", "input_bindings": {"title": "$input.body.title"}},
                },
                "rationale": _rationale("HTTP create ticket entry"),
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
    assert "spec/generated/product_interfaces/html.state_machines.preview.html" not in paths
    assert "spec/generated/product_interfaces/html.state_machines.preview.css" not in paths
    assert "spec/generated/product_interfaces/textual.projection.py" not in paths
    assert "spec/generated/product_interfaces/events.asyncapi.yaml" not in paths
    assert "spec/generated/product_interfaces/workflow.cwl.yaml" not in paths


def test_authoring_layers_reject_irrelevant_ui_targets() -> None:
    from pyspec_contract.layers import parse_layers

    author = _api_only_author()
    author["state_machines"] = {
        "state_machine.ticket.list": {
            "model": "Ticket",
            "context": {},
            "data_dependencies": [],
            "initial_view_state": "empty",
            "view_states": {"empty": {}},
            "transitions": [],
            "rationale": _rationale("UI state machine is not part of this API layer"),
        }
    }
    with pytest.raises(ContractError, match="outside active authoring layers"):
        compile_author(author, layers=parse_layers("core,http"))


def test_authoring_layers_reject_wrong_entry_renderer() -> None:
    from pyspec_contract.layers import parse_layers

    author = _api_only_author()
    del author["entry_points"]["entry_point.api.ticket.create"]
    author["entry_points"]["entry_point.html.ticket.create"] = {
        "adapter": {"ui": {"path": "/tickets"}},
        "target": {"state_machine": {"ref": "state_machine.ticket.list", "renderer": "html"}},
    }
    with pytest.raises(ContractError, match="entry point adapter ui requires ui"):
        compile_author(author, layers=parse_layers("core,http"))


def test_cli_state_machine_entry_must_provide_required_context_args() -> None:
    author = _author()
    del author["entry_points"]["entry_point.cli.project.board"]["adapter"]["cli"]["input"]["args"]
    with pytest.raises(ContractError, match=r"Entry entry_point.cli\.project\.board input\.args must include required state machine context inputs: \['workspace_id'\]"):
        compile_source(author)


def test_entry_rejects_renderer_irrelevant_fields() -> None:
    author = _author()
    author["entry_points"]["entry_point.html.project.board"]["adapter"]["ui"]["input"]["args"] = {"workspace_id": P("ID")}
    with pytest.raises(ContractError, match=r"Schema validation failed"):
        compile_source(author)


def test_textual_is_not_an_entrypoint_renderer() -> None:
    author = _author()
    author["entry_points"]["textual.project.board"] = {
        "rationale": _rationale("Textual is a render target, not an entrypoint adapter."),
        "adapter": {"textual": {"cli_command": "project board"}},
        "target": {"state_machine": {"ref": "state_machine.project.board", "renderer": "textual"}},
    }
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)


def test_cli_entry_args_must_exactly_match_operation_input() -> None:
    author = _author()
    del author["entry_points"]["entry_point.cli.project.approve"]["adapter"]["cli"]["input"]["args"]
    with pytest.raises(ContractError, match=r"Entry entry_point.cli\.project\.approve input\.args must exactly match target input: missing: approved_by, project_id"):
        compile_source(author)


def test_entry_target_bindings_must_exactly_match_target_input() -> None:
    author = _author()
    del author["entry_points"]["entry_point.api.project.create"]["target"]["operation"]["input_bindings"]["title"]
    with pytest.raises(ContractError, match=r"Entry entry_point.api\.project\.create target\.input_bindings must exactly bind target input: missing: title"):
        compile_source(author)


def test_entry_response_must_match_renderer_contract() -> None:
    author = _author()
    author["entry_points"]["entry_point.api.project.create"]["adapter"]["http"]["responses"]["created"]["body"]["type"] = P("Text")
    with pytest.raises(ContractError, match=r"API entry entry_point.api\.project\.create response created\.body must expose \$outcome\.result as Project"):
        compile_source(author)


def test_operation_outcomes_must_have_one_success_and_real_failure_result() -> None:
    author = _author()
    author["operations"]["operation.project.create"]["outcomes"]["validation_failed"]["kind"] = "success"
    with pytest.raises(ContractError, match=r"Operation operation.project\.create must declare exactly one success outcome"):
        compile_source(author)

    author = _author()
    author["operations"]["operation.project.create"]["outcomes"]["validation_failed"]["result"] = M("Project")
    with pytest.raises(ContractError, match=r"failure outcome validation_failed result must be Problem"):
        compile_source(author)


def test_event_emits_must_map_declared_payload() -> None:
    author = _author()
    author["operations"]["operation.project.approve"]["outcomes"]["approved"]["emits"][0]["payload_bindings"]["approved_by"] = "$outcome.result"
    with pytest.raises(ContractError, match=r"emit event.project\.approved mapping approved_by source \$outcome\.result type must be ID"):
        compile_source(author)


def test_runtime_references_are_context_scoped() -> None:
    author = _author()
    author["entry_points"]["entry_point.api.project.create"]["target"]["operation"]["input_bindings"]["title"] = "$trigger.payload.title"
    with pytest.raises(ContractError, match=r"target\.input_bindings\.title references unavailable runtime root: \$trigger"):
        compile_source(author)


def test_runtime_references_validate_declared_fields() -> None:
    author = _author()
    author["workflows"]["workflow.project.approval_notice"]["steps"][0]["input_bindings"]["project_id"] = "$trigger.payload.missing"
    with pytest.raises(ContractError, match=r"input project_id references unknown data_contract\.project\.approved field: missing"):
        compile_source(author)


def test_entry_responses_must_map_all_operation_outcomes() -> None:
    author = _author()
    del author["entry_points"]["entry_point.api.project.create"]["adapter"]["http"]["responses"]["validation_failed"]
    with pytest.raises(ContractError, match=r"Entry entry_point.api\.project\.create responses must exactly map operation outcomes: missing: validation_failed"):
        compile_source(author)


def test_cli_failure_response_must_use_nonzero_exit_and_stderr() -> None:
    author = _author()
    author["entry_points"]["entry_point.cli.project.approve"]["adapter"]["cli"]["responses"]["invalid_state"]["exit_code"] = 0
    with pytest.raises(ContractError, match=r"CLI entry entry_point.cli\.project\.approve failure response invalid_state exit_code must be nonzero"):
        compile_source(author)


def test_state_machine_entry_must_not_declare_output() -> None:
    author = _author()
    entry = author["entry_points"]["entry_point.html.project.board"]
    entry["output"] = {"status": 200}
    with pytest.raises(ContractError, match=r"Schema validation failed"):
        compile_source(author)


def test_worker_entry_payload_must_match_trigger_event_payload() -> None:
    author = _author()
    author["entry_points"]["entry_point.worker.project.approval_notice"]["adapter"]["worker"]["input"]["payload"] = D("data_contract.project.notice_result")
    with pytest.raises(ContractError, match=r"Entry entry_point.worker\.project\.approval_notice input\.payload must be data_contract\.project\.approved, got data_contract\.project\.notice_result"):
        compile_source(author)


def test_worker_entry_must_declare_realistic_dispositions() -> None:
    author = _author()
    author["entry_points"]["entry_point.worker.project.approval_notice"]["adapter"]["worker"]["responses"] = {"accepted": {"disposition": "acknowledge"}}
    with pytest.raises(ContractError, match=r"Entry entry_point.worker\.project\.approval_notice must declare at least one non-acknowledge disposition"):
        compile_source(author)


def test_workflow_steps_must_route_all_operation_outcomes() -> None:
    author = _author()
    del author["workflows"]["workflow.project.approval_notice"]["steps"][0]["outcome_routes"]["delivery_failed"]
    with pytest.raises(ContractError, match=r"Workflow workflow.project\.approval_notice step send_notice outcome_routes must exactly map operation outcomes: missing: delivery_failed"):
        compile_source(author)


def test_workflow_route_actions_must_be_exclusive() -> None:
    author = _author()
    route = author["workflows"]["workflow.project.approval_notice"]["steps"][0]["outcome_routes"]["delivery_failed"]
    route["fail_as"] = "delivery_failed"
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)


def test_workflow_routes_must_reference_known_targets() -> None:
    author = _author()
    route = author["workflows"]["workflow.project.approval_notice"]["steps"][0]["outcome_routes"]["delivery_failed"]
    route["retry_policy"]["fail_as"] = "missing"
    with pytest.raises(ContractError, match=r"route delivery_failed references unknown workflow outcome missing"):
        compile_source(author)


def test_cli_entry_cannot_target_raw_event() -> None:
    author = _author()
    author["entry_points"]["entry_point.cli.project.event"] = {
        "rationale": _rationale("CLI event publishing is intentionally not modeled"),
        "adapter": {"cli": {"cli_command": "project event"}},
        "target": {"event": {"ref": "event.project.approved"}},
    }
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)


def test_state_machine_entry_target_must_declare_renderer() -> None:
    author = _author()
    del author["entry_points"]["entry_point.cli.project.board"]["target"]["state_machine"]["renderer"]
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)


def test_html_state_machine_entry_must_target_html_renderer() -> None:
    author = _author()
    author["entry_points"]["entry_point.html.project.board"]["target"]["state_machine"]["renderer"] = "textual"
    with pytest.raises(ContractError, match=r"Entry entry_point.html\.project\.board cannot target state machine renderer 'textual'"):
        compile_source(author)


def test_cli_state_machine_entry_renderer_must_be_declared_by_state_machine() -> None:
    author = _author()
    del author["state_machines"]["state_machine.project.board"]["view_states"]["ready"]["renderers"]["textual"]
    with pytest.raises(ContractError, match=r"Entry entry_point.cli\.project\.board targets state machine state_machine\.project\.board renderer textual but that state machine does not declare it"):
        compile_source(author)


def test_cli_state_machine_entry_can_launch_html_renderer() -> None:
    author = _author()
    author["entry_points"]["entry_point.cli.project.board"]["target"]["state_machine"]["renderer"] = "html"
    compile_source(author)


def test_workflow_entry_target_must_declare_trigger() -> None:
    author = _author()
    del author["entry_points"]["entry_point.worker.project.approval_notice"]["target"]["workflow"]["when"]
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)


def test_workflow_entry_trigger_must_match_workflow_trigger() -> None:
    author = _author()
    author["entry_points"]["entry_point.worker.project.approval_notice"]["target"]["workflow"]["when"] = {"event": "event.project.created"}
    with pytest.raises(ContractError, match=r"Entry entry_point.worker\.project\.approval_notice workflow target source must match workflow workflow.project\.approval_notice trigger"):
        compile_source(author)


def test_get_api_entry_must_provide_all_operation_input_as_params() -> None:
    author = _author()
    entry = author["entry_points"]["entry_point.api.project.list"]
    entry["adapter"]["http"]["path"] = "/projects"
    entry["adapter"]["http"]["input"].pop("params")
    entry["target"]["operation"]["input_bindings"].pop("workspace_id")
    with pytest.raises(ContractError, match=r"API entry entry_point.api\.project\.list GET must declare all operation inputs as input\.params: \['workspace_id'\]"):
        compile_source(author)


def test_authoring_layers_reject_html_state_machine_layout_without_html_layer() -> None:
    from pyspec_contract.layers import parse_layers

    author = _api_only_author()
    author["state_machines"] = {
        "state_machine.ticket.board": {
            "archetype": "dashboard",
            "model": "Ticket",
            "initial_view_state": "ready",
            "view_states": {"ready": {"renderers": {"html": {"layout": {"regions": {"main": {"must_render": True}}}}}}},
            "rationale": _rationale("HTML layout requires the html layer"),
        }
    }
    with pytest.raises(ContractError, match="state machine view_state renderer html requires html"):
        compile_author(author, layers=parse_layers("core,http,ui,textual"))


def test_layer_pruned_author_schema_hides_irrelevant_sections() -> None:
    from pyspec_contract.layers import author_schema_for_layers, parse_layers

    schema = author_schema_for_layers(parse_layers("core,http"))
    assert "entry_points" in schema["properties"]
    assert "models" in schema["properties"]
    assert "state_machines" not in schema["properties"]
    assert "audit_cases" not in schema["properties"]


def test_pyspec_contract_rejects_test_case_harness_routing() -> None:
    author = _author()
    test_case = _first_item(author, "test_cases")
    test_case["harnesses"] = ["spec", "prod"]
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
