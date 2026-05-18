from __future__ import annotations

import ast
import html
import importlib.util
import json
import py_compile
import re
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator

from .agent_prompts import USER_PROMPT_PLACEHOLDER, agent_prompt_paths
from .compile import ContractError, audit_cases
from .content import ContentContext, ContentError, asset as asset_registry, call_asset, call_text, text as text_registry, instantiate_args, load_resolvers, validate_resolver_function
from .runtime import fixture_namespace, resolve, resolve_binding
from .runtime_refs import ReferenceExpressionError, parse_reference_expression
from .io import read_json, read_yaml
from .layout import renderer_textual_presentation, renderer_textual_style
from .audit import (
    _case_file,
    _case_render_surfaces,
    _case_root,
    _case_scope_inputs,
    _audit_projection_surfaces,
    _fixtures_doc,
    _profile_viewports,
    _projection_render_surfaces,
    _surface_scope_inputs,
    _projection_surface_file,
    _projection_surface_root,
    _scope_asset_file,
    _scope_text_file,
    _text_doc,
    _scope_fixtures_file,
    audit_coverage_file,
    audit_coverage_index,
    audit_expected_files,
    composition_file,
    entrypoint_flow_file,
    application_action_flow_file,
    state_machine_graph_file,
    workflow_flow_file,
)
from .paths import GENERATED_SPEC_DIR, SPEC_ROOT, generated_relative as g
from .project import (
    _cwl_application_action_ids,
    components_projection,
    validated_projection_paths,
    composition_tcss_selector,
    constant_name,
    cwl_type,
    object_json_schema,
    authorization_policies_projection,
    state_machines_projection,
    humanize,
    safe_id,
    textual_screen_entries,
    type_schema,
)
from .targets import entry_state_machine_name, entry_point_adapter_pair, entry_point_input, entry_point_method, entry_point_path, entry_point_responses, entry_target_pair
from .json_schema import sample_value, schema_properties

_HTTP_METHODS = {"get", "put", "post", "delete", "patch", "head", "options", "trace"}
_OPENAPI_OPERATION_KEYS = {
    "operationId",
    "x-entry",
    "x-application-action",
    "x-authorization-policy",
    "parameters",
    "responses",
    "requestBody",
}
_CWL_SCALAR_TYPES = {"string", "boolean", "int", "long", "float", "double", "Any", "null"}
_PYTHON_PROJECTIONS = [
    g("test_adapters", "python_refs.py"),
    g("test_adapters", "driver_protocol.py"),
    g("test_adapters", "pytest_bdd_steps.py"),
    g("product_interfaces", "textual.projection.py"),
    g("content_resolvers", "signatures.py"),
    g("content_resolvers", "stubs.py"),
]


def validate_generated_projections(root: Path, contract: dict[str, Any]) -> None:
    """Strictly validate every compiler-owned projection that has a mechanical contract.

    These checks intentionally do not trust the generated artifacts just because they are fresh.
    They parse each native surface and cross-check it against the canonical contract graph.
    """
    generated = root / GENERATED_SPEC_DIR
    if not generated.exists():
        raise ContractError("Missing spec/generated directory")

    expected_paths = set(validated_projection_paths(contract))
    _validate_python_projections(root)
    validate_refs_py(root, contract)
    if g("product_interfaces", "http.openapi.yaml") in expected_paths:
        validate_openapi(contract, read_yaml(generated / "product_interfaces" / "http.openapi.yaml"))
    if g("product_interfaces", "integration_messages.asyncapi.yaml") in expected_paths:
        validate_asyncapi(contract, read_yaml(generated / "product_interfaces" / "integration_messages.asyncapi.yaml"))
    if g("product_interfaces", "html.routes.json") in expected_paths:
        validate_routes(contract, read_json(generated / "product_interfaces" / "html.routes.json"))
    if g("product_interfaces", "html.state_machines.json") in expected_paths:
        validate_state_machines_json(contract, read_json(generated / "product_interfaces" / "html.state_machines.json"))
    if g("product_interfaces", "textual.projection.py") in expected_paths:
        validate_textual_contract(root, contract)
    if g("content_resolvers", "signatures.py") in expected_paths:
        validate_content_contract(root, contract)
    if g("product_interfaces", "workflow.cwl.yaml") in expected_paths:
        validate_workflows(contract, read_yaml(generated / "product_interfaces" / "workflow.cwl.yaml"))
    if g("product_interfaces", "authorization_policies.json") in expected_paths:
        validate_authorization_policies_json(contract, read_json(generated / "product_interfaces" / "authorization_policies.json"))
    validate_agent_prompts(root)
    validate_fixtures_and_behavior_scenarios(root, contract)
    if (root / GENERATED_SPEC_DIR / "audit_evidence").exists() or any(path.startswith(g("audit_evidence") + "/") for path in audit_expected_files(contract)):
        validate_audit_outputs(root, contract)


