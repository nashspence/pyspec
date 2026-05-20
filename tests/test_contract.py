from __future__ import annotations

import copy
from pathlib import Path

import pytest

from pyspec_contract.api import write_generated
from pyspec_contract.compile import ContractError, ContractLintWarning, render_examples, author_from_source, compile_author, compile_source, validate_against_schema
from pyspec_contract.io import read_yaml, write_yaml
from pyspec_contract.paths import COMPILED_SPEC_PATH, SOURCE_SPEC_PATH
from pyspec_contract.reference_driver import ReferenceSpecDriver
from pyspec_contract.validate import validate_project
from tests.helpers import EXAMPLE_ROOT, copy_project_tree

ROOT = EXAMPLE_ROOT


def _rationale(text: str = "test contract declaration") -> str:
    return text


SCHEMA_ALIASES = {
    "ID": {"type": "string"},
    "Text": {"type": "string"},
    "Markdown": {"type": "string"},
    "Date": {"type": "string", "format": "date"},
    "Timestamp": {"type": "string", "format": "date-time"},
    "Boolean": {"type": "boolean"},
    "Integer": {"type": "integer"},
    "Decimal": {"type": "number"},
    "JSON": {"type": "object", "additionalProperties": True},
}


def P(name: str) -> dict[str, object]:
    return copy.deepcopy(SCHEMA_ALIASES[name])


def ET(name: str) -> str:
    if name.startswith("entity_type."):
        return name
    return "entity_type." + name.lower()


def M(name: str) -> dict[str, str]:
    return {"$ref": ET(name)}


def D(name: str) -> dict[str, str]:
    return {"$ref": name}


def A(item: dict) -> dict:
    return {"type": "array", "items": item}


def E(*values: str) -> dict[str, list[str]]:
    return {"type": "string", "enum": list(values)}


def F(schema: dict, *, required: bool = True, allow_null: bool = False) -> dict:
    schema = copy.deepcopy(schema)
    if allow_null:
        type_value = schema.get("type")
        if isinstance(type_value, list):
            schema["type"] = sorted(set(type_value) | {"null"})
        elif isinstance(type_value, str):
            schema["type"] = sorted({type_value, "null"})
        else:
            schema = {"anyOf": [schema, {"type": "null"}]}
    return schema


def O(fields: dict[str, dict], *, required: list[str] | None = None) -> dict:
    return {
        "type": "object",
        "properties": fields,
        "required": sorted(fields if required is None else required),
        "additionalProperties": False,
    }


EMPTY_OBJECT_SCHEMA = O({}, required=[])


def _author() -> dict:
    return read_yaml(ROOT / SOURCE_SPEC_PATH)


def _item(author: dict, section: str, item_id: str) -> dict:
    return author[section][item_id]


def _first_item(author: dict, section: str) -> dict:
    return next(iter(author[section].values()))


def test_project_validates() -> None:
    validate_project(ROOT)


def test_canonical_top_level_sections_compile_without_compatibility_mirrors() -> None:
    contract = compile_author(_author())

    assert "commands" in contract
    assert "queries" in contract
    assert "access_policies" in contract
    assert "external_interfaces" in contract
    assert "media_assets" in contract
    assert "viewport_profiles" in contract
    assert "reference_index" in contract
    assert "application_" + "act" + "ions" not in contract
    assert "authorization" + "_policies" not in contract
    assert "external_interface" + "_points" not in contract
    assert "assets" not in contract
    assert "render" + "_profiles" not in contract
    assert "refs" not in contract


def test_compiled_then_requires_uses_projection_bucket_names() -> None:
    contract = compile_author(_author())
    behavior_scenario = contract["behavior_scenarios"]["behavior_scenario.project.board.ready"]
    requires = behavior_scenario["then"]["requires"]
    state_machine_assertion = behavior_scenario["then"]["state_machine"]

    assert set(requires) == {
        "command_bindings",
        "media_assets",
        "query_bindings",
        "renderer_surfaces",
        "text_resources",
    }
    assert requires["renderer_surfaces"]
    assert "surfaces" not in requires
    assert "text" not in requires
    assert "assets" not in requires
    assert "renderer_surface" in state_machine_assertion
    assert "state_machine_composition" in state_machine_assertion
    assert "surface" not in state_machine_assertion
    assert "composition" not in state_machine_assertion
    assert all("renderer_surface" in instance for instance in state_machine_assertion["instances"].values())
    assert all("surface" not in instance for instance in state_machine_assertion["instances"].values())


def test_legacy_top_level_sections_are_rejected() -> None:
    asset = {
        "media_kind": "icon",
        "placeholder": {"label": "Logo", "placeholder_symbol": "square"},
    }
    author = {
        "project": "alias_conflict",
        "media_assets": {"media_asset.alias_conflict.logo": asset},
        "assets": {"media_asset.alias_conflict.icon": asset},
    }

    with pytest.raises(ContractError, match="must not contain .*assets"):
        author_from_source(author)




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
    write_yaml(path, {"transition": {"trigger": {"data_refresh_signal": "ready"}, "required": True}}, sort_keys=False)

    text = path.read_text(encoding="utf-8")
    data = read_yaml(path)

    assert "  trigger:" in text
    assert "    data_refresh_signal: ready" in text
    assert "'trigger':" not in text
    assert data["transition"]["trigger"] == {"data_refresh_signal": "ready"}
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
    state = _item(author, "state_machines", "state_machine.project.list")["states"]["loading"]
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
            "payload_schema": D("schema.project.approved"),
        }
    }
    assert "refs" not in author
    assert author["commands"]["command.project.submit"]["entity_changes"]["entity_lifecycle_transition"] == {
        "entity_type": "entity_type.project",
        "field": "status",
        "from": "draft",
        "to": "submitted",
    }
    assert author["behavior_scenarios"]["behavior_scenario.project.approve.success"]["given"]["preconditions"] == [{"ref": "precondition.project.submitted"}]
    assert compile_author(author) == read_yaml(ROOT / COMPILED_SPEC_PATH)


def test_named_precondition_expands_into_compiled_behavior_scenario() -> None:
    author = _author()
    contract = compile_author(author)
    precondition = contract["preconditions"]["precondition.project.submitted"]
    behavior_scenario_fact = contract["behavior_scenarios"]["behavior_scenario.project.approve.success"]["given"]["preconditions"][0]
    assert "ref" not in behavior_scenario_fact
    assert behavior_scenario_fact == {"present": precondition["present"]}
    assert render_examples(contract)["state_machine.project.board.ready.ready_selected.audit"]["precondition_refs"] == [
        {"ref": "precondition.project.submitted"},
        {"ref": "precondition.project.draft"},
    ]
    assert "viewport_profiles" not in render_examples(contract)["state_machine.project.board.ready.ready_selected.audit"]


def test_unknown_precondition_use_is_rejected() -> None:
    author = _author()
    author["behavior_scenarios"]["behavior_scenario.project.approve.success"]["given"]["preconditions"] = [{"ref": "precondition.project.missing"}]
    with pytest.raises(ContractError, match=r"Behavior scenario behavior_scenario.project\.approve\.success references unknown precondition precondition\.project\.missing"):
        compile_author(author)


def test_duplicate_precondition_use_in_one_behavior_scenario_is_rejected() -> None:
    author = _author()
    author["behavior_scenarios"]["behavior_scenario.project.approve.success"]["given"]["preconditions"] = [
        {"ref": "precondition.project.submitted"},
        {"ref": "precondition.project.submitted"},
    ]
    with pytest.raises(ContractError, match=r"Behavior scenario behavior_scenario.project\.approve\.success uses precondition precondition\.project\.submitted more than once"):
        compile_author(author)


def test_unknown_render_example_precondition_use_is_rejected() -> None:
    author = _author()
    author["state_machines"]["state_machine.project.board"]["states"]["ready"]["render_examples"]["ready_selected"]["precondition_refs"] = [{"ref": "precondition.project.missing"}]
    with pytest.raises(ContractError, match=r"Render example state_machine\.project\.board\.ready\.ready_selected\.audit references unknown precondition precondition\.project\.missing"):
        compile_author(author)


def test_duplicate_render_example_precondition_use_is_rejected() -> None:
    author = _author()
    author["state_machines"]["state_machine.project.board"]["states"]["ready"]["render_examples"]["ready_selected"]["precondition_refs"] = [
        {"ref": "precondition.project.submitted"},
        {"ref": "precondition.project.submitted"},
    ]
    with pytest.raises(ContractError, match=r"Render example state_machine\.project\.board\.ready\.ready_selected\.audit uses precondition precondition\.project\.submitted more than once"):
        compile_author(author)


def test_unused_precondition_is_rejected() -> None:
    author = _author()
    author["preconditions"]["precondition.project.unused"] = {
        "present": {
            "entity_type": ET("Project"),
            "values": {
                "id": {"value": "project_unused_1"},
                "status": {"value": "submitted"},
                "title": {"value": "Unused project"},
                "workspace_id": {"from": "$fixture.workspace.id"},
            },
        },
        "rationale": "Unused preconditions are dead setup, so they should be removed.",
    }
    with pytest.raises(ContractError, match=r"Unused preconditions: precondition\.project\.unused"):
        compile_author(author)


def test_precondition_use_requires_declared_fixture_namespace() -> None:
    author = _author()
    author["behavior_scenarios"]["behavior_scenario.project.approve.success"]["given"]["seed_fixtures"] = []
    with pytest.raises(
        ContractError,
        match=r"Behavior scenario behavior_scenario.project\.approve\.success fixture ref \$fixture\.workspace\.id cannot resolve at workspace",
    ):
        compile_author(author)


def test_precondition_template_fields_must_belong_to_model() -> None:
    author = _author()
    author["preconditions"]["precondition.project.submitted"]["present"]["values"]["unknown_field"] = {"value": "nope"}
    with pytest.raises(ContractError, match=r"Precondition precondition\.project\.submitted uses unknown Project fields: \['unknown_field'\]"):
        compile_author(author)


def test_behavior_scenario_system_under_test_ref_must_match_command_under_test() -> None:
    author = _author()
    author["behavior_scenarios"]["behavior_scenario.project.approve.success"]["system_under_test_ref"] = {"command": "command.project.create"}
    with pytest.raises(ContractError, match="system_under_test_ref.command must match the command under test"):
        compile_author(author)


def test_entity_exists_assertion_rejects_unknown_field() -> None:
    author = _author()
    exists = author["behavior_scenarios"]["behavior_scenario.project.approve.success"]["then"]["entity"]["exists"]
    exists["where"]["ghost"] = {"value": "nope"}
    with pytest.raises(ContractError, match=r"entity\.exists filters unknown Project fields: \['ghost'\]"):
        compile_author(author)


def test_response_assertion_requires_call_external_interface() -> None:
    author = _author()
    author["behavior_scenarios"]["behavior_scenario.project.approve.success"]["then"]["response"] = {"status": 200}
    with pytest.raises(ContractError, match="response assertions require call_external_interface"):
        compile_author(author)


def test_authorization_denied_assertion_archetype_outcome_must_be_mapped_authorization_failure() -> None:
    author = _author()
    case = author["behavior_scenarios"]["behavior_scenario.project.approve.access_denied"]
    case["then"]["outcome"] = "lifecycle_transition_not_allowed"
    with pytest.raises(ContractError, match=r"authorization_denied_assertion archetype outcome must be one of command authorization failure outcomes"):
        compile_author(author)


def test_invocation_assertion_must_follow_when() -> None:
    author = _author()
    author["behavior_scenarios"]["behavior_scenario.project.approve.success"]["then"]["invoked"].append("command.project.create")
    with pytest.raises(ContractError, match="asserts command/query bindings unrelated to when"):
        compile_author(author)


