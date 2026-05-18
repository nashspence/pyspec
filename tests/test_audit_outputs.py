from __future__ import annotations
import copy
from pathlib import Path

import pytest

from pyspec_contract.audit import (
    _render_graphviz_svg,
    audit_coverage_file,
    audit_coverage_index,
    audit_expected_files,
    composition_dot,
    composition_file,
    external_interface_flow_dot,
    external_interface_flow_file,
    operation_flow_dot,
    operation_flow_file,
    state_machine_dot,
    state_machine_graph_file,
    state_root,
    generate_audit,
    render_example_render_file,
    workflow_flow_dot,
    workflow_flow_file,
)
from pyspec_contract.compile import ContractError, compile_source, write_compiled
from pyspec_contract.io import read_yaml, write_yaml
from pyspec_contract.paths import COMPILED_SPEC_PATH, SOURCE_SPEC_PATH
from pyspec_contract.projection_validators import validate_audit_outputs
from tests.helpers import EXAMPLE_ROOT, copy_project_tree

ROOT = EXAMPLE_ROOT
PNG_HEADER = bytes([137, 80, 78, 71, 13, 10, 26, 10])


SCHEMA_ALIASES = {
    "ID": {"type": "string"},
    "Text": {"type": "string"},
}


def P(name: str) -> dict[str, object]:
    return copy.deepcopy(SCHEMA_ALIASES[name])


def F(schema: dict, *, required: bool = True, allow_null: bool = False) -> dict:
    schema = copy.deepcopy(schema)
    if allow_null and isinstance(schema.get("type"), str):
        schema["type"] = sorted({schema["type"], "null"})
    return schema


def O(fields: dict[str, dict], *, required: list[str] | None = None) -> dict:
    return {
        "type": "object",
        "properties": fields,
        "required": sorted(fields if required is None else required),
        "additionalProperties": False,
    }


def _contract(root: Path = ROOT) -> dict:
    return read_yaml(root / COMPILED_SPEC_PATH)


def test_audit_outputs_cover_full_contract() -> None:
    contract = _contract()
    expected = audit_expected_files(contract)
    assert audit_coverage_file() in expected
    assert "spec/generated/audit_evidence/state_machines/state_machine_project_list/state_machine.svg" in expected
    assert "spec/generated/audit_evidence/state_machines/state_machine_project_board/states/ready/composition.svg" in expected
    assert "spec/generated/audit_evidence/external_interfaces/html_route/external_interface_html_project_board/flow.svg" in expected
    assert "spec/generated/audit_evidence/external_interfaces/cli/external_interface_cli_project_board/flow.svg" in expected
    assert "spec/generated/audit_evidence/workflows/workflow_project_approval_notice/flow.svg" in expected
    assert operation_flow_file("command.project.approve") in expected
    assert any(path.startswith("spec/generated/audit_evidence/state_machines/") and "/states/" in path and path.endswith("/text.yaml") for path in expected)
    assert any(path.startswith("spec/generated/audit_evidence/state_machines/") and "/states/" in path and "/renders/" in path and path.endswith(".png") for path in expected)
    assert any(path.startswith("spec/generated/audit_evidence/state_machines/") and "/render_examples/" in path and "/renders/" in path and path.endswith(".html") for path in expected)
    assert any(path.startswith("spec/generated/audit_evidence/state_machines/") and "/render_examples/" in path and "/renders/" in path and path.endswith(".svg") for path in expected)
    assert render_example_render_file("state_machine.project.board", "state_machine.project.board.ready.ready_selected.audit", "viewport_profile.default", "wide", "html").endswith("/renders/html.viewport_profile_default.wide.source.html")
    assert render_example_render_file("state_machine.project.board", "state_machine.project.board.ready.ready_selected.audit", "viewport_profile.default", "wide", "png").endswith("/renders/html.viewport_profile_default.wide.screenshot.png")
    assert render_example_render_file("state_machine.project.board", "state_machine.project.board.ready.ready_selected.audit", "viewport_profile.default", "wide", "py").endswith("/renders/textual.viewport_profile_default.wide.source.py")
    assert render_example_render_file("state_machine.project.board", "state_machine.project.board.ready.ready_selected.audit", "viewport_profile.default", "wide", "svg").endswith("/renders/textual.viewport_profile_default.wide.capture.svg")
    validate_audit_outputs(ROOT, contract)


def test_audit_coverage_index_maps_compiled_paths_to_evidence() -> None:
    contract = _contract()
    index = read_yaml(ROOT / audit_coverage_file())
    assert index == audit_coverage_index(contract)
    visual_evidence_sets = index["visual_evidence_sets"]
    assert all(path.startswith("spec/generated/audit_evidence/") and path.endswith((".svg", ".png")) for files in visual_evidence_sets.values() for path in files)
    assert index["summary"]["missing_required_visual_paths"] == 0
    assert index["summary"]["required_visual_text_witnesses"] > 0
    assert index["visual_audit"]["required"]["missing"] == {}
    text_witnesses = index["visual_audit"]["required"]["text_witnesses"]
    cli_delegate_set = index["visual_audit"]["required"]["covered"]["/external_interfaces/external_interface.cli.project.approve/invokes/external_interface/ref"]
    assert visual_evidence_sets[cli_delegate_set] == [
        "spec/generated/audit_evidence/external_interfaces/cli/external_interface_cli_project_approve/flow.svg"
    ]
    assert text_witnesses["/external_interfaces/external_interface.cli.project.approve/invokes/external_interface/ref"] == {
        "visual_evidence_set": cli_delegate_set,
        "tokens": ["external_interface.api.project.approve"],
    }
    approve_policy_path = "/commands/command.project.approve/authorization/policy"
    approve_policy_set = index["visual_audit"]["required"]["covered"][approve_policy_path]
    assert "spec/generated/audit_evidence/external_interfaces/cli/external_interface_cli_project_approve/flow.svg" in visual_evidence_sets[approve_policy_set]
    assert text_witnesses[approve_policy_path] == {
        "visual_evidence_set": approve_policy_set,
        "tokens": ["access_policy.project.reviewer"],
    }
    approved_payload_set = index["visual_audit"]["required"]["covered"]["/domain_events/domain_event.project.approved/payload_schema/$ref"]
    assert "spec/generated/audit_evidence/commands/command_project_approve/flow.svg" in visual_evidence_sets[approved_payload_set]
    assert "spec/generated/audit_evidence/workflows/workflow_project_approval_notice/flow.svg" in visual_evidence_sets[approved_payload_set]
    assert text_witnesses["/domain_events/domain_event.project.approved/payload_schema/$ref"] == {
        "visual_evidence_set": approved_payload_set,
        "tokens": ["schema.project.approved"],
    }
    notice_result_set = index["visual_audit"]["required"]["covered"]["/schemas/schema.project.notice_result/schema/properties/notice_id/type"]
    assert "spec/generated/audit_evidence/commands/command_project_send_approval_notice/flow.svg" in visual_evidence_sets[notice_result_set]
    assert "spec/generated/audit_evidence/workflows/workflow_project_approval_notice/flow.svg" in visual_evidence_sets[notice_result_set]
    assert "/schemas/schema.project.notice_result/schema/properties/notice_id/type" not in text_witnesses
    lifecycle_set = index["visual_audit"]["required"]["covered"]["/entity_types/entity_type.project/entity_lifecycle/lifecycle_transitions/1/triggered_by"]
    assert "spec/generated/audit_evidence/commands/command_project_approve/flow.svg" in visual_evidence_sets[lifecycle_set]
    assert "/entity_types/entity_type.project/entity_lifecycle/lifecycle_transitions/1/triggered_by" not in text_witnesses
    renderer_set = index["visual_audit"]["required"]["covered"]["/state_machines/state_machine.project.board/states/ready/renderers/html/layout/regions/aside/classes/0"]
    assert any(path.endswith(".screenshot.png") for path in visual_evidence_sets[renderer_set])
    assert index["render_presence"]["assets"]["not_rendered"] == []
    assert "text.project.approve.success" in index["render_presence"]["text_resources"]["not_rendered"]
    assert index["render_presence"]["fixtures"]["not_rendered"] == ["fixture.workspace.reviewer"]
    assert "/fixtures/fixture.workspace.reviewer/values/actor/id" in index["visual_audit"]["optional"]["not_shown"]


