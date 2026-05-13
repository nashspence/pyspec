from __future__ import annotations

import ast
import importlib.util
import json
import py_compile
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator

from .compile import ContractError
from .content import ContentContext, ContentError, asset as asset_registry, call_asset, call_copy, copy as copy_registry, instantiate_args, load_resolvers, validate_resolver_function
from .runtime import fixture_namespace, resolve
from .io import read_json, read_yaml
from .audit import audit_expected_files
from .layout import layout_html, layout_html_regions, layout_textual
from .project import (
    components_projection,
    validated_projection_paths,
    composition_css_selector,
    composition_tcss_selector,
    constant_name,
    cwl_type,
    css_selector,
    css_value,
    object_schema,
    panels_projection,
    safe_id,
    tcss_selector,
    type_schema,
)

_HTTP_METHODS = {"get", "put", "post", "delete", "patch", "head", "options", "trace"}
_OPENAPI_OPERATION_KEYS = {
    "operationId",
    "x-entry",
    "x-capability",
    "x-policy",
    "parameters",
    "responses",
    "requestBody",
}
_CWL_SCALAR_TYPES = {"string", "boolean", "int", "long", "float", "double", "Any", "null"}
_PYTHON_PROJECTIONS = [
    "generated/refs.py",
    "generated/driver_protocol.py",
    "generated/bdd_steps.py",
    "generated/textual_contract.py",
    "generated/content_contract.py",
    "generated/content_stubs.py",
]


def validate_generated_projections(root: Path, contract: dict[str, Any]) -> None:
    """Strictly validate every compiler-owned projection that has a mechanical contract.

    These checks intentionally do not trust the generated artifacts just because they are fresh.
    They parse each native surface and cross-check it against the canonical contract graph.
    """
    generated = root / "generated"
    if not generated.exists():
        raise ContractError("Missing generated directory")

    expected_paths = set(validated_projection_paths(contract))
    _validate_python_projections(root)
    validate_refs_py(root, contract)
    if "generated/openapi.yaml" in expected_paths:
        validate_openapi(contract, read_yaml(generated / "openapi.yaml"))
    if "generated/asyncapi.yaml" in expected_paths:
        validate_asyncapi(contract, read_yaml(generated / "asyncapi.yaml"))
    if "generated/routes.json" in expected_paths:
        validate_routes(contract, read_json(generated / "routes.json"))
    if "generated/panels.json" in expected_paths:
        validate_panels_json(contract, read_json(generated / "panels.json"))
    if "generated/panels.html" in expected_paths:
        validate_panels_html(contract, (generated / "panels.html").read_text(encoding="utf-8"))
    if "generated/panel_styles.css" in expected_paths:
        validate_panel_css(contract, (generated / "panel_styles.css").read_text(encoding="utf-8"))
    if "generated/textual_contract.py" in expected_paths:
        validate_textual_contract(root, contract)
    if "generated/content_contract.py" in expected_paths:
        validate_content_contract(root, contract)
    if "generated/workflows.cwl.yaml" in expected_paths:
        validate_workflows(contract, read_yaml(generated / "workflows.cwl.yaml"))
    validate_fixtures_and_scenarios(root, contract)
    if (root / "generated" / "audit").exists() or any(path.startswith("generated/audit/") for path in audit_expected_files(contract)):
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

    expected_operations: dict[tuple[str, str], tuple[str, dict[str, Any], dict[str, Any]]] = {}
    for entry_id, entry in sorted(contract["entries"].items()):
        if entry["surface"] != "api":
            continue
        method = entry["method"].lower()
        key = (entry["path"], method)
        if key in expected_operations:
            raise ContractError(f"OpenAPI duplicate path/method binding in contract: {entry['path']} {method}")
        cap_id = entry["target"]["capability"]
        expected_operations[key] = (entry_id, entry, contract["capabilities"][cap_id])

    actual_operations: dict[tuple[str, str], dict[str, Any]] = {}
    for path, methods in doc["paths"].items():
        if not isinstance(path, str) or not path.startswith("/"):
            raise ContractError(f"OpenAPI path must start with /: {path!r}")
        if not isinstance(methods, dict) or not methods:
            raise ContractError(f"OpenAPI path must declare at least one method: {path}")
        for method, operation in methods.items():
            if method not in _HTTP_METHODS:
                raise ContractError(f"OpenAPI unsupported HTTP method at {path}: {method}")
            if (path, method) in actual_operations:
                raise ContractError(f"OpenAPI duplicate operation: {method.upper()} {path}")
            actual_operations[(path, method)] = operation

    if set(actual_operations) != set(expected_operations):
        raise ContractError(_diff_message("OpenAPI operations", set(expected_operations), set(actual_operations)))

    seen_operation_ids: set[str] = set()
    for (path, method), (entry_id, entry, cap) in expected_operations.items():
        operation = actual_operations[(path, method)]
        unknown_keys = set(operation) - _OPENAPI_OPERATION_KEYS
        if unknown_keys:
            raise ContractError(f"OpenAPI {method.upper()} {path} has unsupported operation keys: {sorted(unknown_keys)}")
        cap_id = entry["target"]["capability"]
        if operation.get("operationId") in seen_operation_ids:
            raise ContractError(f"OpenAPI operationId is duplicated: {operation.get('operationId')}")
        seen_operation_ids.add(operation.get("operationId"))
        if operation.get("operationId") != cap_id:
            raise ContractError(f"OpenAPI operationId must equal capability id for {entry_id}")
        if operation.get("x-entry") != entry_id or operation.get("x-capability") != cap_id:
            raise ContractError(f"OpenAPI extensions do not point back to {entry_id}/{cap_id}")
        if operation.get("x-policy") != cap["policy"]:
            raise ContractError(f"OpenAPI policy extension does not match capability {cap_id}")

        placeholders = _path_params(path)
        params = entry.get("params", {})
        if placeholders != set(params):
            raise ContractError(f"OpenAPI path params for {entry_id} do not match declared params")
        expected_params = [
            {"name": name, "in": "path", "required": True, "schema": type_schema(type_name)}
            for name, type_name in sorted(params.items())
        ]
        if operation.get("parameters", []) != expected_params:
            raise ContractError(f"OpenAPI parameters do not match entry params for {entry_id}")

        body_fields = {k: v for k, v in cap["input"].items() if k not in params}
        if body_fields and method not in {"get", "delete"}:
            expected_body = {
                "required": True,
                "content": {"application/json": {"schema": object_schema(body_fields)}},
            }
            if operation.get("requestBody") != expected_body:
                raise ContractError(f"OpenAPI requestBody does not match capability input for {cap_id}")
        elif "requestBody" in operation:
            raise ContractError(f"OpenAPI requestBody is not allowed for {entry_id}")

        expected_responses = {
            "200": {
                "description": "OK",
                "content": {"application/json": {"schema": type_schema(cap["output"])}},
            }
        }
        if operation.get("responses") != expected_responses:
            raise ContractError(f"OpenAPI response schema does not match capability output for {cap_id}")
        _validate_refs_resolve(operation, doc, f"OpenAPI operation {entry_id}")

    _validate_refs_resolve(doc["components"], doc, "OpenAPI components")


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

    expected_channels = {f"event_{safe_id(event_id)}" for event_id in contract["events"]}
    if set(channels) != expected_channels:
        raise ContractError(_diff_message("AsyncAPI channels", expected_channels, set(channels)))
    expected_messages = {f"message_{safe_id(event_id)}" for event_id in contract["events"]}
    if set(components["messages"]) != expected_messages:
        raise ContractError(_diff_message("AsyncAPI messages", expected_messages, set(components["messages"])))

    expected_operations = {f"send_{safe_id(event_id)}" for event_id in contract["events"]}
    for workflow_id, workflow in contract["workflows"].items():
        if "event" in workflow["trigger"]:
            expected_operations.add(f"receive_{safe_id(workflow_id)}")
    if set(operations) != expected_operations:
        raise ContractError(_diff_message("AsyncAPI operations", expected_operations, set(operations)))

    seen_addresses: set[str] = set()
    for event_id, event in sorted(contract["events"].items()):
        key = safe_id(event_id)
        channel_id = f"event_{key}"
        message_id = f"message_{key}"
        channel = channels[channel_id]
        if channel.get("address") != event_id:
            raise ContractError(f"AsyncAPI channel {channel_id} address must be {event_id}")
        if channel["address"] in seen_addresses:
            raise ContractError(f"AsyncAPI channel address is duplicated: {channel['address']}")
        seen_addresses.add(channel["address"])
        if channel.get("x-event") != event_id:
            raise ContractError(f"AsyncAPI channel {channel_id} missing x-event")
        if channel.get("messages") != {message_id: {"$ref": f"#/components/messages/{message_id}"}}:
            raise ContractError(f"AsyncAPI channel {channel_id} message binding is malformed")

        message = components["messages"][message_id]
        if message.get("name") != event_id:
            raise ContractError(f"AsyncAPI message {message_id} name does not match event")
        if message.get("payload") != type_schema(event["payload"]):
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
        if "event" not in workflow["trigger"]:
            continue
        event_id = workflow["trigger"]["event"]
        op_id = f"receive_{safe_id(workflow_id)}"
        op = operations[op_id]
        if op.get("action") != "receive":
            raise ContractError(f"AsyncAPI receive operation {op_id} must have action=receive")
        _expect_asyncapi_operation_channel(op, f"event_{safe_id(event_id)}", f"message_{safe_id(event_id)}", op_id)
        if op.get("x-workflow") != workflow_id or op.get("x-contract-ref") != workflow["ref"]:
            raise ContractError(f"AsyncAPI receive operation {op_id} does not point to workflow")

    _validate_refs_resolve(doc, doc, "AsyncAPI document")


