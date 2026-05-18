from __future__ import annotations

from typing import Any


STATE_MACHINE_RENDERERS = ("html", "textual")
EXTERNAL_INTERFACE_ADAPTER_KINDS = ("http_api", "cli", "webhook", "scheduled", "worker", "html_route")
EXTERNAL_INTERFACE_INVOCATION_KINDS = ("command", "query", "state_machine", "workflow", "external_interface")


def external_interface_adapter_pair(external_interface_or_adapter: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    adapter = external_interface_or_adapter.get("adapter", external_interface_or_adapter)
    for kind in EXTERNAL_INTERFACE_ADAPTER_KINDS:
        if kind in adapter:
            value = adapter[kind]
            return kind, value if isinstance(value, dict) else {}
    raise KeyError("external interface adapter must declare http_api, cli, webhook, scheduled, worker, or html_route")


def external_interface_adapter(external_interface_or_adapter: dict[str, Any], kind: str | None = None) -> dict[str, Any]:
    actual_kind, adapter = external_interface_adapter_pair(external_interface_or_adapter)
    if kind is not None and actual_kind != kind:
        raise KeyError(f"external interface adapter is {actual_kind}, not {kind}")
    return adapter


def external_interface_invokes_pair(external_interface_or_invokes: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    invokes = external_interface_or_invokes.get("invokes", external_interface_or_invokes)
    for kind in EXTERNAL_INTERFACE_INVOCATION_KINDS:
        if kind in invokes:
            value = invokes[kind]
            if isinstance(value, dict):
                return kind, value
            return kind, {"ref": value}
    raise KeyError("external interface invokes must declare command, query, state_machine, workflow, or external_interface")


def external_interface_invokes(external_interface_or_invokes: dict[str, Any], kind: str | None = None) -> dict[str, Any]:
    actual_kind, invocation = external_interface_invokes_pair(external_interface_or_invokes)
    if kind is not None and actual_kind != kind:
        raise KeyError(f"external interface invokes {actual_kind}, not {kind}")
    return invocation


def external_interface_input_mapping(external_interface: dict[str, Any]) -> dict[str, Any]:
    return external_interface.get("input_mapping", {})


def external_interface_output_mapping(external_interface: dict[str, Any]) -> dict[str, Any]:
    return external_interface.get("output_mapping", {})


def external_interface_output_responses(external_interface: dict[str, Any]) -> dict[str, Any]:
    output_mapping = external_interface_output_mapping(external_interface)
    return output_mapping.get("responses", output_mapping.get("ingress_responses", {}))


def external_interface_path(external_interface: dict[str, Any]) -> str | None:
    kind, adapter = external_interface_adapter_pair(external_interface)
    if kind in {"http_api", "webhook", "html_route"}:
        return adapter.get("path")
    return None


def external_interface_method(external_interface: dict[str, Any]) -> str | None:
    kind, adapter = external_interface_adapter_pair(external_interface)
    return adapter.get("method") if kind == "http_api" else None


def external_interface_cli_command(external_interface: dict[str, Any]) -> str | None:
    kind, adapter = external_interface_adapter_pair(external_interface)
    return adapter.get("cli_command") if kind == "cli" else None


def external_interface_schedule_expression(external_interface: dict[str, Any]) -> str | None:
    kind, adapter = external_interface_adapter_pair(external_interface)
    return adapter.get("schedule_expression") if kind == "scheduled" else None


def external_interface_invocation_input_mapping(external_interface_or_invokes: dict[str, Any]) -> dict[str, Any]:
    input_mapping = external_interface_or_invokes.get("input_mapping", {})
    kind, _ = external_interface_invokes_pair(external_interface_or_invokes)
    if kind == "external_interface":
        return input_mapping.get("delegated_input", {})
    return input_mapping.get("bindings", {})


def external_interface_workflow_input_mapping(external_interface_or_invokes: dict[str, Any]) -> dict[str, Any]:
    return external_interface_input_mapping(external_interface_or_invokes).get("bindings", {})


def external_interface_invoked_ref_pair(invokes: dict[str, Any]) -> tuple[str, str]:
    kind, body = external_interface_invokes_pair(invokes)
    if kind == "state_machine":
        return "state_machine", state_machine_invocation_name(body)
    if kind == "workflow":
        return "workflow", workflow_invocation_name(body)
    if kind == "external_interface":
        return "external_interface", external_interface_delegate_invocation_name(body)
    return kind, operation_invocation_name(body)


def external_interface_state_machine_invocation(external_interface_or_invokes: dict[str, Any]) -> dict[str, str]:
    value = external_interface_invokes(external_interface_or_invokes, "state_machine")
    result: dict[str, str] = {"name": value["ref"]}
    if "renderer" in value:
        result["renderer"] = value["renderer"]
    return result


def external_interface_state_machine_name(external_interface_or_invokes: dict[str, Any]) -> str:
    return external_interface_state_machine_invocation(external_interface_or_invokes)["name"]


def external_interface_state_machine_renderer(external_interface_or_invokes: dict[str, Any]) -> str | None:
    return external_interface_state_machine_invocation(external_interface_or_invokes).get("renderer")


def state_machine_invocation_name(value: Any) -> str:
    if isinstance(value, dict):
        return value.get("ref") or value["name"]
    return value


def operation_invocation_name(value: Any) -> str:
    if isinstance(value, dict):
        return value.get("ref") or value["name"]
    return value


def external_interface_workflow_invocation(external_interface_or_invokes: dict[str, Any]) -> dict[str, Any]:
    value = external_interface_invokes(external_interface_or_invokes, "workflow")
    return {"name": value["ref"]}


def external_interface_workflow_name(external_interface_or_invokes: dict[str, Any]) -> str:
    return external_interface_workflow_invocation(external_interface_or_invokes)["name"]


def workflow_invocation_name(value: Any) -> str:
    if isinstance(value, dict):
        return value.get("ref") or value["name"]
    return value


def external_interface_delegate_invocation_name(value: Any) -> str:
    if isinstance(value, dict):
        return value.get("ref") or value["name"]
    return value


def external_interface_output_response_handlers(external_interface: dict[str, Any]) -> dict[str, Any]:
    if external_interface_adapter_pair(external_interface)[0] != "cli":
        return {}
    return external_interface_output_mapping(external_interface).get("response_handlers", {})
