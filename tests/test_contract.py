from __future__ import annotations

import copy
from pathlib import Path

import pytest

from pyspec_contract.api import write_generated
from pyspec_contract.compile import ContractError, ContractLintWarning, audit_cases, author_from_source, compile_author, compile_source, validate_against_schema
from pyspec_contract.io import read_yaml, write_yaml
from pyspec_contract.paths import COMPILED_SPEC_PATH, SOURCE_SPEC_PATH
from pyspec_contract.reference_driver import ReferenceSpecDriver
from pyspec_contract.validate import validate_project
from tests.helpers import EXAMPLE_ROOT, copy_project_tree

ROOT = EXAMPLE_ROOT


def _rationale(text: str = "test contract declaration") -> str:
    return text


def P(name: str) -> dict[str, str]:
    return {"primitive": name}


def ET(name: str) -> str:
    if name.startswith("entity_type."):
        return name
    return "entity_type." + name.lower()


def M(name: str) -> dict[str, str]:
    return {"entity_type": ET(name)}


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
    write_yaml(path, {"transition": {"on": {"data_refresh_signal": "ready"}, "required": True}}, sort_keys=False)

    text = path.read_text(encoding="utf-8")
    data = read_yaml(path)

    assert "  on:" in text
    assert "    data_refresh_signal: ready" in text
    assert "'on':" not in text
    assert data["transition"]["on"] == {"data_refresh_signal": "ready"}
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
    assert author["domain_events"] == {
        "domain_event.project.approved": {
            "rationale": "Approval domain events carry the reviewer and project identity needed by notification workflows.",
            "payload_schema": D("data_contract.project.approved"),
        }
    }
    assert "refs" not in author
    assert "lifecycle_transition" not in author["application_actions"]["application_action.project.submit"]
    assert author["test_cases"]["test_case.project.approve.success"]["given"]["domain_facts"] == [{"ref": "fact.project.submitted"}]
    assert compile_author(author) == read_yaml(ROOT / COMPILED_SPEC_PATH)


def test_named_fact_expands_into_compiled_test_case() -> None:
    author = _author()
    contract = compile_author(author)
    fact = contract["facts"]["fact.project.submitted"]
    test_case_fact = contract["test_cases"]["test_case.project.approve.success"]["given"]["domain_facts"][0]
    assert "ref" not in test_case_fact
    assert test_case_fact == {"present": fact["present"]}
    assert audit_cases(contract)["state_machine.project.board.ready.ready_selected.audit"]["fact_refs"] == [
        {"ref": "fact.project.submitted"},
        {"ref": "fact.project.draft"},
    ]
    assert "render_profiles" not in audit_cases(contract)["state_machine.project.board.ready.ready_selected.audit"]


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


def test_unknown_render_audit_case_fact_use_is_rejected() -> None:
    author = _author()
    author["state_machines"]["state_machine.project.board"]["view_states"]["ready"]["render_audit_cases"]["ready_selected"]["fact_refs"] = [{"ref": "fact.project.missing"}]
    with pytest.raises(ContractError, match=r"Render audit case state_machine\.project\.board\.ready\.ready_selected\.audit references unknown fact fact\.project\.missing"):
        compile_author(author)


def test_duplicate_render_audit_case_fact_use_is_rejected() -> None:
    author = _author()
    author["state_machines"]["state_machine.project.board"]["view_states"]["ready"]["render_audit_cases"]["ready_selected"]["fact_refs"] = [
        {"ref": "fact.project.submitted"},
        {"ref": "fact.project.submitted"},
    ]
    with pytest.raises(ContractError, match=r"Render audit case state_machine\.project\.board\.ready\.ready_selected\.audit uses fact fact\.project\.submitted more than once"):
        compile_author(author)