def validate_openapi(contract: dict[str, Any], doc: dict[str, Any]) -> None:
    _require_exact_keys(doc, {"openapi", "info", "paths", "components"}, "OpenAPI document")
    if doc["openapi"] != "3.1.0":
        raise ContractError("OpenAPI projection must use openapi: 3.1.0")
    if doc["info"] != {"title": contract["project"], "version": "0.0.0-contract"}:
        raise ContractError("OpenAPI info block does not match the contract project")
    if not isinstance(doc["paths"], dict):
        raise ContractError("OpenAPI paths must be an object")
    _validate_json_schema_components(doc["components"], "OpenAPI")
    if doc["components"] != components_projection(contract):
        raise ContractError("OpenAPI components do not exactly match contract schemas")

    expected_application_actions: dict[tuple[str, str], tuple[str, dict[str, Any], dict[str, Any]]] = {}
    for entry_id, entry in sorted(contract["entry_points"].items()):
        if entry_point_adapter_pair(entry)[0] != "http_api":
            continue
        target_kind, cap_id = entry_target_pair(entry)
        if target_kind != "application_action":
            continue
        method = (entry_point_method(entry) or "").lower()
        key = (entry_point_path(entry), method)
        if key in expected_application_actions:
            raise ContractError(f"OpenAPI duplicate path/method binding in contract: {entry_point_path(entry)} {method}")
        expected_application_actions[key] = (entry_id, entry, contract["application_actions"][cap_id])

    actual_application_actions: dict[tuple[str, str], dict[str, Any]] = {}
    for path, methods in doc["paths"].items():
        if not isinstance(path, str) or not path.startswith("/"):
            raise ContractError(f"OpenAPI path must start with /: {path!r}")
        if not isinstance(methods, dict) or not methods:
            raise ContractError(f"OpenAPI path must declare at least one method: {path}")
        for method, operation in methods.items():
            if method not in _HTTP_METHODS:
                raise ContractError(f"OpenAPI unsupported HTTP method at {path}: {method}")
            if (path, method) in actual_application_actions:
                raise ContractError(f"OpenAPI duplicate operation: {method.upper()} {path}")
            actual_application_actions[(path, method)] = operation

    if set(actual_application_actions) != set(expected_application_actions):
        raise ContractError(_diff_message("OpenAPI operations", set(expected_application_actions), set(actual_application_actions)))

    seen_operation_ids: set[str] = set()
    for (path, method), (entry_id, entry, cap) in expected_application_actions.items():
        operation = actual_application_actions[(path, method)]
        unknown_keys = set(operation) - _OPENAPI_OPERATION_KEYS
        if unknown_keys:
            raise ContractError(f"OpenAPI {method.upper()} {path} has unsupported operation keys: {sorted(unknown_keys)}")
        _, cap_id = entry_target_pair(entry)
        if operation.get("operationId") in seen_operation_ids:
            raise ContractError(f"OpenAPI operationId is duplicated: {operation.get('operationId')}")
        seen_operation_ids.add(operation.get("operationId"))
        if operation.get("operationId") != cap_id:
            raise ContractError(f"OpenAPI operationId must equal operation id for {entry_id}")
        if operation.get("x-entry") != entry_id or operation.get("x-application-action") != cap_id:
            raise ContractError(f"OpenAPI extensions do not point back to {entry_id}/{cap_id}")
        expected_policy = (cap.get("authorization") or {}).get("policy")
        if expected_policy:
            if operation.get("x-authorization-policy") != expected_policy:
                raise ContractError(f"OpenAPI authorization policy extension does not match operation {cap_id}")
        elif "x-authorization-policy" in operation:
            raise ContractError(
                f"OpenAPI authorization policy extension is not allowed for operation without authentication {cap_id}"
            )

        placeholders = _path_params(path)
        path_params = entry_point_input(entry).get("path_params", {})
        query_params = entry_point_input(entry).get("query_params", {})
        if placeholders != set(path_params):
            raise ContractError(f"OpenAPI path params for {entry_id} do not match declared path_params")
        expected_params = [
            {"name": name, "in": "path", "required": True, "schema": type_schema(type_name)}
            for name, type_name in sorted(path_params.items())
        ] + [
            {"name": name, "in": "query", "required": True, "schema": type_schema(type_name)}
            for name, type_name in sorted(query_params.items())
        ]
        if operation.get("parameters", []) != expected_params:
            raise ContractError(f"OpenAPI parameters do not match entry path/query params for {entry_id}")

        body_fields = entry_point_input(entry).get("body", {})
        if body_fields and method not in {"get", "delete"}:
            expected_body = {
                "required": True,
                "content": {"application/json": {"schema": object_json_schema(body_fields)}},
            }
            if operation.get("requestBody") != expected_body:
                raise ContractError(f"OpenAPI requestBody does not match operation input for {cap_id}")
        elif "requestBody" in operation:
            raise ContractError(f"OpenAPI requestBody is not allowed for {entry_id}")

        expected_responses = {
            str(response["status"]): {
                "description": humanize(outcome_id),
                "content": {"application/json": {"schema": type_schema(response["body"]["type"])}},
            }
            for outcome_id, response in sorted(entry_point_responses(entry).items())
        }
        if operation.get("responses") != expected_responses:
            raise ContractError(f"OpenAPI response schema does not match entry responses for {entry_id}")
        _validate_refs_resolve(operation, doc, f"OpenAPI operation {entry_id}")

    _validate_refs_resolve(doc["components"], doc, "OpenAPI components")


def validate_agent_prompts(root: Path) -> None:
    for relative in agent_prompt_paths():
        path = root / relative
        if not path.exists():
            raise ContractError(f"Missing generated agent prompt: {relative}")
        text = path.read_text(encoding="utf-8")
        if text.count(USER_PROMPT_PLACEHOLDER) != 1:
            raise ContractError(f"Generated agent prompt must contain exactly one {USER_PROMPT_PLACEHOLDER} placeholder: {relative}")


def validate_asyncapi(contract: dict[str, Any], doc: dict[str, Any]) -> None:
    _require_exact_keys(doc, {"asyncapi", "info", "channels", "operations", "components"}, "AsyncAPI document")
    if doc["asyncapi"] != "3.1.0":
        raise ContractError("AsyncAPI projection must use asyncapi: 3.1.0")
    if doc["info"] != {"title": contract["project"], "version": "0.0.0-contract"}:
        raise ContractError("AsyncAPI info block does not match the contract project")
    channels = doc["channels"]
    operations = doc["operations"]
    components = doc["components"]
    _require_exact_keys(components, {"messages", "schemas"}, "AsyncAPI components")
    for schema_id, schema in components["schemas"].items():
        _check_json_schema(schema, f"AsyncAPI component schema {schema_id}")
    if components["schemas"] != components_projection(contract)["schemas"]:
        raise ContractError("AsyncAPI component schemas do not exactly match contract schemas")

    expected_channels = {f"domain_event_{safe_id(event_id)}" for event_id in contract["domain_events"]}
    if set(channels) != expected_channels:
        raise ContractError(_diff_message("AsyncAPI channels", expected_channels, set(channels)))
    expected_messages = {f"integration_message_{safe_id(event_id)}" for event_id in contract["domain_events"]}
    if set(components["messages"]) != expected_messages:
        raise ContractError(_diff_message("AsyncAPI messages", expected_messages, set(components["messages"])))

    expected_operations = {f"send_{safe_id(event_id)}" for event_id in contract["domain_events"]}
    for workflow_id, workflow in contract["workflows"].items():
        if "domain_event" in workflow["trigger"]:
            expected_operations.add(f"receive_{safe_id(workflow_id)}")
    if set(operations) != expected_operations:
        raise ContractError(_diff_message("AsyncAPI operations", expected_operations, set(operations)))

    seen_addresses: set[str] = set()
    for event_id, event in sorted(contract["domain_events"].items()):
        key = safe_id(event_id)
        channel_id = f"domain_event_{key}"
        message_id = f"integration_message_{key}"
        channel = channels[channel_id]
        if channel.get("address") != event_id:
            raise ContractError(f"AsyncAPI channel {channel_id} address must be {event_id}")
        if channel["address"] in seen_addresses:
            raise ContractError(f"AsyncAPI channel address is duplicated: {channel['address']}")
        seen_addresses.add(channel["address"])
        if channel.get("x-domain-event") != event_id:
            raise ContractError(f"AsyncAPI channel {channel_id} missing x-domain-event")
        if channel.get("messages") != {message_id: {"$ref": f"#/components/messages/{message_id}"}}:
            raise ContractError(f"AsyncAPI channel {channel_id} message binding is malformed")

        message = components["messages"][message_id]
        if message.get("name") != event_id:
            raise ContractError(f"AsyncAPI message {message_id} name does not match event")
        if message.get("payload") != type_schema(event["payload_schema"]):
            raise ContractError(f"AsyncAPI message {message_id} payload does not match event payload")
        if message.get("x-emitted-by") != sorted(event["emitted_by"]):
            raise ContractError(f"AsyncAPI message {message_id} emitted_by does not match contract")

        send = operations[f"send_{key}"]
        if send.get("action") != "send":
            raise ContractError(f"AsyncAPI send operation for {event_id} must have action=send")
        _expect_asyncapi_operation_channel(send, channel_id, message_id, f"send_{key}")
        if send.get("x-emitted-by") != sorted(event["emitted_by"]):
            raise ContractError(f"AsyncAPI send operation for {event_id} has wrong emitters")

    for workflow_id, workflow in sorted(contract["workflows"].items()):
        if "domain_event" not in workflow["trigger"]:
            continue
        event_id = workflow["trigger"]["domain_event"]
        op_id = f"receive_{safe_id(workflow_id)}"
        op = operations[op_id]
        if op.get("action") != "receive":
            raise ContractError(f"AsyncAPI receive operation {op_id} must have action=receive")
        _expect_asyncapi_operation_channel(op, f"domain_event_{safe_id(event_id)}", f"integration_message_{safe_id(event_id)}", op_id)
        if op.get("x-workflow") != workflow_id or op.get("x-contract-ref") != workflow["ref"]:
            raise ContractError(f"AsyncAPI receive operation {op_id} does not point to workflow")
        expected_dispositions = _workflow_entry_dispositions(contract, workflow_id)
        if expected_dispositions:
            if op.get("x-dispositions") != expected_dispositions:
                raise ContractError(f"AsyncAPI receive operation {op_id} does not preserve worker dispositions")
        elif "x-dispositions" in op:
            raise ContractError(f"AsyncAPI receive operation {op_id} has unexpected worker dispositions")

    _validate_refs_resolve(doc, doc, "AsyncAPI document")