def validate_routes(contract: dict[str, Any], doc: dict[str, Any]) -> None:
    _require_exact_keys(doc, {"project", "routes"}, "routes.json")
    if doc["project"] != contract["project"]:
        raise ContractError("routes.json project does not match contract")
    expected = []
    for entry_id, entry in sorted(contract["entries"].items()):
        if entry["surface"] == "web":
            expected.append({
                "id": entry["route"],
                "entry": entry_id,
                "path": entry["path"],
                "params": entry.get("params", {}),
                "view": entry["target"]["view"],
            })
    if doc["routes"] != expected:
        raise ContractError("routes.json does not exactly match web entries")
    for route in doc["routes"]:
        if _path_params(route["path"]) != set(route["params"]):
            raise ContractError(f"Route {route['id']} path params do not match declared params")


def validate_panels_json(contract: dict[str, Any], doc: dict[str, Any]) -> None:
    _require_exact_keys(doc, {"project", "panels", "compositions"}, "panels.json")
    if doc["project"] != contract["project"]:
        raise ContractError("panels.json project does not match contract")
    expected_doc = panels_projection(contract)
    if doc != expected_doc:
        raise ContractError("panels.json does not exactly match contract views/panels/compositions")
    panel_ids = [panel["id"] for panel in doc["panels"]]
    if len(panel_ids) != len(set(panel_ids)):
        raise ContractError("panels.json contains duplicate panel ids")
    expected_pairs = {("view", view_id, state_name) for view_id, view in contract["views"].items() for state_name in view.get("states", {})}
    expected_pairs.update({("panel", panel_id, state_name) for panel_id, panel in contract.get("panels", {}).items() for state_name in panel.get("states", {})})
    actual_pairs = {(panel["owner_kind"], panel["owner"], panel["state"]) for panel in doc["panels"]}
    if actual_pairs != expected_pairs:
        raise ContractError(_diff_message("Panel owner/state pairs", expected_pairs, actual_pairs))
    expected_compositions = {view_id for view_id, view in contract["views"].items() if view.get("includes")}
    actual_compositions = {composition["id"] for composition in doc["compositions"]}
    if actual_compositions != expected_compositions:
        raise ContractError(_diff_message("Composed view ids", expected_compositions, actual_compositions))