def test_unused_fact_is_rejected() -> None:
    author = _author()
    author["facts"]["fact.project.unused"] = {
        "present": {
            "entity_type": ET("Project"),
            "values": {
                "id": {"value": "project_unused_1"},
                "status": {"value": "submitted"},
                "title": {"value": "Unused project"},
                "workspace_id": {"from": "$fixture.workspace.id"},
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
    author["facts"]["fact.project.submitted"]["present"]["values"]["unknown_field"] = {"value": "nope"}
    with pytest.raises(ContractError, match=r"Fact fact\.project\.submitted seeds unknown Project fields: \['unknown_field'\]"):
        compile_author(author)


def test_test_case_subject_ref_must_match_application_action_under_test() -> None:
    author = _author()
    author["test_cases"]["test_case.project.approve.success"]["subject_ref"] = {"application_action": "application_action.project.create"}
    with pytest.raises(ContractError, match="subject_ref.application_action must match the application action under test"):
        compile_author(author)


def test_entity_exists_assertion_rejects_unknown_field() -> None:
    author = _author()
    exists = author["test_cases"]["test_case.project.approve.success"]["then"]["entity"]["exists"]
    exists["where"]["ghost"] = {"value": "nope"}
    with pytest.raises(ContractError, match=r"entity\.exists filters unknown Project fields: \['ghost'\]"):
        compile_author(author)


def test_response_assertion_requires_call_entry_point() -> None:
    author = _author()
    author["test_cases"]["test_case.project.approve.success"]["then"]["response"] = {"status": 200}
    with pytest.raises(ContractError, match="response assertions require call_entry_point"):
        compile_author(author)


def test_authorization_denial_outcome_must_be_mapped_authorization_failure() -> None:
    author = _author()
    case = author["test_cases"]["test_case.project.approve.forbidden"]
    case["then"]["outcome"] = "transition_not_allowed"
    with pytest.raises(ContractError, match=r"authorization_denial outcome must be one of application action authorization failure outcomes"):
        compile_author(author)


def test_invocation_assertion_must_follow_when() -> None:
    author = _author()
    author["test_cases"]["test_case.project.approve.success"]["then"]["invoked"].append("application_action.project.create")
    with pytest.raises(ContractError, match="asserts action bindings unrelated to when"):
        compile_author(author)


def test_named_assertion_fact_expands_into_compiled_test_case() -> None:
    author = _author()
    author["test_cases"]["test_case.project.approve.success"]["then"]["expected_facts"] = [{"ref": "fact.project.submitted"}]
    contract = compile_author(author)
    fact = contract["facts"]["fact.project.submitted"]
    assert contract["test_cases"]["test_case.project.approve.success"]["then"]["expected_facts"] == [
        {"present": fact["present"]}
    ]


def test_authorization_policies_require_explicit_conditions_and_support_value_equals() -> None:
    author = _derived_transition_author()
    author["application_actions"]["application_action.ticket.submit"]["authorization"] = {
        "policy": "authorization_policy.ticket.submit",
        "unauthenticated_as": "unauthenticated",
        "forbidden_as": "forbidden",
    }
    author["application_actions"]["application_action.ticket.submit"]["outcomes"]["unauthenticated"] = {"kind": "failure", "result": M("Problem")}
    author["application_actions"]["application_action.ticket.submit"]["outcomes"]["forbidden"] = {"kind": "failure", "result": M("Problem")}
    author["authorization_policies"] = {
        "authorization_policy.ticket.submit": {
            "subjects": [{"kind": "actor"}],
            "targets": [{"application_action": "application_action.ticket.submit"}],
            "effect": "allow",
            "rationale": "Explicit policy missing conditions is invalid.",
        }
    }
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_author(author)

    author["authorization_policies"]["authorization_policy.ticket.submit"]["conditions"] = [
        {
            "value_equals": {
                "left": {"from": "$input.ticket_id"},
                "right": {"value": "ticket_1"},
            }
        }
    ]
    contract = compile_author(author)
    assert contract["authorization_policies"]["authorization_policy.ticket.submit"]["conditions"][0]["value_equals"]["right"] == {
        "value": "ticket_1"
    }


def test_authorization_policies_reject_duplicated_rule_sets() -> None:
    author = _authorized_transition_author()
    author["authorization_policies"]["authorization_policy.ticket.submit_duplicate"] = {
        "subjects": [{"kind": "actor"}],
        "targets": [{"entity_type": ET("Ticket")}],
        "effect": "allow",
        "conditions": [{"subject_has_role": "member"}],
        "rationale": "This should reuse the member submit policy instead.",
    }
    with pytest.raises(ContractError, match=r"reuse one authorization_policy with combined targets"):
        compile_author(author)


def _authorized_transition_author() -> dict:
    author = _derived_transition_author()
    operation = author["application_actions"]["application_action.ticket.submit"]
    operation["authorization"] = {
        "policy": "authorization_policy.ticket.submit",
        "unauthenticated_as": "unauthenticated",
        "forbidden_as": "forbidden",
    }
    operation["outcomes"]["unauthenticated"] = {"kind": "failure", "result": M("Problem")}
    operation["outcomes"]["forbidden"] = {"kind": "failure", "result": M("Problem")}
    author["authorization_policies"] = {
        "authorization_policy.ticket.submit": {
            "subjects": [{"kind": "actor"}],
            "targets": [{"application_action": "application_action.ticket.submit"}],
            "effect": "allow",
            "conditions": [{"subject_has_role": "member"}],
            "rationale": "Members may submit tickets.",
        }
    }
    return author


def test_authored_application_action_replaces_legacy_authorization_policy_with_explicit_mapping() -> None:
    author = _authorized_transition_author()
    author["application_actions"]["application_action.ticket.submit"]["authorization_policy"] = "authorization_policy.ticket.submit"
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_author(author)

    author = _authorized_transition_author()
    contract = compile_author(author)
    assert contract["application_actions"]["application_action.ticket.submit"]["authorization"] == {
        "policy": "authorization_policy.ticket.submit",
        "unauthenticated_as": "unauthenticated",
        "forbidden_as": "forbidden",
    }


def test_action_authorization_mapping_rejects_bad_outcome_names() -> None:
    author = _authorized_transition_author()
    author["application_actions"]["application_action.ticket.submit"]["authorization"]["forbidden_as"] = "Forbidden"
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_author(author)


def test_action_authorization_policy_and_outcomes_are_semantically_validated() -> None:
    author = _authorized_transition_author()
    author["application_actions"]["application_action.ticket.submit"]["authorization"]["policy"] = "authorization_policy.ticket.missing"
    with pytest.raises(ContractError, match=r"authorization\.policy references unknown authorization policy"):
        compile_author(author)

    author = _authorized_transition_author()
    del author["application_actions"]["application_action.ticket.submit"]["outcomes"]["unauthenticated"]
    with pytest.raises(ContractError, match=r"authorization\.unauthenticated_as references unknown outcome unauthenticated"):
        compile_author(author)

    author = _authorized_transition_author()
    author["application_actions"]["application_action.ticket.submit"]["authorization"]["forbidden_as"] = "submitted"
    with pytest.raises(ContractError, match=r"authorization\.forbidden_as must map to a failure outcome"):
        compile_author(author)

    author = _authorized_transition_author()
    author["application_actions"]["application_action.ticket.submit"]["authorization"]["forbidden_as"] = "unauthenticated"
    with pytest.raises(ContractError, match=r"unauthenticated_as and forbidden_as must be distinct"):
        compile_author(author)


def test_authorization_failure_outcomes_must_not_emit_domain_events() -> None:
    author = _authorized_transition_author()
    author["domain_events"] = {
        "domain_event.ticket.denied": {
            "payload_schema": M("Problem"),
            "rationale": "Authorization failure outcomes are not domain-event emitters.",
        }
    }
    author["application_actions"]["application_action.ticket.submit"]["outcomes"]["forbidden"]["emits"] = [
        {"domain_event": "domain_event.ticket.denied", "payload_source": "$outcome.result"}
    ]
    with pytest.raises(ContractError, match=r"failure outcome forbidden must not emit domain events"):
        compile_author(author)


def _derived_transition_author() -> dict:
    return {
        "project": "derived_transition",
        "entity_types": {
            "entity_type.ticket": {
                "name": "Ticket",
                "fields": {"id": F(P("ID")), "status": F(E("draft", "submitted"))},
                "entity_lifecycle": {
                    "field": "status",
                    "initial_state": "draft",
                    "lifecycle_states": ["draft", "submitted"],
                    "lifecycle_transitions": [{"triggered_by": "application_action.ticket.submit", "from": "draft", "to": "submitted"}],
                },
                "rationale": "Ticket lifecycle owns state transitions.",
            },
            "entity_type.problem": {
                "name": "Problem",
                "fields": {"code": F(P("Text")), "message": F(P("Text"))},
                "rationale": "Problem describes failed transitions.",
            },
        },
        "application_actions": {
            "application_action.ticket.submit": {
                "action_kind": "lifecycle_transition",
                "input": {"ticket_id": P("ID")},
                "outcomes": {
                    "submitted": {"kind": "success", "result": M("Ticket")},
                    "transition_not_allowed": {"kind": "failure", "result": M("Problem")},
                },
                "rationale": "Submitting moves a draft ticket forward.",
            }
        },
    }


def test_lifecycle_transition_application_action_derives_state_change_from_entity_lifecycle() -> None:
    author = _derived_transition_author()
    contract = compile_author(author)
    assert contract["application_actions"]["application_action.ticket.submit"]["lifecycle_transition"] == {
        "entity_type": "entity_type.ticket",
        "field": "status",
        "from": "draft",
        "to": "submitted",
    }
    assert contract["authorization_policies"] == {}
    assert "authorization" not in contract["application_actions"]["application_action.ticket.submit"]


def test_authored_application_actions_do_not_duplicate_lifecycle_transition_metadata() -> None:
    author = _derived_transition_author()
    author["application_actions"]["application_action.ticket.submit"]["lifecycle_transition"] = {
        "entity_type": "entity_type.ticket",
        "field": "status",
        "from": "draft",
        "to": "submitted",
    }
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_author(author)


def test_lifecycle_transition_application_actions_must_be_referenced_by_entity_lifecycle() -> None:
    author = _derived_transition_author()
    author["application_actions"]["application_action.ticket.close"] = {
        "action_kind": "lifecycle_transition",
        "input": {"ticket_id": P("ID")},
        "outcomes": {
            "closed": {"kind": "success", "result": M("Ticket")},
            "transition_not_allowed": {"kind": "failure", "result": M("Problem")},
        },
        "rationale": "Closing is intentionally not declared in the lifecycle graph.",
    }
    with pytest.raises(ContractError, match=r"Lifecycle-transition application action application_action\.ticket\.close must be referenced by entity_lifecycle declarations"):
        compile_author(author)


def test_lifecycle_transition_application_actions_must_declare_transition_not_allowed_failure() -> None:
    author = _derived_transition_author()
    author["application_actions"]["application_action.ticket.submit"]["outcomes"]["other_failure"] = {"kind": "failure", "result": M("Problem")}
    del author["application_actions"]["application_action.ticket.submit"]["outcomes"]["transition_not_allowed"]
    with pytest.raises(ContractError, match=r"must declare transition_not_allowed failure outcome"):
        compile_author(author)


def test_entity_lifecycle_field_must_exist_on_entity_type() -> None:
    author = _derived_transition_author()
    del author["entity_types"]["entity_type.ticket"]["fields"]["status"]
    with pytest.raises(ContractError, match=r"Entity type entity_type\.ticket entity_lifecycle field is not a field: status"):
        compile_author(author)


def test_lifecycle_initial_state_must_be_declared() -> None:
    author = _derived_transition_author()
    author["entity_types"]["entity_type.ticket"]["entity_lifecycle"]["initial_state"] = "missing"
    with pytest.raises(ContractError, match=r"Entity type entity_type\.ticket initial lifecycle_state is not declared: missing"):
        compile_author(author)


def test_lifecycle_transition_states_must_be_declared() -> None:
    author = _derived_transition_author()
    author["entity_types"]["entity_type.ticket"]["entity_lifecycle"]["lifecycle_transitions"][0]["to"] = "missing"
    with pytest.raises(ContractError, match=r"Entity type entity_type\.ticket lifecycle_transition uses unknown lifecycle_state"):
        compile_author(author)


def test_lifecycle_transition_must_reference_transition_operation() -> None:
    author = _derived_transition_author()
    author["application_actions"]["application_action.ticket.submit"]["action_kind"] = "command"
    with pytest.raises(
        ContractError,
        match=r"Entity type entity_type\.ticket lifecycle_transition application_action\.ticket\.submit must reference a lifecycle_transition application action",
    ):
        compile_author(author)


def test_lifecycle_transition_must_reference_known_operation() -> None:
    author = _derived_transition_author()
    author["entity_types"]["entity_type.ticket"]["entity_lifecycle"]["lifecycle_transitions"][0]["triggered_by"] = "application_action.ticket.missing"
    with pytest.raises(
        ContractError,
        match=r"Entity type entity_type\.ticket lifecycle_transition references unknown application action application_action\.ticket\.missing",
    ):
        compile_author(author)


def test_application_action_rejects_primary_model_field() -> None:
    author = _author()
    author["application_actions"]["application_action.project.create"]["entity_type"] = "Project"
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)


def test_field_type_rejects_nullable_and_presence_wrappers() -> None:
    author = _author()
    author["entity_types"]["entity_type.project"]["fields"]["summary"]["type"] = {"nullable": P("Text")}
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)

    author = _author()
    author["entity_types"]["entity_type.project"]["fields"]["summary"]["type"] = {"op" + "tional": P("Text")}
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)


def test_command_application_action_allows_empty_crud_effects() -> None:
    author = _author()
    del author["application_actions"]["application_action.project.create"]["creates"]
    author["entry_points"]["entry_point.api.project.create"]["adapter"]["http_api"]["responses"]["created"]["status"] = 200
    author["test_cases"]["test_case.project.create.api.success"]["then"]["response"]["status"] = 200
    contract = compile_source(author)
    assert contract["application_actions"]["application_action.project.create"]["creates"] == []


def test_state_machine_data_application_action_must_read_state_machine_entity_type() -> None:
    author = _author()
    author["entity_types"][ET("Workspace")] = {
        "name": "Workspace",
        "fields": {"id": F(P("ID")), "name": F(P("Text"))},
        "rationale": "Workspace is a separate entity_type used to prove data bindings are entity_type-aware.",
    }
    author["application_actions"]["application_action.project.read"]["action_kind"] = "query"
    author["application_actions"]["application_action.project.read"]["reads"] = [ET("Workspace")]
    author["application_actions"]["application_action.project.read"]["outcomes"]["found"]["result"] = M("Workspace")
    with pytest.raises(ContractError, match=r"state machine state_machine\.project\.activity\.ready data_loader read_activity application action must read entity_type entity_type\.project"):
        compile_source(author)


def test_query_application_actions_are_side_effect_free_and_do_not_emit_domain_events() -> None:
    author = _author()
    author["application_actions"]["application_action.project.list"]["creates"] = [ET("Project")]
    with pytest.raises(ContractError, match=r"Application action application_action\.project\.list action_kind query does not support effects: .*creates"):
        compile_source(author)

    author = _author()
    author["application_actions"]["application_action.project.list"]["outcomes"]["listed"]["emits"] = [
        {"domain_event": "domain_event.project.listed", "payload_source": "$outcome.result"}
    ]
    with pytest.raises(ContractError, match=r"Query application action application_action\.project\.list must not emit domain events"):
        compile_source(author)


def test_command_application_action_does_not_need_entity_type_relationship() -> None:
    contract = compile_source(_author())
    assert contract["application_actions"]["application_action.project.send_approval_notice"]["creates"] == []
    assert contract["application_actions"]["application_action.project.send_approval_notice"]["reads"] == []
    assert contract["application_actions"]["application_action.project.send_approval_notice"]["updates"] == []
    assert contract["application_actions"]["application_action.project.send_approval_notice"]["deletes"] == []


