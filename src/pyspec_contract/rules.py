from __future__ import annotations


def dotted(prefix: str, value: str) -> str:
    return f"{prefix}.{value}"


def route_ref(fsm_id: str) -> str:
    return dotted("route", fsm_id)


def endpoint_ref(capability_id: str) -> str:
    return dotted("endpoint", capability_id)


def command_ref(capability_id: str) -> str:
    return dotted("command", capability_id)


def workflow_ref(workflow_id: str) -> str:
    return dotted("workflow", workflow_id)


def policy_ref(capability_id: str) -> str:
    return dotted("policy", capability_id)


def query_ref(fsm_id: str, capability_id: str, many: bool = False) -> str:
    suffix = capability_id.replace(".", "_") if many else capability_id.split(".")[-1]
    return f"query.{fsm_id}.{suffix}"


def fsm_ref(fsm_id: str, state: str) -> str:
    return f"fsm.{fsm_id}.{state}"


def copy_ref(fsm_id: str, state: str, slot: str) -> str:
    return f"copy.{fsm_id}.{state}.{slot}"


def asset_ref(fsm_id: str, state: str, slot: str) -> str:
    return f"asset.{fsm_id}.{state}.{slot}"


def screen_ref(fsm_id: str) -> str:
    return dotted("screen", fsm_id)