def test_behavior_scenario_query_availability_and_invocation_assertions_are_supported() -> None:
    author = _author()
    board_then = author["behavior_scenarios"]["behavior_scenario.project.board.empty"]["then"]
    board_then["enables"].append("query.project.list")
    board_then["forbids"] = ["query.project.read"]
    author["behavior_scenarios"]["behavior_scenario.project.list.success"] = {
        "archetype": "command_outcome",
        "feature_tag": "project.query",
        "system_under_test_ref": {"query": "query.project.list"},
        "title": "List projects",
        "given": {"seed_fixtures": ["fixture.workspace.member"]},
        "when": {
            "invoke_query": {
                "ref": "query.project.list",
                "input": {"workspace_id": {"from": "$fixture.workspace.id"}},
            }
        },
        "then": {
            "outcome": "listed",
            "invoked": ["query.project.list"],
        },
    }
    contract = compile_author(author)
    board_assertions = contract["behavior_scenarios"]["behavior_scenario.project.board.empty"]["then"]
    assert "query.project.list" in board_assertions["enables"]
    assert board_assertions["forbids"] == ["query.project.read"]
    assert contract["behavior_scenarios"]["behavior_scenario.project.list.success"]["then"]["invoked"] == ["query.project.list"]


def test_named_assertion_expands_into_compiled_behavior_scenario() -> None:
    author = _author()
    author["assertions"] = {
        "assertion.project.submitted": {
            "present": copy.deepcopy(author["preconditions"]["precondition.project.submitted"]["present"]),
            "rationale": "The submitted project should remain present.",
        }
    }
    author["behavior_scenarios"]["behavior_scenario.project.approve.success"]["then"]["postconditions"] = [{"ref": "assertion.project.submitted"}]
    contract = compile_author(author)
    assertion = contract["assertions"]["assertion.project.submitted"]
    assert contract["behavior_scenarios"]["behavior_scenario.project.approve.success"]["then"]["postconditions"] == [
        {"present": assertion["present"]}
    ]


def test_access_policies_require_explicit_conditions_and_support_value_equals() -> None:
    author = _explicit_transition_author()
    author["commands"]["command.ticket.submit"]["authorization"] = {
        "policy": "access_policy.ticket.submit",
        "authentication_required_as": "authentication_required",
        "access_denied_as": "access_denied",
    }
    author["commands"]["command.ticket.submit"]["outcomes"]["authentication_required"] = {"kind": "failure", "result": M("Problem")}
    author["commands"]["command.ticket.submit"]["outcomes"]["access_denied"] = {"kind": "failure", "result": M("Problem")}
    author["access_policies"] = {
        "access_policy.ticket.submit": {
            "subject": [{"kind": "actor"}],
            "resource": [{"entity_type": ET("Ticket")}],
            "action": ["command.ticket.submit"],
            "environment": [],
            "combining_algorithm": "all_permit_rules_must_match",
            "rationale": "Explicit policy missing rules is invalid.",
        }
    }
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_author(author)

    author["access_policies"]["access_policy.ticket.submit"]["rules"] = [
        {
            "condition": {
                "value_equals": {
                    "left": {"from": "$command_input.ticket_id"},
                    "right": {"value": "ticket_1"},
                }
            },
            "effect": "permit",
        }
    ]
    contract = compile_author(author)
    assert contract["access_policies"]["access_policy.ticket.submit"]["rules"][0]["condition"]["value_equals"]["right"] == {
        "value": "ticket_1"
    }


def test_access_policies_reject_duplicated_rule_sets() -> None:
    author = _authorized_transition_author()
    author["access_policies"]["access_policy.ticket.submit_duplicate"] = {
        "subject": [{"kind": "actor"}],
        "resource": [{"entity_type": ET("Ticket")}],
        "action": ["command.ticket.submit"],
        "environment": [],
        "rules": [{"condition": {"subject_has_role": "member"}, "effect": "permit"}],
        "combining_algorithm": "all_permit_rules_must_match",
        "rationale": "This should reuse the member submit policy instead.",
    }
    with pytest.raises(ContractError, match=r"reuse one access_policy with combined resource/action coverage"):
        compile_author(author)


def test_access_policy_rule_effect_is_permit_only() -> None:
    author = _authorized_transition_author()
    author["access_policies"]["access_policy.ticket.submit"]["rules"][0]["effect"] = "deny"
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_author(author)


def _authorized_transition_author() -> dict:
    author = _explicit_transition_author()
    command = author["commands"]["command.ticket.submit"]
    command["authorization"] = {
        "policy": "access_policy.ticket.submit",
        "authentication_required_as": "authentication_required",
        "access_denied_as": "access_denied",
    }
    command["outcomes"]["authentication_required"] = {"kind": "failure", "result": M("Problem")}
    command["outcomes"]["access_denied"] = {"kind": "failure", "result": M("Problem")}
    author["access_policies"] = {
        "access_policy.ticket.submit": {
            "subject": [{"kind": "actor"}],
            "resource": [{"entity_type": ET("Ticket")}],
            "action": ["command.ticket.submit"],
            "environment": [],
            "rules": [{"condition": {"subject_has_role": "member"}, "effect": "permit"}],
            "combining_algorithm": "all_permit_rules_must_match",
            "rationale": "Members may submit tickets.",
        }
    }
    return author


def test_authored_command_rejects_legacy_access_policy_shortcut() -> None:
    author = _authorized_transition_author()
    author["commands"]["command.ticket.submit"]["access_policy"] = "access_policy.ticket.submit"
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_author(author)

    author = _authorized_transition_author()
    contract = compile_author(author)
    assert contract["commands"]["command.ticket.submit"]["authorization"] == {
        "policy": "access_policy.ticket.submit",
        "authentication_required_as": "authentication_required",
        "access_denied_as": "access_denied",
    }


def test_command_authorization_mapping_rejects_bad_outcome_names() -> None:
    author = _authorized_transition_author()
    author["commands"]["command.ticket.submit"]["authorization"]["access_denied_as"] = "Forbidden"
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_author(author)


def test_command_access_policy_and_outcomes_are_semantically_validated() -> None:
    author = _authorized_transition_author()
    author["commands"]["command.ticket.submit"]["authorization"]["policy"] = "access_policy.ticket.missing"
    with pytest.raises(ContractError, match=r"authorization\.policy references unknown access policy"):
        compile_author(author)

    author = _authorized_transition_author()
    del author["commands"]["command.ticket.submit"]["outcomes"]["authentication_required"]
    with pytest.raises(ContractError, match=r"authorization\.authentication_required_as references unknown outcome authentication_required"):
        compile_author(author)

    author = _authorized_transition_author()
    author["commands"]["command.ticket.submit"]["authorization"]["access_denied_as"] = "submitted"
    with pytest.raises(ContractError, match=r"authorization\.access_denied_as must map to a failure outcome"):
        compile_author(author)

    author = _authorized_transition_author()
    author["commands"]["command.ticket.submit"]["authorization"]["access_denied_as"] = "authentication_required"
    with pytest.raises(ContractError, match=r"authentication_required_as and access_denied_as must be distinct"):
        compile_author(author)


def test_authorization_failure_outcomes_must_not_emit_domain_events() -> None:
    author = _authorized_transition_author()
    author["domain_events"] = {
        "domain_event.ticket.denied": {
            "payload_schema": M("Problem"),
            "rationale": "Authorization failure outcomes are not domain-event emitters.",
        }
    }
    author["commands"]["command.ticket.submit"]["emits_domain_events"] = [
        {
            "domain_event": "domain_event.ticket.denied",
            "outcome": "access_denied",
            "payload_source": "$command_outcome.result",
        }
    ]
    with pytest.raises(ContractError, match=r"failure outcome access_denied must not emit domain events"):
        compile_author(author)


def _explicit_transition_author() -> dict:
    return {
        "project": "derived_transition",
        "entity_types": {
            "entity_type.ticket": {
                "name": "Ticket",
                "schema": O({"id": P("ID"), "status": E("draft", "submitted")}),
                "entity_lifecycle": {
                    "field": "status",
                    "initial_state": "draft",
                    "lifecycle_states": ["draft", "submitted"],
                    "lifecycle_transitions": [{"command": "command.ticket.submit", "from": "draft", "to": "submitted"}],
                },
                "rationale": "Ticket lifecycle owns entity_lifecycle_transitions.",
            },
            "entity_type.problem": {
                "name": "Problem",
                "schema": O({"code": P("Text"), "message": P("Text")}),
                "rationale": "Problem describes failed transitions.",
            },
        },
        "commands": {
            "command.ticket.submit": {
                "input_schema": O({"ticket_id": P("ID")}),
                "entity_changes": {
                    "entity_lifecycle_transition": {
                        "entity_type": "entity_type.ticket",
                        "field": "status",
                        "from": "draft",
                        "to": "submitted",
                    }
                },
                "emits_domain_events": [],
                "outcomes": {
                    "submitted": {"kind": "success", "result": M("Ticket")},
                    "lifecycle_transition_not_allowed": {"kind": "failure", "result": M("Problem")},
                },
                "rationale": "Submitting moves a draft ticket forward.",
            }
        },
    }


def test_lifecycle_transition_command_compiles_explicit_state_change() -> None:
    author = _explicit_transition_author()
    contract = compile_author(author)
    assert contract["commands"]["command.ticket.submit"]["entity_changes"]["entity_lifecycle_transition"] == {
        "entity_type": "entity_type.ticket",
        "field": "status",
        "from": "draft",
        "to": "submitted",
    }
    assert contract["access_policies"] == {}
    assert "authorization" not in contract["commands"]["command.ticket.submit"]


def test_authored_lifecycle_transition_metadata_must_match_entity_lifecycle() -> None:
    author = _explicit_transition_author()
    author["commands"]["command.ticket.submit"]["entity_changes"]["entity_lifecycle_transition"] = {
        "entity_type": "entity_type.ticket",
        "field": "status",
        "from": "draft",
        "to": "draft",
    }
    with pytest.raises(ContractError, match=r"entity_lifecycle and command command\.ticket\.submit disagree"):
        compile_author(author)


def test_lifecycle_transition_commands_must_be_referenced_by_entity_lifecycle() -> None:
    author = _explicit_transition_author()
    author["commands"]["command.ticket.close"] = {
        "input_schema": O({"ticket_id": P("ID")}),
        "entity_changes": {
            "entity_lifecycle_transition": {
                "entity_type": "entity_type.ticket",
                "field": "status",
                "from": "draft",
                "to": "submitted",
            }
        },
        "emits_domain_events": [],
        "outcomes": {
            "closed": {"kind": "success", "result": M("Ticket")},
            "lifecycle_transition_not_allowed": {"kind": "failure", "result": M("Problem")},
        },
        "rationale": "Closing is intentionally not declared in the lifecycle graph.",
    }
    with pytest.raises(ContractError, match=r"entity_lifecycle_transition command command\.ticket\.close must be referenced by entity_lifecycle declarations"):
        compile_author(author)


def test_lifecycle_transition_commands_must_declare_lifecycle_transition_not_allowed_failure() -> None:
    author = _explicit_transition_author()
    author["commands"]["command.ticket.submit"]["outcomes"]["other_failure"] = {"kind": "failure", "result": M("Problem")}
    del author["commands"]["command.ticket.submit"]["outcomes"]["lifecycle_transition_not_allowed"]
    with pytest.raises(ContractError, match=r"must declare lifecycle_transition_not_allowed failure outcome"):
        compile_author(author)


def test_entity_lifecycle_field_must_exist_on_entity_type() -> None:
    author = _explicit_transition_author()
    del author["entity_types"]["entity_type.ticket"]["schema"]["properties"]["status"]
    author["entity_types"]["entity_type.ticket"]["schema"]["required"].remove("status")
    with pytest.raises(ContractError, match=r"Entity type entity_type\.ticket entity_lifecycle field is not a field: status"):
        compile_author(author)