def _workflow_entry_dispositions(contract: dict[str, Any], workflow_id: str) -> dict[str, Any]:
    dispositions: dict[str, Any] = {}
    for entry_id, entry in sorted(contract.get("entry_points", {}).items()):
        if entry_point_adapter_pair(entry)[0] not in {"worker", "scheduled"}:
            continue
        target_kind, target_ref = entry_target_pair(entry)
        if target_kind != "workflow" or target_ref != workflow_id:
            continue
        entry_dispositions = {}
        for response_id, response in sorted(entry_point_responses(entry).items()):
            projected = dict(response)
            if "problem" in projected:
                projected["problem"] = type_schema(projected["problem"])
            entry_dispositions[response_id] = projected
        dispositions[entry_id] = entry_dispositions
    return dispositions


def validate_routes(contract: dict[str, Any], doc: dict[str, Any]) -> None:
    _require_exact_keys(doc, {"project", "routes"}, "routes.json")
    if doc["project"] != contract["project"]:
        raise ContractError("routes.json project does not match contract")
    expected = []
    for entry_id, entry in sorted(contract["entry_points"].items()):
        if entry_point_adapter_pair(entry)[0] == "html_route":
            expected.append({
                "id": entry["route"],
                "entry": entry_id,
                "path": entry_point_path(entry),
                "path_params": entry_point_input(entry).get("path_params", {}),
                "query_params": entry_point_input(entry).get("query_params", {}),
                "state_machine": entry_state_machine_name(entry),
            })
    if doc["routes"] != expected:
        raise ContractError("routes.json does not exactly match UI entry points")
    for route in doc["routes"]:
        if _path_params(route["path"]) != set(route["path_params"]):
            raise ContractError(f"Route {route['id']} path params do not match declared path_params")


def validate_state_machines_json(contract: dict[str, Any], doc: dict[str, Any]) -> None:
    _require_exact_keys(doc, {"project", "state_machines", "compositions"}, "state_machines.json")
    if doc["project"] != contract["project"]:
        raise ContractError("state_machines.json project does not match contract")
    expected_doc = state_machines_projection(contract)
    if doc != expected_doc:
        raise ContractError("state_machines.json does not exactly match contract state machines/compositions")
    state_machine_ids = [state_machine["id"] for state_machine in doc["state_machines"]]
    if len(state_machine_ids) != len(set(state_machine_ids)):
        raise ContractError("state_machines.json contains duplicate state machine surface ids")
    expected_pairs = {("state_machine", state_machine_id, state_name) for state_machine_id, state_machine in contract["state_machines"].items() for state_name in state_machine.get("view_states", {})}
    actual_pairs = {(state_machine["owner_kind"], state_machine["owner"], state_machine["view_state"]) for state_machine in doc["state_machines"]}
    if actual_pairs != expected_pairs:
        raise ContractError(_diff_message("state machine owner/state pairs", expected_pairs, actual_pairs))
    expected_compositions = {f"{state_machine_id}.{state_name}" for state_machine_id, state_machine in contract["state_machines"].items() for state_name, state in state_machine.get("view_states", {}).items() if state.get("child_state_machines")}
    actual_compositions = {composition["id"] for composition in doc["compositions"]}
    if actual_compositions != expected_compositions:
        raise ContractError(_diff_message("Composed state machine state ids", expected_compositions, actual_compositions))


def validate_textual_contract(root: Path, contract: dict[str, Any]) -> None:
    label = "textual.projection.py"
    path = root / GENERATED_SPEC_DIR / "product_interfaces" / label
    module = _load_generated_module(path, "generated_textual_contract")
    state_machine_projection = state_machines_projection(contract)
    state_machines = state_machine_projection["state_machines"]
    compositions = state_machine_projection["compositions"]
    if module.PROJECT != contract["project"]:
        raise ContractError(f"{label} PROJECT does not match contract")
    if module.STATE_MACHINES != state_machines:
        raise ContractError(f"{label} STATE_MACHINES does not match state machine projection")
    if module.COMPOSITIONS != compositions:
        raise ContractError(f"{label} COMPOSITIONS does not match composition projection")

    expected_screens = textual_screen_entries(contract, state_machines, compositions)
    if module.SCREENS != expected_screens:
        raise ContractError(f"{label} SCREENS does not match textual state machines")

    for state_machine in state_machines:
        if module.state_machine_surface(state_machine["id"]) != state_machine:
            raise ContractError(f"{label} state machine surface lookup failed for {state_machine['id']}")
        expected_widgets = _expected_textual_compose(state_machine)
        if module.compose_contract_state_machine(state_machine["id"]) != expected_widgets:
            raise ContractError(f"{label} compose_contract_state_machine mismatch for {state_machine['id']}")

    for composition in compositions:
        if module.composition(composition["id"]) != composition:
            raise ContractError(f"{label} composition lookup failed for {composition['id']}")
        expected = [((mount.get("textual_container") or mount.get("html_region")), mount["id"], mount["state_machine"]) for mount in composition["child_state_machines"]]
        if module.compose_contract_composition(composition["id"]) != expected:
            raise ContractError(f"{label} compose_contract_composition mismatch for {composition['id']}")

    try:
        module.state_machine_surface("state_machine.missing")
    except KeyError:
        pass
    else:  # pragma: no cover
        raise ContractError(f"{label} state_machine_surface() must raise KeyError for unknown state machine surfaces")

    tcss_rules = _parse_style_rules(module.textual_tcss(), f"{label} Textual style", textual=True)
    expected_selectors = {"Screen", ".contract-state-machine-surface"}
    for state_machine in state_machines:
        textual = renderer_textual_presentation(state_machine)
        widget_ids = [widget["id"] for widget in textual.get("widgets", [])]
        if len(widget_ids) != len(set(widget_ids)):
            raise ContractError(f"Textual widgets for {state_machine['id']} contain duplicate ids")
        for rule in renderer_textual_style(state_machine).get("rules", []):
            expected_selectors.add(_textual_selector(state_machine, rule["selector"]))
    for composition in compositions:
        for rule in renderer_textual_style(composition).get("rules", []):
            expected_selectors.add(composition_tcss_selector(composition, rule["selector"]))
    actual_selectors = {selector for selector, _ in tcss_rules}
    if actual_selectors != expected_selectors:
        raise ContractError(_diff_message("Textual style selectors", expected_selectors, actual_selectors))


