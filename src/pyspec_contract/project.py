from __future__ import annotations

import html
import re
from collections import defaultdict
from typing import Any, Iterable

from .agent_prompts import agent_prompt_paths, agent_prompt_projection_files
from .layout import layout_html, layout_textual, layout_textual_containers
from .paths import generated_relative as g
from .targets import entry_fsm_name


SCALAR_JSON_SCHEMA: dict[str, dict[str, Any]] = {
    "ID": {"type": "string"},
    "Text": {"type": "string"},
    "Markdown": {"type": "string"},
    "Date": {"type": "string", "format": "date"},
    "Timestamp": {"type": "string", "format": "date-time"},
    "Bool": {"type": "boolean"},
    "Int": {"type": "integer"},
    "Decimal": {"type": "number"},
    "JSON": {"type": "object", "additionalProperties": True},
}




def projection_paths(contract: dict[str, Any]) -> list[str]:
    paths = [
        g("__init__.py"),
        g("test_adapters", "__init__.py"),
        g("content_resolvers", "__init__.py"),
        g("test_adapters", "python_refs.py"),
        g("behavior", "fixtures.yaml"),
        g("behavior", "scenarios.yaml"),
        g("test_adapters", "driver_protocol.py"),
        g("test_adapters", "pytest_bdd_steps.py"),
    ]
    if _has_api(contract):
        paths.append(g("product_interfaces", "http.openapi.yaml"))
    if _has_asyncapi(contract):
        paths.append(g("product_interfaces", "events.asyncapi.yaml"))
    if _has_web_routes(contract):
        paths.append(g("product_interfaces", "web.routes.json"))
    if _has_ui(contract):
        paths.append(g("product_interfaces", "web.fsms.json"))
    if _has_textual_ui(contract):
        paths.append(g("product_interfaces", "textual.projection.py"))
    if _has_workflow(contract):
        paths.append(g("product_interfaces", "workflow.cwl.yaml"))
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
    if _has_web_routes(contract):
        yield g("product_interfaces", "web.routes.json"), routes_projection(contract), "json"
    if _has_ui(contract):
        yield g("product_interfaces", "web.fsms.json"), fsms_projection(contract), "json"
    if _has_textual_ui(contract):
        yield g("product_interfaces", "textual.projection.py"), textual_contract_projection(contract), "text"
    if _has_workflow(contract):
        yield g("product_interfaces", "workflow.cwl.yaml"), workflows_projection(contract), "yaml"
    yield g("behavior", "fixtures.yaml"), fixtures_projection(contract), "yaml"
    yield g("behavior", "scenarios.yaml"), scenarios_projection(contract), "yaml"
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


def _entries_with_surface(contract: dict[str, Any], *surfaces: str) -> list[dict[str, Any]]:
    wanted = set(surfaces)
    return [entry for entry in contract.get("entries", {}).values() if entry.get("surface") in wanted]


def _has_api(contract: dict[str, Any]) -> bool:
    return bool(_entries_with_surface(contract, "api"))


def _has_asyncapi(contract: dict[str, Any]) -> bool:
    return bool(contract.get("events")) and (bool(_entries_with_surface(contract, "webhook", "worker")) or any("event" in wf.get("trigger", {}) for wf in contract.get("workflows", {}).values()))


def _has_web_routes(contract: dict[str, Any]) -> bool:
    return bool(_entries_with_surface(contract, "web"))


def _has_workflow(contract: dict[str, Any]) -> bool:
    return bool(contract.get("workflows")) or bool(_entries_with_surface(contract, "cli", "worker", "schedule"))


def _has_ui(contract: dict[str, Any]) -> bool:
    return bool(contract.get("fsms"))


def _state_has_textual_presentation(state: dict[str, Any]) -> bool:
    return "textual" in (state.get("presentation") or {})


def _has_textual_ui(contract: dict[str, Any]) -> bool:
    if any("textual" in case.get("surfaces", []) for fsm in contract.get("fsms", {}).values() for state in fsm.get("states", {}).values() for case in (state.get("audit") or {}).values()):
        return True
    for owner in contract.get("fsms", {}).values():
        if any(_state_has_textual_presentation(state) for state in owner.get("states", {}).values()):
            return True
        if any("textual" in (state.get("layout") or {}) for state in owner.get("states", {}).values()):
            return True
    return False




