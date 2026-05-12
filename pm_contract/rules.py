from __future__ import annotations


def dotted(prefix: str, value: str) -> str:
    return f"{prefix}.{value}"


def route_ref(view_id: str) -> str:
    return dotted("route", view_id)


def endpoint_ref(capability_id: str) -> str:
    return dotted("endpoint", capability_id)


def command_ref(capability_id: str) -> str:
    return dotted("command", capability_id)


def workflow_ref(workflow_id: str) -> str:
    return dotted("workflow", workflow_id)


def policy_ref(capability_id: str) -> str:
    return dotted("policy", capability_id)


def query_ref(view_id: str, capability_id: str, many: bool = False) -> str:
    suffix = capability_id.replace(".", "_") if many else capability_id.split(".")[-1]
    return f"query.{view_id}.{suffix}"


def panel_ref(view_id: str, state: str) -> str:
    return f"panel.{view_id}.{state}"


def copy_ref(view_id: str, state: str, slot: str) -> str:
    return f"copy.{view_id}.{state}.{slot}"


def asset_ref(view_id: str, state: str, slot: str) -> str:
    return f"asset.{view_id}.{state}.{slot}"


def screen_ref(view_id: str) -> str:
    return dotted("screen", view_id)