def validate_content_contract(root: Path, contract: dict[str, Any]) -> None:
    generated = root / GENERATED_SPEC_DIR
    content_doc = read_yaml(generated / "content_resolvers" / "cases.yaml")
    if content_doc != {"project": contract["project"], "content_cases": contract.get("content_cases", {})}:
        raise ContractError("content_resolvers/cases.yaml does not exactly match contract content cases")
    try:
        load_resolvers(root)
    except ContentError as exc:
        if _final_content_refs(contract):
            raise ContractError(str(exc)) from exc
        return
    declared_text = set(contract.get("text_resources", {}))
    declared_assets = set(contract.get("assets", {}))
    unknown_text = text_registry.refs - declared_text
    unknown_assets = asset_registry.refs - declared_assets
    if unknown_text:
        raise ContractError("Unknown text sources: " + ", ".join(sorted(unknown_text)))
    if unknown_assets:
        raise ContractError("Unknown asset sources: " + ", ".join(sorted(unknown_assets)))

    import importlib, sys
    sys.path.insert(0, str(root / SPEC_ROOT))
    try:
        sys.modules.pop("generated.content_resolvers.signatures", None)
        module = importlib.import_module("generated.content_resolvers.signatures")
    finally:
        try:
            sys.path.remove(str(root / SPEC_ROOT))
        except ValueError:
            pass
    for ref, item in contract.get("text_resources", {}).items():
        source_ref = item.get("source_ref")
        arg_cls = module.TEXT_ARG_CLASSES[ref]
        instantiate_args(root, "text", ref, {name: _sample_value_for_type(type_name) for name, type_name in item.get("args", {}).items()})
        if source_ref:
            if ref not in text_registry.refs:
                raise ContractError(f"Missing final text source: {ref}")
            try:
                validate_resolver_function(text_registry.function(ref), arg_cls)
            except ContentError as exc:
                raise ContractError(str(exc)) from exc
    for ref, item in contract.get("assets", {}).items():
        source_ref = item.get("source_ref")
        arg_cls = module.ASSET_ARG_CLASSES[ref]
        instantiate_args(root, "asset", ref, {name: _sample_value_for_type(type_name) for name, type_name in item.get("args", {}).items()})
        if source_ref:
            if ref not in asset_registry.refs:
                raise ContractError(f"Missing final asset source: {ref}")
            try:
                validate_resolver_function(asset_registry.function(ref), arg_cls)
            except ContentError as exc:
                raise ContractError(str(exc)) from exc

    exercised: set[str] = set()
    for case_id, case in contract.get("content_cases", {}).items():
        namespace = fixture_namespace(contract, case.get("seed_fixtures", []))
        args = {key: resolve_binding(value, {"fixture": namespace}) for key, value in case.get("args", {}).items()}
        ref = case["ref"]
        if ref.startswith("text."):
            item = contract["text_resources"][ref]
            if not item.get("source_ref"):
                result = item["placeholder"]
            else:
                try:
                    result = call_text(root, ref, args, ContentContext(surface="content_case"))
                except ContentError as exc:
                    raise ContractError(str(exc)) from exc
            if not isinstance(result, str) or not result.strip():
                raise ContractError(f"Content case {case_id} text result must be non-empty")
            if item.get("max_chars") is not None and len(result) > item["max_chars"]:
                raise ContractError(f"Content case {case_id} text result exceeds max_chars")
        else:
            item = contract["assets"][ref]
            if item.get("source_ref"):
                try:
                    result = call_asset(root, ref, args, ContentContext(surface="content_case"))
                except ContentError as exc:
                    raise ContractError(str(exc)) from exc
                if result.mime_type != "image/svg+xml" or not result.body.lstrip().startswith("<svg") or "</svg>" not in result.body:
                    raise ContractError(f"Content case {case_id} asset result must be SVG")
        exercised.add(ref)
    missing = _final_content_refs(contract) - exercised
    if missing:
        raise ContractError("Final content is not exercised by content cases: " + ", ".join(sorted(missing)))


def _final_content_refs(contract: dict[str, Any]) -> set[str]:
    refs: set[str] = set()
    for section in ["text_resources", "assets"]:
        for ref, item in contract.get(section, {}).items():
            if item.get("source_ref"):
                refs.add(ref)
    return refs


def _sample_value_for_type(type_name: Any) -> Any:
    return sample_value(type_name)

