from __future__ import annotations

import html
import re
from collections import defaultdict
from typing import Any, Iterable

from .agent_prompts import agent_prompt_paths, agent_prompt_projection_files
from .layout import (
    renderer_textual_layout,
    renderer_textual_presentation,
    renderer_textual_style,
    renderer_html_style,
    renderer_textual_containers,
)
from .paths import generated_relative as g
from .runtime_refs import ReferenceExpressionError, parse_reference_expression
from .targets import (
    entry_state_machine_name,
    entry_point_adapter_pair,
    entry_point_input,
    entry_point_method,
    entry_point_path,
    entry_point_responses,
    entry_target_pair,
)
from .type_expr import (
    PRIMITIVES,
    base_model_name,
    effective_field_type,
    object_to_json_schema,
    referenced_named_types,
    type_display,
    type_to_cwl,
    type_to_json_schema,
    type_to_python,
)


SCALAR_JSON_SCHEMA: dict[str, dict[str, Any]] = PRIMITIVES




def projection_paths(contract: dict[str, Any]) -> list[str]:
    paths = [
        g("__init__.py"),
        g("test_adapters", "__init__.py"),
        g("content_resolvers", "__init__.py"),
        g("test_adapters", "python_refs.py"),
        g("behavior", "fixtures.yaml"),
        g("behavior", "test_cases.yaml"),
        g("test_adapters", "driver_protocol.py"),
        g("test_adapters", "pytest_bdd_steps.py"),
    ]
    if _has_api(contract):
        paths.append(g("product_interfaces", "http.openapi.yaml"))
    if _has_asyncapi(contract):
        paths.append(g("product_interfaces", "events.asyncapi.yaml"))
    if _has_html_routes(contract):
        paths.append(g("product_interfaces", "html.routes.json"))
    if _has_ui(contract):
        paths.append(g("product_interfaces", "html.state_machines.json"))
    if _has_textual_ui(contract):
        paths.append(g("product_interfaces", "textual.projection.py"))
    if _has_workflow(contract):
        paths.append(g("product_interfaces", "workflow.cwl.yaml"))
    if _has_authorization_policies(contract):
        paths.append(g("product_interfaces", "authorization_policies.json"))
    if _has_content(contract):
        paths.extend([g("content_resolvers", "__init__.py"), g("content_resolvers", "signatures.py"), g("content_resolvers", "stubs.py"), g("content_resolvers", "cases.yaml")])
    paths.extend(sorted(feature_projections(contract)))
    paths.extend(agent_prompt_paths())
    return paths


def validated_projection_paths(contract: dict[str, Any]) -> list[str]:
    skip = {
        g("__init__.py"),
        g("test_adapters", "__init__.py"),
        g("test_adapters", "driver_protocol.py"),
        g("test_adapters", "pytest_bdd_steps.py"),
    }
    return [path for path in projection_paths(contract) if path not in skip and not path.startswith(g("test_adapters", "pytest_bdd_features") + "/")]


def projection_files(contract: dict[str, Any], *, layers: str | set[str] | None = None) -> Iterable[tuple[str, Any, str]]:
    yield g("__init__.py"), "# Generated package. Do not edit.\n", "text"
    yield g("test_adapters", "__init__.py"), "# Generated package. Do not edit.\n", "text"
    if _has_api(contract):
        yield g("product_interfaces", "http.openapi.yaml"), openapi_projection(contract), "yaml"
    if _has_asyncapi(contract):
        yield g("product_interfaces", "events.asyncapi.yaml"), asyncapi_projection(contract), "yaml"
    if _has_html_routes(contract):
        yield g("product_interfaces", "html.routes.json"), routes_projection(contract), "json"
    if _has_ui(contract):
        yield g("product_interfaces", "html.state_machines.json"), state_machines_projection(contract), "json"
    if _has_textual_ui(contract):
        yield g("product_interfaces", "textual.projection.py"), textual_contract_projection(contract), "text"
    if _has_workflow(contract):
        yield g("product_interfaces", "workflow.cwl.yaml"), workflows_projection(contract), "yaml"
    if _has_authorization_policies(contract):
        yield g("product_interfaces", "authorization_policies.json"), authorization_policies_projection(contract), "json"
    yield g("behavior", "fixtures.yaml"), fixtures_projection(contract), "yaml"
    yield g("behavior", "test_cases.yaml"), test_cases_projection(contract), "yaml"
    yield g("test_adapters", "python_refs.py"), refs_py_projection(contract), "text"
    if _has_content(contract):
        yield g("content_resolvers", "__init__.py"), "# Generated package. Do not edit.\n", "text"
        yield g("content_resolvers", "signatures.py"), content_contract_projection(contract), "text"
        yield g("content_resolvers", "stubs.py"), content_stubs_projection(contract), "text"
        yield g("content_resolvers", "cases.yaml"), content_cases_projection(contract), "yaml"
    yield g("test_adapters", "driver_protocol.py"), driver_protocol_projection(), "text"
    yield g("test_adapters", "pytest_bdd_steps.py"), bdd_steps_projection(), "text"
    for relative, text in feature_projections(contract).items():
        yield relative, text, "text"
    yield from agent_prompt_projection_files(contract, layers=layers)