def test_author_contract_can_omit_absent_sections() -> None:
    author = {
        "project": "author_core",
        "entity_types": {
            ET("Ticket"): {
                "name": "Ticket",
                "fields": {"id": F(P("ID")), "title": F(P("Text"))},
            },
            ET("Problem"): {
                "name": "Problem",
                "fields": {"code": F(P("Text")), "message": F(P("Text"))},
            },
        },
        "application_actions": {
            "application_action.ticket.create": {
                "action_kind": "command",
                "creates": [ET("Ticket")],
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
    assert set(contract["entity_types"]) == {ET("Problem"), ET("Ticket")}
    assert contract["entry_points"] == {}
    assert contract["state_machines"] == {}
    assert contract["authorization_policies"] == {}
    assert "authorization" not in contract["application_actions"]["application_action.ticket.create"]
    assert "authorization_policy" not in contract["refs"]
    assert contract["entity_types"]["entity_type.ticket"]["rationale"] == "Declared entity_type Ticket."
    assert contract["application_actions"]["application_action.ticket.create"]["rationale"] == "Members can create tickets."


def test_author_state_machine_defaults_empty_collections() -> None:
    from pyspec_contract.layers import parse_layers

    author = {
        "project": "author_ui",
        "entity_types": {
            ET("Ticket"): {
                "name": "Ticket",
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
                "entity_type": ET("Ticket"),
                "initial_view_state": "empty",
                "view_states": {"empty": {}},
                "rationale": "state machine can start as a minimal empty-state.",
            }
        },
    }
    contract = compile_author(author, layers=parse_layers("core,ui,html"))
    state_machine = contract["state_machines"]["state_machine.ticket.empty"]
    assert state_machine["context"] == {}
    assert state_machine["data_loaders"] == {}
    assert state_machine["signals"] == {"accepts": {"local_signals": {}, "data_refresh_signals": {}}, "emits": {"local_signals": {}}}
    assert state_machine["transitions"] == []
    assert "kind" not in state_machine


def test_nested_json_values_binding_values_and_model_less_state_machines_compile() -> None:
    author = {
        "project": "nested_values",
        "state_machines": {
            "state_machine.settings.panel": {
                "context": {"settings": F(P("JSON"))},
                "signals": {
                    "accepts": {
                        "local_signals": {
                            "configure": {"payload_schema": {"settings": P("JSON")}},
                        }
                    }
                },
                "initial_view_state": "ready",
                "view_states": {"ready": {}},
                "transitions": [
                    {
                        "from": "ready",
                        "to": "ready",
                        "on": {"local_signal": "configure"},
                        "effects": [
                            {
                                "set": {
                                    "context": "settings",
                                    "value": {"theme": {"colors": ["red", "blue"], "density": {"compact": True}}},
                                }
                            }
                        ],
                    }
                ],
                "rationale": "Entity type-less settings panel keeps local JSON context.",
            }
        },
    }
    contract = compile_author(author)
    state_machine = contract["state_machines"]["state_machine.settings.panel"]
    assert "entity_type" not in state_machine
    assert state_machine["transitions"][0]["effects"][0]["set"]["value"]["theme"]["density"]["compact"] is True


def test_context_set_effect_respects_context_nullability() -> None:
    author = {
        "project": "context_nullability",
        "state_machines": {
            "state_machine.project.panel": {
                "context": {"project_id": F(P("ID"), required=False, nullable=True)},
                "signals": {"accepts": {"local_signals": {"clear": {}}}},
                "initial_view_state": "ready",
                "view_states": {"ready": {}},
                "transitions": [
                    {
                        "from": "ready",
                        "to": "ready",
                        "on": {"local_signal": "clear"},
                        "effects": [{"set": {"context": "project_id", "value": None}}],
                    }
                ],
                "rationale": "Nullable local context may be cleared explicitly.",
            }
        },
    }
    compile_author(author)

    author["state_machines"]["state_machine.project.panel"]["context"]["project_id"]["nullable"] = False
    with pytest.raises(ContractError, match=r"transition set project_id cannot assign null to non-nullable ID"):
        compile_author(author)

    author = {
        "project": "context_nullable_source",
        "state_machines": {
            "state_machine.project.panel": {
                "context": {
                    "source_project_id": F(P("ID"), required=False, nullable=True),
                    "target_project_id": F(P("ID")),
                },
                "signals": {"accepts": {"local_signals": {"copy": {}}}},
                "initial_view_state": "ready",
                "view_states": {"ready": {}},
                "transitions": [
                    {
                        "from": "ready",
                        "to": "ready",
                        "on": {"local_signal": "copy"},
                        "effects": [{"set": {"context": "target_project_id", "from": "$context.source_project_id"}}],
                    }
                ],
                "rationale": "Nullable sources cannot feed non-nullable context fields.",
            }
        },
    }
    with pytest.raises(ContractError, match=r"transition set target_project_id cannot assign nullable source to non-nullable ID"):
        compile_author(author)


def test_workflow_input_bindings_support_runtime_sources_and_literal_values() -> None:
    author = {
        "project": "workflow_bindings",
        "data_contracts": {
            "data_contract.ticket.triggered": {
                "fields": {"source_id": F(P("ID"))},
                "rationale": "Workflow trigger payload.",
            },
            "data_contract.ticket.notice": {
                "fields": {"notice_id": F(P("ID"))},
                "rationale": "Workflow success payload.",
            },
        },
        "entity_types": {
            ET("Problem"): {
                "name": "Problem",
                "fields": {"code": F(P("Text")), "message": F(P("Text"))},
                "rationale": "Problem result.",
            }
        },
        "application_actions": {
            "application_action.ticket.notify": {
                "action_kind": "command",
                "input": {"source_id": P("ID"), "title": P("Text")},
                "outcomes": {
                    "sent": {"kind": "success", "result": D("data_contract.ticket.notice")},
                    "failed": {"kind": "failure", "result": M("Problem")},
                },
                "rationale": "Sends a notice.",
            }
        },
        "domain_events": {
            "domain_event.ticket.triggered": {
                "payload_schema": D("data_contract.ticket.triggered"),
                "rationale": "Ticket trigger domain event.",
            }
        },
        "workflows": {
            "workflow.ticket.notice": {
                "trigger": {"domain_event": "domain_event.ticket.triggered"},
                "outcomes": {
                    "completed": {"kind": "success", "result": D("data_contract.ticket.notice")},
                    "failed": {"kind": "failure", "result": M("Problem")},
                },
                "steps": [
                    {
                        "id": "notify",
                        "application_action": "application_action.ticket.notify",
                        "input_bindings": {
                            "source_id": {"from": "$trigger.payload.source_id"},
                            "title": {"value": "Literal title"},
                        },
                        "outcome_transitions": {
                            "sent": {"complete_as": "completed"},
                            "failed": {"fail_as": "failed"},
                        },
                    }
                ],
                "rationale": "Workflow exercises explicit binding values.",
            }
        },
    }
    contract = compile_author(author)
    bindings = contract["workflows"]["workflow.ticket.notice"]["steps"][0]["input_bindings"]
    assert bindings["source_id"] == {"from": "$trigger.payload.source_id"}
    assert bindings["title"] == {"value": "Literal title"}


def test_state_machine_empty_message_directions_can_be_omitted() -> None:
    author = _author()
    activity = _item(author, "state_machines", "state_machine.project.activity")

    assert "emits" not in activity["signals"]
    contract = compile_source(author)

    assert contract["state_machines"]["state_machine.project.activity"]["signals"]["emits"] == {"local_signals": {}}


def test_author_source_prunes_empty_message_directions() -> None:
    author = _author()
    activity = _item(author, "state_machines", "state_machine.project.activity")
    activity["signals"]["emits"] = {}

    pruned = author_from_source(author)

    assert "emits" not in pruned["state_machines"]["state_machine.project.activity"]["signals"]


def test_empty_state_machine_signal_payloads_can_be_omitted() -> None:
    author = _author()
    activity = _item(author, "state_machines", "state_machine.project.activity")

    assert activity["signals"]["accepts"]["local_signals"]["selection_cleared"] == {}
    contract = compile_source(author)

    assert contract["state_machines"]["state_machine.project.activity"]["signals"]["accepts"]["local_signals"]["selection_cleared"]["payload_schema"] == {}


def test_author_source_prunes_empty_local_signal_payloads() -> None:
    author = _author()
    activity = _item(author, "state_machines", "state_machine.project.activity")
    activity["signals"]["accepts"]["local_signals"]["selection_cleared"]["payload_schema"] = {}

    pruned = author_from_source(author)

    assert pruned["state_machines"]["state_machine.project.activity"]["signals"]["accepts"]["local_signals"]["selection_cleared"] == {}


def test_state_machine_accepted_messages_must_be_used_by_transition() -> None:
    author = _author()
    activity = _item(author, "state_machines", "state_machine.project.activity")
    activity["signals"]["accepts"]["local_signals"]["unused"] = {}
    with pytest.raises(ContractError, match=r"state machine state_machine\.project\.activity declares accepted state-machine signal without transition: .*local_signal\.unused"):
        compile_source(author)


def test_state_machine_local_messages_reject_global_looking_names() -> None:
    author = _author()
    activity = _item(author, "state_machines", "state_machine.project.activity")
    activity["signals"]["accepts"]["local_signals"]["local_signal.global"] = {}
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)


def test_state_machine_transition_messages_must_be_declared_as_accepted() -> None:
    author = _author()
    activity = _item(author, "state_machines", "state_machine.project.activity")
    del activity["signals"]["accepts"]["local_signals"]["selection_cleared"]
    with pytest.raises(ContractError, match=r"state machine state_machine\.project\.activity transition signal references undeclared state-machine signal: local_signal\.selection_cleared"):
        compile_source(author)


def test_state_machine_data_events_require_data_binding() -> None:
    author = _author()
    detail = _item(author, "state_machines", "state_machine.project.detail")
    del detail["view_states"]["loading"]["data_loaders"]
    del detail["view_states"]["ready"]["data_loaders"]
    detail["view_states"]["ready"].pop("field_slots")
    with pytest.raises(ContractError, match=r"state machine state_machine\.project\.detail transition uses data-refresh signal without state machine or source-state data: data_refresh_signal\.project_loaded"):
        compile_source(author)


def test_state_machine_transition_requires_rationale_when_audit_card_would_be_empty() -> None:
    author = _author()
    activity = _item(author, "state_machines", "state_machine.project.activity")
    cleared = next(transition for transition in activity["transitions"] if transition["on"] == {"local_signal": "selection_cleared"})
    cleared.pop("effects")
    with pytest.raises(
        ContractError,
            match=r"state machine state_machine\.project\.activity transition local_signal\.selection_cleared from ready to empty must declare rationale, data, or effects",
    ):
        compile_source(author)


def test_state_machine_transition_rationale_can_explain_otherwise_empty_audit_card() -> None:
    author = _author()
    activity = _item(author, "state_machines", "state_machine.project.activity")
    cleared = next(transition for transition in activity["transitions"] if transition["on"] == {"local_signal": "selection_cleared"})
    cleared.pop("effects")
    cleared["rationale"] = "Clearing the selection returns the activity state machine to its empty state."
    contract = compile_source(author)
    compiled = next(
        transition
        for transition in contract["state_machines"]["state_machine.project.activity"]["transitions"]
        if transition["on"] == {"local_signal": "selection_cleared"}
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
        match=r"state machine state_machine\.project\.list data_loader list_projects input_bindings\.workspace_id references unknown \$context field: workspace_id",
    ):
        compile_source(author)


def test_state_machine_field_slots_require_data_source() -> None:
    author = _author()
    activity = _item(author, "state_machines", "state_machine.project.activity")
    del activity["view_states"]["ready"]["data_loaders"]
    with pytest.raises(
        ContractError,
        match=r"state machine state_machine\.project\.activity\.ready field slot assignee has no data source",
    ):
        compile_source(author)


def test_state_machine_data_source_must_be_query_like_operation() -> None:
    author = _author()
    activity = _item(author, "state_machines", "state_machine.project.activity")
    activity["view_states"]["ready"]["data_loaders"]["read_activity"]["application_action"] = "application_action.project.submit"
    with pytest.raises(
        ContractError,
        match=r"state machine state_machine\.project\.activity\.ready data_loader read_activity application action must have action_kind: query",
    ):
        compile_source(author)


def test_rationale_is_plain_bounded_text() -> None:
    author = _author()
    assert isinstance(author["entity_types"]["entity_type.project"]["rationale"], str)
    bad = _author()
    bad["entity_types"]["entity_type.project"]["rationale"] = {"text": "object rationale", "kind": "explicit", "confidence": "high"}
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(bad)
    bad = _author()
    bad["entity_types"]["entity_type.project"]["rationale"] = "x" * 281
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
    body.setdefault("input", {})["workspace_id"] = {"from": "$fixture.workspace.missing"}
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


def test_html_slots_and_textual_widgets_must_reference_declared_layout_targets() -> None:
    author = _author()
    state = _item(author, "state_machines", "state_machine.project.list")["view_states"]["ready"]
    state["renderers"] = {
        "html": {
            "layout": {"regions": {"main": {"element": "section", "must_render": True}}},
            "presentation": {
                "slots": [
                    {
                        "binding": {"text_slot": "heading"},
                        "component": "text",
                        "element": "h2",
                        "region": "ghost",
                    }
                ]
            },
        }
    }
    with pytest.raises(ContractError, match="HTML slot references undeclared layout region"):
        compile_source(author)

    author = _author()
    state = _item(author, "state_machines", "state_machine.project.list")["view_states"]["ready"]
    state["renderers"] = {
        "textual": {
            "layout": {"containers": {"main": {"id": "main", "container_class": "Container", "must_render": True}}},
            "presentation": {
                "widgets": [
                    {
                        "id": "heading",
                        "widget_class": "Static",
                        "binding": {"text_slot": "heading"},
                        "container": "ghost",
                    }
                ]
            },
        }
    }
    with pytest.raises(ContractError, match="Textual widget references undeclared layout container"):
        compile_source(author)


def test_presentation_rejects_undeclared_textual_action_binding() -> None:
    author = _author()
    state = _item(author, "state_machines", "state_machine.project.list")["view_states"]["ready"]
    state["renderers"] = {
        "textual": {
            "presentation": {
                "widgets": [{"id": "delete", "widget_class": "Button", "binding": {"action_binding": "delete"}, "container": "main"}],
            },
            "layout": {
                "containers": {"main": {"id": "main", "container_class": "Container", "must_render": True}},
            }
        }
    }
    with pytest.raises(ContractError, match="action_binding binding is not declared"):
        compile_source(author)


def test_view_state_rejects_legacy_application_action_array() -> None:
    author = _author()
    state = _item(author, "state_machines", "state_machine.project.list")["view_states"]["ready"]
    state["available_" + "application_actions"] = ["application_action.project.create"]
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)


def test_action_binding_keys_are_local_names() -> None:
    author = _author()
    state = _item(author, "state_machines", "state_machine.project.list")["view_states"]["ready"]
    state["action_bindings"]["application_action.create"] = state["action_bindings"].pop("create")
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)