def _has_content(contract: dict[str, Any]) -> bool:
    return bool(contract.get("copies") or contract.get("assets") or contract.get("content_cases"))


def openapi_projection(contract: dict[str, Any]) -> dict[str, Any]:
    paths: dict[str, Any] = {}
    for entry_id, entry in sorted(contract["entries"].items()):
        if entry["surface"] != "api":
            continue
        cap_id = entry["target"]["capability"]
        cap = contract["capabilities"][cap_id]
        entry_input = entry.get("input", {})
        params = entry_input.get("params", {})
        body_fields = entry_input.get("body", {})
        responses = {}
        for outcome_id, response in sorted(entry["responses"].items()):
            response_status = str(response["status"])
            body_type = response["body"]["type"]
            responses[response_status] = {
                "description": humanize(outcome_id),
                "content": {"application/json": {"schema": type_schema(body_type)}},
            }
        op: dict[str, Any] = {
            "operationId": cap_id,
            "x-entry": entry_id,
            "x-capability": cap_id,
            "x-policy": cap["policy"],
            "parameters": [
                {"name": name, "in": "path", "required": True, "schema": type_schema(type_name)}
                for name, type_name in sorted(params.items())
            ],
            "responses": responses,
        }
        if body_fields and entry["method"].lower() not in {"get", "delete"}:
            op["requestBody"] = {
                "required": True,
                "content": {"application/json": {"schema": object_schema(body_fields)}}
            }
        paths.setdefault(entry["path"], {})[entry["method"].lower()] = op

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
            "payload": type_schema(event["payload"]),
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


def routes_projection(contract: dict[str, Any]) -> dict[str, Any]:
    return {
        "project": contract["project"],
        "routes": [
            {
                "id": entry["route"],
                "entry": entry_id,
                "path": entry["path"],
                "params": entry.get("input", {}).get("params", {}),
                "fsm": entry_fsm_name(entry),
            }
            for entry_id, entry in sorted(contract["entries"].items())
            if entry["surface"] == "web"
        ],
    }


def fsms_projection(contract: dict[str, Any]) -> dict[str, Any]:
    fsms: list[dict[str, Any]] = []
    for fsm_id, fsm in sorted(contract.get("fsms", {}).items()):
        for state_name, state in sorted(fsm.get("states", {}).items()):
            item = fsm_projection_item("fsm", fsm_id, state_name, state)
            item["fsm"] = {
                "initial": fsm["initial"],
                "transitions": fsm.get("transitions", []),
                "context": fsm.get("context", {}),
            }
            fsms.append(item)
    compositions = []
    for fsm_id, fsm in sorted(contract["fsms"].items()):
        for state_name, state in sorted(fsm.get("states", {}).items()):
            if state.get("mounts"):
                compositions.append({
                    "id": f"{fsm_id}.{state_name}",
                    "fsm": fsm_id,
                    "state": state_name,
                    "context": fsm.get("context", {}),
                    "layout": state.get("layout", {}),
                    "mounts": state.get("mounts", []),
                    "sync": state.get("sync", []),
                })
    return {"project": contract["project"], "fsms": fsms, "compositions": compositions}


def fsm_projection_item(owner_kind: str, owner_id: str, state_name: str, state: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": state["surface"],
        "owner_kind": owner_kind,
        "owner": owner_id,
        "state": state_name,
        "data": state.get("data", []),
        "slots": {
            "copy": state["copy"],
            "assets": state["assets"],
            "fields": state.get("fields", []),
            "actions": state["actions"],
        },
        "presentation": state.get("presentation", {}),
    }


