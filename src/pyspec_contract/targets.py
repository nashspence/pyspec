from __future__ import annotations

from typing import Any


FSM_RENDER_SURFACES = ("html", "textual")
ENTRY_POINT_ADAPTER_KINDS = ("http", "cli", "webhook", "scheduled", "worker", "ui")
ENTRY_POINT_TRIGGER_KINDS = ("operation", "state_machine", "workflow")


def entry_point_adapter_pair(entry_or_adapter: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    adapter = entry_or_adapter.get("adapter", entry_or_adapter)
    for kind in ENTRY_POINT_ADAPTER_KINDS:
        if kind in adapter:
            value = adapter[kind]
            return kind, value if isinstance(value, dict) else {}
    raise KeyError("entry point adapter must declare http, cli, webhook, scheduled, worker, or ui")


def entry_point_adapter(entry_or_adapter: dict[str, Any], kind: str | None = None) -> dict[str, Any]:
    actual_kind, adapter = entry_point_adapter_pair(entry_or_adapter)
    if kind is not None and actual_kind != kind:
        raise KeyError(f"entry point adapter is {actual_kind}, not {kind}")
    return adapter


def entry_point_trigger_pair(entry_or_trigger: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    trigger = entry_or_trigger.get("trigger", entry_or_trigger)
    for kind in ENTRY_POINT_TRIGGER_KINDS:
        if kind in trigger:
            value = trigger[kind]
            if isinstance(value, dict):
                return kind, value
            return kind, {"ref": value}
    # Backward-compatible target parsing is intentionally kept here so helper
    # callers can be migrated before every test fixture is rewritten.
    legacy_target = entry_or_trigger.get("target", entry_or_trigger)
    if "operation" in legacy_target:
        value = legacy_target["operation"]
        body = value if isinstance(value, dict) else {"ref": value}
        if "with" in legacy_target:
            body = {**body, "with": legacy_target["with"]}
        return "operation", body
    if "fsm" in legacy_target:
        value = legacy_target["fsm"]
        if isinstance(value, dict):
            body = {"ref": value.get("name"), **{key: val for key, val in value.items() if key != "name"}}
        else:
            body = {"ref": value}
        if "with" in legacy_target:
            body = {**body, "with": legacy_target["with"]}
        return "state_machine", body
    if "workflow" in legacy_target:
        value = legacy_target["workflow"]
        if isinstance(value, dict):
            body = {"ref": value.get("name"), "when": value.get("trigger"), **{key: val for key, val in value.items() if key not in {"name", "trigger"}}}
        else:
            body = {"ref": value}
        return "workflow", body
    raise KeyError("entry point trigger must declare operation, state_machine, or workflow")


def entry_point_trigger(entry_or_trigger: dict[str, Any], kind: str | None = None) -> dict[str, Any]:
    actual_kind, trigger = entry_point_trigger_pair(entry_or_trigger)
    if kind is not None and actual_kind != kind:
        raise KeyError(f"entry point trigger is {actual_kind}, not {kind}")
    return trigger


def entry_point_input(entry: dict[str, Any]) -> dict[str, Any]:
    if "adapter" in entry:
        return entry_point_adapter_pair(entry)[1].get("input", {})
    return entry.get("input", {})


def entry_point_responses(entry: dict[str, Any]) -> dict[str, Any]:
    if "adapter" in entry:
        return entry_point_adapter_pair(entry)[1].get("responses", {})
    return entry.get("responses", {})


def entry_point_path(entry: dict[str, Any]) -> str | None:
    if "adapter" not in entry:
        return entry.get("path")
    kind, adapter = entry_point_adapter_pair(entry)
    if kind in {"http", "webhook", "ui"}:
        return adapter.get("path")
    return None


def entry_point_method(entry: dict[str, Any]) -> str | None:
    if "adapter" not in entry:
        return entry.get("method")
    kind, adapter = entry_point_adapter_pair(entry)
    return adapter.get("method") if kind == "http" else None


def entry_point_cli_command(entry: dict[str, Any]) -> str | None:
    if "adapter" not in entry:
        return entry.get("command")
    kind, adapter = entry_point_adapter_pair(entry)
    return adapter.get("cli_command") if kind == "cli" else None


def entry_point_schedule_expression(entry: dict[str, Any]) -> str | None:
    if "adapter" not in entry:
        return entry.get("schedule")
    kind, adapter = entry_point_adapter_pair(entry)
    return adapter.get("schedule_expression") if kind == "scheduled" else None


def entry_point_bindings(entry_or_trigger: dict[str, Any]) -> dict[str, Any]:
    return entry_point_trigger_pair(entry_or_trigger)[1].get("with", {})


def entry_target_pair(target: dict[str, Any]) -> tuple[str, str]:
    if "trigger" in target:
        kind, body = entry_point_trigger_pair(target)
        if kind == "state_machine":
            return "fsm", fsm_target_name(body)
        return kind, operation_target_name(body) if kind == "operation" else workflow_target_name(body)
    for kind in ("operation", "fsm", "workflow"):
        if kind not in target:
            continue
        value = target[kind]
        if kind == "fsm":
            return kind, fsm_target_name(value)
        if kind == "workflow":
            return kind, workflow_target_name(value)
        return kind, operation_target_name(value)
    raise KeyError("entry target must declare operation, fsm, or workflow")


def entry_fsm_target(entry_or_target: dict[str, Any]) -> dict[str, str]:
    if "trigger" in entry_or_target or "state_machine" in entry_or_target:
        value = entry_point_trigger(entry_or_target, "state_machine")
        result: dict[str, str] = {"name": value["ref"]}
        if "render" in value:
            result["surface"] = value["render"]
        elif "surface" in value:
            result["surface"] = value["surface"]
        return result
    target = entry_or_target.get("target", entry_or_target)
    value = target["fsm"]
    if isinstance(value, dict):
        return value
    return {"name": value}


def entry_fsm_name(entry_or_target: dict[str, Any]) -> str:
    return entry_fsm_target(entry_or_target)["name"]


def entry_fsm_surface(entry_or_target: dict[str, Any]) -> str | None:
    return entry_fsm_target(entry_or_target).get("surface")


def fsm_target_name(value: Any) -> str:
    if isinstance(value, dict):
        return value.get("ref") or value["name"]
    return value


def operation_target_name(value: Any) -> str:
    if isinstance(value, dict):
        return value.get("ref") or value["name"]
    return value


def entry_workflow_target(entry_or_target: dict[str, Any]) -> dict[str, Any]:
    if "trigger" in entry_or_target or "workflow" in entry_or_target:
        value = entry_point_trigger(entry_or_target, "workflow")
        result = {"name": value["ref"]}
        if "when" in value:
            result["trigger"] = value["when"]
        elif "trigger" in value:
            result["trigger"] = value["trigger"]
        return result
    target = entry_or_target.get("target", entry_or_target)
    value = target["workflow"]
    if isinstance(value, dict):
        return value
    return {"name": value}


def entry_workflow_name(entry_or_target: dict[str, Any]) -> str:
    return entry_workflow_target(entry_or_target)["name"]


def entry_workflow_trigger(entry_or_target: dict[str, Any]) -> dict[str, str] | None:
    return entry_workflow_target(entry_or_target).get("trigger")


def workflow_target_name(value: Any) -> str:
    if isinstance(value, dict):
        return value.get("ref") or value["name"]
    return value