def validate_workflows(contract: dict[str, Any], doc: dict[str, Any]) -> None:
    _require_exact_keys(doc, {"cwlVersion", "$graph"}, "workflows.cwl.yaml")
    if doc["cwlVersion"] != "v1.2":
        raise ContractError("CWL projection must use cwlVersion: v1.2")
    graph = doc["$graph"]
    if not isinstance(graph, list):
        raise ContractError("CWL $graph must be a list")
    by_id = {item.get("id"): item for item in graph}
    if len(by_id) != len(graph):
        raise ContractError("CWL $graph contains duplicate or missing ids")
    expected_ids = {f"#{safe_id(workflow_id)}" for workflow_id in contract["workflows"]}
    expected_ids.update(f"#{safe_id(cap_id)}" for cap_id in _cwl_application_action_ids(contract))
    if set(by_id) != expected_ids:
        raise ContractError(_diff_message("CWL graph ids", expected_ids, set(by_id)))

    for workflow_id, workflow in sorted(contract["workflows"].items()):
        item = by_id[f"#{safe_id(workflow_id)}"]
        if set(item) != {"id", "class", "label", "doc", "inputs", "outputs", "steps"}:
            raise ContractError(f"CWL workflow {workflow_id} has unsupported keys")
        if item.get("class") != "Workflow" or item.get("label") != workflow_id:
            raise ContractError(f"CWL workflow {workflow_id} has wrong class/label")
        if f"trigger={workflow['trigger']}" not in item.get("doc", "") or f"ref={workflow['ref']}" not in item.get("doc", ""):
            raise ContractError(f"CWL workflow {workflow_id} doc does not preserve trigger/ref")
        expected_inputs = {"trigger_payload": {"type": cwl_type(_workflow_trigger_payload_type(contract, workflow))}}
        expected_outputs = {
            outcome_id: {"type": cwl_type(outcome["result"])}
            for outcome_id, outcome in sorted(workflow["outcomes"].items())
        }
        if item.get("inputs") != expected_inputs or item.get("outputs") != expected_outputs:
            raise ContractError(f"CWL workflow {workflow_id} inputs/outputs malformed")
        steps = item.get("steps")
        if set(steps) != {step["id"] for step in workflow["steps"]}:
            raise ContractError(f"CWL workflow {workflow_id} steps mismatch")
        for step in workflow["steps"]:
            actual = steps[step["id"]]
            run_id = f"#{safe_id(step['application_action'])}"
            if actual.get("run") != run_id or run_id not in by_id:
                raise ContractError(f"CWL workflow {workflow_id} step {step['id']} references unknown run")
            cap = contract["application_actions"][step["application_action"]]
            expected_in = {name: _workflow_cwl_source(source) for name, source in sorted(step["input_bindings"].items())}
            expected_out = sorted(cap["outcomes"])
            expected_doc = f"input_bindings={step['input_bindings']}; outcome_transitions={step['outcome_transitions']}"
            if set(actual) != {"doc", "run", "in", "out"} or actual.get("doc") != expected_doc or actual.get("in") != expected_in or actual.get("out") != expected_out:
                raise ContractError(f"CWL workflow {workflow_id} step {step['id']} malformed")

    for cap_id in _cwl_application_action_ids(contract):
        cap = contract["application_actions"][cap_id]
        item = by_id[f"#{safe_id(cap_id)}"]
        if set(item) != {"id", "class", "label", "baseCommand", "inputs", "outputs"}:
            raise ContractError(f"CWL operation node {cap_id} has unsupported keys")
        if item.get("class") != "CommandLineTool" or item.get("label") != cap_id:
            raise ContractError(f"CWL operation node {cap_id} must be a labelled CommandLineTool")
        if item.get("baseCommand") != ["contract-operation", cap_id]:
            raise ContractError(f"CWL operation node {cap_id} baseCommand mismatch")
        expected_inputs = {name: {"type": cwl_type(type_name)} for name, type_name in sorted(schema_properties(cap["input"]).items())}
        if item.get("inputs") != expected_inputs:
            raise ContractError(f"CWL operation node {cap_id} inputs mismatch")
        expected_outputs = {
            outcome_id: {"type": cwl_type(outcome["result"])}
            for outcome_id, outcome in sorted(cap["outcomes"].items())
        }
        if item.get("outputs") != expected_outputs:
            raise ContractError(f"CWL operation node {cap_id} outputs mismatch")
        for parameter in list(item["inputs"].values()) + list(item["outputs"].values()):
            if set(parameter) != {"type"}:
                raise ContractError(f"CWL operation {cap_id} parameter has unsupported keys")
            _validate_cwl_type(parameter["type"], f"CWL operation {cap_id}")


def _workflow_trigger_payload_type(contract: dict[str, Any], workflow: dict[str, Any]) -> str:
    trigger = workflow["trigger"]
    if "domain_event" in trigger:
        return contract["domain_events"][trigger["domain_event"]]["payload_schema"]
    operation = contract["application_actions"][trigger["application_action"]]
    successes = [outcome["result"] for outcome in operation["outcomes"].values() if outcome["kind"] == "success"]
    return successes[0]


def _workflow_cwl_source(source: Any) -> str:
    if isinstance(source, dict):
        if "from" in source:
            source = source["from"]
        elif "value" in source:
            return repr(source["value"])
    try:
        ref = parse_reference_expression(source)
    except ReferenceExpressionError:
        return source
    if ref.root == "trigger" and ref.path[:1] == ("payload",):
        return "trigger_payload"
    if ref.root == "steps" and len(ref.path) >= 4 and ref.path[1] == "outcomes" and ref.path[3] == "result":
        return f"{ref.path[0]}/{ref.path[2]}"
    return source


def validate_fixtures_and_behavior_scenarios(root: Path, contract: dict[str, Any]) -> None:
    generated = root / GENERATED_SPEC_DIR
    behavior = generated / "behavior"
    fixtures = read_yaml(behavior / "fixtures.yaml")
    behavior_scenarios = read_yaml(behavior / "behavior_scenarios.yaml")
    if fixtures != {"project": contract["project"], "fixtures": contract["fixtures"]}:
        raise ContractError("fixtures.yaml does not match contract fixtures")
    if behavior_scenarios != {"project": contract["project"], "behavior_scenarios": contract["behavior_scenarios"]}:
        raise ContractError("behavior_scenarios.yaml does not match spec behavior scenarios")

    expected_ids = set(contract["behavior_scenarios"])
    feature_root = generated / "test_adapters" / "pytest_bdd_features"
    actual_ids = _feature_behavior_scenario_ids(feature_root)
    if actual_ids != expected_ids:
        raise ContractError(_diff_message("generated feature behavior scenarios", expected_ids, actual_ids))

    forbidden_harness_dirs = [feature_root / "spec", feature_root / "prod"]
    for path in forbidden_harness_dirs:
        if path.exists():
            raise ContractError(f"Generated features must be single-source; remove {path.relative_to(root)}")


def validate_authorization_policies_json(contract: dict[str, Any], doc: dict[str, Any]) -> None:
    if doc != authorization_policies_projection(contract):
        raise ContractError("authorization_policies.json does not match contract authorization policies")
    for application_action_id, authorization in doc["action_authorizations"].items():
        if application_action_id not in contract["application_actions"]:
            raise ContractError(f"authorization_policies.json has unknown operation authorization {application_action_id}")
        authorization_policy = authorization["policy"]
        if authorization_policy not in doc["authorization_policies"]:
            raise ContractError(f"authorization_policies.json operation authorization references unknown authorization policy {authorization_policy}")
    for entry_id, authorization_policy in doc["entry_point_authorization_policies"].items():
        if entry_id not in contract["entry_points"]:
            raise ContractError(f"authorization_policies.json has unknown entry point authorization policy {entry_id}")
        if authorization_policy not in doc["authorization_policies"]:
            raise ContractError(f"authorization_policies.json entry point authorization policy references unknown authorization policy {authorization_policy}")



