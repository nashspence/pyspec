from __future__ import annotations


def dotted(prefix: str, value: str) -> str:
    return f"{prefix}.{value}"


def resource_tail(value: str) -> str:
    for prefix in (
        "operation",
        "entry_point",
        "event",
        "workflow",
        "state_machine",
        "scenario",
        "fixture",
        "fact",
        "asset",
        "text",
        "content",
        "feature",
        "message",
    ):
        marker = f"{prefix}."
        if value.startswith(marker):
            return value[len(marker):]
    return value


def route_ref(state_machine_id: str) -> str:
    return dotted("route", resource_tail(state_machine_id))


def endpoint_ref(operation_id: str) -> str:
    return dotted("endpoint", resource_tail(operation_id))


def command_ref(ref: str) -> str:
    return dotted("command", resource_tail(ref))


def workflow_ref(workflow_id: str) -> str:
    if workflow_id.startswith("workflow."):
        return workflow_id
    return dotted("workflow", resource_tail(workflow_id))


def policy_ref(operation_id: str) -> str:
    return dotted("policy", resource_tail(operation_id))


def query_ref(state_machine_subject: str, operation_id: str, many: bool = False) -> str:
    operation_subject = resource_tail(operation_id)
    suffix = operation_subject.replace(".", "_") if many else operation_subject.split(".")[-1]
    return f"query.{resource_tail(state_machine_subject)}.{suffix}"


def fsm_ref(state_machine_id: str, state: str) -> str:
    return f"{state_machine_id}.{state}"


def copy_ref(state_machine_id: str, state: str, slot: str) -> str:
    return f"text.{resource_tail(state_machine_id)}.{state}.{slot}"


def asset_ref(state_machine_id: str, state: str, slot: str) -> str:
    return f"asset.{resource_tail(state_machine_id)}.{state}.{slot}"


def screen_ref(state_machine_id: str) -> str:
    return dotted("screen", resource_tail(state_machine_id))