def test_lifecycle_initial_state_must_be_declared() -> None:
    author = _explicit_transition_author()
    author["entity_types"]["entity_type.ticket"]["entity_lifecycle"]["initial_state"] = "missing"
    with pytest.raises(ContractError, match=r"Entity type entity_type\.ticket initial lifecycle_state is not declared: missing"):
        compile_author(author)


def test_lifecycle_transition_states_must_be_declared() -> None:
    author = _explicit_transition_author()
    author["entity_types"]["entity_type.ticket"]["entity_lifecycle"]["lifecycle_transitions"][0]["to"] = "missing"
    with pytest.raises(ContractError, match=r"Entity type entity_type\.ticket entity_lifecycle_transition uses unknown lifecycle_state"):
        compile_author(author)


def test_commands_reject_behavior_kind_field() -> None:
    author = _explicit_transition_author()
    author["commands"]["command.ticket.submit"]["behavior_kind"] = "command"
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_author(author)


def test_lifecycle_transition_must_reference_known_command() -> None:
    author = _explicit_transition_author()
    author["entity_types"]["entity_type.ticket"]["entity_lifecycle"]["lifecycle_transitions"][0]["command"] = "command.ticket.missing"
    with pytest.raises(
        ContractError,
        match=r"Entity type entity_type\.ticket entity_lifecycle_transition references unknown command command\.ticket\.missing",
    ):
        compile_author(author)


def test_command_rejects_primary_entity_type_field() -> None:
    author = _author()
    author["commands"]["command.project.create"]["entity_type"] = "Project"
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)


def test_schema_properties_reject_legacy_nullability_and_presence_wrappers() -> None:
    author = _author()
    author["entity_types"]["entity_type.project"]["schema"]["properties"]["summary"] = {"null" + "able": P("Text")}
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)

    author = _author()
    author["entity_types"]["entity_type.project"]["schema"]["properties"]["summary"] = {"op" + "tional": P("Text")}
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)


def test_command_rejects_empty_entity_changes() -> None:
    author = _author()
    author["commands"]["command.project.create"]["entity_changes"] = {}
    author["external_interfaces"]["external_interface.api.project.create"]["output_mapping"]["responses"]["created"]["status"] = 200
    author["behavior_scenarios"]["behavior_scenario.project.create.api.success"]["then"]["response"]["status"] = 200
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)


def test_state_machine_data_query_result_must_match_state_machine_entity_type() -> None:
    author = _author()
    author["entity_types"][ET("Workspace")] = {
        "name": "Workspace",
        "schema": O({"id": P("ID"), "name": P("Text")}),
        "rationale": "Workspace is a separate entity_type used to prove data bindings are entity_type-aware.",
    }
    author["queries"]["query.project.read"]["result_schema"] = M("Workspace")
    author["queries"]["query.project.read"]["outcomes"]["found"]["result"] = M("Workspace")
    with pytest.raises(ContractError, match=r"state machine state_machine\.project\.activity\.ready query_binding read_activity query result_schema must return entity_type entity_type\.project"):
        compile_source(author)


def test_queries_reject_command_entity_change_and_emit_fields() -> None:
    author = _author()
    author["queries"]["query.project.list"]["creates"] = [ET("Project")]
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)

    author = _author()
    author["queries"]["query.project.list"]["outcomes"]["listed"]["emits"] = [
        {"domain_event": "domain_event.project.listed", "payload_source": "$command_outcome.result"}
    ]
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)


def test_command_entity_changes_declares_non_empty_project_update() -> None:
    contract = compile_source(_author())
    assert contract["commands"]["command.project.send_approval_notice"]["entity_changes"] == {"updates": [ET("Project")]}