def validate_panels_html(contract: dict[str, Any], text: str) -> None:
    if not text.startswith("<!doctype html>\n"):
        raise ContractError("panels.html must start with <!doctype html>")
    parser = _PanelHTMLParser()
    parser.feed(text)
    parser.close()
    panels = panels_projection(contract)["panels"]
    panel_by_id = {panel["id"]: panel for panel in panels}
    root_nodes = [node for node in parser.nodes if node.attrs.get("data-contract-panel")]
    root_ids = [node.attrs["data-contract-panel"] for node in root_nodes]
    if set(root_ids) != set(panel_by_id):
        raise ContractError(_diff_message("HTML panel roots", set(panel_by_id), set(root_ids)))
    if len(root_ids) != len(set(root_ids)):
        raise ContractError("panels.html contains duplicate data-contract-panel roots")

    allowed_copy = set()
    allowed_assets = set()
    allowed_actions = set()
    allowed_fields = set()
    for panel in panels:
        allowed_copy.update(panel["slots"]["copy"])
        allowed_assets.update(panel["slots"]["assets"])
        allowed_actions.update(panel["slots"]["actions"])
        allowed_fields.update(panel["slots"].get("fields", []))

    actual_copy = {node.attrs["data-copy"] for node in parser.nodes if "data-copy" in node.attrs}
    actual_assets = {node.attrs["data-asset"] for node in parser.nodes if "data-asset" in node.attrs}
    actual_actions = {node.attrs["data-action"] for node in parser.nodes if "data-action" in node.attrs}
    actual_fields = {node.attrs["data-field"] for node in parser.nodes if "data-field" in node.attrs}
    if not actual_copy.issubset(allowed_copy):
        raise ContractError(f"panels.html contains undeclared copy refs: {sorted(actual_copy - allowed_copy)}")
    if not actual_assets.issubset(allowed_assets):
        raise ContractError(f"panels.html contains undeclared asset refs: {sorted(actual_assets - allowed_assets)}")
    if not actual_actions.issubset(allowed_actions):
        raise ContractError(f"panels.html contains undeclared action refs: {sorted(actual_actions - allowed_actions)}")
    if not actual_fields.issubset(allowed_fields):
        raise ContractError(f"panels.html contains undeclared field refs: {sorted(actual_fields - allowed_fields)}")

    for root in root_nodes:
        panel = panel_by_id[root.attrs["data-contract-panel"]]
        html_contract = (panel.get("presentation") or {}).get("html") or {}
        root_spec = html_contract.get("root") or {"element": "section"}
        if root.tag != root_spec.get("element", "section"):
            raise ContractError(f"HTML root element for {panel['id']} does not match presentation contract")
        if root.attrs.get("data-contract-owner-kind") != panel["owner_kind"] or root.attrs.get("data-contract-owner") != panel["owner"] or root.attrs.get("data-contract-state") != panel["state"]:
            raise ContractError(f"HTML root for {panel['id']} has wrong owner/state")
        classes = set(root.attrs.get("class", "").split())
        required_classes = {"contract-panel"} | set(root_spec.get("classes", []))
        if not required_classes.issubset(classes):
            raise ContractError(f"HTML root for {panel['id']} is missing required classes: {sorted(required_classes - classes)}")
        if root_spec.get("role") and root_spec["role"] != "none" and root.attrs.get("role") != root_spec["role"]:
            raise ContractError(f"HTML root for {panel['id']} missing required role {root_spec['role']}")

        subtree = parser.subtree(root)
        expected_slots = _html_slots_for_panel(panel)
        for slot in expected_slots:
            _assert_html_slot_present(panel, slot, subtree)


    composition_by_id = {composition["id"]: composition for composition in panels_projection(contract)["compositions"]}
    composition_nodes = [node for node in parser.nodes if node.attrs.get("data-contract-composition")]
    actual_composition_ids = {node.attrs["data-contract-composition"] for node in composition_nodes}
    if actual_composition_ids != set(composition_by_id):
        raise ContractError(_diff_message("HTML composed view roots", set(composition_by_id), actual_composition_ids))
    for root in composition_nodes:
        composition = composition_by_id[root.attrs["data-contract-composition"]]
        layout = composition["layout"]
        html_layout = layout_html(layout)
        root_spec = html_layout.get("root") or {"element": "section"}
        if root.tag != root_spec.get("element", "section"):
            raise ContractError(f"HTML composed view root element for {composition['id']} does not match layout contract")
        root_classes = set(root.attrs.get("class", "").split())
        required_root_classes = {"contract-composed-view"} | set(root_spec.get("classes", []))
        if not required_root_classes.issubset(root_classes):
            raise ContractError(f"HTML composed view root for {composition['id']} is missing classes: {sorted(required_root_classes - root_classes)}")
        if root_spec.get("role") and root_spec["role"] != "none" and root.attrs.get("role") != root_spec["role"]:
            raise ContractError(f"HTML composed view root for {composition['id']} missing required role {root_spec['role']}")

        subtree = parser.subtree(root)
        region_nodes = {node.attrs["data-layout-region"]: node for node in subtree if "data-layout-region" in node.attrs}
        expected_regions = set(layout_html_regions(layout))
        if set(region_nodes) != expected_regions:
            raise ContractError(_diff_message(f"HTML layout regions for {composition['id']}", expected_regions, set(region_nodes)))
        for region_name, region in layout_html_regions(layout).items():
            node = region_nodes[region_name]
            if node.tag != region.get("element", "div"):
                raise ContractError(f"HTML layout region {composition['id']}.{region_name} has wrong element")
            classes = set(node.attrs.get("class", "").split())
            required_classes = {"contract-layout-region", f"contract-layout-region--{region_name}"} | set(region.get("classes", []))
            if not required_classes.issubset(classes):
                raise ContractError(f"HTML layout region {composition['id']}.{region_name} is missing classes: {sorted(required_classes - classes)}")
            if node.attrs.get("data-required") != str(region["required"]).lower():
                raise ContractError(f"HTML layout region {composition['id']}.{region_name} has wrong data-required")
            if region.get("role") and region["role"] != "none" and node.attrs.get("role") != region["role"]:
                raise ContractError(f"HTML layout region {composition['id']}.{region_name} missing required role {region['role']}")

        actual_instances = {node.attrs["data-panel-instance"]: node.attrs for node in subtree if "data-panel-instance" in node.attrs}
        expected_instances = {instance["id"]: instance for instance in composition["instances"]}
        if set(actual_instances) != set(expected_instances):
            raise ContractError(_diff_message(f"HTML panel instances for {composition['id']}", set(expected_instances), set(actual_instances)))
        for instance_id, instance in expected_instances.items():
            attrs = actual_instances[instance_id]
            if attrs.get("data-panel-source") != instance["panel"] or attrs.get("data-initial-state") != instance["initial"]:
                raise ContractError(f"HTML panel instance {composition['id']}.{instance_id} has wrong source/initial")
            selected = instance.get("selected")
            if selected and attrs.get("data-selected-state") != selected["state"]:
                raise ContractError(f"HTML panel instance {composition['id']}.{instance_id} has wrong selected state")


