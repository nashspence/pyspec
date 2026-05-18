from __future__ import annotations

from typing import Any


STATE_MACHINE_RENDERERS = ("html", "textual")
EXTERNAL_INTERFACE_ADAPTER_KINDS = ("http_api", "cli", "webhook", "scheduled", "worker", "html_route")
EXTERNAL_INTERFACE_TARGET_KINDS = ("command", "query", "state_machine", "workflow", "external_interface")


def external_interface_adapter_pair(entry_or_adapter: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    adapter = entry_or_adapter.get("adapter", entry_or_adapter)
    for kind in EXTERNAL_INTERFACE_ADAPTER_KINDS:
        if kind in adapter:
            value = adapter[kind]
            return kind, value if isinstance(value, dict) else {}
    raise KeyError("external interface adapter must declare http_api, cli, webhook, scheduled, worker, or html_route")


def external_interface_adapter(entry_or_adapter: dict[str, Any], kind: str | None = None) -> dict[str, Any]:
    actual_kind, adapter = external_interface_adapter_pair(entry_or_adapter)
    if kind is not None and actual_kind != kind:
        raise KeyError(f"external interface adapter is {actual_kind}, not {kind}")
    return adapter


def external_interface_target_pair(entry_or_target: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    target = entry_or_target.get("target", entry_or_target)
    for kind in EXTERNAL_INTERFACE_TARGET_KINDS:
        if kind in target:
            value = target[kind]
            if isinstance(value, dict):
                return kind, value
            return kind, {"ref": value}
    raise KeyError("external interface target must declare command, query, state_machine, workflow, or external_interface")


def external_interface_target(entry_or_target: dict[str, Any], kind: str | None = None) -> dict[str, Any]:
    actual_kind, target = external_interface_target_pair(entry_or_target)
    if kind is not None and actual_kind != kind:
        raise KeyError(f"external interface target is {actual_kind}, not {kind}")
    return target


def external_interface_input(entry: dict[str, Any]) -> dict[str, Any]:
    if "adapter" in entry:
        return external_interface_adapter_pair(entry)[1].get("input", {})
    return entry.get("input", {})


def external_interface_responses(entry: dict[str, Any]) -> dict[str, Any]:
    if "adapter" in entry:
        adapter = external_interface_adapter_pair(entry)[1]
        return adapter.get("responses", adapter.get("ingress_responses", {}))
    return entry.get("responses", entry.get("ingress_responses", {}))


def external_interface_path(entry: dict[str, Any]) -> str | None:
    if "adapter" not in entry:
        return entry.get("path")
    kind, adapter = external_interface_adapter_pair(entry)
    if kind in {"http_api", "webhook", "html_route"}:
        return adapter.get("path")
    return None


def external_interface_method(entry: dict[str, Any]) -> str | None:
    if "adapter" not in entry:
        return entry.get("method")
    kind, adapter = external_interface_adapter_pair(entry)
    return adapter.get("method") if kind == "http_api" else None


def external_interface_cli_command(entry: dict[str, Any]) -> str | None:
    if "adapter" not in entry:
        return entry.get("command")
    kind, adapter = external_interface_adapter_pair(entry)
    return adapter.get("cli_command") if kind == "cli" else None


def external_interface_schedule_expression(entry: dict[str, Any]) -> str | None:
    if "adapter" not in entry:
        return entry.get("schedule")
    kind, adapter = external_interface_adapter_pair(entry)
    return adapter.get("schedule_expression") if kind == "scheduled" else None


def external_interface_input_bindings(entry_or_target: dict[str, Any]) -> dict[str, Any]:
    return external_interface_target_pair(entry_or_target)[1].get("input_bindings", {})


def external_interface_workflow_trigger_bindings(entry_or_target: dict[str, Any]) -> dict[str, Any]:
    return external_interface_target_pair(entry_or_target)[1].get("trigger_bindings", {})


def external_interface_target_ref_pair(target: dict[str, Any]) -> tuple[str, str]:
    if "target" in target:
        kind, body = external_interface_target_pair(target)
        if kind == "state_machine":
            return "state_machine", state_machine_target_name(body)
        if kind in {"command", "query"}:
            return kind, operation_target_name(body)
        return kind, workflow_target_name(body) if kind == "workflow" else external_interface_delegate_target_name(body)
    for kind in EXTERNAL_INTERFACE_TARGET_KINDS:
        if kind not in target:
            continue
        value = target[kind]
        if kind == "state_machine":
            return kind, state_machine_target_name(value)
        if kind == "workflow":
            return kind, workflow_target_name(value)
        if kind == "external_interface":
            return kind, external_interface_delegate_target_name(value)
        return kind, operation_target_name(value)
    raise KeyError("external interface target must declare command, query, state_machine, workflow, or external_interface")


def external_interface_state_machine_target(entry_or_target: dict[str, Any]) -> dict[str, str]:
    if "target" in entry_or_target or "state_machine" in entry_or_target:
        value = external_interface_target(entry_or_target, "state_machine")
        result: dict[str, str] = {"name": value["ref"]}
        if "renderer" in value:
            result["renderer"] = value["renderer"]
        return result
    target = entry_or_target.get("target", entry_or_target)
    value = target["state_machine"]
    if isinstance(value, dict):
        return value
    return {"name": value}


def external_interface_state_machine_name(entry_or_target: dict[str, Any]) -> str:
    return external_interface_state_machine_target(entry_or_target)["name"]


def external_interface_state_machine_renderer(entry_or_target: dict[str, Any]) -> str | None:
    return external_interface_state_machine_target(entry_or_target).get("renderer")


def state_machine_target_name(value: Any) -> str:
    if isinstance(value, dict):
        return value.get("ref") or value["name"]
    return value


def operation_target_name(value: Any) -> str:
    if isinstance(value, dict):
        return value.get("ref") or value["name"]
    return value


def external_interface_workflow_target(entry_or_target: dict[str, Any]) -> dict[str, Any]:
    if "target" in entry_or_target or "workflow" in entry_or_target:
        value = external_interface_target(entry_or_target, "workflow")
        result = {"name": value["ref"]}
        if "trigger_bindings" in value:
            result["trigger_bindings"] = value["trigger_bindings"]
        return result
    target = entry_or_target.get("target", entry_or_target)
    value = target["workflow"]
    if isinstance(value, dict):
        return value
    return {"name": value}


def external_interface_workflow_name(entry_or_target: dict[str, Any]) -> str:
    return external_interface_workflow_target(entry_or_target)["name"]


def workflow_target_name(value: Any) -> str:
    if isinstance(value, dict):
        return value.get("ref") or value["name"]
    return value


def external_interface_delegate_target_name(value: Any) -> str:
    if isinstance(value, dict):
        return value.get("ref") or value["name"]
    return value


def external_interface_response_handlers(entry: dict[str, Any]) -> dict[str, Any]:
    if "adapter" in entry:
        kind, adapter = external_interface_adapter_pair(entry)
        if kind == "cli":
            return adapter.get("response_handlers", {})
        return {}
    return entry.get("response_handlers", {})