def fsm_styles_projection(
    contract: dict[str, Any],
    *,
    surface_ids: Iterable[str] | None = None,
    composition_ids: Iterable[str] | None = None,
) -> str:
    wanted_surfaces = set(surface_ids) if surface_ids is not None else None
    wanted_compositions = set(composition_ids) if composition_ids is not None else None
    lines = [
        "/* Generated FSM surface style contract. Do not edit. */",
        ":root {",
        "  --contract-space: 1rem;",
        "  --contract-fsm-surface-max-width: 48rem;",
        "}",
        ".contract-fsm-surface {",
        "  display: grid;",
        "  gap: var(--contract-space);",
        "  max-width: var(--contract-fsm-surface-max-width);",
        "}",
    ]
    fsms = fsms_projection(contract)["fsms"]
    for fsm in fsms:
        if wanted_surfaces is not None and fsm["id"] not in wanted_surfaces:
            continue
        css_contract = (fsm.get("presentation") or {}).get("css") or {}
        grouped: dict[str, dict[str, str]] = {}
        root_selector = css_selector(fsm, "root")
        for name, value in sorted((css_contract.get("tokens") or {}).items()):
            grouped.setdefault(root_selector, {})["--" + name.replace("_", "-")] = value
        for rule in css_contract.get("rules", []):
            selector = css_selector(fsm, rule["selector"])
            declarations = grouped.setdefault(selector, {})
            for name, value in sorted(rule["declarations"].items()):
                declarations[name] = css_value(value)
        for selector, declarations in grouped.items():
            lines.append(f"{selector} {{")
            for name, value in declarations.items():
                lines.append(f"  {name}: {value};")
            lines.append("}")
    for composition in fsms_projection(contract)["compositions"]:
        if wanted_compositions is not None and composition["id"] not in wanted_compositions:
            continue
        css_contract = layout_html(composition.get("layout") or {}).get("css") or {}
        grouped: dict[str, dict[str, str]] = {}
        root_selector = composition_css_selector(composition, "root")
        for name, value in sorted((css_contract.get("tokens") or {}).items()):
            grouped.setdefault(root_selector, {})["--" + name.replace("_", "-")] = value
        for rule in css_contract.get("rules", []):
            selector = composition_css_selector(composition, rule["selector"])
            declarations = grouped.setdefault(selector, {})
            for name, value in sorted(rule["declarations"].items()):
                declarations[name] = css_value(value)
        for selector, declarations in grouped.items():
            lines.append(f"{selector} {{")
            for name, value in declarations.items():
                lines.append(f"  {name}: {value};")
            lines.append("}")
    return "\n".join(lines) + "\n"


def textual_contract_projection(contract: dict[str, Any]) -> str:
    projection = fsms_projection(contract)
    fsms = projection["fsms"]
    compositions = projection["compositions"]
    screen_entries = textual_screen_entries(contract, fsms, compositions)
    return f'''from __future__ import annotations

# Generated Textual projection. Do not edit by hand.
# The PM contract owns FSMs/states/actions/widgets/TCSS; a real Textual app imports this file
# and renders FSM state surfaces by id instead of inventing screens, widgets, or action keys.

PROJECT = {contract["project"]!r}
SCREENS = {screen_entries!r}
FSMS = {fsms!r}
COMPOSITIONS = {compositions!r}
TCSS = {textual_tcss(fsms, compositions)!r}


def fsm_surface(surface_id: str) -> dict:
    for item in FSMS:
        if item["id"] == surface_id:
            return item
    raise KeyError(surface_id)


def composition(composition_id: str) -> dict:
    for item in COMPOSITIONS:
        if item["id"] == composition_id:
            return item
    raise KeyError(composition_id)


def textual_css() -> str:
    return TCSS


def compose_contract_fsm(surface_id: str) -> list[tuple[str, str]]:
    item = fsm_surface(surface_id)
    textual = (item.get("presentation") or {{}}).get("textual") or {{}}
    widgets = textual.get("widgets") or []
    if widgets:
        return [(widget["kind"], widget_label(widget)) for widget in widgets]
    slots = item["slots"]
    result: list[tuple[str, str]] = []
    result.extend(("Static", key) for key in slots["copy"])
    result.extend(("Static", key) for key in slots["assets"])
    result.extend(("Static", key) for key in slots.get("fields", []))
    result.extend(("Button", action) for action in slots["actions"])
    return result


def compose_contract_composition(composition_id: str) -> list[tuple[str, str, str]]:
    item = composition(composition_id)
    return [(mount["region"], mount["id"], mount["fsm"]) for mount in item["mounts"]]


def widget_label(widget: dict) -> str:
    bind = widget["bind"]
    if "copy" in bind:
        return bind["copy"]
    if "asset" in bind:
        return bind["asset"]
    if "action" in bind:
        return bind["action"]
    if "field" in bind:
        return bind["field"]
    return bind.get("literal", widget["id"])
'''