def validate_panel_css(contract: dict[str, Any], text: str) -> None:
    rules = _parse_css_rules(text, "panel_styles.css")
    projection = panels_projection(contract)
    panels = projection["panels"]
    compositions = projection["compositions"]
    expected_selectors = {":root", ".contract-panel"}
    for panel in panels:
        css_contract = (panel.get("presentation") or {}).get("css") or {}
        if css_contract.get("tokens"):
            expected_selectors.add(css_selector(panel, "root"))
        for rule in css_contract.get("rules", []):
            expected_selectors.add(css_selector(panel, rule["selector"]))
    for composition in compositions:
        css_contract = (layout_html(composition.get("layout") or {}).get("css") or {})
        if css_contract.get("tokens"):
            expected_selectors.add(composition_css_selector(composition, "root"))
        for rule in css_contract.get("rules", []):
            expected_selectors.add(composition_css_selector(composition, rule["selector"]))
    actual_selectors = {selector for selector, _ in rules}
    if actual_selectors != expected_selectors:
        raise ContractError(_diff_message("panel CSS selectors", expected_selectors, actual_selectors))
    for selector, declarations in rules:
        for name, value in declarations.items():
            _validate_css_property_name(name, f"panel_styles.css selector {selector}")
            if not value or "token." in value:
                raise ContractError(f"panel_styles.css selector {selector} has unresolved or empty value for {name}")

    actual_by_selector = dict(rules)
    for panel in panels:
        css_contract = (panel.get("presentation") or {}).get("css") or {}
        expected_by_selector: dict[str, dict[str, str]] = {}
        root_selector = css_selector(panel, "root")
        for name, value in sorted((css_contract.get("tokens") or {}).items()):
            expected_by_selector.setdefault(root_selector, {})["--" + name.replace("_", "-")] = value
        for rule in css_contract.get("rules", []):
            selector = css_selector(panel, rule["selector"])
            expected = expected_by_selector.setdefault(selector, {})
            for name, value in sorted(rule["declarations"].items()):
                expected[name] = css_value(value)
        for selector, expected in expected_by_selector.items():
            if actual_by_selector.get(selector) != expected:
                raise ContractError(f"panel_styles.css declarations do not match {panel['id']} selector {selector}")
    for composition in compositions:
        css_contract = (composition.get("layout") or {}).get("css") or {}
        expected_by_selector: dict[str, dict[str, str]] = {}
        root_selector = composition_css_selector(composition, "root")
        for name, value in sorted((css_contract.get("tokens") or {}).items()):
            expected_by_selector.setdefault(root_selector, {})["--" + name.replace("_", "-")] = value
        for rule in css_contract.get("rules", []):
            selector = composition_css_selector(composition, rule["selector"])
            expected = expected_by_selector.setdefault(selector, {})
            for name, value in sorted(rule["declarations"].items()):
                expected[name] = css_value(value)
        for selector, expected in expected_by_selector.items():
            if actual_by_selector.get(selector) != expected:
                raise ContractError(f"panel_styles.css declarations do not match composed view {composition['id']} selector {selector}")


def validate_textual_contract(root: Path, contract: dict[str, Any]) -> None:
    path = root / "generated" / "textual_contract.py"
    module = _load_generated_module(path, "generated_textual_contract")
    panel_projection = panels_projection(contract)
    panels = panel_projection["panels"]
    compositions = panel_projection["compositions"]
    if module.PROJECT != contract["project"]:
        raise ContractError("textual_contract.py PROJECT does not match contract")
    if module.PANELS != panels:
        raise ContractError("textual_contract.py PANELS does not match panels projection")
    if module.COMPOSITIONS != compositions:
        raise ContractError("textual_contract.py COMPOSITIONS does not match composition projection")

    expected_screens = []
    panels_by_owner: dict[str, list[dict[str, Any]]] = {}
    for panel in panels:
        panels_by_owner.setdefault(panel["owner"], []).append(panel)
    composition_views = {composition["id"] for composition in compositions}
    for entry_id, entry in sorted(contract["entries"].items()):
        if entry["surface"] != "textual":
            continue
        view_id = entry["target"]["view"]
        screen_class = "ComposedContractScreen" if view_id in composition_views else None
        if screen_class is None:
            for panel in panels_by_owner.get(view_id, []):
                textual = (panel.get("presentation") or {}).get("textual") or {}
                if textual.get("screen_class"):
                    screen_class = textual["screen_class"]
                    break
        expected_screens.append({
            "id": entry.get("screen") or f"screen.{view_id}",
            "entry": entry_id,
            "view": view_id,
            "command": entry.get("command"),
            "screen_class": screen_class,
        })
    if module.SCREENS != expected_screens:
        raise ContractError("textual_contract.py SCREENS does not match textual entries")

    for panel in panels:
        if module.panel(panel["id"]) != panel:
            raise ContractError(f"textual_contract.py panel lookup failed for {panel['id']}")
        expected_widgets = _expected_textual_compose(panel)
        if module.compose_contract_panel(panel["id"]) != expected_widgets:
            raise ContractError(f"textual_contract.py compose_contract_panel mismatch for {panel['id']}")

    for composition in compositions:
        if module.composition(composition["id"]) != composition:
            raise ContractError(f"textual_contract.py composition lookup failed for {composition['id']}")
        expected = [(instance["region"], instance["id"], instance["panel"]) for instance in composition["instances"]]
        if module.compose_contract_view(composition["id"]) != expected:
            raise ContractError(f"textual_contract.py compose_contract_view mismatch for {composition['id']}")

    try:
        module.panel("panel.missing")
    except KeyError:
        pass
    else:  # pragma: no cover
        raise ContractError("textual_contract.py panel() must raise KeyError for unknown panels")

    tcss_rules = _parse_css_rules(module.textual_css(), "textual_contract.py TCSS", textual=True)
    expected_selectors = {"Screen", ".contract-panel"}
    for panel in panels:
        textual = (panel.get("presentation") or {}).get("textual") or {}
        widget_ids = [widget["id"] for widget in textual.get("widgets", [])]
        if len(widget_ids) != len(set(widget_ids)):
            raise ContractError(f"Textual widgets for {panel['id']} contain duplicate ids")
        for rule in textual.get("tcss", {}).get("rules", []):
            expected_selectors.add(_textual_selector(panel, rule["selector"]))
    for composition in compositions:
        textual = layout_textual(composition.get("layout") or {})
        for rule in (textual.get("tcss") or {}).get("rules", []):
            expected_selectors.add(composition_tcss_selector(composition, rule["selector"]))
    actual_selectors = {selector for selector, _ in tcss_rules}
    if actual_selectors != expected_selectors:
        raise ContractError(_diff_message("Textual TCSS selectors", expected_selectors, actual_selectors))