def validate_audit_outputs(root: Path, contract: dict[str, Any]) -> None:
    audit_root = root / GENERATED_SPEC_DIR / "audit_evidence"
    if not audit_root.exists():
        raise ContractError("Missing spec/generated/audit_evidence directory")
    expected = audit_expected_files(contract)
    actual = {
        str(path.relative_to(root))
        for path in audit_root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }
    if actual != expected:
        raise ContractError(_diff_message("audit generated files", expected, actual))

    _validate_audit_coverage_index(root, contract)

    for state_machine_id in contract.get("state_machines", {}):
        _assert_svg(root / state_machine_graph_file(state_machine_id), f"state machine {state_machine_id}")
    for state_machine_id, state_machine in contract.get("state_machines", {}).items():
        for state_name, state in state_machine.get("view_states", {}).items():
            if state.get("child_state_machines"):
                _assert_svg(root / composition_file(state_machine_id, state_name), f"composition {state_machine_id}.{state_name}")
    for entry_id, entry in contract.get("entry_points", {}).items():
        adapter_kind, _ = entry_point_adapter_pair(entry)
        _assert_svg(root / entrypoint_flow_file(entry_id, adapter_kind), f"entrypoint {entry_id}")
    for workflow_id in contract.get("workflows", {}):
        _assert_svg(root / workflow_flow_file(workflow_id), f"workflow {workflow_id}")
    for application_action_id in contract.get("application_actions", {}):
        _assert_svg(root / application_action_flow_file(application_action_id), f"operation {application_action_id}")

    projection = state_machines_projection(contract)
    for state_machine in _audit_projection_surfaces(contract, projection):
        render_surfaces = _projection_render_surfaces(state_machine)
        if not render_surfaces:
            continue
        _validate_audit_scope_inputs(root, contract, _projection_surface_root(state_machine), *_surface_scope_inputs(contract, state_machine))
        if "html" in render_surfaces:
            for profile_id, breakpoint, viewport in _profile_viewports(contract, "html"):
                html_path = root / _projection_surface_file(state_machine, profile_id, breakpoint, "html")
                png_path = root / _projection_surface_file(state_machine, profile_id, breakpoint, "png")
                _assert_html_source(html_path, f"HTML state_machine audit {state_machine['id']}/{breakpoint}")
                _assert_png(png_path, f"HTML state_machine audit {state_machine['id']}/{breakpoint}", viewport)
        if "textual" in render_surfaces:
            for profile_id, breakpoint, _ in _profile_viewports(contract, "textual"):
                py_path = root / _projection_surface_file(state_machine, profile_id, breakpoint, "py")
                svg_path = root / _projection_surface_file(state_machine, profile_id, breakpoint, "svg")
                _assert_textual_source(py_path, f"Textual state_machine audit {state_machine['id']}/{breakpoint}")
                _assert_svg(svg_path, f"Textual state_machine audit {state_machine['id']}/{breakpoint}")
                if "rich-terminal" not in svg_path.read_text(encoding="utf-8"):
                    raise ContractError(f"Textual audit SVG does not look like a Textual capture: {state_machine['id']}/{breakpoint}")

    for case_id, case in audit_cases(contract).items():
        _validate_audit_scope_inputs(root, contract, _case_root(contract, case_id, case), *_case_scope_inputs(contract, case))
        render_surfaces = _case_render_surfaces(contract, case)
        if "html" in render_surfaces:
            for profile_id, breakpoint, viewport in _profile_viewports(contract, "html"):
                html_path = root / _case_file(contract, case_id, case, profile_id, breakpoint, "html")
                png_path = root / _case_file(contract, case_id, case, profile_id, breakpoint, "png")
                _assert_html_source(html_path, f"HTML state_machine audit {case_id}/{breakpoint}")
                _assert_png(png_path, f"HTML state_machine audit {case_id}/{breakpoint}", viewport)
        if "textual" in render_surfaces:
            for profile_id, breakpoint, _ in _profile_viewports(contract, "textual"):
                py_path = root / _case_file(contract, case_id, case, profile_id, breakpoint, "py")
                svg_path = root / _case_file(contract, case_id, case, profile_id, breakpoint, "svg")
                _assert_textual_source(py_path, f"Textual state_machine audit {case_id}/{breakpoint}")
                _assert_svg(svg_path, f"Textual state_machine audit {case_id}/{breakpoint}")
                if "rich-terminal" not in svg_path.read_text(encoding="utf-8"):
                    raise ContractError(f"Textual audit SVG does not look like a Textual capture: {case_id}/{breakpoint}")


def _validate_audit_coverage_index(root: Path, contract: dict[str, Any]) -> None:
    expected = audit_coverage_index(contract)
    actual = read_yaml(root / audit_coverage_file())
    if actual != expected:
        raise ContractError("audit coverage index does not match compiled contract")
    visual_evidence_sets = expected["visual_evidence_sets"]
    missing_required = expected["visual_audit"]["required"]["missing"]
    if missing_required:
        sample = ", ".join(list(missing_required)[:10])
        raise ContractError(f"audit coverage index has missing required visual audit paths: {sample}")
    for section in (expected["visual_audit"]["required"]["covered"], expected["visual_audit"]["optional"]["covered"]):
        for spec_path, evidence_set in section.items():
            if evidence_set not in visual_evidence_sets:
                raise ContractError(f"audit coverage index references unknown evidence set for {spec_path}: {evidence_set}")
            files = visual_evidence_sets[evidence_set]
            for relative in files:
                if not (root / relative).exists():
                    raise ContractError(f"audit coverage index references missing evidence for {spec_path}: {relative}")
    for spec_path, evidence_ref in expected["visual_audit"]["non_visual"].items():
        evidence_set = evidence_ref.get("visual_evidence_set")
        if evidence_set is None:
            continue
        if evidence_set not in visual_evidence_sets:
            raise ContractError(f"audit coverage index references unknown evidence set for {spec_path}: {evidence_set}")
        files = visual_evidence_sets[evidence_set]
        for relative in files:
            if not (root / relative).exists():
                raise ContractError(f"audit coverage index references missing evidence for {spec_path}: {relative}")
    for collection in expected["render_presence"].values():
        for resource_id, evidence_set in collection["rendered"].items():
            if evidence_set not in visual_evidence_sets:
                raise ContractError(f"audit render coverage references unknown evidence set for {resource_id}: {evidence_set}")
    _validate_visual_text_witnesses(root, expected)


def _validate_visual_text_witnesses(root: Path, coverage_index: dict[str, Any]) -> None:
    visual_evidence_sets = coverage_index["visual_evidence_sets"]
    svg_text_cache: dict[str, str] = {}
    for spec_path, witness in coverage_index["visual_audit"]["required"].get("text_witnesses", {}).items():
        evidence_set = witness["visual_evidence_set"]
        if evidence_set not in visual_evidence_sets:
            raise ContractError(f"audit visual text witness references unknown evidence set for {spec_path}: {evidence_set}")
        evidence_files = visual_evidence_sets[evidence_set]
        svg_files = [relative for relative in evidence_files if relative.endswith(".svg")]
        if not svg_files:
            raise ContractError(f"audit visual text witness has no SVG evidence for {spec_path}: {evidence_set}")
        evidence_text = "\n".join(_audit_svg_visible_text(root / relative, svg_text_cache) for relative in svg_files)
        for token in witness["tokens"]:
            if token not in evidence_text:
                raise ContractError(f"audit visual text witness missing for {spec_path}: {token!r} in {evidence_set}")


def _audit_svg_visible_text(path: Path, cache: dict[str, str]) -> str:
    key = str(path)
    if key in cache:
        return cache[key]
    source = path.read_text(encoding="utf-8")
    fragments: list[str] = []
    for match in re.finditer(r"<text\b[^>]*>(.*?)</text>", source, flags=re.IGNORECASE | re.DOTALL):
        fragment = re.sub(r"<[^>]+>", "", match.group(1))
        fragments.append(html.unescape(fragment).replace("\xa0", " "))
    text = "\n".join(fragments)
    cache[key] = text
    return text