def test_author_contract_can_omit_absent_sections() -> None:
    author = {
        "project": "author_core",
        "entity_types": {
            ET("Ticket"): {
                "name": "Ticket",
                "schema": O({"id": P("ID"), "title": P("Text")}),
            },
            ET("Problem"): {
                "name": "Problem",
                "schema": O({"code": P("Text"), "message": P("Text")}),
            },
        },
        "commands": {
            "command.ticket.create": {
                "input_schema": O({"title": P("Text")}),
                "entity_changes": {"creates": [ET("Ticket")]},
                "emits_domain_events": [],
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
    assert contract["external_interfaces"] == {}
    assert contract["state_machines"] == {}
    assert contract["access_policies"] == {}
    assert "authorization" not in contract["commands"]["command.ticket.create"]
    assert "access_policy" not in contract["reference_index"]
    assert contract["entity_types"]["entity_type.ticket"]["rationale"] == "Declared entity_type Ticket."
    assert contract["commands"]["command.ticket.create"]["rationale"] == "Members can create tickets."


def test_author_state_machine_defaults_empty_collections() -> None:
    from pyspec_contract.layers import parse_layers

    author = {
        "project": "author_ui",
        "entity_types": {
            ET("Ticket"): {
                "name": "Ticket",
                "schema": O({"id": P("ID"), "title": P("Text")}),
                "rationale": "Ticket is the product work item.",
            }
        },
        "viewport_profiles": {
            "viewport_profile.default": {
                "html_viewports": {"compact": {"width": 320, "height": 480}},
                "rationale": "Single breakpoint covers the tiny authored example.",
            }
        },
        "state_machines": {
            "state_machine.ticket.empty": {
                "entity_type": ET("Ticket"),
                "initial_state": "empty",
                "states": {"empty": {}},
                "rationale": "state machine can start as a minimal empty-state.",
            }
        },
    }
    contract = compile_author(author, layers=parse_layers("core,ui,html"))
    state_machine = contract["state_machines"]["state_machine.ticket.empty"]
    assert state_machine["context_schema"] == EMPTY_OBJECT_SCHEMA
    assert state_machine["query_bindings"] == {}
    assert state_machine["local_signals"] == {"accepts": {"local_signals": {}, "data_refresh_signals": {}}, "emits": {"local_signals": {}}}
    assert state_machine["transitions"] == []
    assert "kind" not in state_machine


def test_nested_json_values_binding_values_and_model_less_state_machines_compile() -> None:
    author = {
        "project": "nested_values",
        "state_machines": {
            "state_machine.settings.panel": {
                "context_schema": O({"settings": P("JSON")}),
                "local_signals": {
                    "accepts": {
                        "local_signals": {
                            "configure": {"payload_schema": O({"settings": P("JSON")})},
                        }
                    }
                },
                "initial_state": "ready",
                "states": {"ready": {}},
                "transitions": [
                    {
                        "from": "ready",
                        "to": "ready",
                        "trigger": {"local_signal": "configure"},
                        "local_effects": [
                            {
                                "set": {
                                    "context": "settings",
                                    "value": {"theme": {"colors": ["red", "blue"], "density": {"compact": True}}},
                                }
                            }
                        ],
                    }
                ],
                "rationale": "Entity type-less settings panel keeps local JSON context_resource.",
            }
        },
    }
    contract = compile_author(author)
    state_machine = contract["state_machines"]["state_machine.settings.panel"]
    assert "entity_type" not in state_machine
    assert state_machine["transitions"][0]["local_effects"][0]["set"]["value"]["theme"]["density"]["compact"] is True


def test_context_set_local_effect_respects_context_null_type() -> None:
    author = {
        "project": "context_null_type",
        "state_machines": {
            "state_machine.project.panel": {
                "context_schema": O({"project_id": F(P("ID"), allow_null=True)}, required=[]),
                "local_signals": {"accepts": {"local_signals": {"clear": {}}}},
                "initial_state": "ready",
                "states": {"ready": {}},
                "transitions": [
                    {
                        "from": "ready",
                        "to": "ready",
                        "trigger": {"local_signal": "clear"},
                        "local_effects": [{"set": {"context": "project_id", "value": None}}],
                    }
                ],
                "rationale": "Local context that allows null may be cleared explicitly.",
            }
        },
    }
    compile_author(author)

    author["state_machines"]["state_machine.project.panel"]["context_schema"]["properties"]["project_id"] = P("ID")
    with pytest.raises(ContractError, match=r"transition set project_id cannot assign null to string, which does not allow null"):
        compile_author(author)

    author = {
        "project": "context_null_source",
        "state_machines": {
            "state_machine.project.panel": {
                "context_schema": O(
                    {
                        "source_project_id": F(P("ID"), allow_null=True),
                        "target_project_id": P("ID"),
                    },
                    required=["target_project_id"],
                ),
                "local_signals": {"accepts": {"local_signals": {"copy": {}}}},
                "initial_state": "ready",
                "states": {"ready": {}},
                "transitions": [
                    {
                        "from": "ready",
                        "to": "ready",
                        "trigger": {"local_signal": "copy"},
                        "local_effects": [{"set": {"context": "target_project_id", "from": "$state_context.source_project_id"}}],
                    }
                ],
                "rationale": "Sources that allow null cannot feed context fields that do not allow null.",
            }
        },
    }
    with pytest.raises(ContractError, match=r"transition set target_project_id cannot assign a source that allows null to string, which does not allow null"):
        compile_author(author)


def test_workflow_input_mapping_supports_binding_sources_and_literal_values() -> None:
    author = {
        "project": "workflow_bindings",
        "schemas": {
            "schema.ticket.triggered": {
                "schema": O({"source_id": P("ID")}),
                "rationale": "Workflow input payload.",
            },
            "schema.ticket.notice": {
                "schema": O({"notice_id": P("ID")}),
                "rationale": "Workflow success payload.",
            },
        },
        "entity_types": {
            ET("Ticket"): {
                "name": "Ticket",
                "schema": O({"id": P("ID"), "title": P("Text")}),
                "rationale": "Ticket receives notification side effects.",
            },
            ET("Problem"): {
                "name": "Problem",
                "schema": O({"code": P("Text"), "message": P("Text")}),
                "rationale": "Problem result.",
            }
        },
        "commands": {
            "command.ticket.notify": {
                "input_schema": O({"source_id": P("ID"), "title": P("Text")}),
                "entity_changes": {"updates": [ET("Ticket")]},
                "emits_domain_events": [],
                "outcomes": {
                    "sent": {"kind": "success", "result": D("schema.ticket.notice")},
                    "failed": {"kind": "failure", "result": M("Problem")},
                },
                "rationale": "Sends a notice.",
            }
        },
        "domain_events": {
            "domain_event.ticket.triggered": {
                "payload_schema": D("schema.ticket.triggered"),
                "rationale": "Ticket trigger domain event.",
            }
        },
        "workflows": {
            "workflow.ticket.notice": {
                "inputs": {"domain_event": "domain_event.ticket.triggered"},
                "outputs": {
                    "completed": {"kind": "success", "result": D("schema.ticket.notice")},
                    "failed": {"kind": "failure", "result": M("Problem")},
                },
                "activities": {
                    "notify": {
                        "command": "command.ticket.notify",
                        "input_mapping": {
                            "source_id": {"from": "$workflow_input.payload.source_id"},
                            "title": {"value": "Literal title"},
                        },
                    }
                },
                "gateways": {},
                "sequence_flows": {
                    "notify_sent": {"source_ref": {"activity": "notify"}, "source_outcome": "sent", "target_ref": {"terminal": "completed"}},
                    "notify_failed": {"source_ref": {"activity": "notify"}, "source_outcome": "failed", "target_ref": {"terminal": "failed"}},
                },
                "retry_policies": {},
                "failure_handlers": {},
                "rationale": "Workflow exercises explicit binding values.",
            }
        },
    }
    contract = compile_author(author)
    bindings = contract["workflows"]["workflow.ticket.notice"]["activities"][0]["input_mapping"]
    assert bindings["source_id"] == {"from": "$workflow_input.payload.source_id"}
    assert bindings["title"] == {"value": "Literal title"}


def test_state_machine_empty_signal_directions_can_be_omitted() -> None:
    author = _author()
    activity = _item(author, "state_machines", "state_machine.project.activity")

    assert "emits" not in activity["local_signals"]
    contract = compile_source(author)

    assert contract["state_machines"]["state_machine.project.activity"]["local_signals"]["emits"] == {"local_signals": {}}


def test_author_source_prunes_empty_signal_directions() -> None:
    author = _author()
    activity = _item(author, "state_machines", "state_machine.project.activity")
    activity["local_signals"]["emits"] = {}

    pruned = author_from_source(author)

    assert "emits" not in pruned["state_machines"]["state_machine.project.activity"]["local_signals"]


def test_empty_state_machine_signal_payloads_can_be_omitted() -> None:
    author = _author()
    activity = _item(author, "state_machines", "state_machine.project.activity")

    assert activity["local_signals"]["accepts"]["local_signals"]["selection_cleared"] == {}
    contract = compile_source(author)

    assert contract["state_machines"]["state_machine.project.activity"]["local_signals"]["accepts"]["local_signals"]["selection_cleared"]["payload_schema"] == EMPTY_OBJECT_SCHEMA


def test_author_source_prunes_empty_local_signal_payloads() -> None:
    author = _author()
    activity = _item(author, "state_machines", "state_machine.project.activity")
    activity["local_signals"]["accepts"]["local_signals"]["selection_cleared"]["payload_schema"] = {}

    pruned = author_from_source(author)

    assert pruned["state_machines"]["state_machine.project.activity"]["local_signals"]["accepts"]["local_signals"]["selection_cleared"] == {}


def test_state_machine_accepted_messages_must_be_used_by_transition() -> None:
    author = _author()
    activity = _item(author, "state_machines", "state_machine.project.activity")
    activity["local_signals"]["accepts"]["local_signals"]["unused"] = {}
    with pytest.raises(ContractError, match=r"state machine state_machine\.project\.activity declares accepted state-machine signal without transition: .*local_signal\.unused"):
        compile_source(author)


def test_state_machine_local_messages_reject_global_looking_names() -> None:
    author = _author()
    activity = _item(author, "state_machines", "state_machine.project.activity")
    activity["local_signals"]["accepts"]["local_signals"]["local_signal.global"] = {}
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)


def test_state_machine_transition_messages_must_be_declared_as_accepted() -> None:
    author = _author()
    activity = _item(author, "state_machines", "state_machine.project.activity")
    del activity["local_signals"]["accepts"]["local_signals"]["selection_cleared"]
    with pytest.raises(ContractError, match=r"state machine state_machine\.project\.activity transition signal references undeclared state-machine signal: local_signal\.selection_cleared"):
        compile_source(author)


def test_state_machine_data_events_require_data_binding() -> None:
    author = _author()
    detail = _item(author, "state_machines", "state_machine.project.detail")
    del detail["states"]["loading"]["query_bindings"]
    del detail["states"]["ready"]["query_bindings"]
    detail["states"]["ready"].pop("field_slots")
    with pytest.raises(ContractError, match=r"state machine state_machine\.project\.detail transition uses data-refresh signal without state machine or source-state data: data_refresh_signal\.project_loaded"):
        compile_source(author)


def test_state_machine_transition_requires_rationale_when_audit_card_would_be_empty() -> None:
    author = _author()
    activity = _item(author, "state_machines", "state_machine.project.activity")
    cleared = next(transition for transition in activity["transitions"] if transition["trigger"] == {"local_signal": "selection_cleared"})
    cleared.pop("local_effects")
    with pytest.raises(
        ContractError,
            match=r"state machine state_machine\.project\.activity transition local_signal\.selection_cleared from ready to empty must declare rationale, data, or local_effects",
    ):
        compile_source(author)


def test_state_machine_transition_rationale_can_explain_otherwise_empty_audit_card() -> None:
    author = _author()
    activity = _item(author, "state_machines", "state_machine.project.activity")
    cleared = next(transition for transition in activity["transitions"] if transition["trigger"] == {"local_signal": "selection_cleared"})
    cleared.pop("local_effects")
    cleared["rationale"] = "Clearing the selection returns the activity state machine to its empty state."
    contract = compile_source(author)
    compiled = next(
        transition
        for transition in contract["state_machines"]["state_machine.project.activity"]["transitions"]
        if transition["trigger"] == {"local_signal": "selection_cleared"}
    )
    assert compiled["rationale"] == "Clearing the selection returns the activity state machine to its empty state."


def test_state_machine_data_inputs_must_come_from_context() -> None:
    author = _author()
    state_machine = _item(author, "state_machines", "state_machine.project.list")
    del state_machine["context_schema"]["properties"]["workspace_id"]
    state_machine["context_schema"]["required"].remove("workspace_id")
    board = _item(author, "state_machines", "state_machine.project.board")
    for mount in board["states"]["ready"]["child_state_machines"].values():
        if mount["state_machine"] == "state_machine.project.list":
            mount["context_bindings"].pop("workspace_id", None)
    with pytest.raises(
        ContractError,
        match=r"state machine state_machine\.project\.list query_binding list_projects input_mapping\.workspace_id references unknown \$state_context field: workspace_id",
    ):
        compile_source(author)


def test_state_machine_field_slots_require_data_source() -> None:
    author = _author()
    activity = _item(author, "state_machines", "state_machine.project.activity")
    del activity["states"]["ready"]["query_bindings"]
    with pytest.raises(
        ContractError,
        match=r"state machine state_machine\.project\.activity\.ready field slot assignee has no data source",
    ):
        compile_source(author)


def test_state_machine_data_source_must_be_query_binding() -> None:
    author = _author()
    activity = _item(author, "state_machines", "state_machine.project.activity")
    activity["states"]["ready"]["query_bindings"]["read_activity"]["command"] = "command.project.submit"
    with pytest.raises(ContractError, match="Schema validation failed"):
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
    behavior_scenario = _first_item(author, "behavior_scenarios")
    behavior_scenario["given"]["seed_fixtures"] = ["fixture.workspace.ghost"]
    with pytest.raises(ContractError, match="unknown seed fixture"):
        compile_source(author)


def test_unresolved_fixture_reference_is_rejected() -> None:
    author = _author()
    behavior_scenario = _item(author, "behavior_scenarios", "behavior_scenario.project.board.empty")
    _, body = next(iter(behavior_scenario["when"].items()))
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
    state_machine = _item(author, "state_machines", "state_machine.project.board")["states"]["ready"]
    state_machine["renderers"]["html"]["style"]["rules"].append({"selector": "region.ghost", "declarations": {"display": "block"}})
    with pytest.raises(ContractError, match="undeclared layout region"):
        compile_source(author)


def test_html_slots_and_textual_widgets_must_reference_declared_layout_targets() -> None:
    author = _author()
    state = _item(author, "state_machines", "state_machine.project.list")["states"]["ready"]
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
    state = _item(author, "state_machines", "state_machine.project.list")["states"]["ready"]
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


def test_presentation_rejects_undeclared_textual_command_binding() -> None:
    author = _author()
    state = _item(author, "state_machines", "state_machine.project.list")["states"]["ready"]
    state["renderers"] = {
        "textual": {
            "presentation": {
                "widgets": [{"id": "delete", "widget_class": "Button", "binding": {"command_binding": "delete"}, "container": "main"}],
            },
            "layout": {
                "containers": {"main": {"id": "main", "container_class": "Container", "must_render": True}},
            }
        }
    }
    with pytest.raises(ContractError, match="command_binding binding is not declared"):
        compile_source(author)


def test_state_rejects_legacy_available_commands_array() -> None:
    author = _author()
    state = _item(author, "state_machines", "state_machine.project.list")["states"]["ready"]
    state["available_" + "commands"] = ["command.project.create"]
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)


def test_command_binding_keys_are_local_names() -> None:
    author = _author()
    state = _item(author, "state_machines", "state_machine.project.list")["states"]["ready"]
    state["command_bindings"]["command.create"] = state["command_bindings"].pop("create")
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)


def test_legacy_state_machine_command_and_query_fields_are_rejected() -> None:
    author = _author()
    state = _item(author, "state_machines", "state_machine.project.list")["states"]["ready"]
    state["available_" + "commands"] = ["command.project.create"]
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)

    author = _author()
    state_machine = _item(author, "state_machines", "state_machine.project.list")
    state_machine["query_" + "dependencies"] = ["query.project.list"]
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)

    author = _author()
    state = _item(author, "state_machines", "state_machine.project.activity")["states"]["ready"]
    state["query_" + "dependencies"] = ["query.project.read"]
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)


def test_renderer_slot_binding_accepts_command_binding_and_rejects_command_ref() -> None:
    author = _author()
    board = _item(author, "state_machines", "state_machine.project.board")
    board["local_signals"] = {"accepts": {"data_refresh_signals": {"command_completed": {}}}}
    board["transitions"] = [{"from": "ready", "to": "ready", "trigger": {"data_refresh_signal": "command_completed"}}]
    state = board["states"]["ready"]
    state["command_bindings"] = {
        "create": {
            "command": "command.project.create",
            "input_mapping": {
                "customer": {"value": "Atlas Foods"},
                "priority": {"value": "High"},
                "title": {"value": "Replace rooftop condenser fan"},
                "workspace_id": {"from": "$state_context.workspace_id"},
            },
            "local_effects": {
                "created": {"raise": {"data_refresh_signal": "command_completed"}},
                "access_denied": {"raise": {"data_refresh_signal": "command_completed"}},
                "authentication_required": {"raise": {"data_refresh_signal": "command_completed"}},
                "validation_failed": {"raise": {"data_refresh_signal": "command_completed"}},
            },
        }
    }
    state["renderers"]["textual"]["presentation"] = {
        "widgets": [{"id": "create", "widget_class": "Button", "binding": {"command_binding": "create"}, "container": "nav"}],
    }
    compile_source(author)

    bad = _author()
    board = _item(bad, "state_machines", "state_machine.project.board")
    board["local_signals"] = {"accepts": {"data_refresh_signals": {"command_completed": {}}}}
    board["transitions"] = [{"from": "ready", "to": "ready", "trigger": {"data_refresh_signal": "command_completed"}}]
    state = board["states"]["ready"]
    state["command_bindings"] = {
        "create": {
            "command": "command.project.create",
            "input_mapping": {
                "customer": {"value": "Atlas Foods"},
                "priority": {"value": "High"},
                "title": {"value": "Replace rooftop condenser fan"},
                "workspace_id": {"from": "$state_context.workspace_id"},
            },
            "local_effects": {
                "created": {"raise": {"data_refresh_signal": "command_completed"}},
                "access_denied": {"raise": {"data_refresh_signal": "command_completed"}},
                "authentication_required": {"raise": {"data_refresh_signal": "command_completed"}},
                "validation_failed": {"raise": {"data_refresh_signal": "command_completed"}},
            },
        }
    }
    state["renderers"]["textual"]["presentation"] = {
        "widgets": [{"id": "create", "widget_class": "Button", "binding": {"command": "command.project.create"}, "container": "nav"}],
    }
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(bad)


def test_command_binding_command_must_resolve() -> None:
    author = _author()
    invocation = _item(author, "state_machines", "state_machine.project.list")["states"]["ready"]["command_bindings"]["submit"]
    invocation["command"] = "command.project.missing"
    with pytest.raises(ContractError, match=r"command_binding submit references unknown command command\.project\.missing"):
        compile_source(author)