def textual_screen_entries(
    contract: dict[str, Any],
    fsms: list[dict[str, Any]] | None = None,
    compositions: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    projection = None if fsms is not None and compositions is not None else fsms_projection(contract)
    fsms = fsms if fsms is not None else projection["fsms"]  # type: ignore[index]
    compositions = compositions if compositions is not None else projection["compositions"]  # type: ignore[index]
    fsms_by_owner: dict[str, list[dict[str, Any]]] = {}
    for fsm in fsms:
        fsms_by_owner.setdefault(fsm["owner"], []).append(fsm)
    compositions_by_fsm = {composition["id"]: composition for composition in compositions}
    screens = []
    for fsm_id, fsm in sorted(contract["fsms"].items()):
        screen_class = _textual_screen_class(fsm_id, fsm, fsms_by_owner, compositions_by_fsm)
        if screen_class is None:
            continue
        screens.append({
            "id": f"screen.{fsm_id}",
            "fsm": fsm_id,
            "screen_class": screen_class,
        })
    return screens


def _textual_screen_class(
    fsm_id: str,
    fsm: dict[str, Any],
    fsms_by_owner: dict[str, list[dict[str, Any]]],
    compositions_by_fsm: dict[str, dict[str, Any]],
) -> str | None:
    for state_name, state in sorted(fsm.get("states", {}).items()):
        textual = layout_textual(state.get("layout") or {})
        if textual:
            return textual.get("screen_class") or "ComposedContractScreen"
    for surface in fsms_by_owner.get(fsm_id, []):
        textual = (surface.get("presentation") or {}).get("textual") or {}
        if textual.get("screen_class"):
            return textual["screen_class"]
        if textual:
            return "Screen"
    if any("textual" in (state.get("presentation") or {}) for state in fsm.get("states", {}).values()):
        return "Screen"
    return None


def default_html_slots(fsm: dict[str, Any]) -> list[dict[str, Any]]:
    slots: list[dict[str, Any]] = []
    for copy_ref in fsm["slots"]["copy"]:
        slot = copy_ref.rsplit(".", 1)[-1]
        element = "h2" if slot == "title" else "p"
        item: dict[str, Any] = {"kind": "copy", "slot": slot, "element": element}
        if slot == "title":
            item.update({"role": "heading", "level": 2})
        slots.append(item)
    for asset_ref in fsm["slots"]["assets"]:
        slots.append({"kind": "asset", "slot": asset_ref.rsplit(".", 1)[-1], "element": "img"})
    for field in fsm["slots"].get("fields", []):
        slots.append({"kind": "field", "slot": field, "element": "p"})
    for action in fsm["slots"]["actions"]:
        slots.append({"kind": "action", "ref": action, "element": "button"})
    return slots


def css_selector(fsm: dict[str, Any], selector: str) -> str:
    root = f'[data-contract-fsm-surface="{fsm["id"]}"]'
    if selector in {"root", "screen"}:
        return root
    if selector.startswith("slot."):
        slot = selector[len("slot."):]
        return f'{root} [data-contract-slot="{slot}"]'
    if selector.startswith("action."):
        action = selector[len("action."):]
        return f'{root} [data-action="{action}"]'
    return root


def composition_css_selector(composition: dict[str, Any], selector: str) -> str:
    root = f'[data-contract-composition="{composition["id"]}"]'
    if selector in {"root", "screen"}:
        return root
    if selector.startswith("region."):
        region = selector[len("region."):]
        return f'{root} [data-layout-region="{region}"]'
    if selector.startswith("mount."):
        mount = selector[len("mount."):]
        return f'{root} [data-fsm-mount="{mount}"]'
    return root


def textual_tcss(fsms: list[dict[str, Any]], compositions: list[dict[str, Any]] | None = None) -> str:
    grouped: dict[str, dict[str, str]] = {
        "Screen": {"layout": "vertical"},
        ".contract-fsm-surface": {"padding": "1"},
    }
    for fsm in fsms:
        textual = (fsm.get("presentation") or {}).get("textual") or {}
        for rule in textual.get("tcss", {}).get("rules", []):
            selector = tcss_selector(fsm, rule["selector"])
            declarations = grouped.setdefault(selector, {})
            for name, value in sorted(rule["declarations"].items()):
                declarations[name] = css_value(value)
    for composition in compositions or []:
        textual = layout_textual(composition.get("layout") or {})
        for rule in (textual.get("tcss") or {}).get("rules", []):
            selector = composition_tcss_selector(composition, rule["selector"])
            declarations = grouped.setdefault(selector, {})
            for name, value in sorted(rule["declarations"].items()):
                declarations[name] = css_value(value)
    lines = ["/* Generated Textual CSS contract. Do not edit. */"]
    for selector, declarations in grouped.items():
        lines.append(f"{selector} {{")
        for name, value in declarations.items():
            lines.append(f"  {name}: {value};")
        lines.append("}")
    return "\n".join(lines) + "\n"


def tcss_selector(fsm: dict[str, Any], selector: str) -> str:
    if selector in {"root", "screen"}:
        return "Screen"
    textual = (fsm.get("presentation") or {}).get("textual") or {}
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


def composition_tcss_selector(composition: dict[str, Any], selector: str) -> str:
    if selector in {"root", "screen"}:
        textual = layout_textual(composition.get("layout") or {})
        return textual.get("screen_class") or "Screen"
    if selector.startswith("region."):
        region = selector[len("region."):]
        container = layout_textual_containers(composition.get("layout") or {}).get(region, {})
        return "#" + safe_id(container.get("id", region))
    if selector.startswith("mount."):
        return "#" + safe_id(selector[len("mount."):])
    return selector


def css_value(value: str) -> str:
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
            cap = contract["capabilities"][step["capability"]]
            steps[step["id"]] = {
                "run": f"#{safe_id(step['capability'])}",
                "in": {name: "event" for name in sorted(cap["input"])},
                "out": [],
            }
        graph.append({
            "id": f"#{safe_id(workflow_id)}",
            "class": "Workflow",
            "label": workflow_id,
            "doc": f"contract workflow {workflow_id}; trigger={workflow['trigger']}; ref={workflow['ref']}",
            "inputs": {"event": {"type": "Any"}},
            "outputs": {},
            "steps": steps,
        })
    for cap_id, cap in sorted(contract["capabilities"].items()):
        graph.append({
            "id": f"#{safe_id(cap_id)}",
            "class": "CommandLineTool",
            "label": cap_id,
            "baseCommand": ["contract-capability", cap_id],
            "inputs": {name: {"type": cwl_type(type_name)} for name, type_name in sorted(cap["input"].items())},
            "outputs": {
                outcome_id: {"type": cwl_type(outcome["result"])}
                for outcome_id, outcome in sorted(cap["outcomes"].items())
            },
        })
    return {"cwlVersion": "v1.2", "$graph": graph}


def fixtures_projection(contract: dict[str, Any]) -> dict[str, Any]:
    return {"project": contract["project"], "fixtures": contract["fixtures"]}


def scenarios_projection(contract: dict[str, Any]) -> dict[str, Any]:
    return {"project": contract["project"], "scenarios": contract["scenarios"]}


def content_cases_projection(contract: dict[str, Any]) -> dict[str, Any]:
    return {"project": contract["project"], "content_cases": contract.get("content_cases", {})}


def python_type_for_contract_type(type_name: str) -> str:
    if type_name in {"ID", "Text", "Markdown", "Date", "Timestamp"}:
        return "str"
    if type_name == "Bool":
        return "bool"
    if type_name == "Int":
        return "int"
    if type_name == "Decimal":
        return "float"
    if type_name == "JSON":
        return "object"
    if type_name.startswith("list["):
        return "list[object]"
    return "str"


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
        '"""Generated content resolver signatures. Do not edit by hand."""',
        "from __future__ import annotations",
        "",
        "from dataclasses import dataclass",
        "from typing import Any",
        "",
        "from pyspec_contract.content import AssetResult, ContentContext",
        "",
    ]
    copy_classes: dict[str, str] = {}
    asset_classes: dict[str, str] = {}
    for section, mapping_name, store in [("copies", "COPY_SIGNATURES", copy_classes), ("assets", "ASSET_SIGNATURES", asset_classes)]:
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
    lines.append(f"COPY_SIGNATURES = { {ref: {'args': spec.get('args', {}), 'resolver': spec.get('resolver'), 'arg_class': copy_classes[ref]} for ref, spec, _ in _content_signature_items(contract, 'copies')}!r}")
    lines.append(f"ASSET_SIGNATURES = { {ref: {'args': spec.get('args', {}), 'resolver': spec.get('resolver'), 'arg_class': asset_classes[ref]} for ref, spec, _ in _content_signature_items(contract, 'assets')}!r}")
    lines.append(f"COPY_ARG_CLASSES = {{{', '.join(f'{ref!r}: {cls}' for ref, cls in copy_classes.items())}}}")
    lines.append(f"ASSET_ARG_CLASSES = {{{', '.join(f'{ref!r}: {cls}' for ref, cls in asset_classes.items())}}}")
    lines.append("")
    return "\n".join(lines)