def test_legacy_state_machine_action_and_query_fields_are_rejected() -> None:
    author = _author()
    state = _item(author, "state_machines", "state_machine.project.list")["view_states"]["ready"]
    state["available_" + "application_actions"] = ["application_action.project.create"]
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)

    author = _author()
    state_machine = _item(author, "state_machines", "state_machine.project.list")
    state_machine["query_" + "dependencies"] = ["application_action.project.list"]
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)

    author = _author()
    state = _item(author, "state_machines", "state_machine.project.activity")["view_states"]["ready"]
    state["query_" + "dependencies"] = ["application_action.project.read"]
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)


def test_renderer_slot_binding_accepts_action_binding_and_rejects_application_action_ref() -> None:
    author = _author()
    board = _item(author, "state_machines", "state_machine.project.board")
    board["signals"] = {"accepts": {"data_refresh_signals": {"application_action_completed": {}}}}
    board["transitions"] = [{"from": "ready", "to": "ready", "on": {"data_refresh_signal": "application_action_completed"}}]
    state = board["view_states"]["ready"]
    state["action_bindings"] = {
        "create": {
            "application_action": "application_action.project.create",
            "input_bindings": {
                "customer": {"value": "Atlas Foods"},
                "priority": {"value": "High"},
                "title": {"value": "Replace rooftop condenser fan"},
                "workspace_id": {"from": "$context.workspace_id"},
            },
            "outcome_effects": {
                "created": {"raise": {"data_refresh_signal": "application_action_completed"}},
                "forbidden": {"raise": {"data_refresh_signal": "application_action_completed"}},
                "unauthenticated": {"raise": {"data_refresh_signal": "application_action_completed"}},
                "validation_failed": {"raise": {"data_refresh_signal": "application_action_completed"}},
            },
        }
    }
    state["renderers"]["textual"]["presentation"] = {
        "widgets": [{"id": "create", "widget_class": "Button", "binding": {"action_binding": "create"}, "container": "nav"}],
    }
    compile_source(author)

    bad = _author()
    board = _item(bad, "state_machines", "state_machine.project.board")
    board["signals"] = {"accepts": {"data_refresh_signals": {"application_action_completed": {}}}}
    board["transitions"] = [{"from": "ready", "to": "ready", "on": {"data_refresh_signal": "application_action_completed"}}]
    state = board["view_states"]["ready"]
    state["action_bindings"] = {
        "create": {
            "application_action": "application_action.project.create",
            "input_bindings": {
                "customer": {"value": "Atlas Foods"},
                "priority": {"value": "High"},
                "title": {"value": "Replace rooftop condenser fan"},
                "workspace_id": {"from": "$context.workspace_id"},
            },
            "outcome_effects": {
                "created": {"raise": {"data_refresh_signal": "application_action_completed"}},
                "forbidden": {"raise": {"data_refresh_signal": "application_action_completed"}},
                "unauthenticated": {"raise": {"data_refresh_signal": "application_action_completed"}},
                "validation_failed": {"raise": {"data_refresh_signal": "application_action_completed"}},
            },
        }
    }
    state["renderers"]["textual"]["presentation"] = {
        "widgets": [{"id": "create", "widget_class": "Button", "binding": {"application_action": "application_action.project.create"}, "container": "nav"}],
    }
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(bad)


def test_action_binding_application_action_must_resolve() -> None:
    author = _author()
    invocation = _item(author, "state_machines", "state_machine.project.list")["view_states"]["ready"]["action_bindings"]["submit"]
    invocation["application_action"] = "application_action.project.missing"
    with pytest.raises(ContractError, match=r"action_binding submit references unknown application action application_action\.project\.missing"):
        compile_source(author)


def test_action_binding_routes_must_cover_exact_action_outcomes() -> None:
    author = _author()
    effects = _item(author, "state_machines", "state_machine.project.list")["view_states"]["ready"]["action_bindings"]["submit"]["outcome_effects"]
    del effects["not_found"]
    with pytest.raises(ContractError, match=r"outcome_effects must exactly map application action outcomes: missing: not_found"):
        compile_source(author)

    author = _author()
    effects = _item(author, "state_machines", "state_machine.project.list")["view_states"]["ready"]["action_bindings"]["submit"]["outcome_effects"]
    effects["ghost"] = {"no_local_effect": {"reason": "state_unchanged"}}
    with pytest.raises(ContractError, match=r"outcome_effects must exactly map application action outcomes: extra: ghost"):
        compile_source(author)


def test_action_binding_rejects_legacy_non_routing_route() -> None:
    author = _author()
    effect = _item(author, "state_machines", "state_machine.project.list")["view_states"]["ready"]["action_bindings"]["submit"]["outcome_effects"]["forbidden"]
    effect.clear()
    effect["ig" + "nore"] = True
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)


def test_action_binding_failure_no_local_effect_requires_reason_and_rationale() -> None:
    author = _author()
    effect = _item(author, "state_machines", "state_machine.project.list")["view_states"]["ready"]["action_bindings"]["submit"]["outcome_effects"]["transition_not_allowed"]
    effect.clear()
    effect["no_local_effect"] = {"reason": "intentionally_unobservable"}
    with pytest.raises(ContractError, match=r"failure outcome no_local_effect must declare rationale"):
        compile_source(author)

    author = _author()
    effect = _item(author, "state_machines", "state_machine.project.list")["view_states"]["ready"]["action_bindings"]["submit"]["outcome_effects"]["transition_not_allowed"]
    effect.clear()
    effect["no_local_effect"] = {"reason": "handled_by_response_surface", "rationale": "test effect"}
    with pytest.raises(ContractError, match=r"handled_by_response_surface requires an adapter or renderer response surface"):
        compile_source(author)