def test_command_binding_routes_must_cover_exact_command_outcomes() -> None:
    author = _author()
    local_effects = _item(author, "state_machines", "state_machine.project.list")["states"]["ready"]["command_bindings"]["submit"]["local_effects"]
    del local_effects["not_found"]
    with pytest.raises(ContractError, match=r"local_effects must exactly map command outcomes: missing: not_found"):
        compile_source(author)

    author = _author()
    local_effects = _item(author, "state_machines", "state_machine.project.list")["states"]["ready"]["command_bindings"]["submit"]["local_effects"]
    local_effects["ghost"] = {"no_local_effect": {"reason": "state_unchanged"}}
    with pytest.raises(ContractError, match=r"local_effects must exactly map command outcomes: extra: ghost"):
        compile_source(author)


def test_command_binding_rejects_legacy_non_routing_route() -> None:
    author = _author()
    effect = _item(author, "state_machines", "state_machine.project.list")["states"]["ready"]["command_bindings"]["submit"]["local_effects"]["access_denied"]
    effect.clear()
    effect["ig" + "nore"] = True
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)


def test_command_binding_failure_no_local_effect_requires_reason_and_rationale() -> None:
    author = _author()
    effect = _item(author, "state_machines", "state_machine.project.list")["states"]["ready"]["command_bindings"]["submit"]["local_effects"]["lifecycle_transition_not_allowed"]
    effect.clear()
    effect["no_local_effect"] = {"reason": "intentionally_unobservable"}
    with pytest.raises(ContractError, match=r"failure outcome no_local_effect must declare rationale"):
        compile_source(author)

    author = _author()
    effect = _item(author, "state_machines", "state_machine.project.list")["states"]["ready"]["command_bindings"]["submit"]["local_effects"]["lifecycle_transition_not_allowed"]
    effect.clear()
    effect["no_local_effect"] = {"reason": "handled_by_response_mapping", "rationale": "test effect"}
    with pytest.raises(ContractError, match=r"handled_by_response_mapping requires an adapter response mapping or renderer surface"):
        compile_source(author)


def test_command_binding_failure_no_local_effect_rejects_state_unchanged() -> None:
    author = _author()
    effect = _item(author, "state_machines", "state_machine.project.list")["states"]["ready"]["command_bindings"]["submit"]["local_effects"]["lifecycle_transition_not_allowed"]
    effect.clear()
    effect["no_local_effect"] = {"reason": "state_unchanged", "rationale": "Invalid submit leaves the list unchanged."}
    with pytest.raises(ContractError, match=r"failure outcome no_local_effect must use reason handled_by_response_mapping with a proven response mapping or intentionally_unobservable with rationale"):
        compile_source(author)


def test_command_binding_raised_signals_must_be_declared_locally() -> None:
    author = _author()
    effect = _item(author, "state_machines", "state_machine.project.list")["states"]["ready"]["command_bindings"]["submit"]["local_effects"]["submitted"]
    effect["raise"]["data_refresh_signal"] = "ghost"
    with pytest.raises(ContractError, match=r"raise references undeclared state-machine signal: data_refresh_signal\.ghost"):
        compile_source(author)

    author = _author()
    effect = _item(author, "state_machines", "state_machine.project.list")["states"]["ready"]["command_bindings"]["submit"]["local_effects"]["lifecycle_transition_not_allowed"]
    effect["raise"]["local_signal"] = "ghost"
    with pytest.raises(ContractError, match=r"raise references undeclared state-machine signal: local_signal\.ghost"):
        compile_source(author)


def test_command_binding_payload_and_input_mapping_are_type_checked() -> None:
    author = _author()
    effect = _item(author, "state_machines", "state_machine.project.list")["states"]["ready"]["command_bindings"]["submit"]["local_effects"]["lifecycle_transition_not_allowed"]
    del effect["raise"]["payload_bindings"]["message"]
    with pytest.raises(ContractError, match=r"payload_bindings must exactly match payload fields: missing: message"):
        compile_source(author)

    author = _author()
    invocation = _item(author, "state_machines", "state_machine.project.list")["states"]["ready"]["command_bindings"]["submit"]
    del invocation["input_mapping"]["project_id"]
    with pytest.raises(ContractError, match=r"input_mapping must exactly bind invoked input: missing: project_id"):
        compile_source(author)


def test_command_binding_literal_actor_ids_emit_lint_warning() -> None:
    author = _author()
    invocation = _item(author, "state_machines", "state_machine.project.detail")["states"]["ready"]["command_bindings"]["approve"]
    invocation["input_mapping"]["approved_by"] = {"value": "reviewer_1"}
    with pytest.warns(ContractLintWarning, match=r"approved_by uses a literal actor/user id"):
        compile_source(author)


def test_mutation_routes_raising_loaded_signal_emit_lint_warning() -> None:
    author = _author()
    effect = _item(author, "state_machines", "state_machine.project.list")["states"]["ready"]["command_bindings"]["create"]["local_effects"]["created"]
    effect["raise"]["data_refresh_signal"] = "projects_loaded"
    with pytest.warns(ContractLintWarning, match=r"raises data-refresh signal 'projects_loaded' from a mutation"):
        compile_source(author)


def test_command_outcome_emits_is_not_local_state_machine_routing() -> None:
    author = _author()
    local_effects = _item(author, "state_machines", "state_machine.project.list")["states"]["ready"]["command_bindings"]["create"]["local_effects"]
    del local_effects["created"]
    with pytest.raises(ContractError, match=r"local_effects must exactly map command outcomes: missing: created"):
        compile_source(author)


def test_command_binding_routes_are_local_per_state() -> None:
    contract = compile_source(_author())
    empty_create = contract["state_machines"]["state_machine.project.list"]["states"]["empty"]["command_bindings"]["create"]
    ready_create = contract["state_machines"]["state_machine.project.list"]["states"]["ready"]["command_bindings"]["create"]
    assert empty_create["command"] == ready_create["command"] == "command.project.create"
    assert "raise" in empty_create["local_effects"]["validation_failed"]
    assert ready_create["local_effects"]["validation_failed"] == {
        "no_local_effect": {
            "reason": "handled_by_response_mapping",
            "rationale": "The ready list keeps focus while the response mapping shows validation errors.",
        }
    }


def test_query_binding_query_and_effects_are_validated() -> None:
    author = _author()
    invocation = _item(author, "state_machines", "state_machine.project.list")["query_bindings"]["list_projects"]
    invocation["query"] = "query.project.missing"
    with pytest.raises(ContractError, match=r"query_binding list_projects references unknown query query\.project\.missing"):
        compile_source(author)

    author = _author()
    local_effects = _item(author, "state_machines", "state_machine.project.list")["query_bindings"]["list_projects"]["local_effects"]
    del local_effects["unavailable"]
    with pytest.raises(ContractError, match=r"query_binding list_projects local_effects must exactly map query outcomes: missing: unavailable"):
        compile_source(author)

    author = _author()
    local_effects = _item(author, "state_machines", "state_machine.project.list")["query_bindings"]["list_projects"]["local_effects"]
    local_effects["ghost"] = {"no_local_effect": {"reason": "state_unchanged"}}
    with pytest.raises(ContractError, match=r"query_binding list_projects local_effects must exactly map query outcomes: extra: ghost"):
        compile_source(author)


def test_query_binding_bindings_context_updates_and_signals_are_validated() -> None:
    author = _author()
    invocation = _item(author, "state_machines", "state_machine.project.list")["query_bindings"]["list_projects"]
    del invocation["input_mapping"]["workspace_id"]
    with pytest.raises(ContractError, match=r"query_binding list_projects input_mapping must exactly bind invoked input: missing: workspace_id"):
        compile_source(author)

    author = _author()
    effect = _item(author, "state_machines", "state_machine.project.list")["query_bindings"]["list_projects"]["local_effects"]["listed"]
    effect["conditional_local_effects"][0]["context_updates"]["ghost"] = {"value": "nope"}
    with pytest.raises(ContractError, match=r"context_updates references undeclared context field: ghost"):
        compile_source(author)

    author = _author()
    effect = _item(author, "state_machines", "state_machine.project.list")["query_bindings"]["list_projects"]["local_effects"]["listed"]
    effect["conditional_local_effects"][1]["raise"]["data_refresh_signal"] = "ghost"
    with pytest.raises(ContractError, match=r"raise references undeclared state-machine signal: data_refresh_signal\.ghost"):
        compile_source(author)

    author = _author()
    effect = _item(author, "state_machines", "state_machine.project.detail")["states"]["ready"]["query_bindings"]["read_project"]["local_effects"]["not_found"]
    effect["raise"]["local_signal"] = "ghost"
    with pytest.raises(ContractError, match=r"raise references undeclared state-machine signal: local_signal\.ghost"):
        compile_source(author)


def test_query_binding_load_policy_and_query_purity_are_validated() -> None:
    author = _author()
    invocation = _item(author, "state_machines", "state_machine.project.list")["query_bindings"]["list_projects"]
    invocation["load"] = {"refresh_on": [{"data_refresh_signal": "ghost"}]}
    with pytest.raises(ContractError, match=r"load\.refresh_on references undeclared state-machine signal: data_refresh_signal\.ghost"):
        compile_source(author)

    author = _author()
    author["queries"]["query.project.list"]["outcomes"]["listed"]["emits"] = [
        {"domain_event": "domain_event.project.listed", "payload_source": "$command_outcome.result"}
    ]
    author["domain_events"]["domain_event.project.listed"] = {
        "payload_schema": A(M("Project")),
        "rationale": "List domain events are deliberately invalid for data loaders.",
    }
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)

    author = _author()
    author["queries"]["query.project.list"]["updates"] = [ET("Project")]
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)


def test_query_binding_success_cannot_be_semantically_inert() -> None:
    author = _author()
    effect = _item(author, "state_machines", "state_machine.project.list")["query_bindings"]["list_projects"]["local_effects"]["listed"]
    effect.clear()
    effect["no_local_effect"] = {"reason": "state_unchanged"}
    with pytest.raises(ContractError, match=r"successful query no_local_effect must bind/cache data"):
        compile_source(author)


def test_query_binding_query_refresh_requires_explicit_result_or_context_refresh() -> None:
    author = _author()
    effect = _item(author, "state_machines", "state_machine.project.list")["query_bindings"]["list_projects"]["local_effects"]["listed"]
    effect.clear()
    effect["no_local_effect"] = {"reason": "handled_by_query_refresh"}
    with pytest.raises(ContractError, match=r"handled_by_query_refresh requires an explicit query result binding or context refresh"):
        compile_source(author)


def test_query_binding_collection_empty_and_non_empty_routes_are_explicit() -> None:
    contract = compile_source(_author())
    effect = contract["state_machines"]["state_machine.project.list"]["query_bindings"]["list_projects"]["local_effects"]["listed"]
    branches = {branch["result_condition"]: branch["raise"]["data_refresh_signal"] for branch in effect["conditional_local_effects"]}
    assert branches == {"empty": "project_collection_empty", "non_empty": "projects_loaded"}

    author = _author()
    effect = _item(author, "state_machines", "state_machine.project.list")["query_bindings"]["list_projects"]["local_effects"]["listed"]
    effect["conditional_local_effects"] = [effect["conditional_local_effects"][0]]
    with pytest.raises(ContractError, match=r"must declare both empty and non_empty branches"):
        compile_source(author)

    author = _author()
    effect = _item(author, "state_machines", "state_machine.project.list")["query_bindings"]["list_projects"]["local_effects"]["listed"]
    effect["conditional_local_effects"][0]["raise"]["data_refresh_signal"] = "projects_loaded"
    with pytest.raises(ContractError, match=r"empty-collection signal data_refresh_signal\.project_collection_empty without an explicit query local outcome effect raising it"):
        compile_source(author)