def _entry_points_with_adapter(contract: dict[str, Any], *adapters: str) -> list[dict[str, Any]]:
    wanted = set(adapters)
    return [
        entry
        for entry in contract.get("entry_points", {}).values()
        if entry_point_adapter_pair(entry)[0] in wanted
    ]


def _has_api(contract: dict[str, Any]) -> bool:
    return bool(_entry_points_with_adapter(contract, "http_api"))


def _has_asyncapi(contract: dict[str, Any]) -> bool:
    return bool(contract.get("events")) and (bool(_entry_points_with_adapter(contract, "webhook", "worker")) or any("event" in wf.get("trigger", {}) for wf in contract.get("workflows", {}).values()))


def _has_html_routes(contract: dict[str, Any]) -> bool:
    return bool(_entry_points_with_adapter(contract, "html_route"))


def _has_workflow(contract: dict[str, Any]) -> bool:
    return bool(contract.get("workflows")) or bool(_entry_points_with_adapter(contract, "cli", "worker", "scheduled"))


def _has_ui(contract: dict[str, Any]) -> bool:
    return bool(contract.get("state_machines"))


def _state_has_textual_presentation(state: dict[str, Any]) -> bool:
    return bool(renderer_textual_presentation(state))


def _has_textual_ui(contract: dict[str, Any]) -> bool:
    for owner in contract.get("state_machines", {}).values():
        if any(_state_has_textual_presentation(state) for state in owner.get("view_states", {}).values()):
            return True
        if any(renderer_textual_layout(state) for state in owner.get("view_states", {}).values()):
            return True
    return False




def _has_content(contract: dict[str, Any]) -> bool:
    return bool(contract.get("text_resources") or contract.get("assets") or contract.get("content_cases"))


def _has_authorization_policies(contract: dict[str, Any]) -> bool:
    return bool(contract.get("authorization_policies"))


def openapi_projection(contract: dict[str, Any]) -> dict[str, Any]:
    paths: dict[str, Any] = {}
    for entry_id, entry in sorted(contract["entry_points"].items()):
        if entry_point_adapter_pair(entry)[0] != "http_api":
            continue
        target_kind, cap_id = entry_target_pair(entry)
        if target_kind != "application_action":
            continue
        cap = contract["application_actions"][cap_id]
        entry_input = entry_point_input(entry)
        path_params = entry_input.get("path_params", {})
        query_params = entry_input.get("query_params", {})
        body_fields = entry_input.get("body", {})
        responses = {}
        for outcome_id, response in sorted(entry_point_responses(entry).items()):
            response_status = str(response["status"])
            body_type = response["body"]["type"]
            responses[response_status] = {
                "description": humanize(outcome_id),
                "content": {"application/json": {"schema": type_schema(body_type)}},
            }
        op: dict[str, Any] = {
            "operationId": cap_id,
            "x-entry": entry_id,
            "x-application-action": cap_id,
            "parameters": [
                {"name": name, "in": "path", "required": True, "schema": type_schema(type_name)}
                for name, type_name in sorted(path_params.items())
            ] + [
                {"name": name, "in": "query", "required": True, "schema": type_schema(type_name)}
                for name, type_name in sorted(query_params.items())
            ],
            "responses": responses,
        }
        if cap.get("authorization"):
            op["x-authorization-policy"] = cap["authorization"]["policy"]
        method = (entry_point_method(entry) or "").lower()
        if body_fields and method not in {"get", "delete"}:
            op["requestBody"] = {
                "required": True,
                "content": {"application/json": {"schema": object_schema(body_fields)}}
            }
        paths.setdefault(entry_point_path(entry), {})[method] = op

    components = components_projection(contract)
    return {
        "openapi": "3.1.0",
        "info": {"title": contract["project"], "version": "0.0.0-contract"},
        "paths": paths,
        "components": components,
    }


def asyncapi_projection(contract: dict[str, Any]) -> dict[str, Any]:
    channels: dict[str, Any] = {}
    operations: dict[str, Any] = {}
    messages: dict[str, Any] = {}

    for event_id, event in sorted(contract["events"].items()):
        key = safe_id(event_id)
        channel_id = f"event_{key}"
        message_id = f"message_{key}"
        channels[channel_id] = {
            "address": event_id,
            "messages": {message_id: {"$ref": f"#/components/messages/{message_id}"}},
            "x-event": event_id,
        }
        messages[message_id] = {
            "name": event_id,
            "title": humanize(event_id),
            "payload": type_schema(event["payload_schema"]),
            "x-emitted-by": sorted(event["emitted_by"]),
        }
        operations[f"send_{key}"] = {
            "action": "send",
            "channel": {"$ref": f"#/channels/{channel_id}"},
            "messages": [{"$ref": f"#/components/messages/{message_id}"}],
            "x-emitted-by": sorted(event["emitted_by"]),
        }

    for workflow_id, workflow in sorted(contract["workflows"].items()):
        trigger = workflow["trigger"]
        if "event" not in trigger:
            continue
        event_id = trigger["event"]
        key = safe_id(event_id)
        operations[f"receive_{safe_id(workflow_id)}"] = {
            "action": "receive",
            "channel": {"$ref": f"#/channels/event_{key}"},
            "messages": [{"$ref": f"#/components/messages/message_{key}"}],
            "x-workflow": workflow_id,
            "x-contract-ref": workflow["ref"],
        }
        dispositions = _workflow_entry_dispositions(contract, workflow_id)
        if dispositions:
            operations[f"receive_{safe_id(workflow_id)}"]["x-dispositions"] = dispositions

    return {
        "asyncapi": "3.1.0",
        "info": {"title": contract["project"], "version": "0.0.0-contract"},
        "channels": channels,
        "operations": operations,
        "components": {
            "messages": messages,
            "schemas": components_projection(contract)["schemas"],
        },
    }


