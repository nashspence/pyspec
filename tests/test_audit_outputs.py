from __future__ import annotations
from pathlib import Path

import pytest

from pyspec_contract.audit import (
    _render_graphviz_svg,
    audit_expected_files,
    composition_dot,
    composition_file,
    entrypoint_flow_dot,
    entrypoint_flow_file,
    state_machine_dot,
    state_machine_graph_file,
    view_state_root,
    generate_audit,
    audit_case_render_file,
    workflow_flow_dot,
    workflow_flow_file,
)
from pyspec_contract.compile import ContractError, compile_source, write_compiled
from pyspec_contract.io import read_yaml
from pyspec_contract.paths import COMPILED_SPEC_PATH, SOURCE_SPEC_PATH
from pyspec_contract.projection_validators import validate_audit_outputs
from tests.helpers import EXAMPLE_ROOT, copy_project_tree

ROOT = EXAMPLE_ROOT
PNG_HEADER = bytes([137, 80, 78, 71, 13, 10, 26, 10])


def P(name: str) -> dict[str, str]:
    return {"primitive": name}


def _contract(root: Path = ROOT) -> dict:
    return read_yaml(root / COMPILED_SPEC_PATH)


def test_audit_outputs_cover_full_contract() -> None:
    contract = _contract()
    expected = audit_expected_files(contract)
    assert "spec/generated/audit_evidence/state_machines/state_machine_project_list/state_machine.svg" in expected
    assert "spec/generated/audit_evidence/state_machines/state_machine_project_board/view_states/ready/composition.svg" in expected
    assert "spec/generated/audit_evidence/entrypoints/html_route/entry_point_html_project_board/flow.svg" in expected
    assert "spec/generated/audit_evidence/entrypoints/cli/entry_point_cli_project_board/flow.svg" in expected
    assert "spec/generated/audit_evidence/workflows/workflow_project_approval_notice/flow.svg" in expected
    assert any(path.startswith("spec/generated/audit_evidence/state_machines/") and "/view_states/" in path and path.endswith("/text.yaml") for path in expected)
    assert any(path.startswith("spec/generated/audit_evidence/state_machines/") and "/view_states/" in path and "/renders/" in path and path.endswith(".png") for path in expected)
    assert any(path.startswith("spec/generated/audit_evidence/state_machines/") and "/cases/" in path and "/renders/" in path and path.endswith(".html") for path in expected)
    assert any(path.startswith("spec/generated/audit_evidence/state_machines/") and "/cases/" in path and "/renders/" in path and path.endswith(".svg") for path in expected)
    assert audit_case_render_file("state_machine.project.board", "state_machine.project.board.ready.ready_selected.audit", "render_profile.default", "wide", "html").endswith("/renders/html.render_profile_default.wide.source.html")
    assert audit_case_render_file("state_machine.project.board", "state_machine.project.board.ready.ready_selected.audit", "render_profile.default", "wide", "png").endswith("/renders/html.render_profile_default.wide.screenshot.png")
    assert audit_case_render_file("state_machine.project.board", "state_machine.project.board.ready.ready_selected.audit", "render_profile.default", "wide", "py").endswith("/renders/textual.render_profile_default.wide.source.py")
    assert audit_case_render_file("state_machine.project.board", "state_machine.project.board.ready.ready_selected.audit", "render_profile.default", "wide", "svg").endswith("/renders/textual.render_profile_default.wide.capture.svg")
    validate_audit_outputs(ROOT, contract)