def validate_content_contract(root: Path, contract: dict[str, Any]) -> None:
    generated = root / "generated"
    content_doc = read_yaml(generated / "content_cases.yaml")
    if content_doc != {"project": contract["project"], "content_cases": contract.get("content_cases", {})}:
        raise ContractError("content_cases.yaml does not exactly match contract content cases")
    try:
        load_resolvers(root)
    except ContentError as exc:
        if _final_content_refs(contract):
            raise ContractError(str(exc)) from exc
        return
    declared_copy = set(contract.get("copies", {}))
    declared_assets = set(contract.get("assets", {}))
    unknown_copy = copy_registry.refs - declared_copy
    unknown_assets = asset_registry.refs - declared_assets
    if unknown_copy:
        raise ContractError("Unknown copy resolvers: " + ", ".join(sorted(unknown_copy)))
    if unknown_assets:
        raise ContractError("Unknown asset resolvers: " + ", ".join(sorted(unknown_assets)))

    import importlib, sys
    sys.path.insert(0, str(root))
    try:
        sys.modules.pop("generated.content_contract", None)
        module = importlib.import_module("generated.content_contract")
    finally:
        try:
            sys.path.remove(str(root))
        except ValueError:
            pass
    for ref, item in contract.get("copies", {}).items():
        resolver = item.get("resolver")
        arg_cls = module.COPY_ARG_CLASSES[ref]
        instantiate_args(root, "copy", ref, {name: _sample_value_for_type(type_name) for name, type_name in item.get("args", {}).items()})
        if resolver:
            if ref not in copy_registry.refs:
                raise ContractError(f"Missing final copy resolver: {ref}")
            try:
                validate_resolver_function(copy_registry.function(ref), arg_cls)
            except ContentError as exc:
                raise ContractError(str(exc)) from exc
    for ref, item in contract.get("assets", {}).items():
        resolver = item.get("resolver")
        arg_cls = module.ASSET_ARG_CLASSES[ref]
        instantiate_args(root, "asset", ref, {name: _sample_value_for_type(type_name) for name, type_name in item.get("args", {}).items()})
        if resolver:
            if ref not in asset_registry.refs:
                raise ContractError(f"Missing final asset resolver: {ref}")
            try:
                validate_resolver_function(asset_registry.function(ref), arg_cls)
            except ContentError as exc:
                raise ContractError(str(exc)) from exc

    exercised: set[str] = set()
    for case_id, case in contract.get("content_cases", {}).items():
        namespace = fixture_namespace(contract, case.get("fixtures", []))
        args = {key: resolve(value, namespace) for key, value in case.get("args", {}).items()}
        ref = case["ref"]
        if ref.startswith("copy."):
            item = contract["copies"][ref]
            if not item.get("resolver"):
                result = item["placeholder"]
            else:
                try:
                    result = call_copy(root, ref, args, ContentContext(surface="content_case"))
                except ContentError as exc:
                    raise ContractError(str(exc)) from exc
            if not isinstance(result, str) or not result.strip():
                raise ContractError(f"Content case {case_id} copy result must be non-empty text")
            if item.get("max_chars") is not None and len(result) > item["max_chars"]:
                raise ContractError(f"Content case {case_id} copy result exceeds max_chars")
        else:
            item = contract["assets"][ref]
            if item.get("resolver"):
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
    for section in ["copies", "assets"]:
        for ref, item in contract.get(section, {}).items():
            if item.get("resolver"):
                refs.add(ref)
    return refs


def _sample_value_for_type(type_name: str) -> Any:
    if type_name == "Bool":
        return True
    if type_name == "Int":
        return 1
    if type_name == "Decimal":
        return 1.0
    if type_name == "JSON":
        return {}
    if type_name.startswith("list["):
        return []
    return "sample"

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
    expected_ids.update(f"#{safe_id(cap_id)}" for cap_id in contract["capabilities"])
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
        if item.get("inputs") != {"event": {"type": "Any"}} or item.get("outputs") != {}:
            raise ContractError(f"CWL workflow {workflow_id} inputs/outputs malformed")
        steps = item.get("steps")
        if set(steps) != {step["id"] for step in workflow["steps"]}:
            raise ContractError(f"CWL workflow {workflow_id} steps mismatch")
        for step in workflow["steps"]:
            actual = steps[step["id"]]
            run_id = f"#{safe_id(step['capability'])}"
            if actual.get("run") != run_id or run_id not in by_id:
                raise ContractError(f"CWL workflow {workflow_id} step {step['id']} references unknown run")
            expected_in = {name: "event" for name in sorted(contract["capabilities"][step["capability"]]["input"])}
            if set(actual) != {"run", "in", "out"} or actual.get("in") != expected_in or actual.get("out") != []:
                raise ContractError(f"CWL workflow {workflow_id} step {step['id']} malformed")

    for cap_id, cap in sorted(contract["capabilities"].items()):
        item = by_id[f"#{safe_id(cap_id)}"]
        if set(item) != {"id", "class", "label", "baseCommand", "inputs", "outputs"}:
            raise ContractError(f"CWL capability node {cap_id} has unsupported keys")
        if item.get("class") != "CommandLineTool" or item.get("label") != cap_id:
            raise ContractError(f"CWL capability node {cap_id} must be a labelled CommandLineTool")
        if item.get("baseCommand") != ["contract-capability", cap_id]:
            raise ContractError(f"CWL capability node {cap_id} baseCommand mismatch")
        expected_inputs = {name: {"type": cwl_type(type_name)} for name, type_name in sorted(cap["input"].items())}
        if item.get("inputs") != expected_inputs:
            raise ContractError(f"CWL capability node {cap_id} inputs mismatch")
        if item.get("outputs") != {"result": {"type": cwl_type(cap["output"])}}:
            raise ContractError(f"CWL capability node {cap_id} outputs mismatch")
        for parameter in list(item["inputs"].values()) + list(item["outputs"].values()):
            if set(parameter) != {"type"}:
                raise ContractError(f"CWL capability {cap_id} parameter has unsupported keys")
            _validate_cwl_type(parameter["type"], f"CWL capability {cap_id}")


