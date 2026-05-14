from __future__ import annotations

from typing import Any


VIEW_RENDER_SURFACES = ("html", "textual")


def entry_target_pair(target: dict[str, Any]) -> tuple[str, str]:
    kind, value = next(iter(target.items()))
    if kind == "view":
        return kind, view_target_name(value)
    return kind, value


def entry_view_target(entry_or_target: dict[str, Any]) -> dict[str, str]:
    target = entry_or_target.get("target", entry_or_target)
    value = target["view"]
    if isinstance(value, dict):
        return value
    return {"name": value}


def entry_view_name(entry_or_target: dict[str, Any]) -> str:
    return entry_view_target(entry_or_target)["name"]


def entry_view_surface(entry_or_target: dict[str, Any]) -> str | None:
    return entry_view_target(entry_or_target).get("surface")


def view_target_name(value: Any) -> str:
    if isinstance(value, dict):
        return value["name"]
    return value