def test_audit_coverage_index_rejects_missing_required_visual_paths(tmp_path: Path) -> None:
    project = tmp_path / "project"
    copy_project_tree(ROOT, project)
    contract = copy.deepcopy(_contract(project))
    contract["unvisualized_required"] = {"path": "value"}
    coverage_path = project / audit_coverage_file()
    write_yaml(coverage_path, audit_coverage_index(contract), sort_keys=False)
    with pytest.raises(ContractError, match="missing required visual audit paths"):
        validate_audit_outputs(project, contract)


def test_audit_coverage_index_rejects_missing_required_visual_text_witness(tmp_path: Path) -> None:
    project = tmp_path / "project"
    copy_project_tree(ROOT, project)
    flow_path = project / external_interface_flow_file("external_interface.cli.project.approve", "cli")
    flow_path.write_text(
        flow_path.read_text(encoding="utf-8").replace("external_interface.api.project.approve", "external_interface.api.project.REMOVED"),
        encoding="utf-8",
    )
    with pytest.raises(ContractError, match="visual text witness missing"):
        validate_audit_outputs(project, _contract(project))


def test_audit_flowcharts_use_graphviz_dot_sources() -> None:
    contract = _contract()
    state_machine = state_machine_dot("state_machine.project.list", contract["state_machines"]["state_machine.project.list"], contract)
    board = contract["state_machines"]["state_machine.project.board"]
    composition = composition_dot("state_machine.project.board.ready", {"context_schema": board["context_schema"], **board["states"]["ready"]}, contract)
    external_interface = external_interface_flow_dot("external_interface.html.project.board", contract["external_interfaces"]["external_interface.html.project.board"], contract)
    api_external_interface = external_interface_flow_dot("external_interface.api.project.create", contract["external_interfaces"]["external_interface.api.project.create"], contract)
    cli_external_interface = external_interface_flow_dot("external_interface.cli.project.board", contract["external_interfaces"]["external_interface.cli.project.board"], contract)
    cli_approve_external_interface = external_interface_flow_dot("external_interface.cli.project.approve", contract["external_interfaces"]["external_interface.cli.project.approve"], contract)
    worker_external_interface = external_interface_flow_dot("external_interface.worker.project.approval_notice", contract["external_interfaces"]["external_interface.worker.project.approval_notice"], contract)
    workflow = workflow_flow_dot("workflow.project.approval_notice", contract["workflows"]["workflow.project.approval_notice"], contract)
    operation = operation_flow_dot("command.project.approve", contract["commands"]["command.project.approve"], contract)
    create_operation = operation_flow_dot("command.project.create", contract["commands"]["command.project.create"], contract)
    diagram_sources = (
        state_machine,
        composition,
        external_interface,
        api_external_interface,
        cli_external_interface,
        cli_approve_external_interface,
        worker_external_interface,
        workflow,
        operation,
        create_operation,
    )
    for dot_source in diagram_sources:
        edge_lines = [line for line in dot_source.splitlines() if " -> " in line]
        assert edge_lines
        assert all("color=" not in line for line in edge_lines)
    assert state_machine.startswith("digraph ")
    assert composition.startswith("digraph ")
    assert external_interface.startswith("digraph ")
    assert workflow.startswith("digraph ")
    assert operation.startswith("digraph ")
    assert "stateDiagram" not in state_machine
    assert "flowchart" not in composition
    assert "data_refresh_signal.projects_loaded" in state_machine
    assert "on data_refresh_signal.projects_loaded" not in state_machine
    assert '<FONT POINT-SIZE="8" COLOR="#64748b">initial state</FONT>' in state_machine
    assert "initial_state" not in state_machine
    assert '<FONT POINT-SIZE="8" COLOR="#64748b">state</FONT>' in state_machine
    assert '<FONT POINT-SIZE="8" COLOR="#64748b">transition signal</FONT>' in state_machine
    assert "text.project.list.ready.heading" in state_machine
    assert "asset.project.list.empty.illustration" in state_machine
    assert state_machine.index("<B>text</B>") < state_machine.index("<B>assets:</B>")
    assert state_machine.index("<B>assets:</B>") < state_machine.index("<B>command_bindings:</B>")
    assert state_machine.index("<B>text:</B>&#160;&#160;text.project.list.ready.heading") < state_machine.index("<B>query.project.list fields</B>")
    assert state_machine.index("<B>query.project.list fields</B>") < state_machine.index("<B>command_bindings</B>")
    assert "<B>emit:</B>&#160;&#160;local_signal.project_selected" in state_machine
    payload_project = '<FONT POINT-SIZE="10"><B>payload:</B>&#160;&#160;project_id</FONT><FONT POINT-SIZE="8" COLOR="#94a3b8">&#160;&#160;string</FONT>'
    assert payload_project in state_machine
    assert "<B>effects:</B>" not in state_machine
    assert "emit local_signal.project_selected" not in state_machine
    assert "<B>projection:</B>" not in state_machine
    assert '<FONT POINT-SIZE="10"><B>load:</B>&#160;&#160;query.project.list</FONT><FONT POINT-SIZE="8" COLOR="#94a3b8">&#160;&#160;array&lt;Project&gt;</FONT>' in state_machine
    assert "<B>query_bindings:</B>&#160;&#160;list_projects" in state_machine
    input_workspace = '<FONT POINT-SIZE="10"><B>input:</B>&#160;&#160;list_projects.workspace_id</FONT><FONT POINT-SIZE="8" COLOR="#94a3b8">&#160;&#160;string</FONT>'
    assert input_workspace in state_machine
    assert state_machine.index(input_workspace) < state_machine.index("<B>query_bindings:</B>&#160;&#160;list_projects")
    assert state_machine.index("<B>query_bindings:</B>&#160;&#160;list_projects") < state_machine.index("<B>load:</B>&#160;&#160;query.project.list")
    detail_transition = state_machine_dot("state_machine.project.detail", contract["state_machines"]["state_machine.project.detail"], contract)
    selection_card = detail_transition[detail_transition.index("local_signal.selection_changed") :]
    input_project = '<FONT POINT-SIZE="10"><B>input:</B>&#160;&#160;read_project.project_id</FONT><FONT POINT-SIZE="8" COLOR="#94a3b8">&#160;&#160;string</FONT>'
    assert selection_card.index(input_project) < selection_card.index("<B>query_bindings:</B>&#160;&#160;read_project")
    load_project = '<FONT POINT-SIZE="10"><B>load:</B>&#160;&#160;query.project.read</FONT><FONT POINT-SIZE="8" COLOR="#94a3b8">&#160;&#160;Project</FONT>'
    assert selection_card.index("<B>query_bindings:</B>&#160;&#160;read_project") < selection_card.index(load_project)
    assert "<B>query.project.list fields</B>" in state_machine
    assert '<FONT POINT-SIZE="10"><B>command_bindings:</B>&#160;&#160;create: command.project.create</FONT><FONT POINT-SIZE="8" COLOR="#94a3b8">&#160;&#160;Project</FONT>' in state_machine
    assert '<FONT POINT-SIZE="10">submit: command.project.submit</FONT><FONT POINT-SIZE="8" COLOR="#94a3b8">&#160;&#160;Project</FONT>' in state_machine
    assert '<FONT POINT-SIZE="10">title</FONT><FONT POINT-SIZE="8" COLOR="#94a3b8">&#160;&#160;string</FONT>' in state_machine
    assert '<FONT POINT-SIZE="10">status</FONT><FONT POINT-SIZE="8" COLOR="#94a3b8">&#160;&#160;enum&lt;draft|submitted|approved|archived&gt;</FONT>' in state_machine
    assert '<FONT POINT-SIZE="10">summary</FONT><FONT POINT-SIZE="8" COLOR="#94a3b8">&#160;&#160;string</FONT>' in detail_transition
    assert "title: Text" not in state_machine
    assert "status: enum" not in state_machine
    assert "<B>Project fields</B>" not in state_machine
    assert state_machine.count("list_projects") >= 5
    assert "<B>access_policies:</B>&#160;&#160;command.project.create:" in state_machine
    assert "access_policy.project.member" in state_machine
    assert "<B>entity_type:</B>" not in state_machine
    assert "<B>context:</B>" not in state_machine
    assert "$signal.payload." not in state_machine
    assert "$domain_event." not in state_machine
    assert "emitted local signal" in composition
    assert "sent local signal" in composition
    assert "local signal sync" in composition
    assert '<FONT POINT-SIZE="8" COLOR="#64748b">nav mount</FONT>' in composition
    board_fsm = state_machine_dot("state_machine.project.board", contract["state_machines"]["state_machine.project.board"], contract)
    assert "<B>child_state_machines</B>" in board_fsm
    assert '<FONT POINT-SIZE="10">nav</FONT><FONT POINT-SIZE="8" COLOR="#94a3b8">&#160;&#160;state_machine.project.list</FONT>' in board_fsm
    assert "nav: state_machine.project.list" not in board_fsm
    assert '<FONT POINT-SIZE="8" COLOR="#64748b">emitted local signal</FONT>' in composition
    assert "access_policy.project.reviewer" in operation
    assert 'graph [label="command.project.approve"' not in operation
    assert "Project.status" in operation
    assert "domain_event.project.approved" in operation
    assert "domain_event.project.created" in create_operation
    assert '<FONT POINT-SIZE="10"><B>payload</B></FONT>' in operation
    assert '<FONT POINT-SIZE="10">payload</FONT><FONT POINT-SIZE="8" COLOR="#94a3b8">&#160;&#160;schema.project.approved</FONT>' in operation
    assert "payload:" not in operation
    assert "payload_schema:" not in operation
    assert "emitted by" not in operation
    assert "<B>rules:</B>&#160;&#160;subject_has_role member" in create_operation
    assert ('"application' + "_action_application" + '_action_project_approve" [shape=') not in operation
    assert "transition command" not in operation
    assert operation.index('"operation_input_command_project_approve"') < operation.index('"operation_policy_access_policy_project_reviewer"')
    assert operation.index('"operation_policy_access_policy_project_reviewer"') < operation.index('"operation_resource_command_project_approve_lifecycle_transition_entity_type_project_status"')
    assert operation.index('"operation_resource_command_project_approve_lifecycle_transition_entity_type_project_status"') < operation.index('"operation_outcome_command_project_approve_approved"')
    assert operation.index('"operation_outcome_command_project_approve_approved"') < operation.index('"operation_event_command_project_approve_domain_event_project_approved"')
    assert '"operation_input_command_project_approve" -> "operation_policy_access_policy_project_reviewer" [label="authorize"' in operation
    assert '"operation_policy_access_policy_project_reviewer" -> "operation_resource_command_project_approve_lifecycle_transition_entity_type_project_status" [label="lifecycle_transition"' in operation
    assert '"operation_resource_command_project_approve_lifecycle_transition_entity_type_project_status" -> "operation_outcome_command_project_approve_approved" [label="success"' in operation
    assert '"operation_outcome_command_project_approve_approved" -> "operation_event_command_project_approve_domain_event_project_approved" [label="emit"' in operation
    assert "<B>access_policy:</B>" not in operation
    assert "<B>creates:</B>" not in create_operation
    assert "<B>kind:</B>" not in operation
    assert "<B>resource</B>" not in create_operation
    assert "<FONT POINT-SIZE=\"10\">command: command.project.create</FONT>" not in create_operation
    assert "<B>emits</B>" not in operation
    assert "delegated external interface" in cli_approve_external_interface
    assert "command.project.approve action map" not in cli_approve_external_interface
    assert "Project.status" not in cli_approve_external_interface
    assert "access_policy.project.reviewer" in cli_approve_external_interface
    assert "authorization_effect" not in operation
    assert "<B>source:</B>&#160;&#160;local_signal.project_select" in composition
    assert "ready to ready" not in composition
    assert "<B>transition:</B>" not in composition
    assert "selected state:" not in composition
    composition_data_project = '<FONT POINT-SIZE="10"><B>payload:</B>&#160;&#160;project_id</FONT><FONT POINT-SIZE="8" COLOR="#94a3b8">&#160;&#160;string</FONT>'
    composition_set_project = '<FONT POINT-SIZE="10"><B>set:</B>&#160;&#160;selected_project_id</FONT><FONT POINT-SIZE="8" COLOR="#94a3b8">&#160;&#160;string | null</FONT><FONT POINT-SIZE="8">&#160;←&#160;project_id</FONT>'
    assert composition_data_project in composition
    assert composition_set_project in composition
    assert "selected_project_id &lt;- project_id" not in composition
    assert "set selected_project_id" not in composition
    assert "<B>flow:</B>" not in composition
    assert "state machine context" not in composition
    assert "state_machine.project.board" not in composition
    assert "dashboard state machine" not in composition
    assert "query.project.board.list" not in composition
    assert "<B>entity_type:</B>" not in composition
    assert "<B>context</B>" not in composition
    assert "$signal.payload." not in composition
    assert "$domain_event." not in composition
    assert "$state_machine." not in composition
    assert "<B>from:</B>" not in composition
    assert "<B>effects:</B>" not in composition
    assert "Layout / mounted state machines" not in composition
    assert "Local signal routing" not in composition
    assert "Sync rules" not in composition
    assert "<B>region:</B>" not in composition
    assert "<B>list</B>" in composition
    assert "<B>detail</B>" in composition
    assert "<B>activity</B>" in composition
    assert "<B>state_machine:</B>&#160;&#160;state_machine.project.list" in composition
    assert "<B>state_machine:</B>&#160;&#160;state_machine.project.detail" in composition
    assert "<B>causes:</B>&#160;&#160;to loading" in composition
    assert "context binding" not in composition
    assert "state_machine.selected_project_id" not in composition
    assert "state machine context" not in composition
    assert "order:" not in composition
    assert "element:" not in composition
    assert "role:" not in composition
    assert "required:" not in composition
    assert "html_layout_region_nav" not in composition
    assert "fontcolor" not in composition
    assert '<FONT POINT-SIZE="8" COLOR="#64748b">html_route external interface</FONT>' in external_interface
    assert "<B>route:</B>&#160;&#160;route.project.board" in external_interface
    assert "<B>path params</B>" in external_interface
    assert '<FONT POINT-SIZE="10">workspace_id</FONT><FONT POINT-SIZE="8" COLOR="#94a3b8">&#160;&#160;string</FONT>' in external_interface
    assert '<FONT POINT-SIZE="8" COLOR="#64748b">invoked state machine (html)</FONT>' in external_interface
    state_machine_invocation_card = external_interface[external_interface.index('"external_interface_invocation_state_machine_project_board"') :]
    assert 'COLOR="#9333ea" BGCOLOR="#ffffff"' in state_machine_invocation_card
    assert 'BGCOLOR="#faf5ff"' in state_machine_invocation_card
    assert '<FONT POINT-SIZE="8" COLOR="#64748b">invoked state machine (textual)</FONT>' in cli_external_interface
    assert '<FONT POINT-SIZE="8" COLOR="#64748b">invoked workflow</FONT>' in worker_external_interface
    assert "<B>integration message disposition</B>" not in worker_external_interface
    assert '<FONT POINT-SIZE="10"><B>payload:</B>&#160;&#160;payload</FONT><FONT POINT-SIZE="8" COLOR="#94a3b8">&#160;&#160;schema.project.approved</FONT>' in worker_external_interface
    worker_entry_card = worker_external_interface[worker_external_interface.index('"external_interface_external_interface_worker_project_approval_notice"') : worker_external_interface.index('"external_interface_invocation_workflow_project_approval_notice"')]
    assert '<FONT POINT-SIZE="10"><B>payload:</B>&#160;&#160;payload</FONT><FONT POINT-SIZE="8" COLOR="#94a3b8">&#160;&#160;schema.project.approved</FONT>' in worker_entry_card
    worker_accepted_card = worker_external_interface[worker_external_interface.index('"external_interface_response_external_interface_worker_project_approval_notice_accepted"') : worker_external_interface.index('"external_interface_response_external_interface_worker_project_approval_notice_malformed"')]
    worker_malformed_card = worker_external_interface[worker_external_interface.index('"external_interface_response_external_interface_worker_project_approval_notice_malformed"') :]
    assert "<B>accepted</B>" in worker_accepted_card
    assert "success disposition" in worker_accepted_card
    assert 'COLOR="#16a34a" BGCOLOR="#ffffff"' in worker_accepted_card
    assert "<B>malformed</B>" in worker_malformed_card
    assert "failure disposition" in worker_malformed_card
    assert 'COLOR="#dc2626" BGCOLOR="#ffffff"' in worker_malformed_card
    for external_interface_flow in (external_interface, cli_external_interface, cli_approve_external_interface, api_external_interface, worker_external_interface):
        assert ('label="' + "entry" + '"') not in external_interface_flow
        assert 'label="exit"' not in external_interface_flow
        assert ("entry" + "_start") not in external_interface_flow
        assert ("entry" + "_exit") not in external_interface_flow
        assert "external_interface_input" not in external_interface_flow
        assert "external data" not in external_interface_flow
    assert "<B>html renderer handoff</B>" not in external_interface
    assert 'label="ui loop"' not in external_interface
    assert "<B>external interface input</B>" not in external_interface
    assert "<B>external interface output</B>" not in external_interface
    assert "external_interface_mount" not in external_interface
    assert "nav mount" not in external_interface
    assert "<B>html renderer handoff</B>" not in cli_external_interface
    assert "<B>args</B>" in cli_external_interface
    assert 'label="tui loop"' not in cli_external_interface
    assert "<B>external interface input</B>" not in cli_external_interface
    assert "external_interface_mount" not in cli_external_interface
    assert "<B>transitions</B>" not in cli_approve_external_interface
    assert '<FONT POINT-SIZE="10">Project.status</FONT><FONT POINT-SIZE="8" COLOR="#94a3b8">&#160;&#160;enum&lt;draft|submitted|approved|archived&gt;</FONT><FONT POINT-SIZE="8">&#160;&#160;submitted → approved</FONT>' not in cli_approve_external_interface
    assert "command.project.approve action map" not in cli_approve_external_interface
    assert "<B>state:</B>" not in cli_approve_external_interface
    assert "<B>change:</B>" not in cli_approve_external_interface
    assert "<B>transition:</B>" not in cli_approve_external_interface
    assert "<B>args</B>" in cli_approve_external_interface
    assert "success response" in cli_approve_external_interface
    assert "failure response" in cli_approve_external_interface
    assert "<B>external interface input</B>" not in cli_approve_external_interface
    assert "<B>external interface output</B>" not in cli_approve_external_interface
    assert "success response" in api_external_interface
    assert "failure response" in api_external_interface
    api_external_interface_card = api_external_interface[api_external_interface.index('"external_interface_external_interface_api_project_create"') : api_external_interface.index('"external_interface_invocation_command_project_create"')]
    success_response_card = api_external_interface[api_external_interface.index('"external_interface_response_external_interface_api_project_create_created"') : api_external_interface.index('"external_interface_response_external_interface_api_project_create_validation_failed"')]
    failure_response_card = api_external_interface[api_external_interface.index('"external_interface_response_external_interface_api_project_create_validation_failed"') :]
    assert 'COLOR="#0891b2" BGCOLOR="#ffffff"' in api_external_interface_card
    assert "<B>path params</B>" in api_external_interface_card
    assert "<B>body</B>" in api_external_interface_card
    assert 'COLOR="#16a34a" BGCOLOR="#ffffff"' in success_response_card
    assert 'BGCOLOR="#f0fdf4"' in success_response_card
    assert 'COLOR="#dc2626" BGCOLOR="#ffffff"' in failure_response_card
    assert 'BGCOLOR="#fef2f2"' in failure_response_card
    assert "<B>external interface input</B>" not in api_external_interface
    assert "<B>external interface output</B>" not in api_external_interface
    assert "<B>external interface input</B>" not in worker_external_interface
    assert "<B>external interface output</B>" not in worker_external_interface
    assert "<B>body</B>" in api_external_interface
    assert 'body</FONT><FONT POINT-SIZE="8" COLOR="#94a3b8">&#160;&#160;Project</FONT><FONT POINT-SIZE="8">&#160;←&#160;$action_outcome.result</FONT>' in api_external_interface
    assert "validation_failed" in api_external_interface
    invocation_card = api_external_interface[api_external_interface.index('"external_interface_invocation_command_project_create"') : api_external_interface.index('"external_interface_response_external_interface_api_project_create_created"')]
    assert '<FONT POINT-SIZE="10"><B>input</B></FONT>' not in invocation_card
    assert '<FONT POINT-SIZE="10"><B>input:</B>&#160;&#160;customer</FONT>' not in invocation_card
    assert '<FONT POINT-SIZE="10">customer</FONT>' not in invocation_card
    assert '<FONT POINT-SIZE="10">workspace_id</FONT><FONT POINT-SIZE="8" COLOR="#94a3b8">&#160;&#160;string</FONT>' not in invocation_card
    assert "<B>outcomes</B>" not in invocation_card
    assert "validation_failed" not in invocation_card
    assert "command.project.create action map" not in invocation_card
    assert "<B>detail:</B>" not in invocation_card
    assert "<B>emit:</B>&#160;&#160;created → domain_event.project.created" not in invocation_card
    assert '<FONT POINT-SIZE="10"><B>payload_schema:</B>&#160;&#160;payload_schema</FONT><FONT POINT-SIZE="8" COLOR="#94a3b8">&#160;&#160;Project</FONT>' not in invocation_card
    assert "<B>emits:</B>&#160;&#160;domain_event.project.created" not in invocation_card
    assert "<B>access_policy:</B>" not in invocation_card
    assert "access_policy.project.member" in invocation_card
    assert "<B>authorization_effect:</B>&#160;&#160;permit" not in invocation_card
    assert "<B>resource</B>" not in invocation_card
    assert "<FONT POINT-SIZE=\"10\">command: command.project.create</FONT>" not in invocation_card
    assert "<FONT POINT-SIZE=\"10\">entity_type: Project</FONT>" not in invocation_card
    assert "<B>rules:</B>&#160;&#160;unconditional true" not in invocation_card
    cli_approve_invocation_card = cli_approve_external_interface[cli_approve_external_interface.index('"external_interface_invocation_external_interface_api_project_approve"') : cli_approve_external_interface.index('"external_interface_response_external_interface_cli_project_approve_approved"')]
    assert "<B>external_interface.api.project.approve</B>" in cli_approve_external_interface
    assert "delegated external interface" in cli_approve_external_interface
    assert "<B>emit:</B>&#160;&#160;approved → domain_event.project.approved" not in cli_approve_invocation_card
    assert '<FONT POINT-SIZE="10"><B>payload_schema:</B>&#160;&#160;payload_schema</FONT><FONT POINT-SIZE="8" COLOR="#94a3b8">&#160;&#160;schema.project.approved</FONT>' not in cli_approve_invocation_card
    assert "<B>emits:</B>&#160;&#160;domain_event.project.approved" not in cli_approve_invocation_card
    assert "<B>access_policy:</B>" not in cli_approve_invocation_card
    assert "access_policy.project.reviewer" in cli_approve_invocation_card
    assert "principal ← adapter_input.body.approved_by" not in cli_approve_invocation_card
    assert "<B>rules:</B>&#160;&#160;Project.status = submitted" not in cli_approve_invocation_card
    external_interface_input = '<FONT POINT-SIZE="10"><B>input:</B>&#160;&#160;list_board.workspace_id</FONT><FONT POINT-SIZE="8" COLOR="#94a3b8">&#160;&#160;string</FONT>'
    assert external_interface_input in external_interface
    assert external_interface.index(external_interface_input) < external_interface.index("<B>query_bindings:</B>&#160;&#160;list_board")
    assert external_interface.index("<B>query_bindings:</B>&#160;&#160;list_board") < external_interface.index("<B>load:</B>&#160;&#160;query.project.list")
    assert "<B>signal_sync_rules:</B>&#160;&#160;select_project_updates_state_machines" in external_interface
    assert "<B>state_machine:</B>" not in external_interface
    assert "state_machine.selected_project_id" not in external_interface
    assert "$state_machine." not in external_interface
    assert "workflow_start" not in workflow
    assert '"workflow_input_domain_event_domain_event_project_approved" -> "workflow_workflow_project_approval_notice"' in workflow
    workflow_completed_card = workflow[workflow.index('"workflow_outcome_workflow_project_approval_notice_completed"') : workflow.index('"workflow_outcome_workflow_project_approval_notice_delivery_failed"')]
    workflow_failed_card = workflow[workflow.index('"workflow_outcome_workflow_project_approval_notice_delivery_failed"') :]
    assert 'COLOR="#16a34a" BGCOLOR="#ffffff"' in workflow_completed_card
    assert 'COLOR="#dc2626" BGCOLOR="#ffffff"' in workflow_failed_card
    assert '<FONT POINT-SIZE="8" COLOR="#64748b">domain event input</FONT>' in workflow
    assert '<FONT POINT-SIZE="10"><B>payload:</B>&#160;&#160;payload</FONT><FONT POINT-SIZE="8" COLOR="#94a3b8">&#160;&#160;schema.project.approved</FONT>' in workflow
    assert '<FONT POINT-SIZE="8" COLOR="#64748b">workflow step</FONT>' in workflow
    assert "<B>command:</B>&#160;&#160;command.project.send_approval_notice" in workflow
    workflow_step = workflow[workflow.index('"workflow_step_workflow_project_approval_notice_send_notice"') :]
    assert '<FONT POINT-SIZE="10"><B>input</B></FONT>' not in workflow_step
    assert "approved_by ← workflow_input.payload.approved_by" in workflow_step
    assert '<FONT POINT-SIZE="10">completed</FONT><FONT POINT-SIZE="8" COLOR="#94a3b8">&#160;&#160;schema.project.notice_result</FONT>' in workflow
    assert '<FONT POINT-SIZE="10">delivery_failed</FONT><FONT POINT-SIZE="8" COLOR="#94a3b8">&#160;&#160;Problem</FONT>' in workflow
    assert "access_policy.project.reviewer" in workflow_step
    assert "success workflow outcome" in workflow
    assert "failure workflow outcome" in workflow
    assert "sent: complete_as → completed" in workflow
    assert "delivery_failed: retry_policy → delivery_failed" in workflow
    for graph_id, dot_source in {"state_machine_project_list": state_machine, "project_board": composition, "html_project_board": external_interface, "api_project_create": api_external_interface, "cli_project_approve": cli_approve_external_interface, "project_approval_notice": workflow}.items():
        svg = _render_graphviz_svg(dot_source, graph_id)
        assert svg.lstrip().startswith("<svg")
        assert "</svg>" in svg