def test_query_empty_non_empty_conditions_require_array_results() -> None:
    author = _author()
    effect = _item(author, "state_machines", "state_machine.project.detail")["states"]["loading"]["query_bindings"]["read_project"]["local_effects"]["found"]
    effect.clear()
    effect["conditional_local_effects"] = [
        {
            "result_condition": "empty",
            "result_binding": {"data_key": "project", "from": {"from": "$query_outcome.result"}},
            "raise": {"data_refresh_signal": "project_loaded"},
        },
        {
            "result_condition": "non_empty",
            "result_binding": {"data_key": "project", "from": {"from": "$query_outcome.result"}},
            "raise": {"data_refresh_signal": "project_loaded"},
        },
    ]
    with pytest.raises(ContractError, match=r"valid only for array/list query results"):
        compile_source(author)


def test_state_machine_level_query_scope_is_explicit() -> None:
    author = _author()
    del _item(author, "state_machines", "state_machine.project.board")["query_bindings"]["list_board"]["result_scope"]
    with pytest.raises(ContractError, match=r"state-machine-level query_binding must declare result_scope"):
        compile_source(author)

    author = _author()
    invocation = _item(author, "state_machines", "state_machine.project.board")["query_bindings"]["list_board"]
    invocation["result_scope"] = "local"
    with pytest.raises(ContractError, match=r"result_binding with no_local_effect must declare result_scope shared or prefetch"):
        compile_source(author)

    author = _author()
    invocation = _item(author, "state_machines", "state_machine.project.board")["query_bindings"]["list_board"]
    del invocation["rationale"]
    with pytest.raises(ContractError, match=r"result_scope shared must declare rationale"):
        compile_source(author)


def test_result_bound_without_signal_requires_consumed_result_data() -> None:
    author = _author()
    detail = _item(author, "state_machines", "state_machine.project.detail")
    detail["states"]["ready"].pop("field_slots")
    with pytest.raises(ContractError, match=r"result_bound_without_signal requires consumed result data or declared shared/prefetch ownership"):
        compile_source(author)


def test_field_slot_sources_must_be_unambiguous() -> None:
    author = _author()
    detail = _item(author, "state_machines", "state_machine.project.detail")
    owner_query = copy.deepcopy(detail["states"]["loading"]["query_bindings"]["read_project"])
    owner_query["load"] = {"on_start": True}
    owner_query["result_scope"] = "local"
    detail.setdefault("query_bindings", {})["read_project_owner"] = owner_query
    with pytest.raises(ContractError, match=r"field slot assignee has ambiguous data sources"):
        compile_source(author)


def test_query_binding_load_policy_is_scope_sensitive() -> None:
    author = _author()
    invocation = _item(author, "state_machines", "state_machine.project.list")["query_bindings"]["list_projects"]
    invocation["load"] = {"on_enter": True}
    with pytest.raises(ContractError, match=r"state-machine-level load policy must use on_start or on_mount, not on_enter"):
        compile_source(author)

    author = _author()
    invocation = _item(author, "state_machines", "state_machine.project.detail")["states"]["loading"]["query_bindings"]["read_project"]
    invocation["load"] = {"on_start": True}
    with pytest.raises(ContractError, match=r"view-state-level load policy must use on_enter, not on_start or on_mount"):
        compile_source(author)


def test_query_binding_ids_cannot_shadow_state_machine_scope() -> None:
    author = _author()
    list_state_machine = _item(author, "state_machines", "state_machine.project.list")
    list_state_machine["states"]["ready"]["query_bindings"] = {
        "list_projects": {
            "query": "query.project.list",
            "input_mapping": {"workspace_id": {"from": "$state_context.workspace_id"}},
            "local_effects": {
                "listed": {
                    "result_binding": {"data_key": "projects", "from": {"from": "$query_outcome.result"}},
                    "no_local_effect": {"reason": "result_bound_without_signal"},
                },
                "access_denied": {"no_local_effect": {"reason": "handled_by_response_mapping", "rationale": "Shadow test."}},
                "authentication_required": {"no_local_effect": {"reason": "handled_by_response_mapping", "rationale": "Shadow test."}},
                "unavailable": {"no_local_effect": {"reason": "handled_by_response_mapping", "rationale": "Shadow test."}},
            },
        }
    }
    with pytest.raises(ContractError, match=r"query_bindings duplicate state-machine-scope ids: .*list_projects"):
        compile_source(author)


def test_query_binding_effects_are_local_per_state() -> None:
    contract = compile_source(_author())
    loading_read = contract["state_machines"]["state_machine.project.detail"]["states"]["loading"]["query_bindings"]["read_project"]
    ready_read = contract["state_machines"]["state_machine.project.detail"]["states"]["ready"]["query_bindings"]["read_project"]
    assert loading_read["query"] == ready_read["query"] == "query.project.read"
    assert loading_read["local_effects"]["found"] == {
        "result_binding": {"data_key": "project", "from": {"from": "$query_outcome.result"}},
        "raise": {"data_refresh_signal": "project_loaded"},
    }
    assert ready_read["local_effects"]["found"] == {
        "result_binding": {"data_key": "project", "from": {"from": "$query_outcome.result"}},
        "no_local_effect": {"reason": "result_bound_without_signal"},
    }


def test_missing_referenced_command_is_rejected() -> None:
    author = _author()
    del author["commands"]["command.project.create"]
    with pytest.raises(ContractError, match="unknown command|application command references"):
        compile_source(author)


def test_state_machine_composition_rejects_unknown_mounted_state_machine() -> None:
    author = _author()
    state_machine = _item(author, "state_machines", "state_machine.project.board")["states"]["ready"]
    state_machine["child_state_machines"]["list"]["state_machine"] = "state_machine.project.ghost"
    with pytest.raises(ContractError, match="mounts unknown state machine"):
        compile_source(author)


def test_state_machine_composition_rejects_unknown_sync_target_local_signal() -> None:
    author = _author()
    state_machine = _item(author, "state_machines", "state_machine.project.board")["states"]["ready"]
    for effect in state_machine["local_signal_sync_rules"]["select_project_updates_state_machines"]["local_effects"]:
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
        if transition.get("local_effects") and "emit" in transition["local_effects"][0]
    )
    transition["local_effects"][0]["emit"]["payload_bindings"] = {}
    with pytest.raises(ContractError, match=r"transition emit project_selected payload_bindings must exactly match payload fields: missing: project_id"):
        compile_source(author)


def test_sync_send_data_must_exactly_match_target_local_signal_payload() -> None:
    author = _author()
    state_machine = _item(author, "state_machines", "state_machine.project.board")["states"]["ready"]
    sync_rule = state_machine["local_signal_sync_rules"]["select_project_updates_state_machines"]
    send = next(effect["send"] for effect in sync_rule["local_effects"] if "send" in effect)
    send["payload_bindings"] = {}
    with pytest.raises(ContractError, match=r"sync send selection_changed to detail payload_bindings must exactly match payload fields: missing: project_id"):
        compile_source(author)


def test_sync_send_data_must_match_target_local_signal_payload_type() -> None:
    author = _author()
    state_machine = _item(author, "state_machines", "state_machine.project.board")["states"]["ready"]
    sync_rule = state_machine["local_signal_sync_rules"]["select_project_updates_state_machines"]
    send = next(effect["send"] for effect in sync_rule["local_effects"] if "send" in effect)
    send["payload_bindings"]["project_id"] = {"value": 1}
    with pytest.raises(ContractError, match=r"payload_bindings\.project_id literal value is not compatible with string"):
        compile_source(author)


def test_state_machine_signal_payloads_must_be_consistent_across_state_machines() -> None:
    author = _author()
    activity = _item(author, "state_machines", "state_machine.project.activity")
    activity["local_signals"]["accepts"]["local_signals"]["selection_cleared"] = {"payload_schema": O({"project_id": P("ID")})}
    with pytest.raises(ContractError, match=r"state-machine signal local_signal.selection_cleared payload_schema differs"):
        compile_source(author)


def test_state_machine_signal_direction_must_be_unambiguous() -> None:
    author = _author()
    state_machine = _item(author, "state_machines", "state_machine.project.list")
    state_machine["local_signals"]["emits"]["local_signals"]["project_select"] = {"payload_schema": O({"project_id": P("ID")})}
    with pytest.raises(ContractError, match=r"declares state-machine signal as both accepted and emitted: .*local_signal\.project_select"):
        compile_source(author)


def test_state_machine_trigger_payload_uses_trigger_root_not_signal_root() -> None:
    author = _author()
    ready = author["state_machines"]["state_machine.project.board"]["states"]["ready"]
    ready["local_signal_sync_rules"]["select_project_updates_state_machines"]["local_effects"][0]["set"]["from"] = "$" + "signal.payload.project_id"
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)


