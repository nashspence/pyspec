from __future__ import annotations

import copy
from typing import Any

EMPTY_OBJECT_SCHEMA: dict[str, Any] = {"type": "object", "properties": {}, "additionalProperties": False}


def command_or_query_collection(ref: str) -> str:
    if ref.startswith("command."):
        return "commands"
    if ref.startswith("query."):
        return "queries"
    raise KeyError(f"Command/query ref must start with command. or query.: {ref}")


def command_or_query_resource_kind(ref: str) -> str:
    if ref.startswith("command."):
        return "command"
    if ref.startswith("query."):
        return "query"
    raise KeyError(f"Command/query ref must start with command. or query.: {ref}")


def invocation_command_or_query_ref(invocation: dict[str, Any]) -> str:
    if "command" in invocation:
        return invocation["command"]
    if "query" in invocation:
        return invocation["query"]
    raise KeyError("state-machine binding must declare command or query")


def command_emits_by_outcome(command: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for emit in command.get("emits_domain_events", []):
        result.setdefault(emit["outcome"], []).append(copy.deepcopy(emit))
    return result


def command_query_map(contract: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for command_ref, command in contract.get("commands", {}).items():
        item = copy.deepcopy(command)
        effects = item.get("effects", {})
        item["behavior_kind"] = "lifecycle_transition" if effects.get("lifecycle_transition") else "command"
        item["input"] = item.get("input_schema", EMPTY_OBJECT_SCHEMA)
        item["creates"] = list(effects.get("creates", []))
        item["updates"] = list(effects.get("updates", []))
        item["deletes"] = list(effects.get("deletes", []))
        item["reads"] = []
        if effects.get("lifecycle_transition"):
            item["lifecycle_transition"] = copy.deepcopy(effects["lifecycle_transition"])
        emits_by_outcome = command_emits_by_outcome(command)
        for outcome_id, outcome in item.get("outcomes", {}).items():
            outcome["emits"] = copy.deepcopy(emits_by_outcome.get(outcome_id, []))
        result[command_ref] = item
    for query_ref, query in contract.get("queries", {}).items():
        item = copy.deepcopy(query)
        item["behavior_kind"] = "query"
        item["input"] = item.get("input_schema", EMPTY_OBJECT_SCHEMA)
        item["reads"] = list(item.get("reads", []))
        item["creates"] = []
        item["updates"] = []
        item["deletes"] = []
        result[query_ref] = item
    return result