def validate_fixtures_and_scenarios(root: Path, contract: dict[str, Any]) -> None:
    generated = root / "generated"
    fixtures = read_yaml(generated / "fixtures.yaml")
    scenarios = read_yaml(generated / "scenarios.yaml")
    obligations = read_yaml(generated / "test_obligations.yaml")
    if fixtures != {"project": contract["project"], "fixtures": contract["fixtures"]}:
        raise ContractError("fixtures.yaml does not match contract fixtures")
    if scenarios != {"project": contract["project"], "scenarios": contract["scenarios"]}:
        raise ContractError("scenarios.yaml does not match contract scenarios")
    expected_obligation_keys = {"project", "scenarios", "must_validate_projections", "refs"}
    _require_exact_keys(obligations, expected_obligation_keys, "test_obligations.yaml")
    if obligations["project"] != contract["project"]:
        raise ContractError("test_obligations.yaml metadata mismatch")
    if obligations["scenarios"] != contract["scenarios"]:
        raise ContractError("test_obligations.yaml scenarios mismatch")
    if obligations["must_validate_projections"] != validated_projection_paths(contract):
        raise ContractError("test_obligations.yaml must_validate_projections does not match active projections")

    expected_ids = set(contract["scenarios"])
    actual_ids = _feature_scenario_ids(generated / "features")
    if actual_ids != expected_ids:
        raise ContractError(_diff_message("generated feature scenarios", expected_ids, actual_ids))

    forbidden_harness_dirs = [generated / "features" / "spec", generated / "features" / "prod"]
    for path in forbidden_harness_dirs:
        if path.exists():
            raise ContractError(f"Generated features must be single-source; remove {path.relative_to(root)}")



def validate_audit_outputs(root: Path, contract: dict[str, Any]) -> None:
    audit_root = root / "generated" / "audit"
    if not audit_root.exists():
        raise ContractError("Missing generated/audit directory")
    expected = audit_expected_files(contract)
    actual = {
        str(path.relative_to(root))
        for path in audit_root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }
    if actual != expected:
        raise ContractError(_diff_message("audit generated files", expected, actual))

    copy_doc = read_yaml(audit_root / "copy.yaml")
    if copy_doc != {"project": contract["project"], "copy": contract.get("copies", {})}:
        raise ContractError("audit copy.yaml does not match contract copy placeholders")
    fixtures_doc = read_yaml(audit_root / "fixtures.yaml")
    if fixtures_doc != {"project": contract["project"], "fixtures": contract.get("fixtures", {})}:
        raise ContractError("audit fixtures.yaml does not match contract fixtures")

    for asset_id, asset in contract.get("assets", {}).items():
        path = audit_root / "assets" / f"{safe_id(asset_id)}.svg"
        text = path.read_text(encoding="utf-8")
        if not text.lstrip().startswith("<svg") or "</svg>" not in text:
            raise ContractError(f"audit asset placeholder is not SVG: {asset_id}")
        if asset_id in text:
            raise ContractError(f"audit asset placeholder must not render or embed the asset id: {asset_id}")
        if asset["placeholder"]["label"] not in text:
            raise ContractError(f"audit asset placeholder must preserve the accessible label: {asset_id}")

    for panel_id in contract.get("panels", {}):
        _assert_svg(audit_root / "fsm" / f"{safe_id(panel_id)}.svg", f"FSM {panel_id}")
    for view_id, view in contract.get("views", {}).items():
        if view.get("includes"):
            _assert_svg(audit_root / "composition" / f"{safe_id(view_id)}.svg", f"composition {view_id}")

    projection = panels_projection(contract)
    for panel in projection["panels"]:
        for profile_id, profile in sorted(contract.get("audit_profiles", {}).items()):
            for breakpoint, viewport in profile.get("html", {}).get("breakpoints", {}).items():
                stem = f"{safe_id(profile_id)}.{safe_id(breakpoint)}"
                html_path = audit_root / "html" / "panels" / safe_id(panel["id"]) / f"{stem}.html"
                png_path = audit_root / "html" / "panels" / safe_id(panel["id"]) / f"{stem}.png"
                _assert_html_source(html_path, f"HTML panel audit {panel['id']}/{breakpoint}")
                _assert_png(png_path, f"HTML panel audit {panel['id']}/{breakpoint}", viewport)
            for breakpoint in profile.get("textual", {}).get("breakpoints", {}):
                stem = f"{safe_id(profile_id)}.{safe_id(breakpoint)}"
                py_path = audit_root / "textual" / "panels" / safe_id(panel["id"]) / f"{stem}.py"
                svg_path = audit_root / "textual" / "panels" / safe_id(panel["id"]) / f"{stem}.svg"
                _assert_textual_source(py_path, f"Textual panel audit {panel['id']}/{breakpoint}")
                _assert_svg(svg_path, f"Textual panel audit {panel['id']}/{breakpoint}")
                if "rich-terminal" not in svg_path.read_text(encoding="utf-8"):
                    raise ContractError(f"Textual audit SVG does not look like a Textual terminal capture: {panel['id']}/{breakpoint}")

    for case_id, case in contract.get("render_cases", {}).items():
        profile = contract["audit_profiles"][case["profile"]]
        if "html" in case["surfaces"]:
            for breakpoint, viewport in profile.get("html", {}).get("breakpoints", {}).items():
                stem = f"{safe_id(case['profile'])}.{safe_id(breakpoint)}.{safe_id(case_id)}"
                html_path = audit_root / "html" / "views" / safe_id(case["view"]) / f"{stem}.html"
                png_path = audit_root / "html" / "views" / safe_id(case["view"]) / f"{stem}.png"
                _assert_html_source(html_path, f"HTML view audit {case_id}/{breakpoint}")
                _assert_png(png_path, f"HTML view audit {case_id}/{breakpoint}", viewport)
        if "textual" in case["surfaces"]:
            for breakpoint in profile.get("textual", {}).get("breakpoints", {}):
                stem = f"{safe_id(case['profile'])}.{safe_id(breakpoint)}.{safe_id(case_id)}"
                py_path = audit_root / "textual" / "views" / safe_id(case["view"]) / f"{stem}.py"
                svg_path = audit_root / "textual" / "views" / safe_id(case["view"]) / f"{stem}.svg"
                _assert_textual_source(py_path, f"Textual view audit {case_id}/{breakpoint}")
                _assert_svg(svg_path, f"Textual view audit {case_id}/{breakpoint}")
                if "rich-terminal" not in svg_path.read_text(encoding="utf-8"):
                    raise ContractError(f"Textual audit SVG does not look like a Textual terminal capture: {case_id}/{breakpoint}")