def test_signal_names_that_match_states_emit_lint_warnings() -> None:
    author = {
        "project": "signal_lint",
        "state_machines": {
            "state_machine.panel": {
                "local_signals": {"accepts": {"local_signals": {"ready": {}}}},
                "initial_state": "ready",
                "states": {"ready": {}},
                "transitions": [
                    {
                        "from": "ready",
                        "to": "ready",
                        "trigger": {"local_signal": "ready"},
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
    assert any("signal 'ready' also names a state" in message for message in messages)
    assert any("transition trigger 'ready' matches state" in message for message in messages)


def test_composed_behavior_scenario_rejects_unknown_state_machine_instance() -> None:
    author = _author()
    behavior_scenario = _item(author, "behavior_scenarios", "behavior_scenario.project.board.ready")
    behavior_scenario["then"]["state_machine"]["instances"]["ghost"] = {"state": "ready"}
    with pytest.raises(ContractError, match="unknown state machine instance"):
        compile_source(author)


def _api_only_author() -> dict:
    return {
        "project": "api_only",
        "entity_types": {
            ET("Ticket"): {
                "name": "Ticket",
                "schema": O({"id": P("ID"), "title": P("Text")}),
                "rationale": _rationale("ticket entity_type"),
            },
            ET("Problem"): {
                "name": "Problem",
                "schema": O({"code": P("Text"), "message": P("Text")}),
                "rationale": _rationale("problem entity_type"),
            },
        },
        "commands": {
            "command.ticket.create": {
                "input_schema": O({"title": P("Text")}),
                "entity_changes": {"creates": [ET("Ticket")]},
                "emits_domain_events": [],
                "outcomes": {
                    "created": {"kind": "success", "result": M("Ticket")},
                    "validation_failed": {"kind": "failure", "result": M("Problem")},
                },
                "rationale": _rationale("create ticket"),
            }
        },
        "external_interfaces": {
            "external_interface.api.ticket.create": {
                "adapter": {
                    "http_api": {
                        "method": "POST",
                        "path": "/tickets",
                    }
                },
                "invokes": {
                    "command": {"ref": "command.ticket.create"},
                },
                "input_mapping": {
                    "body": {"title": P("Text")},
                    "bindings": {"title": {"from": "$adapter_input.body.title"}},
                },
                "output_mapping": {
                    "responses": {
                        "created": {"status": 201, "body": {"type": M("Ticket"), "from": "$invocation_outcome.result"}},
                        "validation_failed": {"status": 422, "body": {"type": M("Problem"), "from": "$invocation_outcome.result"}},
                    },
                },
                "rationale": _rationale("HTTP create ticket external_interface"),
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


def test_authoring_layers_use_eventing_for_webhook_adapters() -> None:
    from pyspec_contract.layers import parse_layers

    assert parse_layers("core,eventing") == {"core", "eventing"}
    with pytest.raises(ValueError, match="Unknown authoring layer: domain_events"):
        parse_layers("core,domain_events")


def test_authoring_layers_reject_irrelevant_ui_targets() -> None:
    from pyspec_contract.layers import parse_layers

    author = _api_only_author()
    author["state_machines"] = {
        "state_machine.ticket.list": {
            "entity_type": ET("Ticket"),
            "context_schema": {},
            "initial_state": "empty",
            "states": {"empty": {}},
            "transitions": [],
            "rationale": _rationale("UI state machine is not part of this API layer"),
        }
    }
    with pytest.raises(ContractError, match="outside active authoring layers"):
        compile_author(author, layers=parse_layers("core,http"))


def test_authoring_layers_reject_wrong_external_interface_renderer() -> None:
    from pyspec_contract.layers import parse_layers

    author = _api_only_author()
    del author["external_interfaces"]["external_interface.api.ticket.create"]
    author["external_interfaces"]["external_interface.html.ticket.create"] = {
        "adapter": {"html_route": {"path": "/tickets"}},
        "invokes": {"state_machine": {"ref": "state_machine.ticket.list", "renderer": "html"}},
        "input_mapping": {"bindings": {}},
        "output_mapping": {},
    }
    with pytest.raises(ContractError, match="external interface adapter html_route requires ui"):
        compile_author(author, layers=parse_layers("core,http"))


def test_cli_state_machine_external_interface_must_provide_required_context_args() -> None:
    author = _author()
    del author["external_interfaces"]["external_interface.cli.project.board"]["input_mapping"]["args"]
    with pytest.raises(ContractError, match=r"External interface external_interface.cli\.project\.board input\.args must include required state machine context inputs: \['workspace_id'\]"):
        compile_source(author)


def test_external_interface_rejects_renderer_irrelevant_fields() -> None:
    author = _author()
    author["external_interfaces"]["external_interface.html.project.board"]["input_mapping"]["args"] = {"workspace_id": P("ID")}
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)


def test_textual_is_not_an_external_interface_renderer() -> None:
    author = _author()
    author["external_interfaces"]["textual.project.board"] = {
        "rationale": _rationale("Textual is a render target, not an external_interface adapter."),
        "adapter": {"textual": {"cli_command": "project board"}},
        "invokes": {"state_machine": {"ref": "state_machine.project.board", "renderer": "textual"}},
    }
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)


def test_cli_delegation_bindings_use_outer_input_shape() -> None:
    author = _author()
    del author["external_interfaces"]["external_interface.cli.project.approve"]["input_mapping"]["args"]
    with pytest.raises(ContractError, match=r"input_mapping\.delegated_input\.body\.approved_by references unknown \$adapter_input field: args"):
        compile_source(author)


def test_external_interface_target_bindings_must_exactly_match_target_input() -> None:
    author = _author()
    del author["external_interfaces"]["external_interface.api.project.create"]["input_mapping"]["bindings"]["title"]
    with pytest.raises(ContractError, match=r"External interface external_interface.api\.project\.create input_mapping\.bindings must exactly bind invoked input: missing: title"):
        compile_source(author)


def test_external_interface_response_must_match_renderer_contract() -> None:
    author = _author()
    author["external_interfaces"]["external_interface.api.project.create"]["output_mapping"]["responses"]["created"]["body"]["type"] = P("Text")
    with pytest.raises(ContractError, match=r"API external interface external_interface.api\.project\.create response created\.body must expose \$invocation_outcome\.result as Project"):
        compile_source(author)


def test_command_query_outcomes_must_have_one_success_and_real_failure_result() -> None:
    author = _author()
    author["commands"]["command.project.create"]["outcomes"]["validation_failed"]["kind"] = "success"
    with pytest.raises(ContractError, match=r"Command command\.project\.create must declare exactly one success outcome"):
        compile_source(author)

    author = _author()
    author["commands"]["command.project.create"]["outcomes"]["validation_failed"]["result"] = M("Project")
    with pytest.raises(ContractError, match=r"failure outcome validation_failed result must be Problem"):
        compile_source(author)


def test_domain_event_emits_must_map_declared_payload() -> None:
    author = _author()
    author["commands"]["command.project.approve"]["emits_domain_events"][0]["payload_bindings"]["approved_by"] = {"from": "$command_outcome.result"}
    with pytest.raises(ContractError, match=r"emit domain_event.project\.approved mapping approved_by source .*\$command_outcome\.result.* type must be string"):
        compile_source(author)


def test_binding_expressions_are_context_scoped() -> None:
    author = _author()
    author["external_interfaces"]["external_interface.api.project.create"]["input_mapping"]["bindings"]["title"] = {"from": "$workflow_input.payload.title"}
    with pytest.raises(ContractError, match=r"input_mapping\.bindings\.title references unavailable binding root: \$workflow_input"):
        compile_source(author)


def test_binding_expressions_validate_declared_fields() -> None:
    author = _author()
    author["workflows"]["workflow.project.approval_notice"]["activities"]["send_notice"]["input_mapping"]["project_id"] = {"from": "$workflow_input.payload.missing"}
    with pytest.raises(ContractError, match=r"input project_id references unknown schema\.project\.approved field: missing"):
        compile_source(author)


def test_external_interface_responses_must_map_all_command_outcomes() -> None:
    author = _author()
    del author["external_interfaces"]["external_interface.api.project.create"]["output_mapping"]["responses"]["validation_failed"]
    with pytest.raises(ContractError, match=r"External interface external_interface.api\.project\.create responses must exactly map command outcomes: missing: validation_failed"):
        compile_source(author)


def test_external_interface_responses_must_map_authorization_failure_outcomes() -> None:
    author = _author()
    del author["external_interfaces"]["external_interface.api.project.create"]["output_mapping"]["responses"]["access_denied"]
    with pytest.raises(ContractError, match=r"External interface external_interface.api\.project\.create responses must exactly map command outcomes: missing: access_denied"):
        compile_source(author)

    contract = compile_source(_author())
    api_responses = contract["external_interfaces"]["external_interface.api.project.approve"]["output_mapping"]["responses"]
    assert api_responses["authentication_required"]["status"] == 401
    assert api_responses["access_denied"]["status"] == 403
    cli_handlers = contract["external_interfaces"]["external_interface.cli.project.approve"]["output_mapping"]["response_handlers"]
    assert cli_handlers["authentication_required"]["exit_code"] == 4
    assert cli_handlers["access_denied"]["exit_code"] == 5


def test_cli_failure_response_must_use_nonzero_exit_and_stderr() -> None:
    author = _author()
    author["external_interfaces"]["external_interface.cli.project.approve"]["output_mapping"]["response_handlers"]["lifecycle_transition_not_allowed"]["exit_code"] = 0
    with pytest.raises(ContractError, match=r"CLI external interface external_interface.cli\.project\.approve failure response handler lifecycle_transition_not_allowed exit_code must be nonzero"):
        compile_source(author)


def test_external_interface_delegation_compiles_and_generates_refs() -> None:
    contract = compile_source(_author())
    cli_entry = contract["external_interfaces"]["external_interface.cli.project.approve"]
    assert cli_entry["invokes"]["external_interface"]["ref"] == "external_interface.api.project.approve"
    assert "external_interface_invocation.cli.project.approve.external_interface.api.project.approve" in contract["reference_index"]["external_interface_invocation"]
    assert "external_interface_delegate.cli.project.approve.to.api.project.approve" in contract["reference_index"]["external_interface_delegate"]
    assert "cli_response_handler.cli.project.approve.approved" in contract["reference_index"]["cli_response_handler"]
    assert "adapter_response_binding.cli.project.approve.approved.stdout.project_id" in contract["reference_index"]["adapter_response_binding"]


def test_external_interface_delegate_invocation_requires_ref_and_input_mapping() -> None:
    author = _author()
    del author["external_interfaces"]["external_interface.cli.project.approve"]["invokes"]["external_interface"]["ref"]
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)

    author = _author()
    del author["external_interfaces"]["external_interface.cli.project.approve"]["input_mapping"]["delegated_input"]
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)


def test_cli_response_handlers_require_binding_values() -> None:
    author = _author()
    author["external_interfaces"]["external_interface.cli.project.approve"]["output_mapping"]["response_handlers"]["approved"]["stdout"]["bindings"]["project_id"] = "$adapter_response.body.id"
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)


def test_old_cli_delegation_shapes_are_rejected() -> None:
    author = _author()
    cli = author["external_interfaces"]["external_interface.cli.project.approve"]["adapter"]["cli"]
    cli["invokes"] = {"http_api": "external_interface.api.project.approve"}
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)

    author = _author()
    cli = author["external_interfaces"]["external_interface.cli.project.approve"]["adapter"]["cli"]
    cli["handling"] = {"approved": {"exit_code": 0}}
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)


def test_external_interface_delegate_ref_must_resolve_and_not_self_delegate() -> None:
    author = _author()
    author["external_interfaces"]["external_interface.cli.project.approve"]["invokes"]["external_interface"]["ref"] = "external_interface.api.project.missing"
    with pytest.raises(ContractError, match=r"delegates to unknown external interface external_interface\.api\.project\.missing"):
        compile_source(author)

    author = _author()
    author["external_interfaces"]["external_interface.cli.project.approve"]["invokes"]["external_interface"]["ref"] = "external_interface.cli.project.approve"
    with pytest.raises(ContractError, match=r"must not delegate to itself"):
        compile_source(author)


def test_external_interface_delegation_cycles_are_rejected() -> None:
    author = _author()
    author["external_interfaces"]["external_interface.api.project.approve"]["invokes"] = {
        "external_interface": {"ref": "external_interface.cli.project.approve"}
    }
    author["external_interfaces"]["external_interface.api.project.approve"]["input_mapping"] = {
        "body": {"approved_by": P("ID")},
        "path_params": {"project_id": P("ID")},
        "delegated_input": {
            "args": {
                "approved_by": {"from": "$adapter_input.body.approved_by"},
                "project_id": {"from": "$adapter_input.path_params.project_id"},
            }
        },
    }
    with pytest.raises(ContractError, match="delegation cycle is invalid"):
        compile_source(author)


def test_delegation_input_mapping_must_match_delegated_adapter_input() -> None:
    author = _author()
    del author["external_interfaces"]["external_interface.cli.project.approve"]["input_mapping"]["delegated_input"]["body"]["approved_by"]
    with pytest.raises(ContractError, match=r"input_mapping\.delegated_input\.body must exactly bind invoked input: missing: approved_by"):
        compile_source(author)


def test_delegation_input_mapping_uses_outer_input_roots() -> None:
    author = _author()
    author["external_interfaces"]["external_interface.cli.project.approve"]["input_mapping"]["delegated_input"]["path_params"]["project_id"] = {
        "from": "$adapter_response.body.id"
    }
    with pytest.raises(ContractError, match=r"input_mapping\.delegated_input\.path_params\.project_id references unavailable binding root: \$adapter_response"):
        compile_source(author)


def test_cli_response_handler_names_match_delegated_response_names() -> None:
    author = _author()
    del author["external_interfaces"]["external_interface.cli.project.approve"]["output_mapping"]["response_handlers"]["access_denied"]
    del author["text_resources"]["text_resource.project.approve.access_denied"]
    with pytest.raises(ContractError, match=r"response_handlers must exactly map delegated external-interface outcomes: missing: access_denied"):
        compile_source(author)


def test_cli_response_handlers_do_not_restate_http_status_matching() -> None:
    author = _author()
    author["external_interfaces"]["external_interface.cli.project.approve"]["output_mapping"]["response_handlers"]["approved"]["status"] = 200
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)


def test_response_root_is_only_available_inside_delegated_cli_response_handlers() -> None:
    contract = compile_source(_author())
    assert contract["external_interfaces"]["external_interface.cli.project.approve"]["output_mapping"]["response_handlers"]["approved"]["stdout"]["bindings"]["project_id"] == {
        "from": "$adapter_response.body.id"
    }

    author = _author()
    author["external_interfaces"]["external_interface.api.project.create"]["input_mapping"]["bindings"]["title"] = {"from": "$adapter_response.body.title"}
    with pytest.raises(ContractError, match=r"input_mapping\.bindings\.title references unavailable binding root: \$adapter_response"):
        compile_source(author)