def test_audit_flowcharts_use_graphviz_dot_sources() -> None:
    contract = _contract()
    state_machine = state_machine_dot("state_machine.project.list", contract["state_machines"]["state_machine.project.list"], contract)
    board = contract["state_machines"]["state_machine.project.board"]
    composition = composition_dot("state_machine.project.board.ready", {"context": board["context"], **board["view_states"]["ready"]}, contract)
    entrypoint = entrypoint_flow_dot("entry_point.html.project.board", contract["entry_points"]["entry_point.html.project.board"], contract)
    api_entrypoint = entrypoint_flow_dot("entry_point.api.project.create", contract["entry_points"]["entry_point.api.project.create"], contract)
    cli_entrypoint = entrypoint_flow_dot("entry_point.cli.project.board", contract["entry_points"]["entry_point.cli.project.board"], contract)
    cli_approve_entrypoint = entrypoint_flow_dot("entry_point.cli.project.approve", contract["entry_points"]["entry_point.cli.project.approve"], contract)
    worker_entrypoint = entrypoint_flow_dot("entry_point.worker.project.approval_notice", contract["entry_points"]["entry_point.worker.project.approval_notice"], contract)
    workflow = workflow_flow_dot("workflow.project.approval_notice", contract["workflows"]["workflow.project.approval_notice"], contract)
    assert state_machine.startswith("digraph ")
    assert composition.startswith("digraph ")
    assert entrypoint.startswith("digraph ")
    assert workflow.startswith("digraph ")
    assert "stateDiagram" not in state_machine
    assert "flowchart" not in composition
    assert "data_signal.ready" in state_machine
    assert "on data_signal.ready" not in state_machine
    assert '<FONT POINT-SIZE="8" COLOR="#64748b">initial view state</FONT>' in state_machine
    assert "initial_view_state" not in state_machine
    assert '<FONT POINT-SIZE="8" COLOR="#64748b">view state</FONT>' in state_machine
    assert '<FONT POINT-SIZE="8" COLOR="#64748b">transition signal</FONT>' in state_machine
    assert "text.project.list.ready.heading" in state_machine
    assert "asset.project.list.empty.illustration" in state_machine
    assert state_machine.index("<B>text</B>") < state_machine.index("<B>assets:</B>")
    assert state_machine.index("<B>assets:</B>") < state_machine.index("<B>available_operations:</B>")
    assert state_machine.index("<B>text:</B>&#160;&#160;text.project.list.ready.heading") < state_machine.index("<B>operation.project.list fields</B>")
    assert state_machine.index("<B>operation.project.list fields</B>") < state_machine.index("<B>available_operations</B>")
    assert "<B>emit:</B>&#160;&#160;message.project_selected" in state_machine
    payload_project = '<FONT POINT-SIZE="10"><B>payload:</B>&#160;&#160;project_id</FONT><FONT POINT-SIZE="8" COLOR="#94a3b8">&#160;&#160;ID</FONT>'
    assert payload_project in state_machine
    assert "<B>effects:</B>" not in state_machine
    assert "emit message.project_selected" not in state_machine
    assert "<B>projection:</B>" not in state_machine
    assert '<FONT POINT-SIZE="10"><B>load:</B>&#160;&#160;operation.project.list</FONT><FONT POINT-SIZE="8" COLOR="#94a3b8">&#160;&#160;array&lt;Project&gt;</FONT>' in state_machine
    assert "<B>query:</B>&#160;&#160;query.project.list.list" in state_machine
    input_workspace = '<FONT POINT-SIZE="10"><B>input:</B>&#160;&#160;workspace_id</FONT><FONT POINT-SIZE="8" COLOR="#94a3b8">&#160;&#160;ID</FONT>'
    assert input_workspace in state_machine
    assert state_machine.index(input_workspace) < state_machine.index("<B>query:</B>&#160;&#160;query.project.list.list")
    assert state_machine.index("<B>query:</B>&#160;&#160;query.project.list.list") < state_machine.index("<B>load:</B>&#160;&#160;operation.project.list")
    detail_transition = state_machine_dot("state_machine.project.detail", contract["state_machines"]["state_machine.project.detail"], contract)
    selection_card = detail_transition[detail_transition.index("message.selection_changed") :]
    input_project = '<FONT POINT-SIZE="10"><B>input:</B>&#160;&#160;project_id</FONT><FONT POINT-SIZE="8" COLOR="#94a3b8">&#160;&#160;ID</FONT>'
    assert selection_card.index(input_project) < selection_card.index("<B>query:</B>&#160;&#160;query.project.detail.read")
    load_project = '<FONT POINT-SIZE="10"><B>load:</B>&#160;&#160;operation.project.read</FONT><FONT POINT-SIZE="8" COLOR="#94a3b8">&#160;&#160;Project</FONT>'
    assert selection_card.index("<B>query:</B>&#160;&#160;query.project.detail.read") < selection_card.index(load_project)
    assert "<B>operation.project.list fields</B>" in state_machine
    assert '<FONT POINT-SIZE="10"><B>available_operations:</B>&#160;&#160;operation.project.create</FONT><FONT POINT-SIZE="8" COLOR="#94a3b8">&#160;&#160;Project</FONT>' in state_machine
    assert '<FONT POINT-SIZE="10">operation.project.submit</FONT><FONT POINT-SIZE="8" COLOR="#94a3b8">&#160;&#160;Project</FONT>' in state_machine
    assert '<FONT POINT-SIZE="10">title</FONT><FONT POINT-SIZE="8" COLOR="#94a3b8">&#160;&#160;Text</FONT>' in state_machine
    assert '<FONT POINT-SIZE="10">status</FONT><FONT POINT-SIZE="8" COLOR="#94a3b8">&#160;&#160;enum&lt;draft|submitted|approved|archived&gt;</FONT>' in state_machine
    assert '<FONT POINT-SIZE="10">summary</FONT><FONT POINT-SIZE="8" COLOR="#94a3b8">&#160;&#160;Text</FONT>' in detail_transition
    assert "title: Text" not in state_machine
    assert "status: enum" not in state_machine
    assert "<B>Project fields</B>" not in state_machine
    assert state_machine.count("query.project.list.list") == 4
    assert "<B>authorization_policies:</B>&#160;&#160;operation.project.create:" in state_machine
    assert "authorization_policy.project.create" in state_machine
    assert "<B>model:</B>" not in state_machine
    assert "<B>context:</B>" not in state_machine
    assert "$message." not in state_machine
    assert "$event." not in state_machine
    assert "emitted message" in composition
    assert "sent message" in composition
    assert "message route" in composition
    assert '<FONT POINT-SIZE="8" COLOR="#64748b">nav mount</FONT>' in composition
    board_fsm = state_machine_dot("state_machine.project.board", contract["state_machines"]["state_machine.project.board"], contract)
    assert "<B>child_state_machines</B>" in board_fsm
    assert '<FONT POINT-SIZE="10">nav</FONT><FONT POINT-SIZE="8" COLOR="#94a3b8">&#160;&#160;state_machine.project.list</FONT>' in board_fsm
    assert "nav: state_machine.project.list" not in board_fsm
    assert '<FONT POINT-SIZE="8" COLOR="#64748b">emitted message</FONT>' in composition
    assert "<B>source:</B>&#160;&#160;message.project_select" in composition
    assert "ready to ready" not in composition
    assert "<B>transition:</B>" not in composition
    assert "selected state:" not in composition
    composition_data_project = '<FONT POINT-SIZE="10"><B>payload:</B>&#160;&#160;project_id</FONT><FONT POINT-SIZE="8" COLOR="#94a3b8">&#160;&#160;ID</FONT>'
    composition_set_project = '<FONT POINT-SIZE="10"><B>set:</B>&#160;&#160;selected_project_id</FONT><FONT POINT-SIZE="8" COLOR="#94a3b8">&#160;&#160;ID</FONT><FONT POINT-SIZE="8">&#160;←&#160;project_id</FONT>'
    assert composition_data_project in composition
    assert composition_set_project in composition
    assert "selected_project_id &lt;- project_id" not in composition
    assert "set selected_project_id" not in composition
    assert "<B>flow:</B>" not in composition
    assert "state machine context" not in composition
    assert "state_machine.project.board" not in composition
    assert "dashboard state machine" not in composition
    assert "query.project.board.list" not in composition
    assert "<B>model:</B>" not in composition
    assert "<B>context</B>" not in composition
    assert "$message." not in composition
    assert "$event." not in composition
    assert "$state_machine." not in composition
    assert "<B>from:</B>" not in composition
    assert "<B>effects:</B>" not in composition
    assert "Layout / mounted state machines" not in composition
    assert "Message routing" not in composition
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
    assert '<FONT POINT-SIZE="8" COLOR="#64748b">html_route entry point</FONT>' in entrypoint
    assert "<B>route:</B>&#160;&#160;route.project.board" in entrypoint
    assert "<B>request</B>" in entrypoint
    assert "<B>path params</B>" in entrypoint
    assert '<FONT POINT-SIZE="10">workspace_id</FONT><FONT POINT-SIZE="8" COLOR="#94a3b8">&#160;&#160;ID</FONT>' in entrypoint
    assert '<FONT POINT-SIZE="8" COLOR="#64748b">target state machine (html)</FONT>' in entrypoint
    assert '<FONT POINT-SIZE="8" COLOR="#64748b">target state machine (textual)</FONT>' in cli_entrypoint
    assert '<FONT POINT-SIZE="8" COLOR="#64748b">target workflow</FONT>' in worker_entrypoint
    assert "<B>event payload</B>" in worker_entrypoint
    assert "<B>message disposition</B>" in worker_entrypoint
    assert '<FONT POINT-SIZE="10"><B>payload:</B>&#160;&#160;payload</FONT><FONT POINT-SIZE="8" COLOR="#94a3b8">&#160;&#160;data_contract.project.approved</FONT>' in worker_entrypoint
    for entrypoint_flow in (entrypoint, cli_entrypoint, cli_approve_entrypoint, api_entrypoint, worker_entrypoint):
        assert 'label="entry"' not in entrypoint_flow
        assert 'label="exit"' not in entrypoint_flow
        assert "entry_start" not in entrypoint_flow
        assert "entry_exit" not in entrypoint_flow
    assert "<B>html renderer handoff</B>" not in entrypoint
    assert 'label="ui loop"' not in entrypoint
    assert "<B>entry input</B>" not in entrypoint
    assert "<B>entry output</B>" not in entrypoint
    assert "entrypoint_mount" not in entrypoint
    assert "nav mount" not in entrypoint
    assert "<B>html renderer handoff</B>" not in cli_entrypoint
    assert "<B>command input</B>" in cli_entrypoint
    assert 'label="tui loop"' not in cli_entrypoint
    assert "<B>entry input</B>" not in cli_entrypoint
    assert "entrypoint_mount" not in cli_entrypoint
    assert "<B>transitions</B>" in cli_approve_entrypoint
    assert '<FONT POINT-SIZE="10">Project.status</FONT><FONT POINT-SIZE="8" COLOR="#94a3b8">&#160;&#160;enum&lt;draft|submitted|approved|archived&gt;</FONT><FONT POINT-SIZE="8">&#160;&#160;submitted → approved</FONT>' in cli_approve_entrypoint
    assert "<B>state:</B>" not in cli_approve_entrypoint
    assert "<B>change:</B>" not in cli_approve_entrypoint
    assert "<B>transition:</B>" not in cli_approve_entrypoint
    assert "<B>command input</B>" in cli_approve_entrypoint
    assert "success response" in cli_approve_entrypoint
    assert "failure response" in cli_approve_entrypoint
    assert "<B>entry input</B>" not in cli_approve_entrypoint
    assert "<B>entry output</B>" not in cli_approve_entrypoint
    assert "<B>request</B>" in api_entrypoint
    assert "success response" in api_entrypoint
    assert "failure response" in api_entrypoint
    assert "<B>entry input</B>" not in api_entrypoint
    assert "<B>entry output</B>" not in api_entrypoint
    assert "<B>entry input</B>" not in worker_entrypoint
    assert "<B>entry output</B>" not in worker_entrypoint
    assert "<B>body</B>" in api_entrypoint
    assert 'body</FONT><FONT POINT-SIZE="8" COLOR="#94a3b8">&#160;&#160;Project</FONT><FONT POINT-SIZE="8">&#160;←&#160;$outcome.result</FONT>' in api_entrypoint
    assert "validation_failed" in api_entrypoint
    target_card = api_entrypoint[api_entrypoint.index('"entrypoint_target_operation_project_create"') : api_entrypoint.index('"entrypoint_response_entry_point_api_project_create_created"')]
    assert '<FONT POINT-SIZE="10"><B>input</B></FONT>' in target_card
    assert '<FONT POINT-SIZE="10"><B>input:</B>&#160;&#160;customer</FONT>' not in target_card
    assert target_card.index("<B>input</B>") < target_card.index('<FONT POINT-SIZE="10">customer</FONT>')
    assert '<FONT POINT-SIZE="10">workspace_id</FONT><FONT POINT-SIZE="8" COLOR="#94a3b8">&#160;&#160;ID</FONT>' in target_card
    assert "<B>success</B>" in target_card
    assert "<B>failure</B>" in target_card
    assert "<B>emit:</B>&#160;&#160;created → event.project.created" in target_card
    assert '<FONT POINT-SIZE="10"><B>payload_schema:</B>&#160;&#160;payload_schema</FONT><FONT POINT-SIZE="8" COLOR="#94a3b8">&#160;&#160;Project</FONT>' in target_card
    assert "<B>emits:</B>&#160;&#160;event.project.created" not in target_card
    assert "<B>authorization_policy:</B>&#160;&#160;authorization_policy.project.create" in target_card
    assert "<B>authorization_effect:</B>&#160;&#160;allow" in target_card
    assert "<B>authorization_targets</B>" in target_card
    assert "<FONT POINT-SIZE=\"10\">operation: operation.project.create</FONT>" in target_card
    assert "<FONT POINT-SIZE=\"10\">model: Project</FONT>" in target_card
    assert "<B>authorization_conditions:</B>&#160;&#160;unconditional true" in target_card
    cli_approve_target_card = cli_approve_entrypoint[cli_approve_entrypoint.index('"entrypoint_target_entry_point_api_project_approve"') : cli_approve_entrypoint.index('"entrypoint_response_entry_point_cli_project_approve_approved"')]
    assert "<B>entry_point.api.project.approve</B>" in cli_approve_entrypoint
    assert "delegated entry point" in cli_approve_entrypoint
    assert "<B>emit:</B>&#160;&#160;approved → event.project.approved" in cli_approve_target_card
    assert '<FONT POINT-SIZE="10"><B>payload_schema:</B>&#160;&#160;payload_schema</FONT><FONT POINT-SIZE="8" COLOR="#94a3b8">&#160;&#160;data_contract.project.approved</FONT>' in cli_approve_target_card
    assert "<B>emits:</B>&#160;&#160;event.project.approved" not in cli_approve_target_card
    assert "<B>authorization_policy:</B>&#160;&#160;authorization_policy.project.approve" in cli_approve_entrypoint
    assert "actor ← input.approved_by" in cli_approve_target_card
    assert "<B>authorization_conditions:</B>&#160;&#160;Project.status = submitted" in cli_approve_target_card
    entrypoint_input = '<FONT POINT-SIZE="10"><B>input:</B>&#160;&#160;workspace_id</FONT><FONT POINT-SIZE="8" COLOR="#94a3b8">&#160;&#160;ID</FONT>'
    assert entrypoint_input in entrypoint
    assert entrypoint.index(entrypoint_input) < entrypoint.index("<B>query:</B>&#160;&#160;query.project.board.list")
    assert entrypoint.index("<B>query:</B>&#160;&#160;query.project.board.list") < entrypoint.index("<B>load:</B>&#160;&#160;operation.project.list")
    assert "<B>signal_sync_rules:</B>&#160;&#160;select_project_updates_state_machines" in entrypoint
    assert "<B>state_machine:</B>" not in entrypoint
    assert "state_machine.selected_project_id" not in entrypoint
    assert "$state_machine." not in entrypoint
    assert '<FONT POINT-SIZE="8" COLOR="#64748b">event trigger</FONT>' in workflow
    assert '<FONT POINT-SIZE="10"><B>payload_schema:</B>&#160;&#160;payload_schema</FONT><FONT POINT-SIZE="8" COLOR="#94a3b8">&#160;&#160;data_contract.project.approved</FONT>' in workflow
    assert '<FONT POINT-SIZE="8" COLOR="#64748b">workflow step</FONT>' in workflow
    assert "<B>operation:</B>&#160;&#160;operation.project.send_approval_notice" in workflow
    workflow_step = workflow[workflow.index('"workflow_step_workflow_project_approval_notice_send_notice"') :]
    assert '<FONT POINT-SIZE="10"><B>input</B></FONT>' in workflow_step
    assert '<FONT POINT-SIZE="10">approved_by</FONT><FONT POINT-SIZE="8" COLOR="#94a3b8">&#160;&#160;ID</FONT>' in workflow_step
    assert '<FONT POINT-SIZE="10">sent</FONT><FONT POINT-SIZE="8" COLOR="#94a3b8">&#160;&#160;data_contract.project.notice_result</FONT>' in workflow
    assert '<FONT POINT-SIZE="10">delivery_failed</FONT><FONT POINT-SIZE="8" COLOR="#94a3b8">&#160;&#160;Problem</FONT>' in workflow
    assert "<B>authorization_policy:</B>&#160;&#160;authorization_policy.project.send_approval_notice" in workflow
    assert "success workflow outcome" in workflow
    assert "failure workflow outcome" in workflow
    assert "sent: complete_as → completed" in workflow
    assert "delivery_failed: retry_policy → delivery_failed" in workflow
    for graph_id, dot_source in {"state_machine_project_list": state_machine, "project_board": composition, "html_project_board": entrypoint, "api_project_create": api_entrypoint, "cli_project_approve": cli_approve_entrypoint, "project_approval_notice": workflow}.items():
        svg = _render_graphviz_svg(dot_source, graph_id)
        assert svg.lstrip().startswith("<svg")
        assert "</svg>" in svg