def _assert_html_source(path: Path, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("<!doctype html>\n"):
        raise ContractError(f"{label} source is not exact generated HTML")
    forbidden = ["data-audit-label", "data-audit-fixtures", "audit-fixtures", "Render case:", "View:", "Panel:"]
    present = [item for item in forbidden if item in text]
    if present:
        raise ContractError(f"{label} source contains audit metadata labels: {present}")


def _assert_textual_source(path: Path, label: str) -> None:
    source = path.read_text(encoding="utf-8")
    if "class AuditApp" not in source or "LINES = " not in source:
        raise ContractError(f"{label} source is not exact generated Textual code")
    forbidden = ["Render case:", "View:", "Panel:", "data-audit"]
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
    module = _load_generated_module(root / "generated" / "refs.py", "generated_refs")
    expected_groups: dict[str, list[str]] = {
        "Asset": sorted(contract.get("assets", {})),
        "AuditProfile": sorted(contract.get("audit_profiles", {})),
        "Capability": sorted(contract["capabilities"]),
        "Copy": sorted(contract.get("copies", {})),
        "ContentCase": sorted(contract.get("content_cases", {})),
        "Entry": sorted(contract["entries"]),
        "Event": sorted(contract["events"]),
        "Fact": sorted(contract.get("facts", {})),
        "Fixture": sorted(contract["fixtures"]),
        "Panel": sorted(contract.get("panels", {})),
        "RenderCase": sorted(contract.get("render_cases", {})),
        "Scenario": sorted(contract["scenarios"]),
        "View": sorted(contract["views"]),
    }
    for kind, values in sorted(contract["refs"].items()):
        expected_groups[kind.title().replace("_", "")] = values
    for class_name, values in expected_groups.items():
        cls = getattr(module, class_name, None)
        if cls is None:
            raise ContractError(f"refs.py missing class {class_name}")
        actual = {name: value for name, value in vars(cls).items() if name.isupper()}
        expected = {constant_name(value): value for value in values}
        if actual != expected:
            raise ContractError(f"refs.py constants for {class_name} do not match contract refs")


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


def _slot_ref(panel: dict[str, Any], kind: str, slot: str) -> str:
    key = "copy" if kind == "copy" else "assets"
    for ref in panel["slots"][key]:
        if ref.rsplit(".", 1)[-1] == slot:
            return ref
    raise ContractError(f"{panel['id']} has no {kind} slot {slot}")


def _expect_asyncapi_operation_channel(op: dict[str, Any], channel_id: str, message_id: str, op_id: str) -> None:
    if op.get("channel") != {"$ref": f"#/channels/{channel_id}"}:
        raise ContractError(f"AsyncAPI operation {op_id} references wrong channel")
    if op.get("messages") != [{"$ref": f"#/components/messages/{message_id}"}]:
        raise ContractError(f"AsyncAPI operation {op_id} references wrong message")


def _html_slots_for_panel(panel: dict[str, Any]) -> list[dict[str, Any]]:
    html_contract = (panel.get("presentation") or {}).get("html") or {}
    if html_contract.get("slots"):
        return html_contract["slots"]
    slots: list[dict[str, Any]] = []
    for copy_ref in panel["slots"]["copy"]:
        slot = copy_ref.rsplit(".", 1)[-1]
        item: dict[str, Any] = {"kind": "copy", "slot": slot, "element": "h2" if slot == "title" else "p"}
        if slot == "title":
            item.update({"role": "heading", "level": 2})
        slots.append(item)
    for asset_ref in panel["slots"]["assets"]:
        slots.append({"kind": "asset", "slot": asset_ref.rsplit(".", 1)[-1], "element": "img"})
    for field in panel["slots"].get("fields", []):
        slots.append({"kind": "field", "slot": field, "element": "p"})
    for action in panel["slots"]["actions"]:
        slots.append({"kind": "action", "ref": action, "element": "button"})
    return slots


def _assert_html_slot_present(panel: dict[str, Any], slot: dict[str, Any], nodes: list["_HTMLNode"]) -> None:
    kind = slot["kind"]
    if kind == "copy":
        ref = _slot_ref(panel, "copy", slot["slot"])
        matches = [node for node in nodes if node.tag == slot["element"] and node.attrs.get("data-copy") == ref]
        if not matches:
            raise ContractError(f"panels.html missing copy slot {ref}")
        node = matches[0]
        if node.attrs.get("data-contract-slot") != slot["slot"]:
            raise ContractError(f"panels.html copy slot {ref} has wrong data-contract-slot")
        if slot.get("role") and slot["role"] != "none" and node.attrs.get("role") != slot["role"]:
            raise ContractError(f"panels.html copy slot {ref} missing role")
        if slot.get("level") and node.attrs.get("aria-level") != str(slot["level"]):
            raise ContractError(f"panels.html copy slot {ref} missing aria-level")
        return
    if kind == "asset":
        ref = _slot_ref(panel, "asset", slot["slot"])
        tag = "img" if slot["element"] == "img" else slot["element"]
        matches = [node for node in nodes if node.tag == tag and node.attrs.get("data-asset") == ref]
        if not matches:
            raise ContractError(f"panels.html missing asset slot {ref}")
        node = matches[0]
        if slot.get("alt_copy_slot"):
            alt = _slot_ref(panel, "copy", slot["alt_copy_slot"])
            if node.attrs.get("data-alt-copy") != alt:
                raise ContractError(f"panels.html asset slot {ref} missing data-alt-copy")
        return
    if kind == "field":
        field = slot["slot"]
        if field not in panel["slots"].get("fields", []):
            raise ContractError(f"panels.html field slot is not declared: {field}")
        matches = [node for node in nodes if node.tag == slot["element"] and node.attrs.get("data-field") == field]
        if not matches:
            raise ContractError(f"panels.html missing field slot {field}")
        if matches[0].attrs.get("data-contract-slot") != field:
            raise ContractError(f"panels.html field slot {field} has wrong data-contract-slot")
        return
    action = slot["ref"]
    matches = [node for node in nodes if node.tag == slot["element"] and node.attrs.get("data-action") == action]
    if not matches:
        raise ContractError(f"panels.html missing action slot {action}")
    node = matches[0]
    if slot["element"] == "button" and node.attrs.get("type") != "button":
        raise ContractError(f"panels.html action button {action} must declare type=button")


class _HTMLNode:
    def __init__(self, tag: str, attrs: dict[str, str], parent: int | None):
        self.tag = tag
        self.attrs = attrs
        self.parent = parent


class _PanelHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.nodes: list[_HTMLNode] = []
        self.stack: list[int] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {name: "" if value is None else value for name, value in attrs}
        parent = self.stack[-1] if self.stack else None
        self.nodes.append(_HTMLNode(tag, attr_map, parent))
        idx = len(self.nodes) - 1
        if tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}:
            self.stack.append(idx)

    def handle_endtag(self, tag: str) -> None:
        if not self.stack:
            return
        # Generated HTML is regular enough that the top element should match.
        top = self.nodes[self.stack[-1]]
        if top.tag == tag:
            self.stack.pop()

    def subtree(self, root: _HTMLNode) -> list[_HTMLNode]:
        try:
            root_idx = self.nodes.index(root)
        except ValueError:  # pragma: no cover
            return []
        descendants = []
        for idx, node in enumerate(self.nodes):
            current = node.parent
            while current is not None:
                if current == root_idx:
                    descendants.append(node)
                    break
                current = self.nodes[current].parent
        return descendants