def _workflow_entry_dispositions(contract: dict[str, Any], workflow_id: str) -> dict[str, Any]:
    dispositions: dict[str, Any] = {}
    for entry_id, entry in sorted(contract.get("entry_points", {}).items()):
        if entry_point_adapter_pair(entry)[0] not in {"worker", "scheduled"}:
            continue
        target_kind, target_ref = entry_target_pair(entry)
        if target_kind != "workflow" or target_ref != workflow_id:
            continue
        dispositions[entry_id] = entry_point_responses(entry)
    return dispositions


def routes_projection(contract: dict[str, Any]) -> dict[str, Any]:
    return {
        "project": contract["project"],
        "routes": [
            {
                "id": entry["route"],
                "entry": entry_id,
                "path": entry_point_path(entry),
                "path_params": entry_point_input(entry).get("path_params", {}),
                "query_params": entry_point_input(entry).get("query_params", {}),
                "state_machine": entry_state_machine_name(entry),
            }
            for entry_id, entry in sorted(contract["entry_points"].items())
            if entry_point_adapter_pair(entry)[0] == "html_route"
        ],
    }


def state_machines_projection(contract: dict[str, Any]) -> dict[str, Any]:
    state_machines: list[dict[str, Any]] = []
    for state_machine_id, state_machine in sorted(contract.get("state_machines", {}).items()):
        for state_name, state in sorted(state_machine.get("view_states", {}).items()):
            item = state_machine_projection_item("state_machine", state_machine_id, state_name, state)
            item["state_machine"] = {
                "initial_view_state": state_machine["initial_view_state"],
                "transitions": state_machine.get("transitions", []),
                "context": state_machine.get("context", {}),
            }
            state_machines.append(item)
    compositions = []
    for state_machine_id, state_machine in sorted(contract["state_machines"].items()):
        for state_name, state in sorted(state_machine.get("view_states", {}).items()):
            if state.get("child_state_machines"):
                compositions.append({
                    "id": f"{state_machine_id}.{state_name}",
                    "state_machine": state_machine_id,
                    "view_state": state_name,
                    "context": state_machine.get("context", {}),
                    "renderers": state.get("renderers", {}),
                    "child_state_machines": state.get("child_state_machines", []),
                    "signal_sync_rules": state.get("signal_sync_rules", []),
                })
    return {"project": contract["project"], "state_machines": state_machines, "compositions": compositions}


def state_machine_projection_item(owner_kind: str, owner_id: str, state_name: str, state: dict[str, Any]) -> dict[str, Any]:
    item = {
        "id": state["surface"],
        "owner_kind": owner_kind,
        "owner": owner_id,
        "view_state": state_name,
        "data_loaders": state.get("data_loaders", {}),
        "slots": {
            "text": state["text"],
            "assets": state["assets"],
            "fields": state.get("fields", []),
            "action_bindings": state["action_bindings"],
        },
    }
    if state.get("renderers"):
        item["renderers"] = _surface_renderers(state)
    return item


def _surface_renderers(state: dict[str, Any]) -> dict[str, Any]:
    if not state.get("child_state_machines"):
        return state.get("renderers", {})
    renderers: dict[str, Any] = {}
    for platform, renderer in (state.get("renderers") or {}).items():
        if renderer.get("layout"):
            renderers[platform] = {"layout": renderer["layout"]}
    return renderers


