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


def html_route_ref(state_machine_id: str) -> str:
    return dotted("html_route", resource_tail(state_machine_id))


def http_operation_ref(command_query_ref: str) -> str:
    return dotted("http_operation", resource_tail(command_query_ref))


def cli_command_ref(ref: str) -> str:
    return dotted("cli_command", resource_tail(ref))


def workflow_ref(workflow_id: str) -> str:
    if workflow_id.startswith("workflow."):
        return workflow_id
    return dotted("workflow", resource_tail(workflow_id))


def access_policy_ref(command_query_ref: str) -> str:
    return dotted("access_policy", resource_tail(command_query_ref))


def query_ref(state_machine_subject: str, command_query_ref: str, many: bool = False) -> str:
    behavior_subject = resource_tail(command_query_ref)
    suffix = behavior_subject.replace(".", "_") if many else behavior_subject.split(".")[-1]
    return f"query.{resource_tail(state_machine_subject)}.{suffix}"


def state_machine_surface_ref(state_machine_id: str, state: str) -> str:
    return f"{state_machine_id}.{state}"


def text_ref(state_machine_id: str, state: str, slot: str) -> str:
    return f"text.{resource_tail(state_machine_id)}.{state}.{slot}"


def asset_ref(state_machine_id: str, state: str, slot: str) -> str:
    return f"asset.{resource_tail(state_machine_id)}.{state}.{slot}"


def renderer_screen_ref(state_machine_id: str) -> str:
    return dotted("renderer_screen", resource_tail(state_machine_id))