def _parse_css_rules(text: str, label: str, textual: bool = False) -> list[tuple[str, dict[str, str]]]:
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
            _validate_css_property_name(name, label)
            if not value:
                raise ContractError(f"{label} declaration has empty value for {name}")
            declarations[name] = value
        rules.append((selector, declarations))
        pos = match.end()
    trailing = without_comments[pos:].strip()
    if trailing:
        raise ContractError(f"{label} contains trailing text outside rule blocks: {trailing[:40]!r}")
    # Ensure there are no duplicated selectors in generated contract CSS/TCSS.
    selectors = [selector for selector, _ in rules]
    if len(selectors) != len(set(selectors)):
        duplicates = sorted({selector for selector in selectors if selectors.count(selector) > 1})
        raise ContractError(f"{label} contains duplicate selectors: {duplicates}")
    return rules


def _validate_css_property_name(name: str, label: str) -> None:
    if not re.fullmatch(r"(?:[a-z][a-z0-9-]*|--[a-z][a-z0-9-]*)", name):
        raise ContractError(f"{label} contains invalid CSS property name: {name}")


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


def _expected_textual_compose(panel: dict[str, Any]) -> list[tuple[str, str]]:
    textual = (panel.get("presentation") or {}).get("textual") or {}
    widgets = textual.get("widgets") or []
    if widgets:
        return [(widget["kind"], _widget_label(widget)) for widget in widgets]
    slots = panel["slots"]
    result: list[tuple[str, str]] = []
    result.extend(("Static", key) for key in slots["copy"])
    result.extend(("Static", key) for key in slots["assets"])
    result.extend(("Static", key) for key in slots.get("fields", []))
    result.extend(("Button", action) for action in slots["actions"])
    return result


def _widget_label(widget: dict[str, Any]) -> str:
    bind = widget["bind"]
    for key in ["copy", "asset", "action", "field", "literal"]:
        if key in bind:
            return bind[key]
    return widget["id"]


def _textual_selector(panel: dict[str, Any], selector: str) -> str:
    if selector in {"root", "screen"}:
        return "Screen"
    textual = (panel.get("presentation") or {}).get("textual") or {}
    widgets = textual.get("widgets") or []
    if selector.startswith("slot."):
        slot = selector[len("slot."):]
        for widget in widgets:
            bind = widget["bind"]
            if bind.get("copy") == slot or bind.get("asset") == slot:
                return "#" + safe_id(widget["id"])
        return "#" + slot
    if selector.startswith("action."):
        action = selector[len("action."):]
        for widget in widgets:
            if widget["bind"].get("action") == action:
                return "#" + safe_id(widget["id"])
        return "#" + safe_id(action)
    return selector



def _sample_sql_value(column: dict[str, Any]) -> Any:
    if column["primary_key"]:
        return f"{column['name']}-sample"
    if column["type"] == "Bool":
        return 1
    if column["type"] == "Int":
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
    raise ContractError(f"{label} has malformed CWL type: {type_spec!r}")


def _feature_scenario_ids(folder: Path) -> set[str]:
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
                match = re.fullmatch(r'Given contract scenario "([a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+)" is arranged', stripped)
                if not match:
                    raise ContractError(f"Generated feature has non-contract Given step: {path}: {stripped}")
                sid = match.group(1)
                ids.add(sid)
                expected_when = f'When contract scenario "{sid}" is executed'
                expected_then = f'Then contract scenario "{sid}" obligations hold'
                if idx + 2 >= len(lines) or lines[idx + 1].strip() != expected_when or lines[idx + 2].strip() != expected_then:
                    raise ContractError(f"Generated feature scenario {sid} does not use canonical When/Then steps")
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