def state_machine_styles_projection(
    contract: dict[str, Any],
    *,
    surface_ids: Iterable[str] | None = None,
    composition_ids: Iterable[str] | None = None,
) -> str:
    wanted_surfaces = set(surface_ids) if surface_ids is not None else None
    wanted_compositions = set(composition_ids) if composition_ids is not None else None
    lines = [
        "/* Generated state machine surface style contract. Do not edit. */",
        ":root {",
        "  --contract-space: 1rem;",
        "  --contract-state-machine-surface-max-width: 48rem;",
        "}",
        ".contract-state-machine-surface {",
        "  display: grid;",
        "  gap: var(--contract-space);",
        "  max-width: var(--contract-state-machine-surface-max-width);",
        "}",
    ]
    state_machines = state_machines_projection(contract)["state_machines"]
    for state_machine in state_machines:
        if wanted_surfaces is not None and state_machine["id"] not in wanted_surfaces:
            continue
        css_contract = renderer_html_style(state_machine)
        grouped: dict[str, dict[str, str]] = {}
        root_selector = css_selector(state_machine, "root")
        for name, value in sorted((css_contract.get("tokens") or {}).items()):
            grouped.setdefault(root_selector, {})["--" + name.replace("_", "-")] = value
        for rule in css_contract.get("rules", []):
            selector = css_selector(state_machine, rule["selector"])
            declarations = grouped.setdefault(selector, {})
            for name, value in sorted(rule["declarations"].items()):
                declarations[name] = style_token_value(value)
        for selector, declarations in grouped.items():
            lines.append(f"{selector} {{")
            for name, value in declarations.items():
                lines.append(f"  {name}: {value};")
            lines.append("}")
    for composition in state_machines_projection(contract)["compositions"]:
        if wanted_compositions is not None and composition["id"] not in wanted_compositions:
            continue
        css_contract = renderer_html_style(composition)
        grouped: dict[str, dict[str, str]] = {}
        root_selector = composition_css_selector(composition, "root")
        for name, value in sorted((css_contract.get("tokens") or {}).items()):
            grouped.setdefault(root_selector, {})["--" + name.replace("_", "-")] = value
        for rule in css_contract.get("rules", []):
            selector = composition_css_selector(composition, rule["selector"])
            declarations = grouped.setdefault(selector, {})
            for name, value in sorted(rule["declarations"].items()):
                declarations[name] = style_token_value(value)
        for selector, declarations in grouped.items():
            lines.append(f"{selector} {{")
            for name, value in declarations.items():
                lines.append(f"  {name}: {value};")
            lines.append("}")
    return "\n".join(lines) + "\n"


def textual_contract_projection(contract: dict[str, Any]) -> str:
    projection = state_machines_projection(contract)
    state_machines = projection["state_machines"]
    compositions = projection["compositions"]
    screen_entries = textual_screen_entries(contract, state_machines, compositions)
    return f'''from __future__ import annotations

# Generated Textual projection. Do not edit by hand.
# The PM contract owns state machines/view states/application_actions/widgets/Textual styles; a real Textual app imports this file
# and renders state machine view-state surfaces by id instead of inventing screens, widgets, or operation keys.

PROJECT = {contract["project"]!r}
SCREENS = {screen_entries!r}
STATE_MACHINES = {state_machines!r}
COMPOSITIONS = {compositions!r}
TEXTUAL_TCSS = {textual_tcss(state_machines, compositions)!r}


def state_machine_surface(surface_id: str) -> dict:
    for item in STATE_MACHINES:
        if item["id"] == surface_id:
            return item
    raise KeyError(surface_id)


def composition(composition_id: str) -> dict:
    for item in COMPOSITIONS:
        if item["id"] == composition_id:
            return item
    raise KeyError(composition_id)


def textual_tcss() -> str:
    return TEXTUAL_TCSS


def compose_contract_state_machine(surface_id: str) -> list[tuple[str, str]]:
    item = state_machine_surface(surface_id)
    textual = ((item.get("renderers") or {{}}).get("textual") or {{}}).get("presentation") or {{}}
    widgets = textual.get("widgets") or []
    if widgets:
        return [(widget["widget_class"], widget_label(widget)) for widget in widgets]
    slots = item["slots"]
    result: list[tuple[str, str]] = []
    result.extend(("Static", key) for key in slots["text"])
    result.extend(("Static", key) for key in slots["assets"])
    result.extend(("Static", key) for key in slots.get("fields", []))
    result.extend(("Button", invocation_id) for invocation_id in slots["action_bindings"])
    return result


def compose_contract_composition(composition_id: str) -> list[tuple[str, str, str]]:
    item = composition(composition_id)
    return [((mount.get("textual_container") or mount.get("html_region")), mount["id"], mount["state_machine"]) for mount in item["child_state_machines"]]


def widget_label(widget: dict) -> str:
    binding = widget["binding"]
    if "text_slot" in binding:
        return binding["text_slot"]
    if "asset_slot" in binding:
        return binding["asset_slot"]
    if "action_binding" in binding:
        return binding["action_binding"]
    if "field_slot" in binding:
        return binding["field_slot"]
    return binding.get("literal", widget["id"])
'''