def test_composition_dot_routes_messages_generically() -> None:
    state_machine = {
        "archetype": "workspace",
        "model": "generic.model",
        "context": {"selected_id": P("ID"), "workspace_id": P("ID")},
        "query_dependencies": [],
        "renderers": {
            "html": {
                "layout": {
                    "regions": {
                        "target": {"order": 10, "element": "aside", "role": "complementary"},
                        "source": {"order": 20, "element": "main", "role": "main", "must_render": True},
                        "unused": {"order": 30, "element": "footer", "role": "contentinfo"},
                    }
                }
            }
        },
        "child_state_machines": [
            {"id": "publisher", "html_region": "source", "state_machine": "state_machine.alpha", "initial_view_state": "idle", "context_bindings": {}},
            {"id": "receiver", "html_region": "target", "state_machine": "state_machine.beta", "initial_view_state": "waiting", "context_bindings": {"item_id": {"from": "$state_machine.selected_id"}}},
        ],
        "signal_sync_rules": [
            {
                "id": "route_alpha_beta",
                "when": {"instance": "publisher", "message": "ready"},
                "effects": [
                    {"send": {"instance": "receiver", "message": "consume", "payload_bindings": {"item_id": {"from": "$message.id"}}}},
                    {"set": {"context": "selected_id", "from": "$message.id"}},
                ],
            }
        ],
    }
    contract = {
        "state_machines": {
            "state_machine.alpha": {
                "signals": {
                    "accepts": {
                        "messages": {"submit": {"payload_schema": {"id": P("ID")}}},
                        "data_signals": {},
                    },
                    "emits": {
                        "messages": {"ready": {"payload_schema": {"id": P("ID")}}},
                    },
                },
                "transitions": [
                    {
                        "on": {"message": "submit"},
                        "from": "idle",
                        "to": "ready",
                        "effects": [{"emit": {"message": "ready", "payload_bindings": {"id": {"from": "$message.id"}}}}],
                    }
                ]
            },
            "state_machine.beta": {
                "signals": {
                    "accepts": {
                        "messages": {"consume": {"payload_schema": {"item_id": P("ID")}}},
                        "data_signals": {},
                    },
                    "emits": {"messages": {}},
                },
                "transitions": [
                    {
                        "on": {"message": "consume"},
                        "from": "waiting",
                        "to": "consumed",
                    }
                ]
            }
        }
    }

    composition = composition_dot("generic.state_machine", state_machine, contract)

    assert "emitted message" in composition
    assert "sent message" in composition
    assert "message route" in composition
    assert '<FONT POINT-SIZE="8" COLOR="#64748b">source mount</FONT>' in composition
    assert "<B>source:</B>&#160;&#160;message.submit" in composition
    assert "idle to ready" not in composition
    assert "<B>transition:</B>" not in composition
    assert "message.consume" in composition
    assert "<B>causes:</B>&#160;&#160;to consumed" in composition
    assert '<FONT POINT-SIZE="10"><B>payload:</B>&#160;&#160;id</FONT><FONT POINT-SIZE="8" COLOR="#94a3b8">&#160;&#160;ID</FONT>' in composition
    assert '<FONT POINT-SIZE="10"><B>set:</B>&#160;&#160;selected_id</FONT><FONT POINT-SIZE="8" COLOR="#94a3b8">&#160;&#160;ID</FONT><FONT POINT-SIZE="8">&#160;←&#160;id</FONT>' in composition
    assert 'item_id</FONT><FONT POINT-SIZE="8" COLOR="#94a3b8">&#160;&#160;ID</FONT><FONT POINT-SIZE="8">&#160;←&#160;id</FONT>' in composition
    assert "item_id &lt;- state_machine.selected_id" not in composition
    assert "context binding" not in composition
    assert "$message." not in composition
    assert "$event." not in composition
    assert "$state_machine." not in composition
    assert "<B>target:</B>" not in composition
    assert "<B>from:</B>" not in composition
    assert "<B>effects:</B>" not in composition
    assert '"message_effect_route_alpha_beta_0" -> "child_state_machine_receiver"' in composition
    assert "message_effect_route_alpha_beta_1" not in composition
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
    cleared = next(transition for transition in activity["transitions"] if transition["on"] == {"message": "selection_cleared"})
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
    api_entrypoint = (ROOT / entrypoint_flow_file("entry_point.api.project.create", "http_api")).read_text(encoding="utf-8")
    cli_approve_entrypoint = (ROOT / entrypoint_flow_file("entry_point.cli.project.approve", "cli")).read_text(encoding="utf-8")
    workflow = (ROOT / workflow_flow_file("workflow.project.approval_notice")).read_text(encoding="utf-8")
    assert "data_signal.ready" in list_fsm
    assert "on data_signal.ready" not in list_fsm
    assert "text.project.list.ready.heading" in list_fsm
    assert "asset.project.list.empty.illustration" in list_fsm
    assert "emit:" in list_fsm
    assert "message.project_selected" in list_fsm
    assert "payload:" in list_fsm
    assert "emit message.project_selected" not in list_fsm
    assert "effects:" not in list_fsm
    assert "operation: operation.project.list" not in list_fsm
    assert "query.project.list.list" in list_fsm
    assert "workspace_id: ID" not in list_fsm
    assert 'workspace_id</text>' in list_fsm
    assert 'fill="#94a3b8">\xa0\xa0ID</text>' in list_fsm
    assert "operation.project.list fields" in list_fsm
    assert "title: Text" not in list_fsm
    assert "status: enum" not in list_fsm
    assert 'fill="#94a3b8">\xa0\xa0Text</text>' in list_fsm
    assert 'fill="#94a3b8">\xa0\xa0enum&lt;draft|submitted|approved|archived&gt;</text>' in list_fsm
    assert "Project fields" not in list_fsm
    assert "projection:" not in list_fsm
    assert "model:" not in list_fsm
    assert "context:" not in list_fsm
    assert "&#45; data_signal.ready" not in list_fsm
    assert "&#45; text.project" not in list_fsm
    assert "&#45; none" not in list_fsm
    assert ">rationale<" not in list_fsm
    assert "loading &#45;&gt; empty" not in list_fsm
    assert "(initial)" not in list_fsm
    assert "initial:" not in list_fsm
    assert "state machine html renderer" not in list_fsm
    assert "declared, no arrow" not in list_fsm
    assert "transition events" not in list_fsm
    assert "emitted events" not in list_fsm
    assert "$message." not in list_fsm
    assert "$event." not in list_fsm
    assert "text.project.detail.ready.heading" in detail_fsm
    assert "operation.project.read fields" in detail_fsm
    assert "array&lt;Project&gt;" in list_fsm
    assert "operation.project.read" in detail_fsm
    assert 'fill="#94a3b8">\xa0\xa0Project</text>' in detail_fsm
    assert "summary: Text" not in detail_fsm
    assert 'fill="#94a3b8">\xa0\xa0Text</text>' in detail_fsm
    assert "operation.project.approve" in detail_fsm
    assert "operation.project.archive" in detail_fsm
    assert "operation.project.approve:" in detail_fsm
    assert "authorization_policy.project.approve" in detail_fsm
    assert "operation.project.read fields" in activity_fsm
    assert "updated_at: Timestamp" not in activity_fsm
    assert "assignee: Text" not in activity_fsm
    assert 'fill="#94a3b8">\xa0\xa0Timestamp</text>' in activity_fsm
    assert "input:" in detail_fsm
    assert "query.project.detail.read" in detail_fsm
    assert "project_id: ID" not in detail_fsm
    assert 'project_id</text>' in detail_fsm
    assert 'fill="#94a3b8">\xa0\xa0ID</text>' in detail_fsm
    assert "operation: operation.project.read" not in detail_fsm
    assert "set:" in detail_fsm
    assert "project_id &lt;&#45; null" not in detail_fsm
    assert 'fill="#94a3b8">\xa0\xa0ID</text>' in detail_fsm
    assert '\xa0←\xa0null</text>' in detail_fsm
    assert "select_project_updates_state_machines" not in detail_fsm
    assert "data_signal.ready" not in activity_fsm
    assert "input:" in activity_fsm
    assert "query.project.activity.read" in activity_fsm
    assert "project_id: ID" not in activity_fsm
    assert 'project_id</text>' in activity_fsm
    assert 'fill="#94a3b8">\xa0\xa0ID</text>' in activity_fsm
    assert "set:" in activity_fsm
    assert "project_id &lt;&#45; null" not in activity_fsm
    assert '\xa0←\xa0null</text>' in activity_fsm
    assert "emitted message" in composition
    assert "sent message" in composition
    assert "message.project_select" in composition
    assert "selection_changed" in composition
    assert "to loading" in composition
    assert "to ready" in composition
    assert "none to loading" not in composition
    assert "empty to ready" not in composition
    assert "selected state:" not in composition
    assert "set:" in composition
    assert "selected_project_id &lt;&#45; project_id" not in composition
    assert 'selected_project_id</text>' in composition
    assert 'fill="#94a3b8">\xa0\xa0ID</text>' in composition
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
    assert "$message." not in composition
    assert "$event." not in composition
    assert "$state_machine." not in composition
    assert "region:" not in composition
    assert "mount" in composition
    assert "state_machine:" in composition
    assert "instance:" not in composition
    assert "target:" not in composition
    assert "from:" not in composition
    assert "effects:" not in composition
    assert "Layout / mounted state machines" not in composition
    assert "Message routing" not in composition
    assert "Sync rules" not in composition
    assert "nav" in composition
    assert "main" in composition
    assert "aside" in composition
    assert "order:" not in composition
    assert "element:" not in composition
    assert "role:" not in composition
    assert "required:" not in composition
    assert "authorization_policy.project.create" in api_entrypoint
    assert "authorization_conditions" in api_entrypoint
    assert "authorization_policy.project.approve" in cli_approve_entrypoint
    assert "Project.status = submitted" in cli_approve_entrypoint
    assert "authorization_policy.project.send_approval_notice" in workflow


