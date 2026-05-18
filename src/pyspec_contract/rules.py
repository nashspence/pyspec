from __future__ import annotations


def dotted(prefix: str, value: str) -> str:
    return f"{prefix}.{value}"


def resource_tail(value: str) -> str:
    for prefix in (
        "application_action",
        "entry_point",
        "event",
        "workflow",
        "state_machine",
        "test_case",
        "fixture",
        "fact",
        "asset",
        "text",
        "content_case",
        "data_contract",
        "render_profile",
        "message",
        "data_signal",
        "authorization_policy",
    ):
        marker = f"{prefix}."
        if value.startswith(marker):
            return value[len(marker):]
    return value


def route_ref(state_machine_id: str) -> str:
    return dotted("route", resource_tail(state_machine_id))


def endpoint_ref(application_action_id: str) -> str:
    return dotted("endpoint", resource_tail(application_action_id))


def cli_command_ref(ref: str) -> str:
    return dotted("cli_command", resource_tail(ref))


def workflow_ref(workflow_id: str) -> str:
    if workflow_id.startswith("workflow."):
        return workflow_id
    return dotted("workflow", resource_tail(workflow_id))


def authorization_policy_ref(application_action_id: str) -> str:
    return dotted("authorization_policy", resource_tail(application_action_id))


def query_ref(state_machine_subject: str, application_action_id: str, many: bool = False) -> str:
    application_action_subject = resource_tail(application_action_id)
    suffix = application_action_subject.replace(".", "_") if many else application_action_subject.split(".")[-1]
    return f"query.{resource_tail(state_machine_subject)}.{suffix}"


def state_machine_surface_ref(state_machine_id: str, state: str) -> str:
    return f"{state_machine_id}.{state}"


def text_ref(state_machine_id: str, state: str, slot: str) -> str:
    return f"text.{resource_tail(state_machine_id)}.{state}.{slot}"


def asset_ref(state_machine_id: str, state: str, slot: str) -> str:
    return f"asset.{resource_tail(state_machine_id)}.{state}.{slot}"


def screen_ref(state_machine_id: str) -> str:
    return dotted("screen", resource_tail(state_machine_id))
