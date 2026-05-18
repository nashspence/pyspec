from __future__ import annotations


def dotted(prefix: str, value: str) -> str:
    return f"{prefix}.{value}"


def resource_tail(value: str) -> str:
    for prefix in (
        "command",
        "query",
        "external_interface",
        "domain_event",
        "workflow",
        "state_machine",
        "behavior_scenario",
        "fixture",
        "precondition",
        "assertion",
        "asset",
        "text",
        "content_example",
        "schema",
        "viewport_profile",
        "local_signal",
        "data_refresh_signal",
        "access_policy",
    ):
        marker = f"{prefix}."
        if value.startswith(marker):
            return value[len(marker):]
    return value


def route_ref(state_machine_id: str) -> str:
    return dotted("route", resource_tail(state_machine_id))


def endpoint_ref(operation_ref: str) -> str:
    return dotted("endpoint", resource_tail(operation_ref))


def cli_command_ref(ref: str) -> str:
    return dotted("cli_command", resource_tail(ref))


def workflow_ref(workflow_id: str) -> str:
    if workflow_id.startswith("workflow."):
        return workflow_id
    return dotted("workflow", resource_tail(workflow_id))


def access_policy_ref(operation_ref: str) -> str:
    return dotted("access_policy", resource_tail(operation_ref))


def query_ref(state_machine_subject: str, operation_ref: str, many: bool = False) -> str:
    operation_subject = resource_tail(operation_ref)
    suffix = operation_subject.replace(".", "_") if many else operation_subject.split(".")[-1]
    return f"query.{resource_tail(state_machine_subject)}.{suffix}"


def state_machine_surface_ref(state_machine_id: str, state: str) -> str:
    return f"{state_machine_id}.{state}"


def text_ref(state_machine_id: str, state: str, slot: str) -> str:
    return f"text.{resource_tail(state_machine_id)}.{state}.{slot}"


def asset_ref(state_machine_id: str, state: str, slot: str) -> str:
    return f"asset.{resource_tail(state_machine_id)}.{state}.{slot}"


def screen_ref(state_machine_id: str) -> str:
    return dotted("screen", resource_tail(state_machine_id))