def _validate_audit_scope_inputs(
    root: Path,
    contract: dict[str, Any],
    scope_root: str,
    copy_refs: set[str],
    asset_refs: set[str],
    fixture_ids: set[str],
    fact_ids: set[str],
    context: dict[str, Any],
) -> None:
    text_doc = read_yaml(root / _scope_text_file(scope_root))
    if text_doc != _text_doc(contract, copy_refs):
        raise ContractError(f"audit text.yaml does not match scoped text resources: {scope_root}")
    fixtures_doc = read_yaml(root / _scope_fixtures_file(scope_root))
    if fixtures_doc != _fixtures_doc(contract, fixture_ids, fact_ids, context):
        raise ContractError(f"audit fixtures.yaml does not match scoped fixtures: {scope_root}")
    for asset_id in asset_refs:
        path = root / _scope_asset_file(scope_root, asset_id)
        text = path.read_text(encoding="utf-8")
        if not text.lstrip().startswith("<svg") or "</svg>" not in text:
            raise ContractError(f"audit asset placeholder is not SVG: {asset_id}")
        if asset_id in text:
            raise ContractError(f"audit asset placeholder must not render or embed the asset id: {asset_id}")
        if contract["assets"][asset_id]["placeholder"]["label"] not in text:
            raise ContractError(f"audit asset placeholder must preserve the accessible label: {asset_id}")