def test_action_binding_failure_no_local_effect_rejects_state_unchanged() -> None:
    author = _author()
    effect = _item(author, "state_machines", "state_machine.project.list")["view_states"]["ready"]["action_bindings"]["submit"]["outcome_effects"]["transition_not_allowed"]
    effect.clear()
    effect["no_local_effect"] = {"reason": "state_unchanged", "rationale": "Invalid submit leaves the list unchanged."}
    with pytest.raises(ContractError, match=r"failure outcome no_local_effect must use reason handled_by_response_surface with a proven response surface or intentionally_unobservable with rationale"):
        compile_source(author)


def test_action_binding_raised_signals_must_be_declared_locally() -> None:
    author = _author()
    effect = _item(author, "state_machines", "state_machine.project.list")["view_states"]["ready"]["action_bindings"]["submit"]["outcome_effects"]["submitted"]
    effect["raise"]["data_refresh_signal"] = "ghost"
    with pytest.raises(ContractError, match=r"raise references undeclared state-machine signal: data_refresh_signal\.ghost"):
        compile_source(author)

    author = _author()
    effect = _item(author, "state_machines", "state_machine.project.list")["view_states"]["ready"]["action_bindings"]["submit"]["outcome_effects"]["transition_not_allowed"]
    effect["raise"]["local_signal"] = "ghost"
    with pytest.raises(ContractError, match=r"raise references undeclared state-machine signal: local_signal\.ghost"):
        compile_source(author)


def test_action_binding_payload_and_input_bindings_are_type_checked() -> None:
    author = _author()
    effect = _item(author, "state_machines", "state_machine.project.list")["view_states"]["ready"]["action_bindings"]["submit"]["outcome_effects"]["transition_not_allowed"]
    del effect["raise"]["payload_bindings"]["message"]
    with pytest.raises(ContractError, match=r"payload_bindings must exactly match payload fields: missing: message"):
        compile_source(author)

    author = _author()
    invocation = _item(author, "state_machines", "state_machine.project.list")["view_states"]["ready"]["action_bindings"]["submit"]
    del invocation["input_bindings"]["project_id"]
    with pytest.raises(ContractError, match=r"input_bindings must exactly bind target input: missing: project_id"):
        compile_source(author)


def test_action_binding_literal_actor_ids_emit_lint_warning() -> None:
    author = _author()
    invocation = _item(author, "state_machines", "state_machine.project.detail")["view_states"]["ready"]["action_bindings"]["approve"]
    invocation["input_bindings"]["approved_by"] = {"value": "reviewer_1"}
    with pytest.warns(ContractLintWarning, match=r"approved_by uses a literal actor/user id"):
        compile_source(author)


def test_mutation_routes_raising_loaded_signal_emit_lint_warning() -> None:
    author = _author()
    effect = _item(author, "state_machines", "state_machine.project.list")["view_states"]["ready"]["action_bindings"]["create"]["outcome_effects"]["created"]
    effect["raise"]["data_refresh_signal"] = "projects_loaded"
    with pytest.warns(ContractLintWarning, match=r"raises data-refresh signal 'projects_loaded' from a mutation"):
        compile_source(author)


def test_action_outcome_emits_is_not_local_state_machine_routing() -> None:
    author = _author()
    effects = _item(author, "state_machines", "state_machine.project.list")["view_states"]["ready"]["action_bindings"]["create"]["outcome_effects"]
    del effects["created"]
    with pytest.raises(ContractError, match=r"outcome_effects must exactly map application action outcomes: missing: created"):
        compile_source(author)


def test_action_binding_routes_are_local_per_view_state() -> None:
    contract = compile_source(_author())
    empty_create = contract["state_machines"]["state_machine.project.list"]["view_states"]["empty"]["action_bindings"]["create"]
    ready_create = contract["state_machines"]["state_machine.project.list"]["view_states"]["ready"]["action_bindings"]["create"]
    assert empty_create["application_action"] == ready_create["application_action"] == "application_action.project.create"
    assert "raise" in empty_create["outcome_effects"]["validation_failed"]
    assert ready_create["outcome_effects"]["validation_failed"] == {
        "no_local_effect": {
            "reason": "handled_by_response_surface",
            "rationale": "The ready list keeps focus while the response surface shows validation errors.",
        }
    }


def test_data_loader_application_action_and_routes_are_validated() -> None:
    author = _author()
    invocation = _item(author, "state_machines", "state_machine.project.list")["data_loaders"]["list_projects"]
    invocation["application_action"] = "application_action.project.missing"
    with pytest.raises(ContractError, match=r"data_loader list_projects references unknown application action application_action\.project\.missing"):
        compile_source(author)

    author = _author()
    effects = _item(author, "state_machines", "state_machine.project.list")["data_loaders"]["list_projects"]["outcome_effects"]
    del effects["unavailable"]
    with pytest.raises(ContractError, match=r"data_loader list_projects outcome_effects must exactly map query application action outcomes: missing: unavailable"):
        compile_source(author)

    author = _author()
    effects = _item(author, "state_machines", "state_machine.project.list")["data_loaders"]["list_projects"]["outcome_effects"]
    effects["ghost"] = {"no_local_effect": {"reason": "state_unchanged"}}
    with pytest.raises(ContractError, match=r"data_loader list_projects outcome_effects must exactly map query application action outcomes: extra: ghost"):
        compile_source(author)


def test_data_loader_bindings_context_updates_and_signals_are_validated() -> None:
    author = _author()
    invocation = _item(author, "state_machines", "state_machine.project.list")["data_loaders"]["list_projects"]
    del invocation["input_bindings"]["workspace_id"]
    with pytest.raises(ContractError, match=r"data_loader list_projects input_bindings must exactly bind target input: missing: workspace_id"):
        compile_source(author)

    author = _author()
    effect = _item(author, "state_machines", "state_machine.project.list")["data_loaders"]["list_projects"]["outcome_effects"]["listed"]
    effect["conditional_effects"][0]["context_updates"]["ghost"] = {"value": "nope"}
    with pytest.raises(ContractError, match=r"context_updates references undeclared context field: ghost"):
        compile_source(author)

    author = _author()
    effect = _item(author, "state_machines", "state_machine.project.list")["data_loaders"]["list_projects"]["outcome_effects"]["listed"]
    effect["conditional_effects"][1]["raise"]["data_refresh_signal"] = "ghost"
    with pytest.raises(ContractError, match=r"raise references undeclared state-machine signal: data_refresh_signal\.ghost"):
        compile_source(author)

    author = _author()
    effect = _item(author, "state_machines", "state_machine.project.detail")["view_states"]["ready"]["data_loaders"]["read_project"]["outcome_effects"]["not_found"]
    effect["raise"]["local_signal"] = "ghost"
    with pytest.raises(ContractError, match=r"raise references undeclared state-machine signal: local_signal\.ghost"):
        compile_source(author)


def test_data_loader_load_policy_and_application_action_purity_are_validated() -> None:
    author = _author()
    invocation = _item(author, "state_machines", "state_machine.project.list")["data_loaders"]["list_projects"]
    invocation["load"] = {"refresh_on": [{"data_refresh_signal": "ghost"}]}
    with pytest.raises(ContractError, match=r"load\.refresh_on references undeclared state-machine signal: data_refresh_signal\.ghost"):
        compile_source(author)

    author = _author()
    author["application_actions"]["application_action.project.list"]["outcomes"]["listed"]["emits"] = [
        {"domain_event": "domain_event.project.listed", "payload_source": "$outcome.result"}
    ]
    author["domain_events"]["domain_event.project.listed"] = {
        "payload_schema": {"array": {"entity_type": ET("Project")}},
        "rationale": "List domain events are deliberately invalid for data loaders.",
    }
    with pytest.raises(ContractError, match=r"Query application action application_action\.project\.list must not emit domain events: .*listed"):
        compile_source(author)

    author = _author()
    author["application_actions"]["application_action.project.list"]["updates"] = [ET("Project")]
    with pytest.raises(ContractError, match=r"Application action application_action\.project\.list action_kind query does not support effects: .*updates"):
        compile_source(author)


def test_data_loader_success_cannot_be_semantically_inert() -> None:
    author = _author()
    effect = _item(author, "state_machines", "state_machine.project.list")["data_loaders"]["list_projects"]["outcome_effects"]["listed"]
    effect.clear()
    effect["no_local_effect"] = {"reason": "state_unchanged"}
    with pytest.raises(ContractError, match=r"successful query no_local_effect must bind/cache data"):
        compile_source(author)


def test_data_loader_query_refresh_requires_explicit_result_or_context_refresh() -> None:
    author = _author()
    effect = _item(author, "state_machines", "state_machine.project.list")["data_loaders"]["list_projects"]["outcome_effects"]["listed"]
    effect.clear()
    effect["no_local_effect"] = {"reason": "handled_by_query_refresh"}
    with pytest.raises(ContractError, match=r"handled_by_query_refresh requires an explicit query result binding or context refresh"):
        compile_source(author)


def test_data_loader_collection_empty_and_non_empty_routes_are_explicit() -> None:
    contract = compile_source(_author())
    effect = contract["state_machines"]["state_machine.project.list"]["data_loaders"]["list_projects"]["outcome_effects"]["listed"]
    branches = {next(iter(branch["when"])): branch["raise"]["data_refresh_signal"] for branch in effect["conditional_effects"]}
    assert branches == {"result_empty": "project_collection_empty", "result_non_empty": "projects_loaded"}

    author = _author()
    effect = _item(author, "state_machines", "state_machine.project.list")["data_loaders"]["list_projects"]["outcome_effects"]["listed"]
    effect["conditional_effects"] = [effect["conditional_effects"][0]]
    with pytest.raises(ContractError, match=r"must declare both result_empty and result_non_empty branches"):
        compile_source(author)

    author = _author()
    effect = _item(author, "state_machines", "state_machine.project.list")["data_loaders"]["list_projects"]["outcome_effects"]["listed"]
    effect["conditional_effects"][0]["raise"]["data_refresh_signal"] = "projects_loaded"
    with pytest.raises(ContractError, match=r"empty-collection signal data_refresh_signal\.project_collection_empty without an explicit query outcome effect raising it"):
        compile_source(author)