def content_stubs_projection(contract: dict[str, Any]) -> str:
    lines = [
        '"""Generated content resolver stubs. Do not edit; copy needed functions into spec.py."""',
        "from __future__ import annotations",
        "",
        "from pyspec_contract.content import AssetResult, ContentContext, asset, copy",
        "from generated.content_resolvers.signatures import *  # generated arg classes",
        "from generated.test_adapters.python_refs import Asset, Copy",
        "",
    ]
    for ref, spec, class_name in _content_signature_items(contract, "copies"):
        resolver = spec.get("resolver")
        if not resolver:
            continue
        lines.extend([
            f"@copy.implements(Copy.{constant_name(ref)})",
            f"def {safe_id(ref)}(args: {class_name}, ctx: ContentContext) -> str:",
            f"    raise NotImplementedError({ref!r})",
            "",
        ])
    for ref, spec, class_name in _content_signature_items(contract, "assets"):
        resolver = spec.get("resolver")
        if not resolver:
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
        "AuditProfile": sorted(contract.get("audit_profiles", {})),
        "Capability": sorted(contract["capabilities"]),
        "Copy": sorted(contract.get("copies", {})),
        "ContentCase": sorted(contract.get("content_cases", {})),
        "Entry": sorted(contract["entries"]),
        "Event": sorted(contract["events"]),
        "Fact": sorted(contract.get("facts", {})),
        "Fixture": sorted(contract["fixtures"]),
        "FSM": sorted(contract.get("fsms", {})),
        "AuditCase": sorted(
            f"{fsm_id}.{state_name}.{case_name}.audit"
            for fsm_id, fsm in contract.get("fsms", {}).items()
            for state_name, state in fsm.get("states", {}).items()
            for case_name in (state.get("audit") or {})
        ),
        "Scenario": sorted(contract["scenarios"]),
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

    def arrange(self, scenario_id: str, scenario: Mapping[str, Any]) -> None: ...
    def execute(self, scenario_id: str, scenario: Mapping[str, Any]) -> None: ...
    def assert_obligations(self, scenario_id: str, scenario: Mapping[str, Any]) -> None: ...