def test_composition_dot_syncs_local_signals_generically() -> None:
    state_machine = {
        "archetype": "workspace",
        "entity_type": "generic.entity_type",
        "context_schema": O({"selected_id": P("ID"), "workspace_id": P("ID")}),
        "query_bindings": {},
        "renderers": {
            "html": {
                "layout": {
                    "regions": {
                        "receiver": {"order": 10, "element": "aside", "role": "complementary"},
                        "source": {"order": 20, "element": "main", "role": "main", "must_render": True},
                        "unused": {"order": 30, "element": "footer", "role": "contentinfo"},
                    }
                }
            }
        },
        "child_state_machines": [
            {"id": "publisher", "html_region": "source", "state_machine": "state_machine.alpha", "initial_state": "idle", "context_bindings": {}},
            {"id": "receiver", "html_region": "receiver", "state_machine": "state_machine.beta", "initial_state": "waiting", "context_bindings": {"item_id": {"from": "$state_machine.selected_id"}}},
        ],
        "signal_sync_rules": [
            {
                    "id": "sync_alpha_beta",
                "when": {"instance": "publisher", "local_signal": "ready"},
                "effects": [
                    {"send": {"instance": "receiver", "local_signal": "consume", "payload_bindings": {"item_id": {"from": "$signal.payload.id"}}}},
                    {"set": {"context": "selected_id", "from": "$signal.payload.id"}},
                ],
            }
        ],
    }
    contract = {
        "state_machines": {
            "state_machine.alpha": {
                "local_signals": {
                    "accepts": {
                            "local_signals": {"submit": {"payload_schema": O({"id": P("ID")})}},
                        "data_refresh_signals": {},
                    },
                    "emits": {
                            "local_signals": {"ready": {"payload_schema": O({"id": P("ID")})}},
                    },
                },
                "transitions": [
                    {
                        "trigger": {"local_signal": "submit"},
                        "from": "idle",
                        "to": "ready",
                        "effects": [{"emit": {"local_signal": "ready", "payload_bindings": {"id": {"from": "$signal.payload.id"}}}}],
                    }
                ]
            },
            "state_machine.beta": {
                "local_signals": {
                    "accepts": {
                            "local_signals": {"consume": {"payload_schema": O({"item_id": P("ID")})}},
                        "data_refresh_signals": {},
                    },
                    "emits": {"local_signals": {}},
                },
                "transitions": [
                    {
                        "trigger": {"local_signal": "consume"},
                        "from": "waiting",
                        "to": "consumed",
                    }
                ]
            }
        }
    }

    composition = composition_dot("generic.state_machine", state_machine, contract)

    assert "emitted local signal" in composition
    assert "sent local signal" in composition
    assert "local signal sync" in composition
    assert '<FONT POINT-SIZE="8" COLOR="#64748b">source mount</FONT>' in composition
    assert "<B>source:</B>&#160;&#160;local_signal.submit" in composition
    assert "idle to ready" not in composition
    assert "<B>transition:</B>" not in composition
    assert "local_signal.consume" in composition
    assert "<B>causes:</B>&#160;&#160;to consumed" in composition
    assert '<FONT POINT-SIZE="10"><B>payload:</B>&#160;&#160;id</FONT><FONT POINT-SIZE="8" COLOR="#94a3b8">&#160;&#160;string</FONT>' in composition
    assert '<FONT POINT-SIZE="10"><B>set:</B>&#160;&#160;selected_id</FONT><FONT POINT-SIZE="8" COLOR="#94a3b8">&#160;&#160;string</FONT><FONT POINT-SIZE="8">&#160;←&#160;id</FONT>' in composition
    assert 'item_id</FONT><FONT POINT-SIZE="8" COLOR="#94a3b8">&#160;&#160;string</FONT><FONT POINT-SIZE="8">&#160;←&#160;id</FONT>' in composition
    assert "item_id &lt;- state_machine.selected_id" not in composition
    assert "context binding" not in composition
    assert "$signal.payload." not in composition
    assert "$domain_event." not in composition
    assert "$state_machine." not in composition
    assert "<B>target:</B>" not in composition
    assert "<B>from:</B>" not in composition
    assert "<B>effects:</B>" not in composition
    assert '"local_signal_effect_sync_alpha_beta_0" -> "child_state_machine_receiver"' in composition
    assert "local_signal_effect_sync_alpha_beta_1" not in composition
    assert '#ecfdf5' in composition
    assert '#047857' in composition
    assert '#fdf2f8' in composition
    assert "No mounted state machines" not in composition
    assert "<B>region:</B>" not in composition
    assert "<B>publisher</B>" in composition
    assert "<B>receiver</B>" in composition
    assert "<B>state_machine:</B>&#160;&#160;state_machine.alpha" in composition
    assert "<B>state_machine:</B>&#160;&#160;state_machine.beta" in composition
    assert "unused" not in composition
    assert "order:" not in composition
    assert "element:" not in composition
    assert "role:" not in composition
    assert "required:" not in composition
    assert "layout_instance" not in composition
    assert "html_layout_region_empty" not in composition
    assert "state_machine.project.board" not in composition
    assert "state_machine.project" not in composition
    svg = _render_graphviz_svg(composition, "generic_composition")
    assert svg.lstrip().startswith("<svg")


