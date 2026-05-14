from __future__ import annotations

from typing import Any


FSM_RENDER_SURFACES = ("html", "textual")


def entry_target_pair(target: dict[str, Any]) -> tuple[str, str]:
    kind, value = next(iter(target.items()))
    if kind == "fsm":
        return kind, fsm_target_name(value)
    if kind == "workflow":
        return kind, workflow_target_name(value)
    return kind, value


def entry_fsm_target(entry_or_target: dict[str, Any]) -> dict[str, str]:
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
        return value["name"]
    return value


def entry_workflow_target(entry_or_target: dict[str, Any]) -> dict[str, Any]:
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
        return value["name"]
    return value