'''


def bdd_steps_projection() -> str:
    return '''from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from pytest_bdd import given, parsers, then, when

from pyspec_contract.io import read_yaml


@lru_cache(maxsize=1)
def _scenarios() -> dict[str, Any]:
    path = Path(__file__).resolve().parents[1] / "behavior" / "scenarios.yaml"
    return read_yaml(path)["scenarios"]


def _scenario(scenario_id: str) -> dict[str, Any]:
    try:
        return _scenarios()[scenario_id]
    except KeyError as exc:  # pragma: no cover - generated features should prevent this.
        raise AssertionError(f"Unknown spec scenario: {scenario_id}") from exc


@given(parsers.parse('spec scenario "{scenario_id}" is arranged'))
def arrange_spec_scenario(spec_driver, scenario_id: str) -> None:
    spec_driver.arrange(scenario_id, _scenario(scenario_id))


@when(parsers.parse('spec scenario "{scenario_id}" is executed'))
def execute_spec_scenario(spec_driver, scenario_id: str) -> None:
    spec_driver.execute(scenario_id, _scenario(scenario_id))


@then(parsers.parse('spec scenario "{scenario_id}" obligations hold'))
def assert_spec_scenario(spec_driver, scenario_id: str) -> None:
    spec_driver.assert_obligations(scenario_id, _scenario(scenario_id))