def test_audit_transition_rationale_renders_for_otherwise_sparse_card() -> None:
    author = read_yaml(ROOT / SOURCE_SPEC_PATH)
    activity = author["state_machines"]["state_machine.project.activity"]
    cleared = next(transition for transition in activity["transitions"] if transition["trigger"] == {"local_signal": "selection_cleared"})
    cleared.pop("effects")
    cleared["rationale"] = "Clearing the selection returns the activity state to its empty state."
    contract = compile_source(author)

    state_machine = state_machine_dot("state_machine.project.activity", contract["state_machines"]["state_machine.project.activity"], contract)

    assert "Clearing the selection returns the activity state" in state_machine
    assert "its empty state." in state_machine


def test_generated_flowchart_svgs_include_contract_audit_details() -> None:
    list_fsm = (ROOT / state_machine_graph_file("state_machine.project.list")).read_text(encoding="utf-8")
    detail_fsm = (ROOT / state_machine_graph_file("state_machine.project.detail")).read_text(encoding="utf-8")
    activity_fsm = (ROOT / state_machine_graph_file("state_machine.project.activity")).read_text(encoding="utf-8")
    composition = (ROOT / composition_file("state_machine.project.board")).read_text(encoding="utf-8")
    api_external_interface = (ROOT / external_interface_flow_file("external_interface.api.project.create", "http_api")).read_text(encoding="utf-8")
    cli_approve_external_interface = (ROOT / external_interface_flow_file("external_interface.cli.project.approve", "cli")).read_text(encoding="utf-8")
    workflow = (ROOT / workflow_flow_file("workflow.project.approval_notice")).read_text(encoding="utf-8")
    approve_operation = (ROOT / operation_flow_file("command.project.approve")).read_text(encoding="utf-8")
    assert "data_refresh_signal.projects_loaded" in list_fsm
    assert "on data_refresh_signal.projects_loaded" not in list_fsm
    assert "text.project.list.ready.heading" in list_fsm
    assert "asset.project.list.empty.illustration" in list_fsm
    assert "emit:" in list_fsm
    assert "local_signal.project_selected" in list_fsm
    assert "payload:" in list_fsm
    assert "emit local_signal.project_selected" not in list_fsm
    assert "effects:" not in list_fsm
    assert "application" + "_action: query.project.list" not in list_fsm
    assert "query_bindings:" in list_fsm
    assert "list_projects" in list_fsm
    assert "workspace_id: string" not in list_fsm
    assert 'workspace_id</text>' in list_fsm
    assert 'fill="#94a3b8">\xa0\xa0string</text>' in list_fsm
    assert "query.project.list fields" in list_fsm
    assert "title: Text" not in list_fsm
    assert "status: enum" not in list_fsm
    assert 'fill="#94a3b8">\xa0\xa0string</text>' in list_fsm
    assert 'fill="#94a3b8">\xa0\xa0enum&lt;draft|submitted|approved|archived&gt;</text>' in list_fsm
    assert "Project fields" not in list_fsm
    assert "projection:" not in list_fsm
    assert "entity_type:" not in list_fsm
    assert "context:" not in list_fsm
    assert "&#45; data_refresh_signal.projects_loaded" not in list_fsm
    assert "&#45; text.project" not in list_fsm
    assert "&#45; none" not in list_fsm
    assert ">rationale<" not in list_fsm
    assert "loading &#45;&gt; empty" not in list_fsm
    assert "(initial)" not in list_fsm
    assert "initial:" not in list_fsm
    assert "state machine html renderer" not in list_fsm
    assert "declared, no arrow" not in list_fsm
    assert "transition domain_events" not in list_fsm
    assert "emitted domain_events" not in list_fsm
    assert "$signal.payload." not in list_fsm
    assert "$domain_event." not in list_fsm
    assert "text.project.detail.ready.heading" in detail_fsm
    assert "query.project.read fields" in detail_fsm
    assert "array&lt;Project&gt;" in list_fsm
    assert "query.project.read" in detail_fsm
    assert 'fill="#94a3b8">\xa0\xa0Project</text>' in detail_fsm
    assert "summary: Text" not in detail_fsm
    assert 'fill="#94a3b8">\xa0\xa0string</text>' in detail_fsm
    assert "command.project.approve" in detail_fsm
    assert "command.project.archive" in detail_fsm
    assert "command.project.approve:" in detail_fsm
    assert "access_policy.project.reviewer" in detail_fsm
    assert "query.project.read fields" in activity_fsm
    assert "updated_at: Timestamp" not in activity_fsm
    assert "assignee: Text" not in activity_fsm
    assert 'fill="#94a3b8">\xa0\xa0string:date&#45;time</text>' in activity_fsm
    assert "input:" in detail_fsm
    assert "query_bindings:" in detail_fsm
    assert "read_project" in detail_fsm
    assert "project_id: string" not in detail_fsm
    assert 'project_id</text>' in detail_fsm
    assert 'fill="#94a3b8">\xa0\xa0string</text>' in detail_fsm
    assert "application" + "_action: query.project.read" not in detail_fsm
    assert "set:" in detail_fsm
    assert "project_id &lt;&#45; null" not in detail_fsm
    assert 'fill="#94a3b8">\xa0\xa0string</text>' in detail_fsm
    assert '\xa0←\xa0null</text>' in detail_fsm
    assert "select_project_updates_state_machines" not in detail_fsm
    assert "data_refresh_signal.project_loaded" not in activity_fsm
    assert "input:" in activity_fsm
    assert "query_bindings:" in activity_fsm
    assert "read_activity" in activity_fsm
    assert "project_id: string" not in activity_fsm
    assert 'project_id</text>' in activity_fsm
    assert 'fill="#94a3b8">\xa0\xa0string</text>' in activity_fsm
    assert "set:" in activity_fsm
    assert "project_id &lt;&#45; null" not in activity_fsm
    assert '\xa0←\xa0null</text>' in activity_fsm
    assert "emitted local signal" in composition
    assert "sent local signal" in composition
    assert "local_signal.project_select" in composition
    assert "selection_changed" in composition
    assert "to loading" in composition
    assert "to ready" in composition
    assert "none to loading" not in composition
    assert "empty to ready" not in composition
    assert "selected state:" not in composition
    assert "set:" in composition
    assert "selected_project_id &lt;&#45; project_id" not in composition
    assert 'selected_project_id</text>' in composition
    assert 'fill="#94a3b8">\xa0\xa0string</text>' in composition
    assert '\xa0←\xa0project_id</text>' in composition
    assert "set selected_project_id" not in composition
    assert "flow:" not in composition
    assert "state machine context" not in composition
    assert "state_machine.project.board" not in composition
    assert "dashboard state machine" not in composition
    assert "query.project.board.list" not in composition
    assert "context binding" not in composition
    assert "state_machine.selected_project_id" not in composition
    assert "state machine context" not in composition
    assert "$signal.payload." not in composition
    assert "$domain_event." not in composition
    assert "$state_machine." not in composition
    assert "region:" not in composition
    assert "mount" in composition
    assert "state_machine:" in composition
    assert "instance:" not in composition
    assert "target:" not in composition
    assert "from:" not in composition
    assert "effects:" not in composition
    assert "Layout / mounted state machines" not in composition
    assert "Local signal routing" not in composition
    assert "Sync rules" not in composition
    assert "nav" in composition
    assert "main" in composition
    assert "aside" in composition
    assert "order:" not in composition
    assert "element:" not in composition
    assert "role:" not in composition
    assert "required:" not in composition
    assert "access_policy.project.member" in api_external_interface
    assert "<B>rules:</B>" not in api_external_interface
    assert "access_policy.project.reviewer" in cli_approve_external_interface
    assert "Project.status = submitted" not in cli_approve_external_interface
    assert "access_policy.project.reviewer" in workflow
    assert "access_policy.project.reviewer" in approve_operation
    assert "rules" in approve_operation
    assert "submitted → approved" in approve_operation
    assert "domain_event.project.approved" in approve_operation