def test_query_empty_non_empty_conditions_require_array_results() -> None:
    author = _author()
    effect = _item(author, "state_machines", "state_machine.project.detail")["view_states"]["loading"]["data_loaders"]["read_project"]["outcome_effects"]["found"]
    effect.clear()
    effect["conditional_effects"] = [
        {
            "when": {"result_empty": True},
            "result_binding": {"data_key": "project", "from": {"from": "$outcome.result"}},
            "raise": {"data_refresh_signal": "project_loaded"},
        },
        {
            "when": {"result_non_empty": True},
            "result_binding": {"data_key": "project", "from": {"from": "$outcome.result"}},
            "raise": {"data_refresh_signal": "project_loaded"},
        },
    ]
    with pytest.raises(ContractError, match=r"valid only for array/list query results"):
        compile_source(author)


def test_state_machine_level_query_scope_is_explicit() -> None:
    author = _author()
    del _item(author, "state_machines", "state_machine.project.board")["data_loaders"]["list_board"]["result_scope"]
    with pytest.raises(ContractError, match=r"state-machine-level data_loader must declare result_scope"):
        compile_source(author)

    author = _author()
    invocation = _item(author, "state_machines", "state_machine.project.board")["data_loaders"]["list_board"]
    invocation["result_scope"] = "local"
    with pytest.raises(ContractError, match=r"result_binding with no_local_effect must declare result_scope shared or prefetch"):
        compile_source(author)

    author = _author()
    invocation = _item(author, "state_machines", "state_machine.project.board")["data_loaders"]["list_board"]
    del invocation["rationale"]
    with pytest.raises(ContractError, match=r"result_scope shared must declare rationale"):
        compile_source(author)


def test_result_bound_without_signal_requires_consumed_result_data() -> None:
    author = _author()
    detail = _item(author, "state_machines", "state_machine.project.detail")
    detail["view_states"]["ready"].pop("field_slots")
    with pytest.raises(ContractError, match=r"result_bound_without_signal requires consumed result data or declared shared/prefetch ownership"):
        compile_source(author)


def test_field_slot_sources_must_be_unambiguous() -> None:
    author = _author()
    detail = _item(author, "state_machines", "state_machine.project.detail")
    owner_query = copy.deepcopy(detail["view_states"]["loading"]["data_loaders"]["read_project"])
    owner_query["load"] = {"on_start": True}
    owner_query["result_scope"] = "local"
    detail.setdefault("data_loaders", {})["read_project_owner"] = owner_query
    with pytest.raises(ContractError, match=r"field slot assignee has ambiguous data sources"):
        compile_source(author)


def test_data_loader_load_policy_is_scope_sensitive() -> None:
    author = _author()
    invocation = _item(author, "state_machines", "state_machine.project.list")["data_loaders"]["list_projects"]
    invocation["load"] = {"on_enter": True}
    with pytest.raises(ContractError, match=r"state-machine-level load policy must use on_start or on_mount, not on_enter"):
        compile_source(author)

    author = _author()
    invocation = _item(author, "state_machines", "state_machine.project.detail")["view_states"]["loading"]["data_loaders"]["read_project"]
    invocation["load"] = {"on_start": True}
    with pytest.raises(ContractError, match=r"view-state-level load policy must use on_enter, not on_start or on_mount"):
        compile_source(author)


def test_data_loader_ids_cannot_shadow_state_machine_scope() -> None:
    author = _author()
    list_fsm = _item(author, "state_machines", "state_machine.project.list")
    list_fsm["view_states"]["ready"]["data_loaders"] = {
        "list_projects": {
            "application_action": "application_action.project.list",
            "input_bindings": {"workspace_id": {"from": "$context.workspace_id"}},
            "outcome_effects": {
                "listed": {
                    "result_binding": {"data_key": "projects", "from": {"from": "$outcome.result"}},
                    "no_local_effect": {"reason": "result_bound_without_signal"},
                },
                "forbidden": {"no_local_effect": {"reason": "handled_by_response_surface", "rationale": "Shadow test."}},
                "unauthenticated": {"no_local_effect": {"reason": "handled_by_response_surface", "rationale": "Shadow test."}},
                "unavailable": {"no_local_effect": {"reason": "handled_by_response_surface", "rationale": "Shadow test."}},
            },
        }
    }
    with pytest.raises(ContractError, match=r"data_loaders duplicate state-machine-scope ids: .*list_projects"):
        compile_source(author)


def test_data_loader_routes_are_local_per_state() -> None:
    contract = compile_source(_author())
    loading_read = contract["state_machines"]["state_machine.project.detail"]["view_states"]["loading"]["data_loaders"]["read_project"]
    ready_read = contract["state_machines"]["state_machine.project.detail"]["view_states"]["ready"]["data_loaders"]["read_project"]
    assert loading_read["application_action"] == ready_read["application_action"] == "application_action.project.read"
    assert loading_read["outcome_effects"]["found"] == {
        "result_binding": {"data_key": "project", "from": {"from": "$outcome.result"}},
        "raise": {"data_refresh_signal": "project_loaded"},
    }
    assert ready_read["outcome_effects"]["found"] == {
        "result_binding": {"data_key": "project", "from": {"from": "$outcome.result"}},
        "no_local_effect": {"reason": "result_bound_without_signal"},
    }


def test_missing_referenced_application_action_is_rejected() -> None:
    author = _author()
    del author["application_actions"]["application_action.project.create"]
    with pytest.raises(ContractError, match="unknown application action|application action references"):
        compile_source(author)


def test_state_machine_composition_rejects_unknown_mounted_state_machine() -> None:
    author = _author()
    state_machine = _item(author, "state_machines", "state_machine.project.board")["view_states"]["ready"]
    state_machine["child_state_machines"][0]["state_machine"] = "state_machine.project.ghost"
    with pytest.raises(ContractError, match="mounts unknown state machine"):
        compile_source(author)


def test_state_machine_composition_rejects_unknown_sync_target_local_signal() -> None:
    author = _author()
    state_machine = _item(author, "state_machines", "state_machine.project.board")["view_states"]["ready"]
    for effect in state_machine["signal_sync_rules"][0]["effects"]:
        if "send" in effect:
            effect["send"]["local_signal"] = "ghost_message"
            break
    with pytest.raises(ContractError, match="sync sends local_signal the target does not accept"):
        compile_source(author)


def test_state_machine_emit_data_must_exactly_match_emitted_local_signal_payload() -> None:
    author = _author()
    transition = next(
        transition
        for transition in _item(author, "state_machines", "state_machine.project.list")["transitions"]
        if transition.get("effects") and "emit" in transition["effects"][0]
    )
    transition["effects"][0]["emit"]["payload_bindings"] = {}
    with pytest.raises(ContractError, match=r"transition emit project_selected payload_bindings must exactly match payload fields: missing: project_id"):
        compile_source(author)


def test_sync_send_data_must_exactly_match_target_local_signal_payload() -> None:
    author = _author()
    state_machine = _item(author, "state_machines", "state_machine.project.board")["view_states"]["ready"]
    send = next(effect["send"] for effect in state_machine["signal_sync_rules"][0]["effects"] if "send" in effect)
    send["payload_bindings"] = {}
    with pytest.raises(ContractError, match=r"sync send selection_changed to detail payload_bindings must exactly match payload fields: missing: project_id"):
        compile_source(author)


def test_sync_send_data_must_match_target_local_signal_payload_type() -> None:
    author = _author()
    state_machine = _item(author, "state_machines", "state_machine.project.board")["view_states"]["ready"]
    send = next(effect["send"] for effect in state_machine["signal_sync_rules"][0]["effects"] if "send" in effect)
    send["payload_bindings"]["project_id"] = {"value": 1}
    with pytest.raises(ContractError, match=r"payload_bindings\.project_id literal value is not compatible with ID"):
        compile_source(author)


def test_state_machine_signal_payloads_must_be_consistent_across_state_machines() -> None:
    author = _author()
    activity = _item(author, "state_machines", "state_machine.project.activity")
    activity["signals"]["accepts"]["local_signals"]["selection_changed"]["payload_schema"]["project_id"] = P("Text")
    with pytest.raises(ContractError, match=r"sync send selection_changed to activity payload_bindings\.project_id type mismatch"):
        compile_source(author)


def test_state_machine_signal_direction_must_be_unambiguous() -> None:
    author = _author()
    state_machine = _item(author, "state_machines", "state_machine.project.list")
    state_machine["signals"]["emits"]["local_signals"]["project_select"] = {"payload_schema": {"project_id": P("ID")}}
    with pytest.raises(ContractError, match=r"declares state-machine signal as both accepted and emitted: .*local_signal\.project_select"):
        compile_source(author)


def test_signal_names_that_match_view_states_emit_lint_warnings() -> None:
    author = {
        "project": "signal_lint",
        "state_machines": {
            "state_machine.panel": {
                "signals": {"accepts": {"local_signals": {"ready": {}}}},
                "initial_view_state": "ready",
                "view_states": {"ready": {}},
                "transitions": [
                    {
                        "from": "ready",
                        "to": "ready",
                        "on": {"local_signal": "ready"},
                        "rationale": "Self-transition is present only to exercise lint warnings.",
                    }
                ],
                "rationale": "Synthetic state machine exercises signal-name linting.",
            }
        },
    }
    with pytest.warns(ContractLintWarning) as warnings_record:
        compile_author(author)
    messages = [str(item.message) for item in warnings_record]
    assert any("signal 'ready' also names a view state" in message for message in messages)
    assert any("transition trigger 'ready' matches target view state" in message for message in messages)


def test_composed_test_case_rejects_unknown_state_machine_instance() -> None:
    author = _author()
    test_case = _item(author, "test_cases", "test_case.project.board.ready")
    test_case["then"]["state_machine"]["instances"]["ghost"] = {"view_state": "ready"}
    with pytest.raises(ContractError, match="unknown state machine instance"):
        compile_source(author)