def test_audit_html_sources_render_copy_assets_and_fixture_fields() -> None:
    ready = ROOT / audit_case_render_file("state_machine.project.board", "state_machine.project.board.ready.ready_selected.audit", "render_profile.default", "wide", "html")
    text = ready.read_text(encoding="utf-8")
    assert "Dispatch queue" in text
    assert "Replace rooftop condenser fan · Atlas Foods" in text
    assert "Latest activity" in text
    assert "High priority" in text
    assert "Replace rooftop condenser fan" in text
    assert "Atlas Foods" in text
    assert "fixture.projects.audit_records" not in text
    assert "data-audit" not in text

    empty = ROOT / audit_case_render_file("state_machine.project.board", "state_machine.project.board.ready.empty.audit", "render_profile.default", "compact", "html")
    empty_text = empty.read_text(encoding="utf-8")
    assert "No dispatch projects yet" in empty_text
    assert "asset.project.list.empty.illustration" in empty_text
    assert "data:image/svg+xml;base64" in empty_text


def test_audit_asset_placeholder_is_generic_and_not_named() -> None:
    asset = ROOT / "spec/generated/audit_evidence/state_machines/state_machine_project_board/view_states/ready/cases/state_machine_project_board_ready_empty_audit/assets/asset_project_list_empty_illustration.svg"
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
    asset_id = next(iter(author["assets"]))
    del author["assets"][asset_id]["placeholder"]
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_source(author)


def test_render_audit_case_coverage_is_required() -> None:
    author = read_yaml(ROOT / SOURCE_SPEC_PATH)
    author["state_machines"]["state_machine.project.board"]["view_states"]["ready"].pop("render_audit_cases")
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