def test_audit_html_sources_render_copy_assets_and_fixture_fields() -> None:
    ready = ROOT / render_example_render_file("state_machine.project.board", "state_machine.project.board.ready.ready_selected.audit", "viewport_profile.default", "wide", "html")
    text = ready.read_text(encoding="utf-8")
    assert "Dispatch queue" in text
    assert "Replace rooftop condenser fan · Atlas Foods" in text
    assert "Latest activity" in text
    assert "High priority" in text
    assert "Replace rooftop condenser fan" in text
    assert "Atlas Foods" in text
    assert "fixture.projects.audit_records" not in text
    assert "data-audit" not in text

    empty = ROOT / render_example_render_file("state_machine.project.board", "state_machine.project.board.ready.empty.audit", "viewport_profile.default", "compact", "html")
    empty_text = empty.read_text(encoding="utf-8")
    assert "No dispatch projects yet" in empty_text
    assert "asset.project.list.empty.illustration" in empty_text
    assert "data:image/svg+xml;base64" in empty_text


def test_audit_asset_placeholder_is_generic_and_not_named() -> None:
    asset = ROOT / "spec/generated/audit_evidence/state_machines/state_machine_project_board/states/ready/render_examples/state_machine_project_board_ready_empty_audit/assets/asset_project_list_empty_illustration.svg"
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