'''


def feature_projections(contract: dict[str, Any]) -> dict[str, str]:
    by_feature: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    for scenario_id, scenario in sorted(contract["scenarios"].items()):
        by_feature[scenario["feature"]].append((scenario_id, scenario))
    files: dict[str, str] = {}
    for feature_id, scenarios in sorted(by_feature.items()):
        files[g("test_adapters", "pytest_bdd_features", f"{safe_id(feature_id)}.feature")] = feature_text(feature_id, scenarios)
    return files


def feature_text(feature_id: str, scenarios: list[tuple[str, dict[str, Any]]]) -> str:
    lines = [f"Feature: {humanize(feature_id)}", ""]
    for scenario_id, scenario in scenarios:
        tag_id = safe_id(scenario_id)
        lines.extend([
            f"  @spec @{tag_id}",
            f"  Scenario: {scenario['title']}",
            f"    Given spec scenario \"{scenario_id}\" is arranged",
            f"    When spec scenario \"{scenario_id}\" is executed",
            f"    Then spec scenario \"{scenario_id}\" obligations hold",
            "",
        ])
    return "\n".join(lines).rstrip() + "\n"


def components_projection(contract: dict[str, Any]) -> dict[str, Any]:
    components = {"schemas": {}}
    opaque: set[str] = set()
    enum_types: dict[str, list[str]] = {}
    for rid, model in sorted(contract["models"].items()):
        components["schemas"][rid] = object_schema(model["fields"])
        lifecycle = model.get("lifecycle")
        if lifecycle:
            enum_type = model["fields"].get(lifecycle["field"])
            if enum_type:
                enum_types[enum_type] = lifecycle["states"]
        for type_name in model["fields"].values():
            base = base_type(type_name)
            if base != rid and not is_scalar(base):
                opaque.add(base)
    for type_name, states in sorted(enum_types.items()):
        components["schemas"][type_name] = {"type": "string", "enum": states}
        opaque.discard(type_name)
    for cap in contract["capabilities"].values():
        outcome_types = [outcome["result"] for outcome in cap["outcomes"].values()]
        for type_name in list(cap["input"].values()) + outcome_types:
            base = base_type(type_name)
            if base and base not in components["schemas"] and not is_scalar(base):
                opaque.add(base)
    for type_name in sorted(opaque):
        components["schemas"].setdefault(type_name, {"type": "object", "additionalProperties": True})
    return components


def object_schema(fields: dict[str, str]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": sorted(fields),
        "properties": {name: type_schema(type_name) for name, type_name in sorted(fields.items())},
    }


def type_schema(type_name: str) -> dict[str, Any]:
    if type_name.startswith("list[") and type_name.endswith("]"):
        return {"type": "array", "items": type_schema(type_name[5:-1])}
    if type_name in SCALAR_JSON_SCHEMA:
        return dict(SCALAR_JSON_SCHEMA[type_name])
    return {"$ref": f"#/components/schemas/{type_name}"}


def cwl_type(type_name: str) -> str | dict[str, Any]:
    if type_name.startswith("list[") and type_name.endswith("]"):
        return {"type": "array", "items": cwl_type(type_name[5:-1])}
    if type_name in {"ID", "Text", "Markdown", "Date", "Timestamp"}:
        return "string"
    if type_name == "Bool":
        return "boolean"
    if type_name == "Int":
        return "int"
    if type_name == "Decimal":
        return "double"
    return "Any"


def base_type(type_name: str) -> str:
    if type_name.startswith("list[") and type_name.endswith("]"):
        return type_name[5:-1]
    return type_name


def is_scalar(type_name: str) -> bool:
    return type_name in SCALAR_JSON_SCHEMA



def snake_case(value: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", value).lower()


def safe_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]+", "_", value).strip("_") or "scenario"


def constant_name(value: str) -> str:
    name = re.sub(r"[^A-Za-z0-9]+", "_", value).upper().strip("_")
    if name and name[0].isdigit():
        name = "_" + name
    return name or "EMPTY"


def humanize(value: str) -> str:
    return value.replace(".", " ").replace("_", " ").title()