def _assert_html_source(path: Path, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("<!doctype html>\n"):
        raise ContractError(f"{label} source is not exact generated HTML")
    forbidden = ["data-audit-label", "data-audit-fixtures", "audit-fixtures", "Audit case:", "state machine:"]
    present = [item for item in forbidden if item in text]
    if present:
        raise ContractError(f"{label} source contains audit metadata labels: {present}")


def _assert_textual_source(path: Path, label: str) -> None:
    source = path.read_text(encoding="utf-8")
    if "class AuditApp" not in source or "LINES = " not in source:
        raise ContractError(f"{label} source is not exact generated Textual code")
    forbidden = ["Audit case:", "state machine:", "data-audit"]
    present = [item for item in forbidden if item in source]
    if present:
        raise ContractError(f"{label} source contains audit metadata labels: {present}")
    try:
        ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        raise ContractError(f"{label} source is not valid Python: {exc}") from exc

def _assert_svg(path: Path, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    if not text.lstrip().startswith("<svg") or "</svg>" not in text:
        raise ContractError(f"{label} audit artifact is not SVG")


def _assert_png(path: Path, label: str, viewport: dict[str, int]) -> None:
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ContractError(f"{label} audit artifact is not PNG")
    try:
        from PIL import Image
        with Image.open(path) as image:
            if image.size != (viewport["width"], viewport["height"]):
                raise ContractError(f"{label} PNG dimensions {image.size} do not match viewport {(viewport['width'], viewport['height'])}")
    except ContractError:
        raise
    except Exception as exc:
        raise ContractError(f"{label} PNG could not be decoded: {exc}") from exc

def _validate_python_projections(root: Path) -> None:
    for relative in _PYTHON_PROJECTIONS:
        path = root / relative
        if not path.exists():
            continue
        source = path.read_text(encoding="utf-8")
        try:
            ast.parse(source, filename=str(path))
            py_compile.compile(str(path), doraise=True)
        except Exception as exc:  # pragma: no cover - exact exception type varies across Python versions.
            raise ContractError(f"Generated Python projection is not importable: {relative}: {exc}") from exc


def validate_refs_py(root: Path, contract: dict[str, Any]) -> None:
    module = _load_generated_module(root / GENERATED_SPEC_DIR / "test_adapters" / "python_refs.py", "generated_refs")
    expected_groups: dict[str, list[str]] = {
        "Asset": sorted(contract.get("assets", {})),
        "RenderProfile": sorted(contract.get("render_profiles", {})),
        "ContentCase": sorted(contract.get("content_cases", {})),
        "EntryPoint": sorted(contract["entry_points"]),
        "DomainEvent": sorted(contract["domain_events"]),
        "Fact": sorted(contract.get("facts", {})),
        "Fixture": sorted(contract["fixtures"]),
        "Operation": sorted(contract["application_actions"]),
        "StateMachine": sorted(contract.get("state_machines", {})),
        "Text": sorted(contract.get("text_resources", {})),
        "RenderAuditCase": sorted(audit_cases(contract)),
        "BehaviorScenario": sorted(contract["behavior_scenarios"]),
    }
    for kind, values in sorted(contract["refs"].items()):
        expected_groups[kind.title().replace("_", "")] = values
    for class_name, values in expected_groups.items():
        cls = getattr(module, class_name, None)
        if cls is None:
            raise ContractError(f"python_refs.py missing class {class_name}")
        actual = {name: value for name, value in vars(cls).items() if name.isupper()}
        expected = {constant_name(value): value for value in values}
        if actual != expected:
            raise ContractError(f"python_refs.py constants for {class_name} do not match contract refs")


def _validate_json_schema_components(components: dict[str, Any], label: str) -> None:
    _require_exact_keys(components, {"schemas"}, f"{label} components")
    expected = components_projection_schema_shape(components)
    for schema_id, schema in components["schemas"].items():
        _check_json_schema(schema, f"{label} component schema {schema_id}")
    _validate_refs_resolve(components, {"components": components}, f"{label} components")
    # Force deterministic JSON encoding; catches non-serializable schema values.
    json.dumps(expected, sort_keys=True)


def components_projection_schema_shape(components: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(components.get("schemas"), dict):
        raise ContractError("components.schemas must be an object")
    return components


def _check_json_schema(schema: dict[str, Any], label: str) -> None:
    try:
        Draft202012Validator.check_schema(schema)
    except Exception as exc:
        raise ContractError(f"{label} is not a valid JSON Schema: {exc}") from exc


def _validate_refs_resolve(node: Any, root: dict[str, Any], label: str) -> None:
    for ref in _find_refs(node):
        if not ref.startswith("#/"):
            raise ContractError(f"{label} contains non-local $ref: {ref}")
        target: Any = root
        for raw_part in ref[2:].split("/"):
            part = raw_part.replace("~1", "/").replace("~0", "~")
            if not isinstance(target, dict) or part not in target:
                raise ContractError(f"{label} contains unresolved $ref: {ref}")
            target = target[part]


def _find_refs(node: Any) -> Iterable[str]:
    if isinstance(node, dict):
        if "$ref" in node:
            yield node["$ref"]
        for value in node.values():
            yield from _find_refs(value)
    elif isinstance(node, list):
        for value in node:
            yield from _find_refs(value)


def _expect_asyncapi_operation_channel(op: dict[str, Any], channel_id: str, message_id: str, op_id: str) -> None:
    if op.get("channel") != {"$ref": f"#/channels/{channel_id}"}:
        raise ContractError(f"AsyncAPI operation {op_id} references wrong channel")
    if op.get("messages") != [{"$ref": f"#/components/messages/{message_id}"}]:
        raise ContractError(f"AsyncAPI operation {op_id} references wrong message")


def _parse_style_rules(text: str, label: str, textual: bool = False) -> list[tuple[str, dict[str, str]]]:
    without_comments = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    rules: list[tuple[str, dict[str, str]]] = []
    pos = 0
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", without_comments, flags=re.S):
        between = without_comments[pos:match.start()].strip()
        if between:
            raise ContractError(f"{label} contains text outside rule blocks: {between[:40]!r}")
        selector = " ".join(match.group(1).strip().split())
        if not selector:
            raise ContractError(f"{label} contains an empty selector")
        declarations: dict[str, str] = {}
        body = match.group(2).strip()
        for raw_line in body.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if not line.endswith(";"):
                raise ContractError(f"{label} declaration must end with semicolon: {line!r}")
            name_value = line[:-1].split(":", 1)
            if len(name_value) != 2:
                raise ContractError(f"{label} declaration is malformed: {line!r}")
            name, value = name_value[0].strip(), name_value[1].strip()
            _validate_style_property_name(name, label)
            if not value:
                raise ContractError(f"{label} declaration has empty value for {name}")
            declarations[name] = value
        rules.append((selector, declarations))
        pos = match.end()
    trailing = without_comments[pos:].strip()
    if trailing:
        raise ContractError(f"{label} contains trailing text outside rule blocks: {trailing[:40]!r}")
    # Ensure there are no duplicated selectors in generated contract CSS/Textual style.
    selectors = [selector for selector, _ in rules]
    if len(selectors) != len(set(selectors)):
        duplicates = sorted({selector for selector in selectors if selectors.count(selector) > 1})
        raise ContractError(f"{label} contains duplicate selectors: {duplicates}")
    return rules


def _validate_style_property_name(name: str, label: str) -> None:
    if not re.fullmatch(r"(?:[a-z][a-z0-9-]*|--[a-z][a-z0-9-]*)", name):
        raise ContractError(f"{label} contains invalid style property name: {name}")


def _load_generated_module(path: Path, module_name: str):
    try:
        py_compile.compile(str(path), doraise=True)
        spec = importlib.util.spec_from_file_location(f"{module_name}_{abs(hash(path))}", path)
        if spec is None or spec.loader is None:
            raise ContractError(f"Cannot import generated Python projection: {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except ContractError:
        raise
    except Exception as exc:  # pragma: no cover - exact import failure varies across Python versions.
        raise ContractError(f"Generated Python projection is not importable: {path}: {exc}") from exc


def _expected_textual_compose(state_machine: dict[str, Any]) -> list[tuple[str, str]]:
    widgets = renderer_textual_presentation(state_machine).get("widgets") or []
    if widgets:
        return [(widget["widget_class"], _widget_label(widget)) for widget in widgets]
    slots = state_machine["slots"]
    result: list[tuple[str, str]] = []
    result.extend(("Static", key) for key in slots["text"])
    result.extend(("Static", key) for key in slots["assets"])
    result.extend(("Static", key) for key in slots.get("fields", []))
    result.extend(("Button", invocation_id) for invocation_id in slots["action_bindings"])
    return result


def _widget_label(widget: dict[str, Any]) -> str:
    binding = widget["binding"]
    for key in ["text_slot", "asset_slot", "action_binding", "field_slot", "literal"]:
        if key in binding:
            return binding[key]
    return widget["id"]


def _textual_selector(state_machine: dict[str, Any], selector: str) -> str:
    if selector in {"root", "screen"}:
        return "Screen"
    widgets = renderer_textual_presentation(state_machine).get("widgets") or []
    if selector.startswith("slot."):
        slot = selector[len("slot."):]
        for widget in widgets:
            binding = widget["binding"]
            if binding.get("text_slot") == slot or binding.get("asset_slot") == slot or binding.get("field_slot") == slot:
                return "#" + safe_id(widget["id"])
        return "#" + slot
    if selector.startswith("action_binding."):
        operation = selector[len("action_binding."):]
        for widget in widgets:
            if widget["binding"].get("action_binding") == application_action:
                return "#" + safe_id(widget["id"])
        return "#" + safe_id(operation)
    return selector



def _sample_sql_value(column: dict[str, Any]) -> Any:
    if column["primary_key"]:
        return f"{column['name']}-sample"
    if column["type"] == "Boolean":
        return 1
    if column["type"] == "Integer":
        return 1
    if column["type"] == "Decimal":
        return 1.5
    if column["type"].startswith("list[") or column["type"] == "JSON":
        return "{}"
    if column["type"] == "Date":
        return "2026-01-01"
    if column["type"] == "Timestamp":
        return "2026-01-01T00:00:00Z"
    return "sample"



def _validate_cwl_type(type_spec: Any, label: str) -> None:
    if isinstance(type_spec, str):
        if type_spec not in _CWL_SCALAR_TYPES:
            raise ContractError(f"{label} has unsupported CWL scalar type: {type_spec}")
        return
    if isinstance(type_spec, dict):
        if set(type_spec) != {"type", "items"} or type_spec["type"] != "array":
            raise ContractError(f"{label} has unsupported CWL complex type: {type_spec}")
        _validate_cwl_type(type_spec["items"], label)
        return
    if isinstance(type_spec, list):
        if "null" not in type_spec or len(type_spec) != 2:
            raise ContractError(f"{label} has unsupported CWL union type: {type_spec}")
        for item in type_spec:
            _validate_cwl_type(item, label)
        return
    raise ContractError(f"{label} has malformed CWL type: {type_spec!r}")


def _feature_behavior_scenario_ids(folder: Path) -> set[str]:
    if not folder.exists():
        return set()
    ids: set[str] = set()
    for path in sorted(folder.glob("*.feature")):
        text = path.read_text(encoding="utf-8")
        if not text.startswith("Feature: "):
            raise ContractError(f"Generated feature does not start with Feature: {path}")
        lines = [line.rstrip("\n") for line in text.splitlines()]
        for idx, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("Given "):
                match = re.fullmatch(r'Given spec behavior scenario "([a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+)" is given', stripped)
                if not match:
                    raise ContractError(f"Generated feature has non-spec Given step: {path}: {stripped}")
                behavior_scenario_id = match.group(1)
                ids.add(behavior_scenario_id)
                expected_when = f'When spec behavior scenario "{behavior_scenario_id}" runs when'
                expected_then = f'Then spec behavior scenario "{behavior_scenario_id}" then holds'
                if idx + 2 >= len(lines) or lines[idx + 1].strip() != expected_when or lines[idx + 2].strip() != expected_then:
                    raise ContractError(f"Generated feature behavior scenario {behavior_scenario_id} does not use canonical When/Then steps")
            elif stripped.startswith(("When ", "Then ")):
                # These are validated only immediately after a matching Given.
                continue
            elif stripped.startswith("And ") or stripped.startswith("But "):
                raise ContractError(f"Generated feature contains non-canonical BDD conjunction: {path}: {stripped}")
    return ids


def _path_params(path: str) -> set[str]:
    return set(re.findall(r"{([a-z][a-z0-9_]*)}", path or ""))


def _require_exact_keys(mapping: dict[str, Any], keys: set[str], label: str) -> None:
    actual = set(mapping)
    if actual != keys:
        raise ContractError(_diff_message(label + " keys", keys, actual))


def _diff_message(label: str, expected: set[Any], actual: set[Any]) -> str:
    extra = sorted(actual - expected)
    missing = sorted(expected - actual)
    parts = []
    if missing:
        parts.append("missing " + repr(missing))
    if extra:
        parts.append("extra " + repr(extra))
    return f"{label} mismatch: " + "; ".join(parts)