def test_text_resource_placeholder_is_required_for_used_text_ref() -> None:
    author = read_yaml(ROOT / SOURCE_SPEC_PATH)
    text_id = next(iter(author["text_resources"]))
    del author["text_resources"][text_id]
    with pytest.raises(ContractError, match="text resources drift"):
        compile_source(author)


def test_asset_placeholder_schema_rejects_missing_visual_intent() -> None:
    author = read_yaml(ROOT / SOURCE_SPEC_PATH)
    asset_id = next(iter(author["media_assets"]))
    del author["media_assets"][asset_id]["placeholder"]
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)


def test_render_example_coverage_is_required() -> None:
    author = read_yaml(ROOT / SOURCE_SPEC_PATH)
    author["state_machines"]["state_machine.project.board"]["states"]["ready"].pop("render_examples")
    with pytest.raises(ContractError, match="Missing render audit coverage for composed state machine states"):
        compile_source(author)


def test_audit_validator_rejects_corrupt_html_png(tmp_path: Path) -> None:
    project = tmp_path / "project"
    copy_project_tree(ROOT, project)
    contract = read_yaml(project / COMPILED_SPEC_PATH)
    png = next(project / path for path in audit_expected_files(contract) if path.endswith(".png"))
    png.write_bytes(b"not-a-png")
    with pytest.raises(ContractError, match="not PNG"):
        validate_audit_outputs(project, contract)