def _api_only_author() -> dict:
    return {
        "project": "api_only",
        "entity_types": {
            ET("Ticket"): {
                "name": "Ticket",
                "fields": {"id": F(P("ID")), "title": F(P("Text"))},
                "rationale": _rationale("ticket entity_type"),
            },
            ET("Problem"): {
                "name": "Problem",
                "fields": {"code": F(P("Text")), "message": F(P("Text"))},
                "rationale": _rationale("problem entity_type"),
            },
        },
        "application_actions": {
            "application_action.ticket.create": {
                "action_kind": "command",
                "creates": [ET("Ticket")],
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
                    "http_api": {
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
                    "application_action": {"ref": "application_action.ticket.create", "input_bindings": {"title": {"from": "$input.body.title"}}},
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
    assert "spec/generated/product_interfaces/integration_messages.asyncapi.yaml" not in paths
    assert "spec/generated/product_interfaces/workflow.cwl.yaml" not in paths


def test_authoring_layers_reject_irrelevant_ui_targets() -> None:
    from pyspec_contract.layers import parse_layers

    author = _api_only_author()
    author["state_machines"] = {
        "state_machine.ticket.list": {
            "entity_type": ET("Ticket"),
            "context": {},
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
        "adapter": {"html_route": {"path": "/tickets"}},
        "target": {"state_machine": {"ref": "state_machine.ticket.list", "renderer": "html"}},
    }
    with pytest.raises(ContractError, match="entry point adapter html_route requires ui"):
        compile_author(author, layers=parse_layers("core,http"))


def test_cli_state_machine_entry_must_provide_required_context_args() -> None:
    author = _author()
    del author["entry_points"]["entry_point.cli.project.board"]["adapter"]["cli"]["input"]["args"]
    with pytest.raises(ContractError, match=r"Entry entry_point.cli\.project\.board input\.args must include required state machine context inputs: \['workspace_id'\]"):
        compile_source(author)


def test_entry_rejects_renderer_irrelevant_fields() -> None:
    author = _author()
    author["entry_points"]["entry_point.html.project.board"]["adapter"]["html_route"]["input"]["args"] = {"workspace_id": P("ID")}
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


def test_cli_delegation_bindings_use_outer_input_shape() -> None:
    author = _author()
    del author["entry_points"]["entry_point.cli.project.approve"]["adapter"]["cli"]["input"]["args"]
    with pytest.raises(ContractError, match=r"target\.entry_point\.input_bindings\.body\.approved_by references unknown \$input field: args"):
        compile_source(author)


def test_entry_target_bindings_must_exactly_match_target_input() -> None:
    author = _author()
    del author["entry_points"]["entry_point.api.project.create"]["target"]["application_action"]["input_bindings"]["title"]
    with pytest.raises(ContractError, match=r"Entry entry_point.api\.project\.create target\.input_bindings must exactly bind target input: missing: title"):
        compile_source(author)


def test_entry_point_response_must_match_renderer_contract() -> None:
    author = _author()
    author["entry_points"]["entry_point.api.project.create"]["adapter"]["http_api"]["responses"]["created"]["body"]["type"] = P("Text")
    with pytest.raises(ContractError, match=r"API entry entry_point.api\.project\.create response created\.body must expose \$outcome\.result as Project"):
        compile_source(author)


def test_action_outcomes_must_have_one_success_and_real_failure_result() -> None:
    author = _author()
    author["application_actions"]["application_action.project.create"]["outcomes"]["validation_failed"]["kind"] = "success"
    with pytest.raises(ContractError, match=r"Application action application_action.project\.create must declare exactly one success outcome"):
        compile_source(author)

    author = _author()
    author["application_actions"]["application_action.project.create"]["outcomes"]["validation_failed"]["result"] = M("Project")
    with pytest.raises(ContractError, match=r"failure outcome validation_failed result must be Problem"):
        compile_source(author)


def test_event_emits_must_map_declared_payload() -> None:
    author = _author()
    author["application_actions"]["application_action.project.approve"]["outcomes"]["approved"]["emits"][0]["payload_bindings"]["approved_by"] = {"from": "$outcome.result"}
    with pytest.raises(ContractError, match=r"emit domain_event.project\.approved mapping approved_by source .*\$outcome\.result.* type must be ID"):
        compile_source(author)


def test_runtime_references_are_context_scoped() -> None:
    author = _author()
    author["entry_points"]["entry_point.api.project.create"]["target"]["application_action"]["input_bindings"]["title"] = {"from": "$trigger.payload.title"}
    with pytest.raises(ContractError, match=r"target\.input_bindings\.title references unavailable runtime root: \$trigger"):
        compile_source(author)


def test_runtime_references_validate_declared_fields() -> None:
    author = _author()
    author["workflows"]["workflow.project.approval_notice"]["steps"][0]["input_bindings"]["project_id"] = {"from": "$trigger.payload.missing"}
    with pytest.raises(ContractError, match=r"input project_id references unknown data_contract\.project\.approved field: missing"):
        compile_source(author)


def test_entry_point_responses_must_map_all_action_outcomes() -> None:
    author = _author()
    del author["entry_points"]["entry_point.api.project.create"]["adapter"]["http_api"]["responses"]["validation_failed"]
    with pytest.raises(ContractError, match=r"Entry entry_point.api\.project\.create responses must exactly map application action outcomes: missing: validation_failed"):
        compile_source(author)


def test_entry_point_responses_must_map_authorization_failure_outcomes() -> None:
    author = _author()
    del author["entry_points"]["entry_point.api.project.create"]["adapter"]["http_api"]["responses"]["forbidden"]
    with pytest.raises(ContractError, match=r"Entry entry_point.api\.project\.create responses must exactly map application action outcomes: missing: forbidden"):
        compile_source(author)

    contract = compile_source(_author())
    api_responses = contract["entry_points"]["entry_point.api.project.approve"]["adapter"]["http_api"]["responses"]
    assert api_responses["unauthenticated"]["status"] == 401
    assert api_responses["forbidden"]["status"] == 403
    cli_handlers = contract["entry_points"]["entry_point.cli.project.approve"]["adapter"]["cli"]["response_handlers"]
    assert cli_handlers["unauthenticated"]["exit_code"] == 4
    assert cli_handlers["forbidden"]["exit_code"] == 5


def test_cli_failure_response_must_use_nonzero_exit_and_stderr() -> None:
    author = _author()
    author["entry_points"]["entry_point.cli.project.approve"]["adapter"]["cli"]["response_handlers"]["transition_not_allowed"]["exit_code"] = 0
    with pytest.raises(ContractError, match=r"CLI entry entry_point.cli\.project\.approve failure response handler transition_not_allowed exit_code must be nonzero"):
        compile_source(author)


def test_entry_point_delegation_compiles_and_generates_refs() -> None:
    contract = compile_source(_author())
    cli_entry = contract["entry_points"]["entry_point.cli.project.approve"]
    assert cli_entry["target"]["entry_point"]["ref"] == "entry_point.api.project.approve"
    assert "entry_point_target.cli.project.approve.entry_point.api.project.approve" in contract["refs"]["entry_point_target"]
    assert "entry_point_delegate.cli.project.approve.to.api.project.approve" in contract["refs"]["entry_point_delegate"]
    assert "cli_response_handler.cli.project.approve.approved" in contract["refs"]["cli_response_handler"]
    assert "runtime_response.cli.project.approve.approved.stdout.project_id" in contract["refs"]["runtime_response"]


def test_entry_point_delegate_target_requires_ref_and_input_bindings() -> None:
    author = _author()
    del author["entry_points"]["entry_point.cli.project.approve"]["target"]["entry_point"]["ref"]
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)

    author = _author()
    del author["entry_points"]["entry_point.cli.project.approve"]["target"]["entry_point"]["input_bindings"]
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)


def test_cli_response_handlers_require_binding_values() -> None:
    author = _author()
    author["entry_points"]["entry_point.cli.project.approve"]["adapter"]["cli"]["response_handlers"]["approved"]["stdout"]["bindings"]["project_id"] = "$response.body.id"
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)


def test_old_cli_delegation_shapes_are_rejected() -> None:
    author = _author()
    cli = author["entry_points"]["entry_point.cli.project.approve"]["adapter"]["cli"]
    cli["invokes"] = {"http_api": "entry_point.api.project.approve"}
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)

    author = _author()
    cli = author["entry_points"]["entry_point.cli.project.approve"]["adapter"]["cli"]
    cli["handling"] = {"approved": {"exit_code": 0}}
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)


def test_entry_point_delegate_ref_must_resolve_and_not_self_delegate() -> None:
    author = _author()
    author["entry_points"]["entry_point.cli.project.approve"]["target"]["entry_point"]["ref"] = "entry_point.api.project.missing"
    with pytest.raises(ContractError, match=r"delegates to unknown entry point entry_point\.api\.project\.missing"):
        compile_source(author)

    author = _author()
    author["entry_points"]["entry_point.cli.project.approve"]["target"]["entry_point"]["ref"] = "entry_point.cli.project.approve"
    with pytest.raises(ContractError, match=r"must not delegate to itself"):
        compile_source(author)


def test_entry_point_delegation_cycles_are_rejected() -> None:
    author = _author()
    author["entry_points"]["entry_point.api.project.approve"]["target"] = {
        "entry_point": {
            "ref": "entry_point.cli.project.approve",
            "input_bindings": {
                "args": {
                    "approved_by": {"from": "$input.body.approved_by"},
                    "project_id": {"from": "$input.path_params.project_id"},
                }
            },
        }
    }
    with pytest.raises(ContractError, match="delegation cycle is invalid"):
        compile_source(author)


def test_delegation_input_bindings_must_match_delegated_adapter_input() -> None:
    author = _author()
    del author["entry_points"]["entry_point.cli.project.approve"]["target"]["entry_point"]["input_bindings"]["body"]["approved_by"]
    with pytest.raises(ContractError, match=r"input_bindings\.body must exactly bind target input: missing: approved_by"):
        compile_source(author)


def test_delegation_input_bindings_use_outer_input_roots() -> None:
    author = _author()
    author["entry_points"]["entry_point.cli.project.approve"]["target"]["entry_point"]["input_bindings"]["path_params"]["project_id"] = {
        "from": "$response.body.id"
    }
    with pytest.raises(ContractError, match=r"input_bindings\.path_params\.project_id references unavailable runtime root: \$response"):
        compile_source(author)