def textual_screen_entries(
    contract: dict[str, Any],
    state_machines: list[dict[str, Any]] | None = None,
    compositions: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    projection = None if state_machines is not None and compositions is not None else state_machines_projection(contract)
    state_machines = state_machines if state_machines is not None else projection["state_machines"]  # type: ignore[index]
    compositions = compositions if compositions is not None else projection["compositions"]  # type: ignore[index]
    state_machines_by_owner: dict[str, list[dict[str, Any]]] = {}
    for state_machine in state_machines:
        state_machines_by_owner.setdefault(state_machine["owner"], []).append(state_machine)
    compositions_by_state_machine = {composition["id"]: composition for composition in compositions}
    screens = []
    for state_machine_id, state_machine in sorted(contract["state_machines"].items()):
        screen_class = _textual_screen_class(state_machine_id, state_machine, state_machines_by_owner, compositions_by_state_machine)
        if screen_class is None:
            continue
        screens.append({
            "id": f"screen.{state_machine_id}",
            "state_machine": state_machine_id,
            "screen_class": screen_class,
        })
    return screens


def _textual_screen_class(
    state_machine_id: str,
    state_machine: dict[str, Any],
    state_machines_by_owner: dict[str, list[dict[str, Any]]],
    compositions_by_state_machine: dict[str, dict[str, Any]],
) -> str | None:
    for state_name, state in sorted(state_machine.get("view_states", {}).items()):
        textual = renderer_textual_layout(state)
        if textual:
            return textual.get("screen_class") or "ComposedContractScreen"
    for surface in state_machines_by_owner.get(state_machine_id, []):
        textual = renderer_textual_presentation(surface)
        if textual:
            return "Screen"
    if any(
        not state.get("child_state_machines") and bool(renderer_textual_presentation(state))
        for state in state_machine.get("view_states", {}).values()
    ):
        return "Screen"
    return None


def default_html_slots(state_machine: dict[str, Any]) -> list[dict[str, Any]]:
    slots: list[dict[str, Any]] = []
    for text_ref in state_machine["slots"]["text"]:
        slot = text_ref.rsplit(".", 1)[-1]
        element = "h2" if slot == "title" else "p"
        item: dict[str, Any] = {"binding": {"text_slot": slot}, "component": "text", "element": element}
        if slot == "title":
            item.update({"role": "heading", "level": 2})
        slots.append(item)
    for asset_ref in state_machine["slots"]["assets"]:
        slots.append({"binding": {"asset_slot": asset_ref.rsplit(".", 1)[-1]}, "component": "image", "element": "img"})
    for field in state_machine["slots"].get("fields", []):
        slots.append({"binding": {"field_slot": field}, "component": "field", "element": "p"})
    for invocation_id in state_machine["slots"]["action_bindings"]:
        slots.append({"binding": {"action_binding": invocation_id}, "component": "button", "element": "button"})
    return slots


def css_selector(state_machine: dict[str, Any], selector: str) -> str:
    root = f'[data-contract-state-machine-surface="{state_machine["id"]}"]'
    if selector in {"root", "screen"}:
        return root
    if selector.startswith("slot."):
        slot = selector[len("slot."):]
        return f'{root} [data-contract-slot="{slot}"]'
    if selector.startswith("action_binding."):
        invocation_id = selector[len("action_binding."):]
        return f'{root} [data-operation-invocation="{invocation_id}"]'
    return root


def composition_css_selector(composition: dict[str, Any], selector: str) -> str:
    root = f'[data-contract-composition="{composition["id"]}"]'
    if selector in {"root", "screen"}:
        return root
    if selector.startswith("region."):
        region = selector[len("region."):]
        return f'{root} [data-layout-region="{region}"]'
    if selector.startswith("child_state_machine."):
        child_state_machine = selector[len("child_state_machine."):]
        return f'{root} [data-child-state-machine="{child_state_machine}"]'
    return root


def textual_tcss(state_machines: list[dict[str, Any]], compositions: list[dict[str, Any]] | None = None) -> str:
    grouped: dict[str, dict[str, str]] = {
        "Screen": {"layout": "vertical"},
        ".contract-state-machine-surface": {"padding": "1"},
    }
    for state_machine in state_machines:
        for rule in renderer_textual_style(state_machine).get("rules", []):
            selector = tcss_selector(state_machine, rule["selector"])
            declarations = grouped.setdefault(selector, {})
            for name, value in sorted(rule["declarations"].items()):
                declarations[name] = style_token_value(value)
    for composition in compositions or []:
        for rule in renderer_textual_style(composition).get("rules", []):
            selector = composition_tcss_selector(composition, rule["selector"])
            declarations = grouped.setdefault(selector, {})
            for name, value in sorted(rule["declarations"].items()):
                declarations[name] = style_token_value(value)
    lines = ["/* Generated Textual TCSS contract. Do not edit. */"]
    for selector, declarations in grouped.items():
        lines.append(f"{selector} {{")
        for name, value in declarations.items():
            lines.append(f"  {name}: {value};")
        lines.append("}")
    return "\n".join(lines) + "\n"


def tcss_selector(state_machine: dict[str, Any], selector: str) -> str:
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


def composition_tcss_selector(composition: dict[str, Any], selector: str) -> str:
    if selector in {"root", "screen"}:
        textual = renderer_textual_layout(composition)
        return textual.get("screen_class") or "Screen"
    if selector.startswith("container."):
        container_name = selector[len("container."):]
        container = renderer_textual_containers(composition).get(container_name, {})
        return "#" + safe_id(container.get("id", container_name))
    if selector.startswith("child_state_machine."):
        return "#" + safe_id(selector[len("child_state_machine."):])
    return selector


def style_token_value(value: str) -> str:
    def repl(match: re.Match[str]) -> str:
        return f"var(--{match.group(1).replace('_', '-')})"
    return re.sub(r"token\.([a-z][a-z0-9_]*)", repl, value)


def format_attrs(attrs: dict[str, str]) -> str:
    if not attrs:
        return ""
    return " " + " ".join(f'{name}="{html.escape(str(value), quote=True)}"' for name, value in sorted(attrs.items()))


def workflows_projection(contract: dict[str, Any]) -> dict[str, Any]:
    graph = []
    for workflow_id, workflow in sorted(contract["workflows"].items()):
        steps = {}
        for step in workflow["steps"]:
            cap = contract["application_actions"][step["application_action"]]
            steps[step["id"]] = {
                "doc": f"input_bindings={step['input_bindings']}; outcome_routes={step['outcome_routes']}",
                "run": f"#{safe_id(step['application_action'])}",
                "in": {name: _workflow_cwl_source(source) for name, source in sorted(step["input_bindings"].items())},
                "out": sorted(cap["outcomes"]),
            }
        trigger_payload_type = _workflow_trigger_payload_type(contract, workflow)
        graph.append({
            "id": f"#{safe_id(workflow_id)}",
            "class": "Workflow",
            "label": workflow_id,
            "doc": f"contract workflow {workflow_id}; trigger={workflow['trigger']}; outcomes={list(workflow['outcomes'])}; ref={workflow['ref']}",
            "inputs": {"trigger_payload": {"type": cwl_type(trigger_payload_type)}},
            "outputs": {
                outcome_id: {"type": cwl_type(outcome["result"])}
                for outcome_id, outcome in sorted(workflow["outcomes"].items())
            },
            "steps": steps,
        })
    for cap_id in _cwl_application_action_ids(contract):
        cap = contract["application_actions"][cap_id]
        graph.append({
            "id": f"#{safe_id(cap_id)}",
            "class": "CommandLineTool",
            "label": cap_id,
            "baseCommand": ["contract-operation", cap_id],
            "inputs": {name: {"type": cwl_type(type_name)} for name, type_name in sorted(cap["input"].items())},
            "outputs": {
                outcome_id: {"type": cwl_type(outcome["result"])}
                for outcome_id, outcome in sorted(cap["outcomes"].items())
            },
        })
    return {"cwlVersion": "v1.2", "$graph": graph}


def _cwl_application_action_ids(contract: dict[str, Any]) -> list[str]:
    application_action_ids = {
        step["application_action"]
        for workflow in contract.get("workflows", {}).values()
        for step in workflow.get("steps", [])
    }
    for entry in contract.get("entry_points", {}).values():
        adapter_kind, _ = entry_point_adapter_pair(entry)
        target_kind, target_ref = entry_target_pair(entry)
        if adapter_kind == "cli" and target_kind == "application_action":
            application_action_ids.add(target_ref)
        elif adapter_kind == "cli" and target_kind == "entry_point":
            application_action_id = _entry_point_effective_application_action_ref(contract, target_ref)
            if application_action_id:
                application_action_ids.add(application_action_id)
    return sorted(application_action_ids)


def _entry_point_effective_application_action_ref(contract: dict[str, Any], entry_id: str) -> str | None:
    target_kind, target_ref = entry_target_pair(contract["entry_points"][entry_id])
    if target_kind == "application_action":
        return target_ref
    if target_kind == "entry_point":
        return _entry_point_effective_application_action_ref(contract, target_ref)
    return None


def _workflow_trigger_payload_type(contract: dict[str, Any], workflow: dict[str, Any]) -> str:
    trigger = workflow["trigger"]
    if "event" in trigger:
        return contract["events"][trigger["event"]]["payload_schema"]
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


def fixtures_projection(contract: dict[str, Any]) -> dict[str, Any]:
    return {"project": contract["project"], "fixtures": contract["fixtures"]}


def test_cases_projection(contract: dict[str, Any]) -> dict[str, Any]:
    return {"project": contract["project"], "test_cases": contract["test_cases"]}


def authorization_policies_projection(contract: dict[str, Any]) -> dict[str, Any]:
    return {
        "project": contract["project"],
        "authorization_policies": contract.get("authorization_policies", {}),
        "action_authorizations": {
            application_action_id: operation["authorization"]
            for application_action_id, operation in sorted(contract.get("application_actions", {}).items())
            if "authorization" in operation
        },
        "entry_point_authorization_policies": {
            entry_id: entry["authorization_policy"]
            for entry_id, entry in sorted(contract.get("entry_points", {}).items())
            if "authorization_policy" in entry
        },
    }


def content_cases_projection(contract: dict[str, Any]) -> dict[str, Any]:
    return {"project": contract["project"], "content_cases": contract.get("content_cases", {})}


def python_type_for_contract_type(type_name: Any) -> str:
    return type_to_python(type_name)


def content_arg_class_name(ref: str) -> str:
    prefix, *parts = ref.replace("_", " ").replace(".", " ").split()
    return prefix.title() + "".join(part.title() for part in parts) + "Args"


def _content_signature_items(contract: dict[str, Any], section: str) -> list[tuple[str, dict[str, Any], str]]:
    items = []
    for ref, spec in sorted(contract.get(section, {}).items()):
        items.append((ref, spec, content_arg_class_name(ref)))
    return items


def content_contract_projection(contract: dict[str, Any]) -> str:
    lines = [
        '"""Generated content source signatures. Do not edit by hand."""',
        "from __future__ import annotations",
        "",
        "from dataclasses import dataclass",
        "from typing import Any",
        "",
        "from pyspec_contract.content import AssetResult, ContentContext",
        "",
    ]
    text_classes: dict[str, str] = {}
    asset_classes: dict[str, str] = {}
    for section, mapping_name, store in [("text_resources", "TEXT_SIGNATURES", text_classes), ("assets", "ASSET_SIGNATURES", asset_classes)]:
        for ref, spec, class_name in _content_signature_items(contract, section):
            store[ref] = class_name
            args = spec.get("args", {})
            lines.append("@dataclass(frozen=True)")
            lines.append(f"class {class_name}:")
            if args:
                for name, type_name in sorted(args.items()):
                    lines.append(f"    {name}: {python_type_for_contract_type(type_name)}")
            else:
                lines.append("    pass")
            lines.append("")
    lines.append(f"TEXT_SIGNATURES = { {ref: {'args': spec.get('args', {}), 'source_ref': spec.get('source_ref'), 'arg_class': text_classes[ref]} for ref, spec, _ in _content_signature_items(contract, 'text_resources')}!r}")
    lines.append(f"ASSET_SIGNATURES = { {ref: {'args': spec.get('args', {}), 'source_ref': spec.get('source_ref'), 'arg_class': asset_classes[ref]} for ref, spec, _ in _content_signature_items(contract, 'assets')}!r}")
    lines.append(f"TEXT_ARG_CLASSES = {{{', '.join(f'{ref!r}: {cls}' for ref, cls in text_classes.items())}}}")
    lines.append(f"ASSET_ARG_CLASSES = {{{', '.join(f'{ref!r}: {cls}' for ref, cls in asset_classes.items())}}}")
    lines.append("")
    return "\n".join(lines)


def content_stubs_projection(contract: dict[str, Any]) -> str:
    lines = [
        '"""Generated content source stubs. Do not edit; move needed functions into spec.py."""',
        "from __future__ import annotations",
        "",
        "from pyspec_contract.content import AssetResult, ContentContext, asset, text",
        "from generated.content_resolvers.signatures import *  # generated arg classes",
        "from generated.test_adapters.python_refs import Asset, Text",
        "",
    ]
    for ref, spec, class_name in _content_signature_items(contract, "text_resources"):
        source_ref = spec.get("source_ref")
        if not source_ref:
            continue
        lines.extend([
            f"@text.implements(Text.{constant_name(ref)})",
            f"def {safe_id(ref)}(args: {class_name}, ctx: ContentContext) -> str:",
            f"    raise NotImplementedError({ref!r})",
            "",
        ])
    for ref, spec, class_name in _content_signature_items(contract, "assets"):
        source_ref = spec.get("source_ref")
        if not source_ref:
            continue
        lines.extend([
            f"@asset.implements(Asset.{constant_name(ref)})",
            f"def {safe_id(ref)}(args: {class_name}, ctx: ContentContext) -> AssetResult:",
            f"    raise NotImplementedError({ref!r})",
            "",
        ])
    if lines[-1] != "":
        lines.append("")
    return "\n".join(lines)


def refs_py_projection(contract: dict[str, Any]) -> str:
    groups: dict[str, list[str]] = {
        "Asset": sorted(contract.get("assets", {})),
        "RenderProfile": sorted(contract.get("render_profiles", {})),
        "EntryPoint": sorted(contract["entry_points"]),
        "Operation": sorted(contract["application_actions"]),
        "Text": sorted(contract.get("text_resources", {})),
        "ContentCase": sorted(contract.get("content_cases", {})),
        "Event": sorted(contract["events"]),
        "Fact": sorted(contract.get("facts", {})),
        "Fixture": sorted(contract["fixtures"]),
        "StateMachine": sorted(contract.get("state_machines", {})),
        "RenderAuditCase": sorted(
            f"{state_machine_id}.{state_name}.{case_name}.audit"
            for state_machine_id, state_machine in contract.get("state_machines", {}).items()
            for state_name, state in state_machine.get("view_states", {}).items()
            for case_name in (state.get("render_audit_cases") or {})
        ),
        "TestCase": sorted(contract["test_cases"]),
    }
    for kind, values in sorted(contract["refs"].items()):
        groups[kind.title().replace("_", "")] = values
    lines = ['"""Generated contract references. Do not edit by hand."""', ""]
    for class_name, values in sorted(groups.items()):
        lines.append(f"class {class_name}:")
        if not values:
            lines.append("    pass")
        for value in values:
            lines.append(f"    {constant_name(value)} = {value!r}")
        lines.append("")
    return "\n".join(lines)


def driver_protocol_projection() -> str:
    return '''from __future__ import annotations

from typing import Any, Mapping, Protocol


class SpecDriver(Protocol):
    """Implemented by pytest-bdd harness drivers. Generated; do not edit."""

    def given(self, test_case_id: str, test_case: Mapping[str, Any]) -> None: ...
    def when(self, test_case_id: str, test_case: Mapping[str, Any]) -> None: ...
    def then(self, test_case_id: str, test_case: Mapping[str, Any]) -> None: ...
'''


def bdd_steps_projection() -> str:
    return '''from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from pytest_bdd import given, parsers, then, when

from pyspec_contract.io import read_yaml


@lru_cache(maxsize=1)
def _test_cases() -> dict[str, Any]:
    path = Path(__file__).resolve().parents[1] / "behavior" / "test_cases.yaml"
    return read_yaml(path)["test_cases"]


def _test_case(test_case_id: str) -> dict[str, Any]:
    try:
        return _test_cases()[test_case_id]
    except KeyError as exc:  # pragma: no cover - generated features should prevent this.
        raise AssertionError(f"Unknown spec test case: {test_case_id}") from exc


@given(parsers.parse('spec test case "{test_case_id}" is given'))
def given_spec_test_case(spec_driver, test_case_id: str) -> None:
    spec_driver.given(test_case_id, _test_case(test_case_id))


@when(parsers.parse('spec test case "{test_case_id}" runs when'))
def when_spec_test_case(spec_driver, test_case_id: str) -> None:
    spec_driver.when(test_case_id, _test_case(test_case_id))


@then(parsers.parse('spec test case "{test_case_id}" then holds'))
def then_spec_test_case(spec_driver, test_case_id: str) -> None:
    spec_driver.then(test_case_id, _test_case(test_case_id))
'''


def feature_projections(contract: dict[str, Any]) -> dict[str, str]:
    by_feature_tag: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    for test_case_id, test_case in sorted(contract["test_cases"].items()):
        by_feature_tag[test_case["feature_tag"]].append((test_case_id, test_case))
    files: dict[str, str] = {}
    for feature_tag, test_cases in sorted(by_feature_tag.items()):
        files[g("test_adapters", "pytest_bdd_features", f"{safe_id(feature_tag)}.feature")] = feature_text(feature_tag, test_cases)
    return files


def feature_text(feature_tag: str, test_cases: list[tuple[str, dict[str, Any]]]) -> str:
    lines = [f"Feature: {humanize(feature_tag)}", ""]
    for test_case_id, test_case in test_cases:
        tag_id = safe_id(test_case_id)
        lines.extend([
            f"  @spec @{tag_id}",
            f"  Scenario: {test_case['title']}",
            f"    Given spec test case \"{test_case_id}\" is given",
            f"    When spec test case \"{test_case_id}\" runs when",
            f"    Then spec test case \"{test_case_id}\" then holds",
            "",
        ])
    return "\n".join(lines).rstrip() + "\n"


def components_projection(contract: dict[str, Any]) -> dict[str, Any]:
    components = {"schemas": {}}
    opaque: set[str] = set()
    for rid, data_contract in sorted(contract.get("data_contracts", {}).items()):
        components["schemas"][rid] = object_schema(data_contract["fields"])
    for rid, model in sorted(contract["models"].items()):
        components["schemas"][rid] = object_schema(model["fields"])
        for field in model["fields"].values():
            for ref in referenced_named_types(effective_field_type(field)):
                if ref != rid and ref not in contract["models"] and ref not in contract.get("data_contracts", {}):
                    opaque.add(ref)
    for cap in contract["application_actions"].values():
        outcome_types = [outcome["result"] for outcome in cap["outcomes"].values()]
        for type_name in list(cap["input"].values()) + outcome_types:
            for ref in referenced_named_types(type_name):
                if ref not in components["schemas"] and ref not in contract["models"] and ref not in contract.get("data_contracts", {}):
                    opaque.add(ref)
    for type_name in sorted(opaque):
        components["schemas"].setdefault(type_name, {"type": "object", "additionalProperties": True})
    return components


def object_schema(fields: dict[str, Any]) -> dict[str, Any]:
    return object_to_json_schema(fields)


def type_schema(type_name: Any) -> dict[str, Any]:
    return type_to_json_schema(type_name)


def cwl_type(type_name: Any) -> str | dict[str, Any] | list[Any]:
    return type_to_cwl(type_name)


def base_type(type_name: Any) -> str | None:
    return base_model_name(type_name)


def is_scalar(type_name: Any) -> bool:
    return type_display(type_name) in SCALAR_JSON_SCHEMA



def snake_case(value: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", value).lower()


def safe_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]+", "_", value).strip("_") or "test_case"


def constant_name(value: str) -> str:
    name = re.sub(r"[^A-Za-z0-9]+", "_", value).upper().strip("_")
    if name and name[0].isdigit():
        name = "_" + name
    return name or "EMPTY"


def humanize(value: str) -> str:
    return value.replace(".", " ").replace("_", " ").title()