def test_audit_validator_rejects_missing_state_machine_svg(tmp_path: Path) -> None:
    project = tmp_path / "project"
    copy_project_tree(ROOT, project)
    contract = read_yaml(project / COMPILED_SPEC_PATH)
    svg = next(project / path for path in audit_expected_files(contract) if path.startswith("spec/generated/audit_evidence/state_machines/") and path.endswith("/state_machine.svg"))
    svg.unlink()
    with pytest.raises(ContractError, match="audit generated files"):
        validate_audit_outputs(project, contract)


def test_audit_generation_restores_existing_outputs_on_renderer_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = tmp_path / "project"
    copy_project_tree(ROOT, project)
    contract = read_yaml(project / COMPILED_SPEC_PATH)
    audit_root = project / "spec" / "generated" / "audit_evidence"
    before = {
        str(path.relative_to(audit_root)): path.read_bytes()
        for path in audit_root.rglob("*")
        if path.is_file()
    }
    monkeypatch.setenv("CONTRACT_AUDIT_CHROMIUM", "/does/not/exist")

    with pytest.raises(ContractError, match="Visual audit renderer failed"):
        generate_audit(project, contract)

    after = {
        str(path.relative_to(audit_root)): path.read_bytes()
        for path in audit_root.rglob("*")
        if path.is_file()
    }
    assert after == before


def test_compile_restores_generated_tree_on_audit_renderer_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = tmp_path / "project"
    copy_project_tree(ROOT, project)
    generated = project / "spec" / "generated"
    before = {
        str(path.relative_to(generated)): path.read_bytes()
        for path in generated.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
    }
    monkeypatch.setenv("CONTRACT_AUDIT_CHROMIUM", "/does/not/exist")

    with pytest.raises(ContractError, match="Visual audit renderer failed"):
        write_compiled(project, project / SOURCE_SPEC_PATH)

    after = {
        str(path.relative_to(generated)): path.read_bytes()
        for path in generated.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
    }
    assert after == before