def test_cli_response_handler_names_match_delegated_response_names() -> None:
    author = _author()
    del author["entry_points"]["entry_point.cli.project.approve"]["adapter"]["cli"]["response_handlers"]["forbidden"]
    del author["text_resources"]["text.project.approve.forbidden"]
    with pytest.raises(ContractError, match=r"response_handlers must exactly map delegated entry outcomes: missing: forbidden"):
        compile_source(author)


def test_cli_response_handlers_do_not_restate_http_status_matching() -> None:
    author = _author()
    author["entry_points"]["entry_point.cli.project.approve"]["adapter"]["cli"]["response_handlers"]["approved"]["status"] = 200
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)


def test_response_root_is_only_available_inside_delegated_cli_response_handlers() -> None:
    contract = compile_source(_author())
    assert contract["entry_points"]["entry_point.cli.project.approve"]["adapter"]["cli"]["response_handlers"]["approved"]["stdout"]["bindings"]["project_id"] == {
        "from": "$response.body.id"
    }

    author = _author()
    author["entry_points"]["entry_point.api.project.create"]["target"]["application_action"]["input_bindings"]["title"] = {"from": "$response.body.title"}
    with pytest.raises(ContractError, match=r"target\.input_bindings\.title references unavailable runtime root: \$response"):
        compile_source(author)


def test_cli_retry_policy_requires_retry_safe_delegated_entry_point() -> None:
    author = _author()
    del author["entry_points"]["entry_point.api.project.approve"]["retry_safe"]
    with pytest.raises(ContractError, match=r"retry_policy requires delegated entry point entry_point\.api\.project\.approve and its final target to be retry_safe or query"):
        compile_source(author)


def test_cli_retry_policy_requires_retry_safe_final_operation() -> None:
    author = _author()
    del author["application_actions"]["application_action.project.approve"]["retry_safe"]
    with pytest.raises(ContractError, match=r"retry_policy requires delegated entry point entry_point\.api\.project\.approve and its final target to be retry_safe or query"):
        compile_source(author)


def test_delegated_and_outer_authorization_policies_are_both_evaluated(tmp_path: Path) -> None:
    author = _author()
    outer_policy = "authorization_policy.project.cli_approve"
    author.setdefault("authorization_policies", {})[outer_policy] = {
        "subjects": [{"kind": "actor"}],
        "targets": [{"entry_point": "entry_point.cli.project.approve"}],
        "effect": "allow",
        "conditions": [{"subject_has_role": "reviewer"}, {"input_present": "approved_by"}],
        "rationale": "CLI approval requires reviewer role and an explicit approver argument.",
    }
    author["entry_points"]["entry_point.cli.project.approve"]["authorization_policy"] = outer_policy
    author["test_cases"]["test_case.project.approve.cli.success"] = {
        "archetype": "entry_point_response",
        "feature_tag": "project.approve.cli",
        "subject_ref": {"entry_point": "entry_point.cli.project.approve"},
        "given": {"domain_facts": [{"ref": "fact.project.submitted"}], "seed_fixtures": ["fixture.workspace.reviewer"]},
            "when": {
                "call_entry_point": {
                    "ref": "entry_point.cli.project.approve",
                    "input": {"approved_by": {"from": "$fixture.actor.id"}, "project_id": {"value": "project_submitted_1"}},
                }
            },
        "then": {
            "outcome": "approved",
            "response": {"exit_code": 0},
            "invoked": ["application_action.project.approve"],
            "authorization": {
                "allowed": [
                    {"entry_point": "entry_point.cli.project.approve", "authorization_policy": outer_policy},
                    {"entry_point": "entry_point.api.project.approve", "authorization_policy": "authorization_policy.project.reviewer"},
                    {"application_action": "application_action.project.approve", "authorization_policy": "authorization_policy.project.reviewer"},
                ]
            },
        },
        "title": "Approve through CLI delegation",
        "rationale": "Delegated entry point authorization remains part of the invocation.",
    }
    contract = compile_source(author)
    project = tmp_path / "project"
    copy_project_tree(ROOT, project)
    write_generated(project, contract, render_audit=False)
    driver = ReferenceSpecDriver(project)
    test_case = contract["test_cases"]["test_case.project.approve.cli.success"]
    driver.given("test_case.project.approve.cli.success", test_case)
    driver.when("test_case.project.approve.cli.success", test_case)
    driver.then("test_case.project.approve.cli.success", test_case)


def test_state_machine_entry_must_not_declare_output() -> None:
    author = _author()
    entry = author["entry_points"]["entry_point.html.project.board"]
    entry["output"] = {"status": 200}
    with pytest.raises(ContractError, match=r"Schema validation failed"):
        compile_source(author)


def test_worker_entry_payload_must_match_trigger_domain_event_payload() -> None:
    author = _author()
    author["entry_points"]["entry_point.worker.project.approval_notice"]["adapter"]["worker"]["input"]["payload"] = D("data_contract.project.notice_result")
    with pytest.raises(ContractError, match=r"Entry entry_point.worker\.project\.approval_notice input\.payload must be data_contract\.project\.approved, got data_contract\.project\.notice_result"):
        compile_source(author)


def test_worker_entry_must_declare_realistic_dispositions() -> None:
    author = _author()
    author["entry_points"]["entry_point.worker.project.approval_notice"]["adapter"]["worker"]["ingress_responses"] = {"accepted": {"disposition": "acknowledge"}}
    with pytest.raises(ContractError, match=r"Entry entry_point.worker\.project\.approval_notice must declare at least one non-acknowledge ingress disposition"):
        compile_source(author)


def test_workflow_steps_must_transition_all_action_outcomes() -> None:
    author = _author()
    del author["workflows"]["workflow.project.approval_notice"]["steps"][0]["outcome_transitions"]["delivery_failed"]
    with pytest.raises(ContractError, match=r"Workflow workflow.project\.approval_notice step send_notice outcome_transitions must exactly map application action outcomes: missing: delivery_failed"):
        compile_source(author)


def test_workflow_steps_must_transition_authorization_failure_outcomes() -> None:
    author = _author()
    del author["workflows"]["workflow.project.approval_notice"]["steps"][0]["outcome_transitions"]["forbidden"]
    with pytest.raises(ContractError, match=r"Workflow workflow.project\.approval_notice step send_notice outcome_transitions must exactly map application action outcomes: missing: forbidden"):
        compile_source(author)


def test_workflow_authorization_failure_collapse_requires_rationale() -> None:
    author = _author()
    workflow = author["workflows"]["workflow.project.approval_notice"]
    del workflow["outcomes"]["notice_forbidden"]
    workflow["steps"][0]["outcome_transitions"]["forbidden"] = {"fail_as": "delivery_failed"}
    with pytest.raises(ContractError, match=r"collapses authorization failure into delivery_failed"):
        compile_source(author)

    workflow["steps"][0]["outcome_transitions"]["forbidden"]["rationale"] = "The worker deliberately treats policy denial as a delivery failure for this integration."
    compile_source(author)


def test_workflow_transition_actions_must_be_exclusive() -> None:
    author = _author()
    transition = author["workflows"]["workflow.project.approval_notice"]["steps"][0]["outcome_transitions"]["delivery_failed"]
    transition["fail_as"] = "delivery_failed"
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)


def test_workflow_transitions_must_reference_known_targets() -> None:
    author = _author()
    transition = author["workflows"]["workflow.project.approval_notice"]["steps"][0]["outcome_transitions"]["delivery_failed"]
    transition["retry_policy"]["fail_as"] = "missing"
    with pytest.raises(ContractError, match=r"transition delivery_failed references unknown workflow outcome missing"):
        compile_source(author)


def test_cli_entry_cannot_target_raw_domain_event() -> None:
    author = _author()
    author["entry_points"]["entry_point.cli.project.event"] = {
        "rationale": _rationale("CLI domain-event publishing is intentionally not modeled"),
        "adapter": {"cli": {"cli_command": "project domain-event"}},
        "target": {"domain_event": {"ref": "domain_event.project.approved"}},
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


def test_workflow_entry_target_must_declare_trigger_bindings() -> None:
    author = _author()
    del author["entry_points"]["entry_point.worker.project.approval_notice"]["target"]["workflow"]["trigger_bindings"]
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)


def test_workflow_entry_trigger_bindings_must_match_workflow_trigger_payload() -> None:
    author = _author()
    del author["entry_points"]["entry_point.worker.project.approval_notice"]["target"]["workflow"]["trigger_bindings"]["project_id"]
    with pytest.raises(ContractError, match=r"Entry entry_point.worker\.project\.approval_notice target\.trigger_bindings must exactly bind workflow trigger: missing: project_id"):
        compile_source(author)


def test_get_api_entry_must_provide_all_application_action_input_as_path_or_query_params() -> None:
    author = _author()
    entry = author["entry_points"]["entry_point.api.project.list"]
    entry["adapter"]["http_api"]["path"] = "/projects"
    entry["adapter"]["http_api"]["input"].pop("path_params")
    entry["target"]["application_action"]["input_bindings"].pop("workspace_id")
    with pytest.raises(ContractError, match=r"API entry entry_point.api\.project\.list GET must declare all application action inputs as path_params or query_params: \['workspace_id'\]"):
        compile_source(author)


def test_authoring_layers_reject_html_state_machine_layout_without_html_layer() -> None:
    from pyspec_contract.layers import parse_layers

    author = _api_only_author()
    author["state_machines"] = {
        "state_machine.ticket.board": {
            "archetype": "dashboard",
            "entity_type": ET("Ticket"),
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
    assert "entity_types" in schema["properties"]
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
    entity_type = _first_item(author, "entity_types")
    entity_type["persistence"] = {"dialect": "sqlite", "table": "projects"}
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)


def test_generated_gherkin_is_single_corpus() -> None:
    features = ROOT / "spec" / "generated" / "test_adapters" / "pytest_bdd_features"
    assert features.exists()
    assert not (features / "spec").exists()
    assert not (features / "prod").exists()
    assert sorted(path.name for path in features.glob("*.feature"))