def test_cli_retry_policy_requires_retryable_delegated_external_interface() -> None:
    author = _author()
    del author["external_interfaces"]["external_interface.api.project.approve"]["retryable"]
    with pytest.raises(ContractError, match=r"retry_policy requires delegated external interface external_interface\.api\.project\.approve and its final invocation to be retryable or query"):
        compile_source(author)


def test_cli_retry_policy_requires_retryable_final_command() -> None:
    author = _author()
    del author["commands"]["command.project.approve"]["retryable"]
    with pytest.raises(ContractError, match=r"retry_policy requires delegated external interface external_interface\.api\.project\.approve and its final invocation to be retryable or query"):
        compile_source(author)


def test_retryable_command_requires_idempotent_marker() -> None:
    author = _author()
    del author["commands"]["command.project.approve"]["idempotent"]
    with pytest.raises(ContractError, match=r"Schema validation failed"):
        compile_source(author)


def test_retryable_external_interface_requires_idempotent_marker() -> None:
    author = _author()
    del author["external_interfaces"]["external_interface.api.project.approve"]["idempotent"]
    with pytest.raises(ContractError, match=r"Schema validation failed"):
        compile_source(author)


def test_delegated_and_outer_access_policies_are_both_evaluated(tmp_path: Path) -> None:
    author = _author()
    outer_policy = "access_policy.project.cli_approve"
    author.setdefault("access_policies", {})[outer_policy] = {
        "subject": [{"kind": "actor"}],
        "resource": [{"external_interface": "external_interface.cli.project.approve"}],
        "action": [],
        "environment": [],
        "rules": [
            {"condition": {"subject_has_role": "reviewer"}, "effect": "permit"},
            {"condition": {"input_present": "approved_by"}, "effect": "permit"},
        ],
        "combining_algorithm": "all_permit_rules_must_match",
        "rationale": "CLI approval requires reviewer role and an explicit approver argument.",
    }
    author["external_interfaces"]["external_interface.cli.project.approve"]["access_policy"] = outer_policy
    author["behavior_scenarios"]["behavior_scenario.project.approve.cli.success"] = {
        "archetype": "external_interface_response",
        "feature_tag": "project.approve.cli",
        "system_under_test_ref": {"external_interface": "external_interface.cli.project.approve"},
        "given": {"preconditions": [{"ref": "precondition.project.submitted"}], "seed_fixtures": ["fixture.workspace.reviewer"]},
            "when": {
                "call_external_interface": {
                    "ref": "external_interface.cli.project.approve",
                    "input": {"approved_by": {"from": "$fixture.actor.id"}, "project_id": {"value": "project_submitted_1"}},
                }
            },
        "then": {
            "outcome": "approved",
            "response": {"exit_code": 0},
            "invoked": ["command.project.approve"],
            "authorization": {
                "allowed": [
                    {"external_interface": "external_interface.cli.project.approve", "access_policy": outer_policy},
                    {"external_interface": "external_interface.api.project.approve", "access_policy": "access_policy.project.reviewer"},
                    {"command": "command.project.approve", "access_policy": "access_policy.project.reviewer"},
                ]
            },
        },
        "title": "Approve through CLI delegation",
        "rationale": "Delegated external interface authorization remains part of the invocation.",
    }
    contract = compile_source(author)
    project = tmp_path / "project"
    copy_project_tree(ROOT, project)
    write_generated(project, contract, render_audit=False)
    driver = ReferenceSpecDriver(project)
    behavior_scenario = contract["behavior_scenarios"]["behavior_scenario.project.approve.cli.success"]
    driver.given("behavior_scenario.project.approve.cli.success", behavior_scenario)
    driver.when("behavior_scenario.project.approve.cli.success", behavior_scenario)
    driver.then("behavior_scenario.project.approve.cli.success", behavior_scenario)


def test_state_machine_external_interface_must_not_declare_output() -> None:
    author = _author()
    external_interface = author["external_interfaces"]["external_interface.html.project.board"]
    external_interface["output"] = {"status": 200}
    with pytest.raises(ContractError, match=r"Schema validation failed"):
        compile_source(author)


def test_worker_external_interface_payload_must_match_trigger_domain_event_payload() -> None:
    author = _author()
    author["external_interfaces"]["external_interface.worker.project.approval_notice"]["input_mapping"]["payload"] = D("schema.project.notice_result")
    with pytest.raises(ContractError, match=r"External interface external_interface.worker\.project\.approval_notice input\.payload must be schema\.project\.approved, got schema\.project\.notice_result"):
        compile_source(author)


def test_worker_external_interface_must_declare_realistic_dispositions() -> None:
    author = _author()
    author["external_interfaces"]["external_interface.worker.project.approval_notice"]["output_mapping"]["ingress_responses"] = {"accepted": {"disposition": "acknowledge"}}
    with pytest.raises(ContractError, match=r"External interface external_interface.worker\.project\.approval_notice must declare at least one non-acknowledge ingress disposition"):
        compile_source(author)


def test_workflow_activities_must_sequence_flow_all_command_outcomes() -> None:
    author = _author()
    del author["workflows"]["workflow.project.approval_notice"]["sequence_flows"]["send_notice_delivery_failed"]
    with pytest.raises(ContractError, match=r"Workflow workflow.project\.approval_notice activity send_notice sequence_flows must exactly map command outcomes: missing: delivery_failed"):
        compile_source(author)


def test_workflow_activities_must_sequence_flow_authorization_failure_outcomes() -> None:
    author = _author()
    del author["workflows"]["workflow.project.approval_notice"]["sequence_flows"]["send_notice_access_denied"]
    with pytest.raises(ContractError, match=r"Workflow workflow.project\.approval_notice activity send_notice sequence_flows must exactly map command outcomes: missing: access_denied"):
        compile_source(author)


def test_workflow_retry_policy_requires_retryable_command() -> None:
    author = _author()
    del author["commands"]["command.project.send_approval_notice"]["retryable"]
    with pytest.raises(ContractError, match=r"Workflow workflow\.project\.approval_notice activity send_notice sequence_flow send_notice_delivery_failed retry_policy requires a query or retryable invoked behavior"):
        compile_source(author)


def test_workflow_authorization_failure_collapse_requires_rationale() -> None:
    author = _author()
    workflow = author["workflows"]["workflow.project.approval_notice"]
    del workflow["outputs"]["notice_access_denied"]
    workflow["sequence_flows"]["send_notice_access_denied"] = {
        "source_ref": {"activity": "send_notice"},
        "source_outcome": "access_denied",
        "target_ref": {"terminal": "delivery_failed"},
    }
    with pytest.raises(ContractError, match=r"collapses authorization failure into delivery_failed"):
        compile_source(author)

    workflow["sequence_flows"]["send_notice_access_denied"]["rationale"] = "The worker deliberately treats policy denial as a delivery failure for this integration."
    compile_source(author)


def test_workflow_sequence_flow_target_refs_must_be_exclusive() -> None:
    author = _author()
    transition = author["workflows"]["workflow.project.approval_notice"]["sequence_flows"]["send_notice_delivery_failed"]
    transition["target_ref"]["activity"] = "send_notice"
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)


def test_workflow_sequence_flows_must_reference_known_outputs() -> None:
    author = _author()
    transition = author["workflows"]["workflow.project.approval_notice"]["sequence_flows"]["send_notice_delivery_failed"]
    transition["target_ref"]["terminal"] = "missing"
    with pytest.raises(ContractError, match=r"sequence_flow send_notice_delivery_failed references unknown workflow outcome missing"):
        compile_source(author)


def test_cli_external_interface_cannot_target_raw_domain_event() -> None:
    author = _author()
    author["external_interfaces"]["external_interface.cli.project.domain_event"] = {
        "rationale": _rationale("CLI domain-event publishing is intentionally not modeled"),
        "adapter": {"cli": {"cli_command": "project domain-event"}},
        "invokes": {"domain_event": {"ref": "domain_event.project.approved"}},
    }
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)


def test_state_machine_external_interface_target_must_declare_renderer() -> None:
    author = _author()
    del author["external_interfaces"]["external_interface.cli.project.board"]["invokes"]["state_machine"]["renderer"]
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)


def test_html_state_machine_external_interface_must_target_html_renderer() -> None:
    author = _author()
    author["external_interfaces"]["external_interface.html.project.board"]["invokes"]["state_machine"]["renderer"] = "textual"
    with pytest.raises(ContractError, match=r"External interface external_interface.html\.project\.board cannot invoke state machine renderer 'textual'"):
        compile_source(author)


def test_cli_state_machine_external_interface_renderer_must_be_declared_by_state_machine() -> None:
    author = _author()
    del author["state_machines"]["state_machine.project.board"]["states"]["ready"]["renderers"]["textual"]
    with pytest.raises(ContractError, match=r"External interface external_interface.cli\.project\.board invokes state machine state_machine\.project\.board renderer textual but that state machine does not declare it"):
        compile_source(author)


def test_cli_state_machine_external_interface_can_launch_html_renderer() -> None:
    author = _author()
    author["external_interfaces"]["external_interface.cli.project.board"]["invokes"]["state_machine"]["renderer"] = "html"
    compile_source(author)


def test_workflow_invocation_must_declare_input_mapping_bindings() -> None:
    author = _author()
    del author["external_interfaces"]["external_interface.worker.project.approval_notice"]["input_mapping"]["bindings"]
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)


def test_workflow_invocation_input_mapping_must_match_workflow_input() -> None:
    author = _author()
    del author["external_interfaces"]["external_interface.worker.project.approval_notice"]["input_mapping"]["bindings"]["project_id"]
    with pytest.raises(ContractError, match=r"External interface external_interface.worker\.project\.approval_notice input_mapping\.bindings must exactly bind workflow input: missing: project_id"):
        compile_source(author)


def test_get_api_external_interface_must_provide_all_query_input_as_path_or_query_params() -> None:
    author = _author()
    external_interface = author["external_interfaces"]["external_interface.api.project.list"]
    external_interface["adapter"]["http_api"]["path"] = "/projects"
    external_interface["input_mapping"].pop("path_params")
    external_interface["input_mapping"]["bindings"].pop("workspace_id")
    with pytest.raises(ContractError, match=r"API external interface external_interface.api\.project\.list GET must declare all command/query inputs as path_params or query_params: \['workspace_id'\]"):
        compile_source(author)


def test_authoring_layers_reject_html_state_machine_layout_without_html_layer() -> None:
    from pyspec_contract.layers import parse_layers

    author = _api_only_author()
    author["state_machines"] = {
        "state_machine.ticket.board": {
            "archetype": "dashboard",
            "entity_type": ET("Ticket"),
            "initial_state": "ready",
            "states": {"ready": {"renderers": {"html": {"layout": {"regions": {"main": {"must_render": True}}}}}}},
            "rationale": _rationale("HTML layout requires the html layer"),
        }
    }
    with pytest.raises(ContractError, match="state machine state renderer html requires html"):
        compile_author(author, layers=parse_layers("core,http,ui,textual"))


def test_layer_pruned_author_schema_hides_irrelevant_sections() -> None:
    from pyspec_contract.layers import author_schema_for_layers, parse_layers

    schema = author_schema_for_layers(parse_layers("core,http"))
    assert "external_interfaces" in schema["properties"]
    assert "entity_types" in schema["properties"]
    assert "state_machines" not in schema["properties"]
    assert "render_examples" not in schema["properties"]


def test_pyspec_contract_rejects_behavior_scenario_harness_routing() -> None:
    author = _author()
    behavior_scenario = _first_item(author, "behavior_scenarios")
    behavior_scenario["harnesses"] = ["spec", "prod"]
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
