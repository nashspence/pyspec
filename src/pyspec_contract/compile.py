from __future__ import annotations

import argparse
import copy
import json
import os
from functools import lru_cache
import re
import shutil
import sys
import tempfile
import warnings
from pathlib import Path
from typing import Any, Callable

import fastjsonschema

from . import rules
from .layers import LayerError, parse_layers, validate_author_layers
from .io import read_json, read_yaml, write_json, write_yaml
from .layout import (
    renderer_textual,
    renderer_textual_containers,
    renderer_textual_presentation,
    renderer_textual_style,
    renderer_html_presentation,
    renderer_html_regions,
    renderer_html_style,
)
from .paths import COMPILED_SPEC_PATH, GENERATED_SPEC_DIR, SOURCE_SPEC_PATH
from .project import projection_files
from .binding_refs import BindingExpressionError, is_binding_expression, parse_binding_expression
from .targets import (
    STATE_MACHINE_RENDERERS,
    external_interface_state_machine_renderer,
    external_interface_adapter_pair,
    external_interface_input_mapping,
    external_interface_cli_command,
    external_interface_invocation_input_mapping,
    external_interface_method,
    external_interface_path,
    external_interface_output_response_handlers,
    external_interface_output_mapping,
    external_interface_output_responses,
    external_interface_schedule_expression,
    external_interface_invokes_pair,
    external_interface_invoked_ref_pair,
    external_interface_workflow_input_mapping,
)
from .json_schema import (
    EMPTY_OBJECT_SCHEMA,
    SchemaExpressionError,
    array_of,
    base_entity_type_id,
    dereference_type,
    effective_property_schema,
    entity_type_display_name,
    is_array_of_entity_type,
    is_problem_type,
    literal_schema,
    normalize_property_map,
    normalize_object_json_schema,
    normalize_schema,
    schema_property_required,
    schema_properties,
    schema_required,
    normalize_schema_map,
    entity_type_id,
    object_fields_for_type,
    referenced_named_types,
    type_display,
    type_equals,
    schema_without_null,
)

ROOT = Path(__file__).resolve().parent


class ContractError(ValueError):
    pass


class ContractLintWarning(UserWarning):
    pass


TypeScope = dict[tuple[str, ...], Any]
TypeScopes = dict[str, TypeScope]


ACTOR_SOURCE_SCOPE: TypeScope = {
    ("id",): {"type": "string"},
}

ACTOR_LITERAL_FIELD_NAMES = {
    "actor_id",
    "approved_by",
    "created_by",
    "reviewer_id",
    "updated_by",
    "user_id",
}


def _schema_path(name: str) -> Path:
    return ROOT / "schemas" / name


@lru_cache(maxsize=None)
def _validator(schema_name: str):
    schema = read_json(_schema_path(schema_name))
    return fastjsonschema.compile(schema)


def validate_against_schema(data: dict[str, Any], schema_name: str) -> None:
    validator = _validator(schema_name)
    try:
        validator(data)
    except fastjsonschema.JsonSchemaException as exc:
        raise ContractError("Schema validation failed:\n" + str(exc)) from exc


TARGET_ORDER = (
    "text_resource",
    "media_asset",
    "content_example",
    "viewport_profile",
    "fixture",
    "precondition",
    "assertion",
    "schema",
    "entity_type",
    "access_policy",
    "command",
    "query",
    "domain_event",
    "state_machine",
    "external_interface",
    "workflow",
    "behavior_scenario",
)



ENTITY_SECTIONS: dict[str, str] = {
    "text_resource": "text_resources",
    "media_asset": "media_assets",
    "content_example": "content_examples",
    "viewport_profile": "viewport_profiles",
    "fixture": "fixtures",
    "precondition": "preconditions",
    "assertion": "assertions",
    "schema": "schemas",
    "entity_type": "entity_types",
    "access_policy": "access_policies",
    "command": "commands",
    "query": "queries",
    "domain_event": "domain_events",
    "state_machine": "state_machines",
    "external_interface": "external_interfaces",
    "workflow": "workflows",
    "behavior_scenario": "behavior_scenarios",
}


REF_KINDS = [
    "media_asset",
    "access_policy",
    "cli_command",
    "cli_response_handler",
    "http_operation",
    "external_interface_delegate",
    "external_interface_invocation",
    "local_signal_raise",
    "command_binding",
    "command_binding_local_outcome_effect",
    "query_binding",
    "query_binding_local_outcome_effect",
    "html_route",
    "adapter_response_binding",
    "renderer_screen",
    "state_machine",
    "renderer_surface",
    "text_resource",
    "workflow",
]


def empty_compiled_contract(project: str) -> dict[str, Any]:
    return {
        "project": project,
        "entity_types": {},
        "schemas": {},
        "commands": {},
        "queries": {},
        "domain_events": {},
        "workflows": {},
        "state_machines": {},
        "external_interfaces": {},
        "access_policies": {},
        "fixtures": {},
        "behavior_scenarios": {},
        "media_assets": {},
        "text_resources": {},
        "content_examples": {},
        "viewport_profiles": {},
        "reference_index": {},
        "preconditions": {},
        "assertions": {},
    }


AUTHOR_SECTION_ORDER = (
    "fixtures",
    "preconditions",
    "assertions",
    "schemas",
    "entity_types",
    "access_policies",
    "commands",
    "queries",
    "domain_events",
    "state_machines",
    "external_interfaces",
    "workflows",
    "behavior_scenarios",
    "text_resources",
    "media_assets",
    "content_examples",
    "viewport_profiles",
)


def _prune_empty_author_sections(author: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {"project": author["project"]}
    for section_name in AUTHOR_SECTION_ORDER:
        value = author.get(section_name)
        if value:
            result[section_name] = value
    return result


def _default_rationale(entity: str, entity_id: str) -> str:
    return f"Declared {entity} {entity_id}."[:280]


def _empty_signals() -> dict[str, dict[str, Any]]:
    return {"accepts": {"local_signals": {}, "data_refresh_signals": {}}, "emits": {"local_signals": {}}}


def _schema_fields(schema: Any) -> dict[str, Any]:
    return schema_properties(schema or EMPTY_OBJECT_SCHEMA)


def _schema_required_fields(schema: Any) -> set[str]:
    return schema_required(schema or EMPTY_OBJECT_SCHEMA)


def _state_machine_context(state_machine: dict[str, Any]) -> dict[str, Any]:
    return _schema_fields(state_machine.get("context_schema"))


def _command_input(command: dict[str, Any]) -> dict[str, Any]:
    return _schema_fields(command.get("input_schema", command.get("input")))


def _signal_payload_fields(payload_schema: dict[str, Any] | None) -> dict[str, Any]:
    return _schema_fields(payload_schema)


def _normalize_signals(local_signals: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    local_signals = local_signals or {}
    normalized = _empty_signals()
    accepts = local_signals.get("accepts") or {}
    for signal_name, signal in (accepts.get("local_signals") or {}).items():
        signal_spec = copy.deepcopy(signal)
        signal_spec["payload_schema"] = normalize_object_json_schema(signal_spec.get("payload_schema") or EMPTY_OBJECT_SCHEMA)
        normalized["accepts"]["local_signals"][signal_name] = signal_spec
    for signal_name, signal in (accepts.get("data_refresh_signals") or {}).items():
        signal_spec = copy.deepcopy(signal)
        signal_spec["payload_schema"] = normalize_object_json_schema(signal_spec.get("payload_schema") or EMPTY_OBJECT_SCHEMA)
        normalized["accepts"]["data_refresh_signals"][signal_name] = signal_spec
    emits = local_signals.get("emits") or {}
    for signal_name, signal in (emits.get("local_signals") or {}).items():
        signal_spec = copy.deepcopy(signal)
        signal_spec["payload_schema"] = normalize_object_json_schema(signal_spec.get("payload_schema") or EMPTY_OBJECT_SCHEMA)
        normalized["emits"]["local_signals"][signal_name] = signal_spec
    return normalized


def _prune_empty_author_state_machine_signal_directions(author: dict[str, Any]) -> None:
    for state_machine in (author.get("state_machines") or {}).values():
        local_signals = state_machine.get("local_signals")
        if not isinstance(local_signals, dict):
            continue
        for direction, groups in (("accepts", ("local_signals", "data_refresh_signals")), ("emits", ("local_signals",))):
            direction_body = local_signals.get(direction)
            if not isinstance(direction_body, dict):
                continue
            for group in groups:
                for signal in (direction_body.get(group) or {}).values():
                    if isinstance(signal, dict) and signal.get("payload_schema") == {}:
                        signal.pop("payload_schema")
                if direction_body.get(group) == {}:
                    direction_body.pop(group)
            if not direction_body:
                local_signals.pop(direction)
        if not local_signals:
            state_machine.pop("local_signals", None)


def author_from_source(source: dict[str, Any], layers: set[str] | None = None) -> dict[str, Any]:
    validate_against_schema(source, "author.schema.json")
    try:
        validate_author_layers(source, layers)
    except LayerError as exc:
        raise ContractError(str(exc)) from exc
    author = _prune_empty_author_sections(copy.deepcopy(source))
    _prune_empty_author_state_machine_signal_directions(author)
    return author


def compile_source(source: dict[str, Any], layers: set[str] | None = None) -> dict[str, Any]:
    return compile_author(author_from_source(source, layers=layers), layers=layers)


def compile_author(author: dict[str, Any], layers: set[str] | None = None) -> dict[str, Any]:
    validate_against_schema(author, "author.schema.json")
    try:
        validate_author_layers(author, layers)
    except LayerError as exc:
        raise ContractError(str(exc)) from exc

    contract = empty_compiled_contract(author["project"])
    for entity in TARGET_ORDER:
        section_name = ENTITY_SECTIONS[entity]
        section = contract[section_name]
        for entity_id, item in (author.get(section_name) or {}).items():
            spec = copy.deepcopy(item)
            spec["id"] = entity_id
            _apply_author_defaults(entity, spec)
            section[entity_id] = _compile_entity(entity, spec, contract)

    _derive_command_entity_lifecycle_transitions(contract)
    contract["domain_events"] = _derive_domain_events(contract)
    contract["reference_index"] = _derive_refs(contract)
    used_preconditions, used_assertions = _expand_behavior_scenario_predicate_refs(contract)
    _semantic_validate(contract, used_preconditions, used_assertions)
    _expand_behavior_scenarios(contract)
    validate_against_schema(contract, "spec.schema.json")
    return contract


def _apply_author_defaults(entity: str, spec: dict[str, Any]) -> None:
    rationale_subject = spec.get("name", spec["id"]) if entity == "entity_type" else spec["id"]
    spec.setdefault("rationale", _default_rationale(entity, rationale_subject))
    if entity == "state_machine":
        spec.setdefault("context_schema", EMPTY_OBJECT_SCHEMA)
        spec.setdefault("query_bindings", {})
        spec["local_signals"] = _normalize_signals(spec.get("local_signals"))
        spec.setdefault("transitions", [])
    elif entity == "command":
        for outcome in spec.get("outputs", {}).values():
            outcome.setdefault("result", EMPTY_OBJECT_SCHEMA)


def _compile_entity(entity: str, spec: dict[str, Any] | None, contract: dict[str, Any]) -> dict[str, Any]:
    if spec is None:  # pragma: no cover - delete never compiles an entity.
        raise ContractError(f"Cannot compile missing {entity} spec")

    if entity == "text_resource":
        item = {"placeholder": spec["placeholder"], "rationale": spec["rationale"]}
        for field in ["max_chars", "intent", "args", "resolver_ref"]:
            if field in spec:
                item[field] = spec[field]
        return item

    if entity == "media_asset":
        item = {"media_kind": spec["media_kind"], "placeholder": spec["placeholder"], "rationale": spec["rationale"]}
        for field in ["asset_role", "alt_text", "args", "resolver_ref"]:
            if field in spec:
                item[field] = spec[field]
        return item

    if entity == "content_example":
        item = {"ref": spec["ref"], "args": spec["args"], "rationale": spec["rationale"]}
        if "seed_fixtures" in spec:
            item["seed_fixtures"] = spec["seed_fixtures"]
        return item

    if entity == "viewport_profile":
        item = {"rationale": spec["rationale"]}
        for field in ["html_viewports", "textual_viewports"]:
            if field in spec:
                item[field] = spec[field]
        return item

    if entity == "fixture":
        return {"values": spec["values"], "rationale": spec["rationale"]}

    if entity in {"precondition", "assertion"}:
        kind, body = _one_predicate(spec, f"{entity.replace('_', ' ').title()} {spec['id']}")
        return {kind: body, "rationale": spec["rationale"]}

    if entity == "entity_type":
        item = {
            "name": spec["name"],
            "schema": normalize_object_json_schema(spec["schema"]),
            "entity_lifecycle": spec.get("entity_lifecycle"),
            "rationale": spec["rationale"],
        }
        return item

    if entity == "schema":
        return {
            "schema": normalize_object_json_schema(spec["schema"]),
            "rationale": spec["rationale"],
        }

    if entity == "command":
        outcomes = {}
        for outcome_id, outcome in spec["outcomes"].items():
            normalized_outcome = copy.deepcopy(outcome)
            normalized_outcome["result"] = normalize_schema(normalized_outcome["result"])
            outcomes[outcome_id] = normalized_outcome
        command: dict[str, Any] = {
            "input_schema": normalize_object_json_schema(spec.get("input_schema", EMPTY_OBJECT_SCHEMA)),
            "entity_changes": copy.deepcopy(spec.get("entity_changes", {})),
            "outcomes": outcomes,
            "emits_domain_events": copy.deepcopy(spec.get("emits_domain_events", [])),
            "rationale": spec["rationale"],
        }
        if spec.get("idempotent"):
            command["idempotent"] = True
        if spec.get("retryable"):
            command["retryable"] = True
        if "authorization" in spec:
            command["authorization"] = copy.deepcopy(spec["authorization"])
        return command

    if entity == "query":
        outcomes = {}
        for outcome_id, outcome in spec["outcomes"].items():
            normalized_outcome = copy.deepcopy(outcome)
            normalized_outcome["result"] = normalize_schema(normalized_outcome["result"])
            outcomes[outcome_id] = normalized_outcome
        return {
            "input_schema": normalize_object_json_schema(spec.get("input_schema", EMPTY_OBJECT_SCHEMA)),
            "result_schema": normalize_schema(spec["result_schema"]),
            "outcomes": outcomes,
            "rationale": spec["rationale"],
        }

    if entity == "access_policy":
        return {
            "subject": copy.deepcopy(spec["subject"]),
            "resource": copy.deepcopy(spec["resource"]),
            "action": copy.deepcopy(spec["action"]),
            "environment": copy.deepcopy(spec["environment"]),
            "combining_algorithm": spec["combining_algorithm"],
            "rules": copy.deepcopy(spec["rules"]),
            "rationale": spec["rationale"],
        }

    if entity == "domain_event":
        return {
            "payload_schema": normalize_schema(spec["payload_schema"]),
            "emitted_by": [],
            "rationale": spec["rationale"],
        }

    if entity == "state_machine":
        state_machine_id = spec["id"]
        state_machine: dict[str, Any] = {
            "context_schema": normalize_object_json_schema(spec["context_schema"]),
            "query_bindings": _compile_query_bindings(spec.get("query_bindings", {}), scope="state_machine"),
            "local_signals": _normalize_signals(spec.get("local_signals")),
            "initial_state": spec["initial_state"],
            "states": _compile_states(state_machine_id, spec.get("states", {})),
            "transitions": spec.get("transitions", []),
            "rationale": spec["rationale"],
        }
        if "entity_type" in spec:
            state_machine["entity_type"] = spec["entity_type"]
        if "archetype" in spec:
            state_machine["archetype"] = spec["archetype"]
        return state_machine

    if entity == "external_interface":
        external_interface: dict[str, Any] = {
            "adapter": spec["adapter"],
            "invokes": spec["invokes"],
            "input_mapping": copy.deepcopy(spec.get("input_mapping", {})),
            "output_mapping": copy.deepcopy(spec.get("output_mapping", {})),
            "rationale": spec["rationale"],
        }
        if "access_policy" in spec:
            external_interface["access_policy"] = copy.deepcopy(spec["access_policy"])
        if spec.get("idempotent"):
            external_interface["idempotent"] = True
        if spec.get("retryable"):
            external_interface["retryable"] = True
        adapter_kind, _ = external_interface_adapter_pair(external_interface)
        invoked_kind, invoked = external_interface_invokes_pair(external_interface)
        if adapter_kind == "html_route" and invoked_kind == "state_machine":
            external_interface["html_route"] = rules.html_route_ref(invoked["ref"])
        elif adapter_kind == "http_api" and invoked_kind in {"command", "query"}:
            external_interface["http_operation"] = rules.http_operation_ref(invoked["ref"])
            if invoked["ref"] in _command_query_map(contract):
                command_authorization = _command_query_map(contract)[invoked["ref"]].get("authorization")
                if command_authorization:
                    external_interface.setdefault("access_policy", copy.deepcopy(command_authorization["policy"]))
        elif adapter_kind == "cli":
            external_interface_id = spec["id"]
            command_ref_source = external_interface_id[len("external_interface.cli."):] if invoked_kind == "external_interface" and external_interface_id.startswith("external_interface.cli.") else invoked["ref"]
            external_interface["cli_command_ref"] = rules.cli_command_ref(command_ref_source)
            if invoked_kind in {"command", "query"} and invoked["ref"] in _command_query_map(contract):
                command_authorization = _command_query_map(contract)[invoked["ref"]].get("authorization")
                if command_authorization:
                    external_interface.setdefault("access_policy", copy.deepcopy(command_authorization["policy"]))
        elif adapter_kind in {"worker", "scheduled"} and invoked_kind == "workflow":
            external_interface["workflow_ref"] = rules.workflow_ref(invoked["ref"])
        return external_interface

    if entity == "workflow":
        return {
            "inputs": spec["inputs"],
            "activities": spec["activities"],
            "gateways": spec["gateways"],
            "sequence_flows": spec["sequence_flows"],
            "outputs": spec["outputs"],
            "retry_policies": spec["retry_policies"],
            "failure_handlers": spec["failure_handlers"],
            "ref": rules.workflow_ref(spec["id"]),
            "rationale": spec["rationale"],
        }

    if entity == "behavior_scenario":
        return {
            "feature_tag": spec["feature_tag"],
            "title": spec["title"],
            "archetype": spec["archetype"],
            "system_under_test_ref": spec["system_under_test_ref"],
            "given": spec["given"],
            "when": spec["when"],
            "then": dict(spec["then"]),
            "rationale": spec["rationale"],
        }

    raise ContractError(f"Unknown contract entity kind: {entity}")


def _ref_subject(owner_id: str) -> str:
    return rules.resource_tail(owner_id)


def _state_surface_ref(owner_id: str, state_name: str) -> str:
    if owner_id.startswith("state_machine."):
        return f"{owner_id}.{state_name}"
    return rules.state_machine_surface_ref(owner_id, state_name)


def _compile_query_bindings(invocations: dict[str, Any], *, scope: str) -> dict[str, Any]:
    compiled = copy.deepcopy(invocations or {})
    for invocation in compiled.values():
        default_load = {"on_start": True} if scope == "state_machine" else {"on_enter": True}
        invocation.setdefault("load", default_load)
    return compiled


def _compile_states(owner_id: str, states: dict[str, Any]) -> dict[str, Any]:
    subject = _ref_subject(owner_id)
    compiled = {}
    for state_name, state in states.items():
        item = {
            "renderer_surface": _state_surface_ref(owner_id, state_name),
            "query_bindings": _compile_query_bindings(state.get("query_bindings", {}), scope="state"),
            "text_resources": [rules.text_resource_ref(subject, state_name, slot) for slot in state.get("text_slots", [])],
            "media_assets": [rules.media_asset_ref(subject, state_name, slot) for slot in state.get("media_asset_slots", [])],
            "fields": state.get("field_slots", []),
            "command_bindings": copy.deepcopy(state.get("command_bindings", {})),
        }
        if "renderers" in state:
            item["renderers"] = state["renderers"]
        for field in ["child_state_machines", "local_signal_sync_rules"]:
            if field in state:
                item[field] = state[field]
        if state.get("render_examples"):
            item["render_examples"] = {
                case_name: _compile_render_example(owner_id, state_name, case_name, case)
                for case_name, case in state["render_examples"].items()
            }
        compiled[state_name] = item
    return compiled


def _compile_render_example(state_machine_id: str, state_name: str, case_name: str, case: dict[str, Any]) -> dict[str, Any]:
    item = {
        "seed_fixtures": case["seed_fixtures"],
        "rationale": case.get("rationale", _default_rationale("render_example", f"{state_machine_id}.{state_name}.{case_name}")),
    }
    for field in ["context", "precondition_refs", "instances"]:
        if field in case:
            item[field] = case[field]
    return item


def render_examples(contract: dict[str, Any]) -> dict[str, dict[str, Any]]:
    cases: dict[str, dict[str, Any]] = {}
    for state_machine_id, state_machine in sorted(contract.get("state_machines", {}).items()):
        for state_name, state in sorted(state_machine.get("states", {}).items()):
            for case_name, case in sorted((state.get("render_examples") or {}).items()):
                case_id = f"{state_machine_id}.{state_name}.{case_name}.audit"
                cases[case_id] = {"state_machine": state_machine_id, "state": state_name, "name": case_name, **case}
    return cases


def _command_query_map(contract: dict[str, Any]) -> dict[str, dict[str, Any]]:
    command_queries: dict[str, dict[str, Any]] = {}
    for command_ref, command in contract.get("commands", {}).items():
        item = copy.deepcopy(command)
        entity_changes = item.get("entity_changes", {})
        item["behavior_kind"] = "entity_lifecycle_transition" if entity_changes.get("entity_lifecycle_transition") else "command"
        item["input"] = item.get("input_schema", EMPTY_OBJECT_SCHEMA)
        item["creates"] = list(entity_changes.get("creates", []))
        item["updates"] = list(entity_changes.get("updates", []))
        item["deletes"] = list(entity_changes.get("deletes", []))
        item["reads"] = []
        if entity_changes.get("entity_lifecycle_transition"):
            item["entity_lifecycle_transition"] = copy.deepcopy(entity_changes["entity_lifecycle_transition"])
        emits_by_outcome = _command_emits_by_outcome(command)
        for outcome_id, outcome in item.get("outcomes", {}).items():
            outcome["emits"] = copy.deepcopy(emits_by_outcome.get(outcome_id, []))
        command_queries[command_ref] = item
    for query_ref, query in contract.get("queries", {}).items():
        item = copy.deepcopy(query)
        item["behavior_kind"] = "query"
        item["input"] = item.get("input_schema", EMPTY_OBJECT_SCHEMA)
        item["reads"] = []
        item["creates"] = []
        item["updates"] = []
        item["deletes"] = []
        command_queries[query_ref] = item
    return command_queries


def _command_or_query_input(behavior: dict[str, Any]) -> dict[str, Any]:
    return _schema_fields(behavior.get("input_schema", EMPTY_OBJECT_SCHEMA))


def _invocation_command_or_query_ref(invocation: dict[str, Any]) -> str:
    if "command" in invocation:
        return invocation["command"]
    if "query" in invocation:
        return invocation["query"]
    raise ContractError("Command/query binding must declare command or query")


def _command_emits_by_outcome(command: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for emit in command.get("emits_domain_events", []):
        result.setdefault(emit["outcome"], []).append(emit)
    return result


def _derive_command_entity_lifecycle_transitions(contract: dict[str, Any]) -> None:
    """Derive entity_lifecycle_transition action details from entity_lifecycle declarations.

    Authored sources should not have to repeat the same entity_lifecycle_transition in both
    the entity_lifecycle and the command. The compiled contract remains
    explicit for downstream projections and validators.
    """
    by_command: dict[str, dict[str, Any]] = {}
    for entity_type_ref, entity_type in contract.get("entity_types", {}).items():
        entity_lifecycle = entity_type.get("entity_lifecycle")
        if not entity_lifecycle:
            continue
        field = entity_lifecycle["field"]
        for entity_lifecycle_transition in entity_lifecycle.get("lifecycle_transitions", []):
            command_id = entity_lifecycle_transition["command"]
            if command_id in by_command:
                raise ContractError(f"Command {command_id} is used by multiple entity_lifecycle_transitions")
            by_command[command_id] = {
                "entity_type": entity_type_ref,
                "field": field,
                "from": entity_lifecycle_transition["from"],
                "to": entity_lifecycle_transition["to"],
            }

    for command_id, command in contract.get("commands", {}).items():
        entity_changes = command.setdefault("entity_changes", {})
        if "entity_lifecycle_transition" in entity_changes:
            continue
        derived = by_command.get(command_id)
        if not derived:
            continue
        entity_changes["entity_lifecycle_transition"] = derived


def _derive_domain_events(contract: dict[str, Any]) -> dict[str, Any]:
    domain_events: dict[str, Any] = copy.deepcopy(contract.get("domain_events", {}))
    for command_id, command in sorted(contract["commands"].items()):
        for emit in command.get("emits_domain_events", []):
            outcome_id = emit["outcome"]
            outcome = command["outcomes"].get(outcome_id)
            if not outcome:
                raise ContractError(f"Command {command_id} emits_domain_events references unknown outcome {outcome_id}")
            domain_event_id = _emit_domain_event_id(emit)
            if outcome["kind"] != "success":
                raise ContractError(f"Command {command_id} failure outcome {outcome_id} must not emit domain events")
            payload_type = domain_events.get(domain_event_id, {}).get("payload_schema", outcome["result"])
            domain_event = domain_events.setdefault(domain_event_id, {
                "emitted_by": [],
                "payload_schema": payload_type,
                "rationale": command["rationale"],
            })
            _validate_emit_payload_mapping(contract, command_id, command, outcome_id, outcome, domain_event_id, domain_event["payload_schema"], emit)
            domain_event["emitted_by"].append(command_id)
    return domain_events


def _emit_domain_event_id(emit: Any) -> str:
    if isinstance(emit, str):
        return emit
    return emit["domain_event"]


def _derive_refs(contract: dict[str, Any]) -> dict[str, list[str]]:
    refs: dict[str, set[str]] = {kind: set() for kind in REF_KINDS}
    refs["access_policy"].update(contract.get("access_policies", {}))
    refs["text_resource"].update(contract.get("text_resources", {}))
    refs["media_asset"].update(contract.get("media_assets", {}))
    for state_machine_id in contract["state_machines"]:
        refs["state_machine"].add(state_machine_id)
    for state_machine_id, owner in contract["state_machines"].items():
        for invocation_id, invocation in sorted((owner.get("query_bindings") or {}).items()):
            refs["query_binding"].add(_generated_query_binding_ref(state_machine_id, None, invocation_id))
            for outcome_id, effect in sorted(invocation.get("local_effects", {}).items()):
                refs["query_binding_local_outcome_effect"].add(_generated_query_binding_local_outcome_effect_ref(state_machine_id, None, invocation_id, outcome_id))
                for branch in _query_local_outcome_effect_branches(effect):
                    signal = branch.get("raise")
                    if signal:
                        kind, signal_id = _signal_raise_selector_key(signal)
                        refs["local_signal_raise"].add(
                            _generated_query_local_signal_raise_ref(state_machine_id, None, invocation_id, outcome_id, kind, signal_id)
                        )
        for state_name, state in owner.get("states", {}).items():
            refs["renderer_surface"].add(state["renderer_surface"])
            refs["text_resource"].update(state["text_resources"])
            refs["media_asset"].update(state["media_assets"])
            for invocation_id, invocation in sorted((state.get("query_bindings") or {}).items()):
                refs["query_binding"].add(_generated_query_binding_ref(state_machine_id, state_name, invocation_id))
                for outcome_id, effect in sorted(invocation.get("local_effects", {}).items()):
                    refs["query_binding_local_outcome_effect"].add(_generated_query_binding_local_outcome_effect_ref(state_machine_id, state_name, invocation_id, outcome_id))
                    for branch in _query_local_outcome_effect_branches(effect):
                        signal = branch.get("raise")
                        if signal:
                            kind, signal_id = _signal_raise_selector_key(signal)
                            refs["local_signal_raise"].add(
                                _generated_query_local_signal_raise_ref(state_machine_id, state_name, invocation_id, outcome_id, kind, signal_id)
                            )
            for invocation_id, invocation in sorted((state.get("command_bindings") or {}).items()):
                refs["command_binding"].add(_generated_command_binding_ref(state_machine_id, state_name, invocation_id))
                for outcome_id, effect in sorted(invocation.get("local_effects", {}).items()):
                    refs["command_binding_local_outcome_effect"].add(_generated_command_binding_local_outcome_effect_ref(state_machine_id, state_name, invocation_id, outcome_id))
                    signal = effect.get("raise")
                    if signal:
                        kind, signal_id = _signal_raise_selector_key(signal)
                        refs["local_signal_raise"].add(
                            _generated_command_local_signal_raise_ref(state_machine_id, state_name, invocation_id, outcome_id, kind, signal_id)
                        )
    for external_interface_id, external_interface in contract["external_interfaces"].items():
        target_kind, target_ref = external_interface_invoked_ref_pair(external_interface)
        refs["external_interface_invocation"].add(_generated_external_interface_invocation_ref(external_interface_id, target_kind, target_ref))
        if target_kind == "external_interface":
            refs["external_interface_delegate"].add(_generated_external_interface_delegate_ref(external_interface_id, target_ref))
        if external_interface_adapter_pair(external_interface)[0] == "cli":
            for outcome_id, handler in sorted(external_interface_output_response_handlers(external_interface).items()):
                refs["cli_response_handler"].add(_generated_cli_response_handler_ref(external_interface_id, outcome_id))
                for stream_name in ("stdout", "stderr"):
                    output = handler.get(stream_name) or {}
                    bindings = output.get("bindings") or {}
                    for binding_name, binding in sorted(bindings.items()):
                        if _binding_references_root(binding, "adapter_response"):
                            refs["adapter_response_binding"].add(_generated_adapter_response_binding_ref(external_interface_id, outcome_id, stream_name, binding_name))
        for ref_kind, field in [
            ("html_route", "html_route"),
            ("http_operation", "http_operation"),
            ("cli_command", "cli_command_ref"),
            ("workflow", "workflow_ref"),
        ]:
            if field in external_interface:
                refs[ref_kind].add(external_interface[field])
    for state_machine_id, state_machine in contract["state_machines"].items():
        if _state_machine_has_textual_screen(state_machine):
            refs["renderer_screen"].add(rules.renderer_screen_ref(state_machine_id))
    for workflow in contract["workflows"].values():
        refs["workflow"].add(workflow["ref"])
    return {kind: sorted(values) for kind, values in sorted(refs.items()) if values}


def _generated_external_interface_invocation_ref(external_interface_id: str, target_kind: str, target_ref: str) -> str:
    return f"external_interface_invocation.{rules.resource_tail(external_interface_id)}.{target_kind}.{rules.resource_tail(target_ref)}"


def _generated_external_interface_delegate_ref(external_interface_id: str, delegated_external_interface_id: str) -> str:
    return f"external_interface_delegate.{rules.resource_tail(external_interface_id)}.to.{rules.resource_tail(delegated_external_interface_id)}"


def _generated_cli_response_handler_ref(external_interface_id: str, outcome_id: str) -> str:
    return f"cli_response_handler.{rules.resource_tail(external_interface_id)}.{outcome_id}"


def _generated_adapter_response_binding_ref(external_interface_id: str, outcome_id: str, stream_name: str, binding_name: str) -> str:
    return f"adapter_response_binding.{rules.resource_tail(external_interface_id)}.{outcome_id}.{stream_name}.{binding_name}"


def _generated_command_binding_ref(state_machine_id: str, state_name: str, invocation_id: str) -> str:
    return f"command_binding.{rules.resource_tail(state_machine_id)}.{state_name}.{invocation_id}"


def _generated_command_binding_local_outcome_effect_ref(state_machine_id: str, state_name: str, invocation_id: str, outcome_id: str) -> str:
    return f"command_binding_local_outcome_effect.{rules.resource_tail(state_machine_id)}.{state_name}.{invocation_id}.{outcome_id}"


def _generated_query_binding_ref(state_machine_id: str, state_name: str | None, invocation_id: str) -> str:
    state_part = f".{state_name}" if state_name else ""
    return f"query_binding.{rules.resource_tail(state_machine_id)}{state_part}.{invocation_id}"


def _generated_query_binding_local_outcome_effect_ref(state_machine_id: str, state_name: str | None, invocation_id: str, outcome_id: str) -> str:
    state_part = f".{state_name}" if state_name else ""
    return f"query_binding_local_outcome_effect.{rules.resource_tail(state_machine_id)}{state_part}.{invocation_id}.{outcome_id}"


def _generated_command_local_signal_raise_ref(
    state_machine_id: str,
    state_name: str,
    invocation_id: str,
    outcome_id: str,
    signal_kind: str,
    signal_id: str,
) -> str:
    return f"local_signal_raise.{rules.resource_tail(state_machine_id)}.{state_name}.command_binding.{invocation_id}.{outcome_id}.{signal_kind}.{signal_id}"


def _generated_query_local_signal_raise_ref(
    state_machine_id: str,
    state_name: str | None,
    invocation_id: str,
    outcome_id: str,
    signal_kind: str,
    signal_id: str,
) -> str:
    state_part = f".{state_name}" if state_name else ""
    return f"local_signal_raise.{rules.resource_tail(state_machine_id)}{state_part}.query_binding.{invocation_id}.{outcome_id}.{signal_kind}.{signal_id}"


def _binding_references_root(binding: Any, root: str) -> bool:
    if not isinstance(binding, dict) or "from" not in binding:
        return False
    try:
        return parse_binding_expression(binding["from"]).root == root
    except BindingExpressionError:
        return False


def _state_machine_has_textual_screen(state_machine: dict[str, Any]) -> bool:
    return any(
        bool(renderer_textual(state).get("layout"))
        or (not state.get("child_state_machines") and bool(renderer_textual(state).get("presentation")))
        for state in state_machine.get("states", {}).values()
    )


def _semantic_validate(contract: dict[str, Any], used_preconditions: set[str], used_assertions: set[str]) -> None:
    _validate_text_assets(contract)
    _validate_content_examples(contract)
    _validate_viewport_profiles(contract)
    _validate_schemas(contract)
    _validate_entity_types(contract)
    _validate_type_references(contract)
    _validate_commands(contract)
    _validate_external_interface_delegation_graph(contract)
    _validate_external_interface_response_maps(contract)
    _validate_state_machines(contract)
    _validate_state_machine_signal_payload_consistency(contract)
    _validate_external_interfaces(contract)
    _validate_access_policies(contract)
    _validate_workflows(contract)
    _validate_fixtures(contract)
    _validate_preconditions(contract)
    _validate_assertions(contract)
    _validate_behavior_scenarios(contract)
    _validate_render_examples(contract)
    _validate_preconditions_are_used(contract, used_preconditions)
    _validate_assertions_are_used(contract, used_assertions)



def _validate_text_assets(contract: dict[str, Any]) -> None:
    used_text: set[str] = set()
    used_assets: set[str] = set()
    for owner in contract.get("state_machines", {}).values():
        for state in owner.get("states", {}).values():
            used_text.update(state.get("text_resources", []))
            used_assets.update(state.get("media_assets", []))
    for external_interface in contract.get("external_interfaces", {}).values():
        for handler in external_interface_output_response_handlers(external_interface).values():
            for stream in ("stdout", "stderr"):
                output = handler.get(stream) or {}
                if output.get("text"):
                    used_text.add(output["text"])
    declared_text = set(contract.get("text_resources", {}))
    declared_assets = set(contract.get("media_assets", {}))
    if declared_text != used_text:
        raise ContractError(_diff_message("text resources", used_text, declared_text))
    if declared_assets != used_assets:
        raise ContractError(_diff_message("media asset placeholders", used_assets, declared_assets))
    for text_id, item in contract.get("text_resources", {}).items():
        max_chars = item.get("max_chars")
        if max_chars is not None and len(item["placeholder"]) > max_chars:
            raise ContractError(f"Text resource {text_id} placeholder exceeds max_chars")
    for media_asset_id, item in contract.get("media_assets", {}).items():
        alt_text = item.get("alt_text")
        if alt_text and alt_text not in declared_text:
            raise ContractError(f"Media asset {media_asset_id} alt_text references unknown text resource {alt_text}")




def _validate_content_examples(contract: dict[str, Any]) -> None:
    final_refs = {
        ref
        for section in ["text_resources", "media_assets"]
        for ref, item in contract.get(section, {}).items()
        if item.get("resolver_ref")
    }
    declared_example_refs: set[str] = set()
    for ref, item in list(contract.get("text_resources", {}).items()) + list(contract.get("media_assets", {}).items()):
        resolver_ref = item.get("resolver_ref")
        if resolver_ref:
            if resolver_ref != ref:
                raise ContractError(f"Content resolver_ref for {ref} must equal the content id")
            if not item.get("args"):
                # Arg-less resolvers are allowed, but declaring args is preferred for dynamic content.
                pass
    for case_id, case in contract.get("content_examples", {}).items():
        ref = case["ref"]
        section = "text_resources" if ref.startswith("text_resource.") else "media_assets"
        if ref not in contract.get(section, {}):
            label = "text resource" if section == "text_resources" else "media asset"
            raise ContractError(f"Content example {case_id} references unknown {label} {ref}")
        for fixture_id in case.get("seed_fixtures", []):
            if fixture_id not in contract["fixtures"]:
                raise ContractError(f"Content example {case_id} references unknown fixture {fixture_id}")
        fixture_values = _fixture_namespace(contract, case.get("seed_fixtures", []), f"content example {case_id}")
        _validate_fixture_templates(case, fixture_values, f"content example {case_id}")
        expected = set(contract[section][ref].get("args", {}))
        actual = set(case.get("args", {}))
        if expected != actual:
            raise ContractError(_diff_message(f"content example {case_id} args", expected, actual))
        declared_example_refs.add(ref)
    missing = sorted(final_refs - declared_example_refs)
    if missing:
        raise ContractError("Final content resolvers require content_example coverage: " + ", ".join(missing))


def _validate_viewport_profiles(contract: dict[str, Any]) -> None:
    required_renderers = {
        renderer
        for state_machine in contract.get("state_machines", {}).values()
        for state in state_machine.get("states", {}).values()
        for renderer in _state_renderers(state)
    }
    if required_renderers and not contract.get("viewport_profiles"):
        raise ContractError("At least one viewport_profile is required when renderable state_machines are declared")
    available_renderers = set()
    for profile in contract.get("viewport_profiles", {}).values():
        if profile.get("html_viewports"):
            available_renderers.add("html")
        if profile.get("textual_viewports"):
            available_renderers.add("textual")
    missing = sorted(required_renderers - available_renderers)
    if missing:
        raise ContractError("Renderable state_machines require viewport_profile viewports for: " + ", ".join(missing))


def _validate_render_examples(contract: dict[str, Any]) -> None:
    cases = render_examples(contract)
    composable_states = {
        (state_machine_id, state_name)
        for state_machine_id, state_machine in contract.get("state_machines", {}).items()
        for state_name, state in state_machine.get("states", {}).items()
        if state.get("renderers") or state.get("child_state_machines")
    }
    covered_composable_states: set[tuple[str, str]] = set()
    for case_id, case in cases.items():
        state_machine_id = case["state_machine"]
        state_name = case["state"]
        state_machine = contract["state_machines"][state_machine_id]
        state = state_machine["states"][state_name]
        entity_type = state_machine.get("entity_type")
        if not _state_renderers(state):
            raise ContractError(f"Render example {case_id} references state {state_machine_id}.{state_name} with no visual renderer")
        for fixture_id in case.get("seed_fixtures", []):
            if fixture_id not in contract["fixtures"]:
                raise ContractError(f"Render example {case_id} references unknown fixture {fixture_id}")
        fixture_values = _fixture_namespace(contract, case.get("seed_fixtures", []), f"render example {case_id}")
        _validate_fixture_templates(case, fixture_values, f"render example {case_id}")
        for precondition_use in case.get("precondition_refs", []):
            precondition_id = precondition_use["ref"]
            _validate_fixture_templates(contract["preconditions"][precondition_id], fixture_values, f"render example {case_id} precondition {precondition_id}")
        if entity_type and state.get("fields") and not set(state.get("fields", [])) <= set(_state_machine_context(state_machine)) and not _setup_has_entity_type(contract, case.get("seed_fixtures", []), case.get("precondition_refs", []), entity_type):
            raise ContractError(f"Render example {case_id} renders fields for {state_machine_id}.{state_name} but does not include a {entity_type} fixture or precondition")
        if state.get("child_state_machines"):
            mounted_instances = {mount["id"]: mount for mount in state["child_state_machines"]}
            expected_instances = case.get("instances")
            if not expected_instances:
                raise ContractError(f"Render example {case_id} for composed state machine state {state_machine_id}.{state_name} must declare instances")
            if set(expected_instances) != set(mounted_instances):
                raise ContractError(f"Render example {case_id} instance state vector must exactly cover mounted state machine instances")
            for instance_id, expected in expected_instances.items():
                child_state_machine_id = mounted_instances[instance_id]["state_machine"]
                if expected["state"] not in contract["state_machines"][child_state_machine_id]["states"]:
                    raise ContractError(f"Render example {case_id} references unknown state machine state {child_state_machine_id}.{expected['state']}")
                selected_state = contract["state_machines"][child_state_machine_id]["states"][expected["state"]]
                child_model = contract["state_machines"][child_state_machine_id].get("entity_type")
                child_context = set(_state_machine_context(contract["state_machines"][child_state_machine_id]))
                if child_model and selected_state.get("fields") and not set(selected_state.get("fields", [])) <= child_context and not _setup_has_entity_type(contract, case.get("seed_fixtures", []), case.get("precondition_refs", []), child_model):
                    raise ContractError(f"Render example {case_id} renders fields for {child_state_machine_id}.{expected['state']} but does not include a {child_model} fixture or precondition")
            covered_composable_states.add((state_machine_id, state_name))
    missing_composed = sorted(f"{state_machine_id}.{state_name}" for state_machine_id, state_name in composable_states - covered_composable_states)
    if missing_composed:
        raise ContractError("Missing render audit coverage for composed state machine states: " + ", ".join(missing_composed))
    _validate_state_machine_state_fixture_coverage(contract)


def _state_renderers(state: dict[str, Any]) -> set[str]:
    renderers = state.get("renderers") or {}
    result: set[str] = set()
    if renderers.get("html"):
        result.add("html")
    if renderers.get("textual"):
        result.add("textual")
    return result


def _validate_state_machine_state_fixture_coverage(contract: dict[str, Any]) -> None:
    for state_machine_id, state_machine in contract.get("state_machines", {}).items():
        entity_type = state_machine.get("entity_type")
        for state_name, state in state_machine.get("states", {}).items():
            if entity_type and state.get("fields") and not set(state.get("fields", [])) <= set(_state_machine_context(state_machine)) and not _setup_has_entity_type(contract, list(contract.get("fixtures", {})), _all_precondition_uses(contract), entity_type):
                raise ContractError(f"Rendered fields for {state_machine_id}.{state_name} require at least one {entity_type} fixture or precondition")


def _setup_has_entity_type(contract: dict[str, Any], fixture_ids: list[str], precondition_uses: list[dict[str, str]], entity_type_id: str) -> bool:
    return _fixtures_include_entity_type(contract, fixture_ids, entity_type_id) or _precondition_uses_include_entity_type(contract, precondition_uses, entity_type_id)


def _fixtures_include_entity_type(contract: dict[str, Any], fixture_ids: list[str], entity_type_id: str) -> bool:
    for fixture_id in fixture_ids:
        if fixture_id in contract.get("fixtures", {}) and _value_contains_entity_type(contract["fixtures"][fixture_id]["values"], entity_type_id):
            return True
    return False


def _precondition_uses_include_entity_type(contract: dict[str, Any], precondition_uses: list[dict[str, str]], entity_type_id: str) -> bool:
    for precondition_use in precondition_uses:
        precondition_id = precondition_use["ref"]
        precondition = contract["preconditions"].get(precondition_id)
        if not precondition:
            continue
        kind, body = _one_predicate(precondition, f"Precondition {precondition_id}")
        if kind == "present" and body["entity_type"] == entity_type_id:
            return True
    return False


def _all_precondition_uses(contract: dict[str, Any]) -> list[dict[str, str]]:
    return [{"ref": precondition_id} for precondition_id in contract.get("preconditions", {})]


def _value_contains_entity_type(value: Any, entity_type_id: str) -> bool:
    if isinstance(value, dict):
        if value.get("entity_type") == entity_type_id:
            return True
        return any(_value_contains_entity_type(child, entity_type_id) for child in value.values())
    if isinstance(value, list):
        return any(_value_contains_entity_type(item, entity_type_id) for item in value)
    return False


def _validate_entity_types(contract: dict[str, Any]) -> None:
    for rid, entity_type in contract["entity_types"].items():
        if not rid.startswith("entity_type."):
            raise ContractError(f"Entity type id must start with entity_type.: {rid}")
        expected_name = entity_type_display_name(rid)
        if entity_type["name"] != expected_name:
            raise ContractError(f"Entity type {rid} name must be {expected_name}")
        entity_lifecycle = entity_type.get("entity_lifecycle")
        if not entity_lifecycle:
            continue
        if entity_lifecycle["field"] not in _schema_fields(entity_type["schema"]):
            raise ContractError(f"Entity type {rid} entity_lifecycle field is not a field: {entity_lifecycle['field']}")
        states = set(entity_lifecycle["lifecycle_states"])
        if entity_lifecycle["initial_state"] not in states:
            raise ContractError(f"Entity type {rid} initial lifecycle_state is not declared: {entity_lifecycle['initial_state']}")
        for entity_lifecycle_transition in entity_lifecycle.get("lifecycle_transitions", []):
            if entity_lifecycle_transition["from"] not in states or entity_lifecycle_transition["to"] not in states:
                raise ContractError(f"Entity type {rid} entity_lifecycle_transition uses unknown lifecycle_state: {entity_lifecycle_transition}")
            if entity_lifecycle_transition["command"] not in _command_query_map(contract):
                raise ContractError(
                    f"Entity type {rid} entity_lifecycle_transition references unknown command {entity_lifecycle_transition['command']}"
                )


def _validate_schemas(contract: dict[str, Any]) -> None:
    for schema_id, schema in contract.get("schemas", {}).items():
        if not schema_id.startswith("schema."):
            raise ContractError(f"Schema id must start with schema.: {schema_id}")
        if not _schema_fields(schema.get("schema")):
            raise ContractError(f"Schema {schema_id} must declare properties")


def _validate_type_references(contract: dict[str, Any]) -> None:
    for entity_type_id, entity_type in contract.get("entity_types", {}).items():
        _validate_type_reference(contract, f"Entity type {entity_type_id} schema", entity_type["schema"])
    for schema_id, schema in contract.get("schemas", {}).items():
        _validate_type_reference(contract, f"Schema {schema_id}", schema["schema"])
    for command_id, command in _command_query_map(contract).items():
        for field_name, schema in _command_input(command).items():
            _validate_type_reference(contract, f"Command {command_id} input {field_name}", schema)
        for outcome_id, outcome in command.get("outcomes", {}).items():
            _validate_type_reference(contract, f"Command {command_id} outcome {outcome_id}", outcome["result"])
    for state_machine_id, state_machine in contract.get("state_machines", {}).items():
        for field_name, field in _state_machine_context(state_machine).items():
            _validate_type_reference(contract, f"State machine {state_machine_id} context {field_name}", field)
    for domain_event_id, domain_event in contract.get("domain_events", {}).items():
        _validate_type_reference(contract, f"domain_event {domain_event_id} payload_schema", domain_event["payload_schema"])


def _validate_type_reference(contract: dict[str, Any], label: str, expr: Any) -> None:
    try:
        normalized = normalize_schema(expr)
    except SchemaExpressionError as exc:
        raise ContractError(f"{label} has invalid schema: {exc}") from exc
    for ref in sorted(referenced_named_types(normalized)):
        if ref.startswith("entity_type."):
            if ref not in contract["entity_types"]:
                raise ContractError(f"{label} references unknown entity_type {ref}")
        elif ref.startswith("schema."):
            if ref not in contract.get("schemas", {}):
                raise ContractError(f"{label} references unknown schema {ref}")
        else:
            raise ContractError(f"{label} references unknown schema ref {ref}")


def _validate_commands(contract: dict[str, Any]) -> None:
    entity_types = contract["entity_types"]
    commands = _command_query_map(contract)
    for command_id, behavior in commands.items():
        _validate_command_relationships(command_id, behavior, entity_types)
        _validate_command_authorization_outcomes(command_id, behavior)
        entity_lifecycle_transition = behavior.get("entity_lifecycle_transition")
        if entity_lifecycle_transition:
            entity_type_ref = entity_lifecycle_transition["entity_type"]
            entity_lifecycle = entity_types[entity_type_ref].get("entity_lifecycle")
            if not entity_lifecycle:
                raise ContractError(f"Command {command_id} declares entity_lifecycle_transition but {entity_type_ref} has no entity_lifecycle")
            if not any(
                transition["command"] == command_id
                for transition in entity_lifecycle.get("lifecycle_transitions", [])
            ):
                raise ContractError(f"entity_lifecycle_transition command {command_id} must be referenced by entity_lifecycle declarations")
            if entity_lifecycle_transition["field"] != entity_lifecycle["field"]:
                raise ContractError(f"Command {command_id} entity_lifecycle_transition field does not match entity_lifecycle")
            if entity_lifecycle_transition["from"] not in entity_lifecycle["lifecycle_states"] or entity_lifecycle_transition["to"] not in entity_lifecycle["lifecycle_states"]:
                raise ContractError(f"Command {command_id} entity_lifecycle_transition references unknown lifecycle_state")
    for rid, entity_type in entity_types.items():
        entity_lifecycle = entity_type.get("entity_lifecycle")
        if not entity_lifecycle:
            continue
        for entity_lifecycle_transition in entity_lifecycle.get("lifecycle_transitions", []):
            command = entity_lifecycle_transition["command"]
            behavior = commands[command]
            if behavior["behavior_kind"] != "entity_lifecycle_transition":
                raise ContractError(
                    f"Entity type {rid} entity_lifecycle_transition {command} must reference an entity_lifecycle_transition command"
                )
            lifecycle_transition_not_allowed = behavior["outcomes"].get("lifecycle_transition_not_allowed")
            if not lifecycle_transition_not_allowed or lifecycle_transition_not_allowed["kind"] != "failure":
                raise ContractError(
                    f"entity_lifecycle_transition command {command} referenced by entity_lifecycle must declare lifecycle_transition_not_allowed failure outcome"
                )
            behavior_transition = behavior.get("entity_lifecycle_transition")
            if not behavior_transition:
                raise ContractError(f"entity_lifecycle_transition command {command} must be referenced by entity_lifecycle declarations")
            if (
                behavior_transition["entity_type"] != rid
                or behavior_transition["from"] != entity_lifecycle_transition["from"]
                or behavior_transition["to"] != entity_lifecycle_transition["to"]
            ):
                raise ContractError(f"Entity type {rid} entity_lifecycle and command {command} disagree")
    for domain_event_id, domain_event in contract["domain_events"].items():
        for command_id in domain_event["emitted_by"]:
            if command_id not in commands:
                raise ContractError(f"domain_event {domain_event_id} emitted by unknown command {command_id}")


def _validate_command_relationships(command_id: str, behavior: dict[str, Any], entity_types: dict[str, Any]) -> None:
    _validate_command_query_outcomes(command_id, behavior)
    for field in ["creates", "reads", "updates", "deletes"]:
        for entity_type_id in behavior.get(field, []):
            if entity_type_id not in entity_types:
                raise ContractError(f"Command {command_id} {field} unknown entity_type {entity_type_id}")

    if "entity_lifecycle_transition" in behavior:
        entity_type_ref = behavior["entity_lifecycle_transition"]["entity_type"]
        if entity_type_ref not in entity_types:
            raise ContractError(f"Command {command_id} entity_lifecycle_transition references unknown entity_type {entity_type_ref}")

    behavior_kind = behavior["behavior_kind"]
    if behavior_kind != "query" and behavior.get("retryable") and not behavior.get("idempotent"):
        raise ContractError(f"Command {command_id} retryable requires idempotent true")
    if behavior_kind == "query":
        _reject_non_empty_relationships(command_id, behavior, {"creates", "updates", "deletes"})
        if "entity_lifecycle_transition" in behavior:
            raise ContractError(f"Query command {command_id} must not declare entity_lifecycle_transition")
        emitting_outcomes = sorted(outcome_id for outcome_id, outcome in behavior["outcomes"].items() if outcome.get("emits"))
        if emitting_outcomes:
            raise ContractError(f"Query command {command_id} must not emit domain events: {emitting_outcomes}")
        _validate_query_success_result(command_id, behavior)
    elif behavior_kind == "command":
        if "entity_lifecycle_transition" in behavior:
            raise ContractError(f"Only entity_lifecycle_transition commands may declare entity_lifecycle_transition: {command_id}")
    elif behavior_kind == "entity_lifecycle_transition":
        if "entity_lifecycle_transition" not in behavior:
            raise ContractError(f"entity_lifecycle_transition command {command_id} must be referenced by entity_lifecycle declarations")
        _reject_non_empty_relationships(command_id, behavior, {"creates", "reads", "updates", "deletes"})
        _require_output_entity_type(command_id, behavior, behavior["entity_lifecycle_transition"]["entity_type"])
    else:  # pragma: no cover - schema prevents this.
        raise ContractError(f"Unsupported behavior_kind {behavior_kind}: {command_id}")


def _require_relationship(command_id: str, behavior: dict[str, Any], field: str) -> None:
    if not behavior.get(field):
        raise ContractError(f"Command {command_id} behavior_kind {behavior['behavior_kind']} must declare {field}")


def _require_exact_relationship(command_id: str, behavior: dict[str, Any], field: str, count: int) -> None:
    _require_relationship(command_id, behavior, field)
    actual = len(behavior[field])
    if actual != count:
        raise ContractError(f"Command {command_id} behavior_kind {behavior['behavior_kind']} must declare exactly {count} {field}")


def _reject_non_empty_relationships(command_id: str, behavior: dict[str, Any], fields: set[str]) -> None:
    extras = sorted(field for field in fields if behavior.get(field))
    if extras:
        raise ContractError(f"Command {command_id} behavior_kind {behavior['behavior_kind']} does not support entity_changes: {extras}")


def _require_output_entity_type(command_id: str, behavior: dict[str, Any], expected_entity_type: str) -> None:
    if entity_type_id(_success_result_type(behavior)) != expected_entity_type:
        raise ContractError(f"Command {command_id} success outcome result must be {expected_entity_type}")


def _validate_query_success_result(command_id: str, behavior: dict[str, Any]) -> None:
    reads = behavior.get("reads", [])
    if len(reads) != 1:
        return
    expected_entity_type = reads[0]
    result_type = _success_result_type(behavior)
    if entity_type_id(result_type) == expected_entity_type or is_array_of_entity_type(result_type, expected_entity_type):
        return
    raise ContractError(
        f"Command {command_id} query success outcome result must be {expected_entity_type} "
        f"or {type_display(array_of({'$ref': expected_entity_type}))}"
    )


def _validate_command_query_outcomes(command_id: str, behavior: dict[str, Any]) -> None:
    outcomes = behavior["outcomes"]
    successes = _success_outcomes(behavior)
    failures = _failure_outcomes(behavior)
    if len(successes) != 1:
        raise ContractError(f"Command {command_id} must declare exactly one success outcome")
    if not failures:
        raise ContractError(f"Command {command_id} must declare at least one failure outcome")
    unknown_kinds = sorted(
        f"{name}:{outcome['kind']}" for name, outcome in outcomes.items() if outcome["kind"] not in {"success", "failure"}
    )
    if unknown_kinds:
        raise ContractError(f"Command {command_id} has unsupported outcome kinds: {unknown_kinds}")
    for outcome_id, outcome in outcomes.items():
        emits = outcome.get("emits", [])
        emit_ids = [_emit_domain_event_id(emit) for emit in emits]
        if len(emit_ids) != len(set(emit_ids)):
            raise ContractError(f"Command {command_id} outcome {outcome_id} emits duplicate domain events")
        if outcome["kind"] == "failure":
            if emits:
                raise ContractError(f"Command {command_id} failure outcome {outcome_id} must not emit domain events")
            if not is_problem_type(outcome["result"]):
                raise ContractError(f"Command {command_id} failure outcome {outcome_id} result must be Problem or a *Problem type")


def _validate_command_authorization_outcomes(command_id: str, command: dict[str, Any]) -> None:
    authorization = command.get("authorization")
    if not authorization:
        return
    authentication_required_as = authorization["authentication_required_as"]
    access_denied_as = authorization["access_denied_as"]
    if authentication_required_as == access_denied_as:
        raise ContractError(
            f"Command {command_id} authorization authentication_required_as and access_denied_as must be distinct outcomes"
        )
    for field in ("authentication_required_as", "access_denied_as"):
        outcome_id = authorization[field]
        outcome = command["outcomes"].get(outcome_id)
        if not outcome:
            raise ContractError(
                f"Command {command_id} authorization.{field} references unknown outcome {outcome_id}"
            )
        if outcome["kind"] != "failure":
            raise ContractError(
                f"Command {command_id} authorization.{field} must map to a failure outcome: {outcome_id}"
            )
        if outcome.get("emits"):
            raise ContractError(
                f"Command {command_id} authorization.{field} outcome {outcome_id} must not emit domain events"
            )


def _validate_access_policies(contract: dict[str, Any]) -> None:
    access_policies = contract["access_policies"]
    commands = _command_query_map(contract)
    external_interfaces = contract["external_interfaces"]
    _validate_access_policy_reuse(access_policies)
    for command_id, command in commands.items():
        authorization = command.get("authorization")
        if not authorization:
            continue
        policy_id = authorization["policy"]
        if policy_id not in access_policies:
            raise ContractError(f"Command {command_id} authorization.policy references unknown access policy {policy_id}")
        if not _access_policy_covers_resource(access_policies[policy_id], "query" if command_id.startswith("query.") else "command", command_id):
            raise ContractError(f"Command {command_id} authorization.policy {policy_id} must cover command or query resource")
    for external_interface_id, external_interface in external_interfaces.items():
        policy_id = external_interface.get("access_policy")
        if not policy_id:
            continue
        if policy_id not in access_policies:
            raise ContractError(f"External interface {external_interface_id} references unknown access policy {policy_id}")
        invoked_kind, invoked_ref = external_interface_invoked_ref_pair(external_interface)
        if not _access_policy_covers_resource(access_policies[policy_id], "external_interface", external_interface_id) and not _access_policy_covers_resource(access_policies[policy_id], invoked_kind, invoked_ref):
            raise ContractError(f"External interface {external_interface_id} access_policy {policy_id} must cover external interface or invoked resource")
    for policy_id, policy in access_policies.items():
        rule_effect = {rule["effect"] for rule in policy.get("rules", [])}
        if policy["combining_algorithm"] == "all_permit_rules_must_match" and rule_effect != {"permit"}:
            raise ContractError(f"Access policy {policy_id} combining_algorithm all_permit_rules_must_match requires rule_effect permit")
        if not policy["resource"] and not policy["action"]:
            raise ContractError(f"Access policy {policy_id} must cover at least one resource or action")
        for action in policy["action"]:
            if action not in commands:
                raise ContractError(f"Access policy {policy_id} action references unknown command or query {action}")
        for resource in policy["resource"]:
            kind, ref = _one(resource, f"Access policy {policy_id} resource")
            if kind == "entity_type" and ref not in contract["entity_types"]:
                raise ContractError(f"Access policy {policy_id} resource references unknown entity_type {ref}")
            if kind == "external_interface" and ref not in external_interfaces:
                raise ContractError(f"Access policy {policy_id} resource references unknown external interface {ref}")
        for rule in policy.get("environment", []):
            _validate_access_policy_condition(contract, external_interfaces, policy_id, rule, f"Access policy {policy_id} environment")
        for rule in policy.get("rules", []):
            _validate_access_policy_condition(contract, external_interfaces, policy_id, rule["condition"], f"Access policy {policy_id} rule")


def _validate_access_policy_condition(
    contract: dict[str, Any],
    external_interfaces: dict[str, Any],
    policy_id: str,
    rule: dict[str, Any],
    label: str,
) -> None:
    kind, body = _one(rule, label)
    if kind in {"unconditional", "input_present", "subject_has_role", "value_equals"}:
        return
    if kind in {"entity_exists", "entity_state_condition"}:
        entity_type_id = body["entity_type"]
        if entity_type_id not in contract["entity_types"]:
            raise ContractError(f"Access policy {policy_id} rule references unknown entity_type {entity_type_id}")
        if kind == "entity_state_condition" and body["field"] not in _schema_fields(contract["entity_types"][entity_type_id]["schema"]):
            raise ContractError(f"Access policy {policy_id} rule references unknown {entity_type_id} field {body['field']}")
        return
    raise ContractError(f"Access policy {policy_id} rule is unsupported: {kind}")


def _validate_access_policy_reuse(access_policies: dict[str, Any]) -> None:
    fingerprints: dict[str, str] = {}
    for policy_id, policy in access_policies.items():
        fingerprint = _access_policy_rule_fingerprint(policy)
        existing = fingerprints.get(fingerprint)
        if existing:
            raise ContractError(
                f"Access policies {existing} and {policy_id} have identical subject, resource, action, environment, combining behavior, and rules; "
                "reuse one access_policy with combined resource/action coverage instead of duplicating rule sets"
            )
        fingerprints[fingerprint] = policy_id


def _access_policy_rule_fingerprint(policy: dict[str, Any]) -> str:
    subject = sorted(_canonical_json(subject_item) for subject_item in policy.get("subject", []))
    resource = sorted(_canonical_json(resource_item) for resource_item in policy.get("resource", []))
    action = sorted(policy.get("action", []))
    rules = sorted(_canonical_json(rule) for rule in policy.get("rules", []))
    environment = sorted(_canonical_json(rule) for rule in policy.get("environment", []))
    return _canonical_json(
        {
            "subject": subject,
            "resource": resource,
            "action": action,
            "environment": environment,
            "combining_algorithm": policy.get("combining_algorithm"),
            "rules": rules,
        }
    )


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _authorization_resource_kind(kind: str) -> str:
    return "action" if kind in {"command", "query"} else kind


def _access_policy_covers_resource(policy: dict[str, Any], kind: str, ref: str) -> bool:
    resource_kind = _authorization_resource_kind(kind)
    if resource_kind == "action":
        return ref in policy.get("action", [])
    return any(resource == {resource_kind: ref} for resource in policy.get("resource", []))


def _authorization_assertion_resource(assertion: dict[str, Any], label: str) -> tuple[str, str]:
    items = [(key, assertion[key]) for key in ("command", "external_interface") if key in assertion]
    if len(items) != 1:
        raise ContractError(f"{label} must contain exactly one authorization resource")
    return items[0]


def _validate_emit_payload_mapping(
    contract: dict[str, Any],
    command_id: str,
    command: dict[str, Any],
    outcome_id: str,
    outcome: dict[str, Any],
    domain_event_id: str,
    event_payload: Any,
    emit: Any,
) -> None:
    label = f"Command {command_id} outcome {outcome_id} emit {domain_event_id}"
    source_scopes: TypeScopes = {
        "command_input": _type_scope(_command_input(command)),
        "command_outcome": _typed_source_paths(contract, ("result",), outcome["result"]),
    }

    if isinstance(emit, str):
        if not type_equals(event_payload, outcome["result"]):
            raise ContractError(
                f"{label} must declare payload mapping because domain-event payload is "
                f"{type_display(event_payload)}, not {type_display(outcome['result'])}"
            )
        return

    has_payload = "payload_source" in emit
    has_payload_bindings = "payload_bindings" in emit
    if has_payload == has_payload_bindings:
        raise ContractError(f"{label} must declare exactly one of payload_source or payload_bindings")
    if has_payload:
        source = emit["payload_source"]
        actual = _reference_expression_type(contract, f"{label} payload source", source, source_scopes)
        if not type_equals(actual, event_payload):
            raise ContractError(f"{label} payload source {source} type must be {type_display(event_payload)}, got {type_display(actual)}")
        return

    _validate_mapping_to_type(contract, label, emit["payload_bindings"], event_payload, source_scopes)


def _validate_state_machines(contract: dict[str, Any]) -> None:
    for state_machine_id, state_machine in contract["state_machines"].items():
        if not state_machine_id.startswith("state_machine."):
            raise ContractError(f"state machine id must start with state_machine.: {state_machine_id}")
        entity_type = state_machine.get("entity_type")
        if entity_type and entity_type not in contract["entity_types"]:
            raise ContractError(f"state machine {state_machine_id} references unknown entity_type {entity_type}")
        _validate_query_bindings(
            contract,
            f"state machine {state_machine_id}",
            state_machine,
            state_machine.get("query_bindings", {}),
            scope="state_machine",
            entity_type=entity_type,
        )
        if state_machine["initial_state"] not in state_machine["states"]:
            raise ContractError(f"state machine {state_machine_id} initial state is not declared: {state_machine['initial_state']}")
        entity_type_fields = set(_schema_fields(contract["entity_types"][entity_type]["schema"])) if entity_type else set()
        field_names = entity_type_fields | set(_state_machine_context(state_machine))
        for state_name, state in state_machine["states"].items():
            _validate_state_machine_state(
                contract,
                f"state machine {state_machine_id}",
                state_machine,
                state_name,
                state,
                field_names=field_names,
                data_context=_state_machine_context(state_machine),
                entity_type=entity_type,
            )
            if state.get("child_state_machines") or state.get("renderers") or state.get("local_signal_sync_rules"):
                _validate_state_composition(contract, state_machine_id, state_machine, state_name, state)
        _validate_query_binding_id_scope(state_machine_id, state_machine)
        _validate_field_state_data_sources(
            contract,
            f"state machine {state_machine_id}",
            state_machine,
            state_machine["states"],
            state_machine.get("query_bindings", {}),
            set(_state_machine_context(state_machine)),
        )
        _validate_collection_empty_signal_local_effects(state_machine_id, state_machine)
        _validate_machine_query_ownership(contract, state_machine_id, state_machine)
        _validate_state_machine_transitions(contract, state_machine_id, state_machine)
        _validate_signals(state_machine_id, state_machine)


def _validate_state_machine_state(
    contract: dict[str, Any],
    owner_label: str,
    state_machine: dict[str, Any],
    state_name: str,
    state: dict[str, Any],
    field_names: set[str],
    data_context: dict[str, Any] | None = None,
    entity_type: str | None = None,
) -> None:
    _validate_query_bindings(
        contract,
        f"{owner_label}.{state_name}",
        state_machine,
        state.get("query_bindings", {}),
        scope="state",
        entity_type=entity_type,
        state=state,
    )
    for field in state.get("fields", []):
        if field not in field_names:
            raise ContractError(f"{owner_label}.{state_name} field slot is not declared on the entity_type/context: {field}")
    _validate_command_bindings(contract, owner_label, state_machine, state_name, state)
    _validate_presentation(contract, owner_label, field_names, state_name, state)


def _validate_command_bindings(
    contract: dict[str, Any],
    owner_label: str,
    state_machine: dict[str, Any],
    state_name: str,
    state: dict[str, Any],
) -> None:
    context = _state_machine_context(state_machine)
    for invocation_id, invocation in sorted((state.get("command_bindings") or {}).items()):
        label = f"{owner_label}.{state_name} command_binding {invocation_id}"
        command_id = _invocation_command_or_query_ref(invocation)
        if command_id not in _command_query_map(contract):
            raise ContractError(f"{label} references unknown command {command_id}")
        command = _command_query_map(contract)[command_id]
        expected_input = _command_input(command)
        bindings = invocation.get("input_mapping") or {}
        _validate_binding_map(
            contract,
            f"{label} input_mapping",
            bindings,
            expected_input,
            {"state_context": _type_scope(context), "principal": ACTOR_SOURCE_SCOPE},
        )
        _lint_literal_actor_bindings(label, bindings)
        _validate_command_binding_local_effects(contract, label, state_machine, invocation, command_id, command)


def _lint_literal_actor_bindings(label: str, bindings: dict[str, Any]) -> None:
    for field_name, binding in sorted(bindings.items()):
        if field_name not in ACTOR_LITERAL_FIELD_NAMES:
            continue
        if isinstance(binding, dict) and set(binding) == {"value"} and isinstance(binding["value"], str):
            warnings.warn(
                f"{label} input_mapping.{field_name} uses a literal actor/user id; prefer $principal.id or an explicit context binding",
                ContractLintWarning,
                stacklevel=3,
            )


def _validate_command_binding_local_effects(
    contract: dict[str, Any],
    label: str,
    state_machine: dict[str, Any],
    invocation: dict[str, Any],
    command_id: str,
    command: dict[str, Any],
) -> None:
    local_effects = invocation["local_effects"]
    expected_outcomes = set(command["outcomes"])
    actual_outcomes = set(local_effects)
    if actual_outcomes != expected_outcomes:
        missing = sorted(expected_outcomes - actual_outcomes)
        extra = sorted(actual_outcomes - expected_outcomes)
        parts = []
        if missing:
            parts.append("missing: " + ", ".join(missing))
        if extra:
            parts.append("extra: " + ", ".join(extra))
        raise ContractError(f"{label} local_effects must exactly map command outcomes" + (": " + "; ".join(parts) if parts else ""))

    for outcome_id, effect in sorted(local_effects.items()):
        effect_label = f"{label} local_effects.{outcome_id}"
        outcome = command["outcomes"][outcome_id]
        if _validate_no_local_effect(
            effect_label,
            outcome,
            effect,
            effect_scope="command_binding",
            has_response_mapping_or_renderer_surface=_command_has_response_mapping_or_renderer_surface(contract, command_id, outcome_id),
            authorization_outcome=outcome_id in _command_authorization_outcomes(command),
        ):
            continue
        signal = effect.get("raise")
        if not signal:
            raise ContractError(f"{effect_label} must raise a local signal or declare no_local_effect")
        _lint_mutation_loaded_signal(effect_label, command, signal, effect)
        payload = _state_machine_signal_payload(
            state_machine,
            "accepts",
            _signal_raise_selector(signal),
            f"{effect_label} raise",
        )
        _validate_optional_payload_bindings(
            contract=contract,
            label=f"{effect_label} raise payload_bindings",
            bindings=signal.get("payload_bindings"),
            payload=payload,
            scopes=_local_outcome_effect_scopes(state_machine, command, outcome, outcome_root="command_outcome", binding_root="command_binding"),
        )


def _lint_mutation_loaded_signal(label: str, command: dict[str, Any], signal: dict[str, Any], effect: dict[str, Any]) -> None:
    data_refresh_signal = signal.get("data_refresh_signal")
    if command.get("behavior_kind") not in {"command", "entity_lifecycle_transition"} or not data_refresh_signal:
        return
    if data_refresh_signal == "loaded" or data_refresh_signal.endswith("_loaded"):
        has_loaded_payload = bool(signal.get("payload_bindings")) or "result_binding" in effect or "context_updates" in effect
        if not has_loaded_payload:
            warnings.warn(
                f"{label} raises data-refresh signal {data_refresh_signal!r} from a mutation without binding loaded data; prefer changed/invalidated/completed local_signals and query refresh",
                ContractLintWarning,
                stacklevel=3,
            )


def _validate_no_local_effect(
    label: str,
    outcome: dict[str, Any],
    effect: dict[str, Any],
    *,
    effect_scope: str,
    has_response_mapping_or_renderer_surface: bool = False,
    has_query_refresh: bool = False,
    has_result_binding: bool = False,
    has_data_effect: bool = False,
    authorization_outcome: bool = False,
) -> bool:
    no_local_effect = effect.get("no_local_effect")
    if not no_local_effect:
        return False
    reason = no_local_effect.get("reason")
    if outcome.get("emits"):
        raise ContractError(f"{label} no_local_effect must not suppress durable command_outcome.emits")
    if reason == "handled_by_response_mapping" and not has_response_mapping_or_renderer_surface:
        raise ContractError(f"{label} no_local_effect.reason handled_by_response_mapping requires an adapter response mapping or renderer surface for this outcome")
    if reason == "handled_by_query_refresh" and not has_query_refresh:
        raise ContractError(f"{label} no_local_effect.reason handled_by_query_refresh requires an explicit query result binding or context refresh")
    if reason == "result_bound_without_signal" and not (has_result_binding or has_data_effect):
        raise ContractError(f"{label} no_local_effect.reason result_bound_without_signal requires result_binding or context/cache update")
    if authorization_outcome and effect_scope == "command_binding" and reason != "handled_by_response_mapping":
        raise ContractError(f"{label} authorization failure no_local_effect requires handled_by_response_mapping")
    if outcome.get("kind") == "failure":
        if reason == "handled_by_response_mapping":
            if not has_response_mapping_or_renderer_surface:
                raise ContractError(f"{label} failure outcome no_local_effect handled_by_response_mapping requires a proven response mapping")
            return True
        if reason != "intentionally_unobservable":
            raise ContractError(
                f"{label} failure outcome no_local_effect must use reason handled_by_response_mapping with a proven response mapping or intentionally_unobservable with rationale"
            )
        if not no_local_effect.get("rationale"):
            raise ContractError(f"{label} failure outcome no_local_effect must declare rationale")
    return True


def _command_authorization_outcomes(command: dict[str, Any]) -> set[str]:
    authorization = command.get("authorization") or {}
    return {value for key, value in authorization.items() if key in {"authentication_required_as", "access_denied_as"}}


def _command_has_response_mapping_or_renderer_surface(contract: dict[str, Any], command_id: str, outcome_id: str) -> bool:
    for external_interface_id in contract.get("external_interfaces", {}):
        if _external_interface_effective_command_ref(contract, external_interface_id) != command_id:
            continue
        if outcome_id in _external_interface_named_response_outcomes(contract, external_interface_id):
            return True
    return False


def _command_retryable(command: dict[str, Any]) -> bool:
    return command.get("behavior_kind") == "query" or bool(command.get("retryable"))


def _external_interface_retryable(contract: dict[str, Any], external_interface_id: str) -> bool:
    external_interface = contract["external_interfaces"][external_interface_id]
    target_kind, target_ref = external_interface_invoked_ref_pair(external_interface)
    if target_kind in {"command", "query"}:
        return bool(external_interface.get("retryable")) and _command_retryable(_command_query_map(contract)[target_ref])
    if target_kind == "external_interface":
        return bool(external_interface.get("retryable")) and _external_interface_retryable(contract, target_ref)
    if target_kind == "workflow":
        return bool(external_interface.get("retryable"))
    return bool(external_interface.get("retryable"))


def _local_outcome_effect_scopes(
    state_machine: dict[str, Any],
    command: dict[str, Any],
    outcome: dict[str, Any],
    *,
    outcome_root: str,
    binding_root: str,
) -> TypeScopes:
    command_input = _command_input(command)
    invocation_scope = {("input",): command.get("input", EMPTY_OBJECT_SCHEMA)}
    invocation_scope.update(_prefixed_type_scope(("input",), command_input))
    return {
        outcome_root: {
            ("kind",): {"type": "string"},
            ("result",): outcome["result"],
        },
        binding_root: invocation_scope,
        "state_context": _type_scope(_state_machine_context(state_machine)),
    }


def _validate_query_binding_id_scope(state_machine_id: str, state_machine: dict[str, Any]) -> None:
    owner_ids = set(state_machine.get("query_bindings", {}))
    for state_name, state in state_machine.get("states", {}).items():
        overlap = sorted(owner_ids & set(state.get("query_bindings", {})))
        if overlap:
            raise ContractError(
                f"state machine {state_machine_id}.{state_name} query_bindings duplicate state-machine-scope ids: {overlap}"
            )


def _validate_query_bindings(
    contract: dict[str, Any],
    owner_label: str,
    state_machine: dict[str, Any],
    invocations: dict[str, Any],
    *,
    scope: str,
    entity_type: str | None = None,
    state: dict[str, Any] | None = None,
) -> None:
    context = _state_machine_context(state_machine)
    for invocation_id, invocation in sorted((invocations or {}).items()):
        label = f"{owner_label} query_binding {invocation_id}"
        if scope == "state_machine" and "result_scope" not in invocation:
            raise ContractError(f"{label} state-machine-level query_binding must declare result_scope")
        if invocation.get("result_scope") in {"shared", "prefetch"} and not invocation.get("rationale"):
            raise ContractError(f"{label} result_scope {invocation['result_scope']} must declare rationale")
        if scope == "state_machine" and _query_binding_has_result_bound_no_local_effect(invocation) and invocation.get("result_scope") not in {"shared", "prefetch"}:
            raise ContractError(f"{label} result_binding with no_local_effect must declare result_scope shared or prefetch")
        behavior_ref = _invocation_command_or_query_ref(invocation)
        if behavior_ref not in _command_query_map(contract):
            raise ContractError(f"{label} references unknown query {behavior_ref}")
        command = _command_query_map(contract)[behavior_ref]
        if command["behavior_kind"] != "query":
            raise ContractError(f"{label} must reference a query")
        if command.get("creates") or command.get("updates") or command.get("deletes"):
            raise ContractError(f"{label} query must not create, update, or delete entity_types")
        if command.get("entity_lifecycle_transition"):
            raise ContractError(f"{label} query must not be an entity_lifecycle_transition")
        emitting_outcomes = sorted(
            outcome_id
            for outcome_id, outcome in command.get("outcomes", {}).items()
            if outcome.get("emits")
        )
        if emitting_outcomes:
            raise ContractError(f"{label} query outcomes must not emit durable domain events: {emitting_outcomes}")
        if entity_type and not (
            entity_type_id(command.get("result_schema", EMPTY_OBJECT_SCHEMA)) == entity_type
            or is_array_of_entity_type(command.get("result_schema", EMPTY_OBJECT_SCHEMA), entity_type)
            or any(
                entity_type_id(outcome["result"]) == entity_type or is_array_of_entity_type(outcome["result"], entity_type)
                for outcome in command.get("outcomes", {}).values()
                if outcome["kind"] == "success"
            )
        ):
            raise ContractError(f"{label} query result_schema must return entity_type {entity_type}")
        _validate_binding_map(
            contract,
            f"{label} input_mapping",
            invocation.get("input_mapping") or {},
            _command_input(command),
            {"state_context": _type_scope(context), "principal": ACTOR_SOURCE_SCOPE},
        )
        _validate_query_load_policy(contract, label, state_machine, invocation.get("load") or {}, scope=scope)
        _validate_query_binding_local_effects(contract, label, state_machine, invocation, command, scope=scope, state=state)


def _validate_query_load_policy(
    contract: dict[str, Any],
    label: str,
    state_machine: dict[str, Any],
    load: dict[str, Any],
    *,
    scope: str,
) -> None:
    if scope == "state_machine" and load.get("on_enter"):
        raise ContractError(f"{label} state-machine-level load policy must use on_start or on_mount, not on_enter")
    if scope == "state" and (load.get("on_start") or load.get("on_mount")):
        raise ContractError(f"{label} view-state-level load policy must use on_enter, not on_start or on_mount")
    for trigger in load.get("refresh_on", []):
        _state_machine_signal_payload(state_machine, "accepts", trigger, f"{label} load.refresh_on")


def _validate_query_binding_local_effects(
    contract: dict[str, Any],
    label: str,
    state_machine: dict[str, Any],
    invocation: dict[str, Any],
    command: dict[str, Any],
    *,
    scope: str,
    state: dict[str, Any] | None,
) -> None:
    local_effects = invocation["local_effects"]
    expected_outcomes = set(command["outcomes"])
    actual_outcomes = set(local_effects)
    if actual_outcomes != expected_outcomes:
        missing = sorted(expected_outcomes - actual_outcomes)
        extra = sorted(actual_outcomes - expected_outcomes)
        parts = []
        if missing:
            parts.append("missing: " + ", ".join(missing))
        if extra:
            parts.append("extra: " + ", ".join(extra))
        raise ContractError(f"{label} local_effects must exactly map query outcomes" + (": " + "; ".join(parts) if parts else ""))

    for outcome_id, effect in sorted(local_effects.items()):
        outcome = command["outcomes"][outcome_id]
        effect_label = f"{label} local_effects.{outcome_id}"
        if "conditional_local_effects" in effect:
            if any(key in effect for key in ("context_updates", "result_binding", "raise", "no_local_effect")):
                raise ContractError(f"{effect_label} conditional_local_effects must not be mixed with top-level local outcome effects")
            _validate_query_conditional_local_effects(
                contract,
                effect_label,
                state_machine,
                invocation,
                command,
                outcome_id,
                outcome,
                scope=scope,
                state=state,
            )
            continue
        _validate_query_local_outcome_effect(
            contract,
            effect_label,
            state_machine,
            invocation,
            command,
            outcome_id,
            outcome,
            effect,
            scope=scope,
            state=state,
        )
    if all(_query_local_outcome_is_only_no_local_effect(effect) for effect in local_effects.values()):
        raise ContractError(f"{label} query_binding has only no_local_effect local outcome effects and no explicit result binding, context update, or signal")


def _validate_query_conditional_local_effects(
    contract: dict[str, Any],
    effect_label: str,
    state_machine: dict[str, Any],
    invocation: dict[str, Any],
    command: dict[str, Any],
    outcome_id: str,
    outcome: dict[str, Any],
    *,
    scope: str,
    state: dict[str, Any] | None,
) -> None:
    result_conditions: list[str] = []
    for index, branch in enumerate(invocation["local_effects"][outcome_id]["conditional_local_effects"]):
        condition = branch["result_condition"]
        branch_label = f"{effect_label}.conditional_local_effects[{index}].{condition}"
        if condition in result_conditions:
            raise ContractError(f"{effect_label} conditional_local_effects duplicate condition: {condition}")
        result_conditions.append(condition)
        if condition in {"empty", "non_empty"} and not _type_supports_emptiness(outcome["result"]):
            raise ContractError(f"{branch_label} is valid only for array/list query results")
        _validate_query_local_outcome_effect(
            contract,
            branch_label,
            state_machine,
            invocation,
            command,
            outcome_id,
            outcome,
            branch,
            scope=scope,
            state=state,
        )
    if set(result_conditions) != {"empty", "non_empty"}:
        raise ContractError(f"{effect_label} conditional_local_effects for empty/non-empty result handling must declare both empty and non_empty branches")


def _validate_query_local_outcome_effect(
    contract: dict[str, Any],
    effect_label: str,
    state_machine: dict[str, Any],
    invocation: dict[str, Any],
    command: dict[str, Any],
    outcome_id: str,
    outcome: dict[str, Any],
    effect: dict[str, Any],
    *,
    scope: str,
    state: dict[str, Any] | None,
) -> None:
        scopes = _local_outcome_effect_scopes(state_machine, command, outcome, outcome_root="query_outcome", binding_root="query_binding")
        has_context_updates = bool(effect.get("context_updates"))
        has_result_binding = "result_binding" in effect
        has_raise = "raise" in effect
        if not any((has_context_updates, has_result_binding, has_raise, "no_local_effect" in effect)):
            raise ContractError(f"{effect_label} must declare context_updates, result_binding, raise, or no_local_effect")
        for field, binding in (effect.get("context_updates") or {}).items():
            context = _state_machine_context(state_machine)
            if field not in context:
                raise ContractError(f"{effect_label} context_updates references undeclared context field: {field}")
            _validate_expression_type(
                contract,
                f"{effect_label} context_updates.{field}",
                binding,
                context[field],
                scopes,
                allow_null_source=False,
            )
        result_binding = effect.get("result_binding")
        if result_binding:
            data_key = result_binding["data_key"]
            if data_key in _state_machine_context(state_machine):
                raise ContractError(f"{effect_label} result_binding.data_key {data_key!r} conflicts with state-machine context field")
            _expression_type(
                contract,
                result_binding["from"],
                scopes,
                f"{effect_label} result_binding.{data_key}",
            )
        has_result_consumption = bool(result_binding) and _query_result_binding_consumed(
            contract,
            state_machine,
            invocation,
            outcome,
            result_binding,
            scope=scope,
            state=state,
        )
        has_query_refresh = has_result_binding or has_context_updates
        _validate_no_local_effect(
            effect_label,
            outcome,
            effect,
            effect_scope="query_binding",
            has_response_mapping_or_renderer_surface=_command_has_response_mapping_or_renderer_surface(contract, _invocation_command_or_query_ref(invocation), outcome_id),
            has_query_refresh=has_query_refresh,
            has_result_binding=has_result_binding,
            has_data_effect=has_context_updates,
            authorization_outcome=outcome_id in _command_authorization_outcomes(command),
        )
        no_local_effect = effect.get("no_local_effect")
        if no_local_effect and no_local_effect.get("reason") == "result_bound_without_signal" and has_result_binding and not has_result_consumption:
            raise ContractError(f"{effect_label} no_local_effect.reason result_bound_without_signal requires consumed result data or declared shared/prefetch ownership")
        if outcome["kind"] == "success" and "no_local_effect" in effect and not any((has_context_updates, has_result_binding, has_raise)):
            if no_local_effect.get("reason") != "intentionally_unobservable" or not no_local_effect.get("rationale"):
                raise ContractError(f"{effect_label} successful query no_local_effect must bind/cache data, update context, raise a signal, or declare intentionally_unobservable with rationale")
        signal = effect.get("raise")
        if signal:
            payload = _state_machine_signal_payload(
                state_machine,
                "accepts",
                _signal_raise_selector(signal),
                f"{effect_label} raise",
            )
            _validate_optional_payload_bindings(
                contract=contract,
                label=f"{effect_label} raise payload_bindings",
                bindings=signal.get("payload_bindings"),
                payload=payload,
                scopes=scopes,
            )


def _query_local_outcome_is_only_no_local_effect(effect: dict[str, Any]) -> bool:
    branches = effect.get("conditional_local_effects") or [effect]
    return all("no_local_effect" in branch and not any(key in branch for key in ("context_updates", "result_binding", "raise")) for branch in branches)


def _type_supports_emptiness(schema: Any) -> bool:
    return schema_without_null(_effective_type(schema)).get("type") == "array"


def _result_type_has_field(contract: dict[str, Any], result_type: Any, field: str) -> bool:
    effective = schema_without_null(_effective_type(result_type))
    if effective.get("type") == "array":
        effective = schema_without_null(_effective_type(effective.get("items", {})))
    return field in object_fields_for_type(contract, effective)


def _query_result_binding_consumed(
    contract: dict[str, Any],
    state_machine: dict[str, Any],
    invocation: dict[str, Any],
    outcome: dict[str, Any],
    result_binding: dict[str, Any],
    *,
    scope: str,
    state: dict[str, Any] | None,
) -> bool:
    if invocation.get("result_scope") in {"shared", "prefetch"} and invocation.get("rationale"):
        return True
    if scope == "state" and state:
        return any(_result_type_has_field(contract, outcome["result"], field) for field in state.get("fields", []))
    return False


def _validate_field_state_data_sources(
    contract: dict[str, Any],
    owner_label: str,
    state_machine: dict[str, Any],
    states: dict[str, Any],
    owner_data: dict[str, Any],
    context_fields: set[str],
) -> None:
    owner_sources_by_field = _query_result_field_sources(contract, owner_data)
    for state_name, state in states.items():
        view_sources_by_field = _query_result_field_sources(contract, state.get("query_bindings", {}))
        for field in sorted(state.get("fields", [])):
            sources: set[str] = set()
            if field in context_fields:
                sources.add(f"context.{field}")
            sources.update(view_sources_by_field.get(field, set()))
            sources.update(owner_sources_by_field.get(field, set()))
            if not sources:
                raise ContractError(f"{owner_label}.{state_name} field slot {field} has no data source")
            if len(sources) > 1:
                raise ContractError(f"{owner_label}.{state_name} field slot {field} has ambiguous data sources: {sorted(sources)}")


def _query_result_field_sources(contract: dict[str, Any], invocations: dict[str, Any]) -> dict[str, set[str]]:
    sources: dict[str, set[str]] = {}
    commands = _command_query_map(contract)
    for invocation_id, invocation in sorted((invocations or {}).items()):
        command = commands.get(_invocation_command_or_query_ref(invocation))
        if not command:
            continue
        for outcome_id, effect in sorted((invocation.get("local_effects") or {}).items()):
            outcome = command.get("outcomes", {}).get(outcome_id)
            if not outcome:
                continue
            fields = object_fields_for_type(contract, _query_result_item_type(outcome["result"]))
            for branch in _query_local_outcome_effect_branches(effect):
                result_binding = branch.get("result_binding")
                if not result_binding:
                    continue
                source_label = f"query_binding {invocation_id} result_binding {result_binding['data_key']}"
                for field in fields:
                    sources.setdefault(field, set()).add(source_label)
    return sources


def _query_local_outcome_effect_branches(effect: dict[str, Any]) -> list[dict[str, Any]]:
    return list(effect.get("conditional_local_effects") or [effect])


def _query_result_item_type(result_type: Any) -> Any:
    effective = schema_without_null(_effective_type(result_type))
    if effective.get("type") == "array":
        return schema_without_null(_effective_type(effective.get("items", {})))
    return effective


def _validate_collection_empty_signal_local_effects(state_machine_id: str, state_machine: dict[str, Any]) -> None:
    for transition in state_machine.get("transitions", []):
        if not _is_data_refresh_signal(transition["trigger"]):
            continue
        signal_name = transition["trigger"]["data_refresh_signal"]
        if not _is_empty_collection_signal(signal_name):
            continue
        if not _query_local_effects_raise_data_refresh_signal(state_machine, signal_name):
            raise ContractError(
                f"state machine {state_machine_id} transition uses empty-collection signal data_refresh_signal.{signal_name} "
                "without an explicit query local outcome effect raising it"
            )


def _is_empty_collection_signal(signal_name: str) -> bool:
    return signal_name.endswith("_empty") or "collection_empty" in signal_name


def _query_local_effects_raise_data_refresh_signal(state_machine: dict[str, Any], signal_name: str) -> bool:
    for invocation in (state_machine.get("query_bindings") or {}).values():
        if _query_binding_raises_data_refresh_signal(invocation, signal_name):
            return True
    for state in state_machine.get("states", {}).values():
        for invocation in (state.get("query_bindings") or {}).values():
            if _query_binding_raises_data_refresh_signal(invocation, signal_name):
                return True
    return False


def _query_binding_raises_data_refresh_signal(invocation: dict[str, Any], signal_name: str) -> bool:
    for effect in (invocation.get("local_effects") or {}).values():
        for branch in _query_local_outcome_effect_branches(effect):
            signal = branch.get("raise") or {}
            if signal.get("data_refresh_signal") == signal_name:
                return True
    return False


def _validate_machine_query_ownership(contract: dict[str, Any], state_machine_id: str, state_machine: dict[str, Any]) -> None:
    owner_queries = state_machine.get("query_bindings") or {}
    if not owner_queries:
        return
    child_query_commands = _child_query_commands(contract, state_machine)
    for invocation_id, invocation in sorted(owner_queries.items()):
        label = f"state machine {state_machine_id} query_binding {invocation_id}"
        result_scope = invocation.get("result_scope")
        if _query_binding_has_result_bound_no_local_effect(invocation) and result_scope not in {"shared", "prefetch"}:
            raise ContractError(f"{label} result_binding with no_local_effect must declare result_scope shared or prefetch")
        if _invocation_command_or_query_ref(invocation) in child_query_commands and result_scope not in {"shared", "prefetch"}:
            raise ContractError(f"{label} duplicates child-owned query loading and must declare result_scope shared or prefetch")


def _child_query_commands(contract: dict[str, Any], state_machine: dict[str, Any]) -> set[str]:
    commands: set[str] = set()
    for state in state_machine.get("states", {}).values():
        for mount in state.get("child_state_machines", []):
            child = contract["state_machines"].get(mount["state_machine"])
            if not child:
                continue
            for invocation in (child.get("query_bindings") or {}).values():
                commands.add(_invocation_command_or_query_ref(invocation))
            for child_state in child.get("states", {}).values():
                for invocation in (child_state.get("query_bindings") or {}).values():
                    commands.add(_invocation_command_or_query_ref(invocation))
    return commands


def _query_binding_has_result_bound_no_local_effect(invocation: dict[str, Any]) -> bool:
    for effect in (invocation.get("local_effects") or {}).values():
        for branch in _query_local_outcome_effect_branches(effect):
            no_local_effect = branch.get("no_local_effect") or {}
            if branch.get("result_binding") and no_local_effect.get("reason") == "result_bound_without_signal":
                return True
    return False


def _validate_state_machine_transitions(contract: dict[str, Any], state_machine_id: str, state_machine: dict[str, Any]) -> None:
    states = set(state_machine["states"])
    for transition in state_machine.get("transitions", []):
        if transition["from"] not in states or transition["to"] not in states:
            raise ContractError(f"state machine {state_machine_id} transition uses unknown state: {transition}")
        if _is_data_refresh_signal(transition["trigger"]) and not _transition_data_bindings(state_machine, transition):
            raise ContractError(
                f"state machine {state_machine_id} transition uses data-refresh signal without state machine or source-state data: {_signal_label(transition['trigger'])}"
            )
        local_signal_payload = _state_machine_signal_payload(state_machine, "accepts", transition["trigger"], f"state machine {state_machine_id} transition signal")
        for effect in transition.get("local_effects", []):
            kind, body = _one(effect, f"state machine {state_machine_id} transition local_effect")
            if kind == "set":
                context = _state_machine_context(state_machine)
                if body["context"] not in context:
                    raise ContractError(f"state machine {state_machine_id} transition sets undeclared context: {body['context']}")
                binding = body["from"] if "from" in body else {"value": body.get("value")}
                _validate_expression_type(
                    contract,
                    f"state machine {state_machine_id} transition set {body['context']}",
                    binding,
                    context[body["context"]],
                    {"trigger": _prefixed_type_scope(("payload",), local_signal_payload), "state_context": _type_scope(context)},
                    allow_null_source=False,
                )
            elif kind == "emit":
                emitted_payload = _state_machine_signal_payload(state_machine, "emits", {"local_signal": body["local_signal"]}, f"state machine {state_machine_id} transition emit")
                _validate_payload_bindings(
                    contract=contract,
                    label=f"state machine {state_machine_id} transition emit {body['local_signal']} payload_bindings",
                    bindings=body["payload_bindings"],
                    payload=emitted_payload,
                    scopes={"trigger": _prefixed_type_scope(("payload",), local_signal_payload), "state_context": _type_scope(_state_machine_context(state_machine))},
                )
            else:  # pragma: no cover - schema prevents this.
                raise ContractError(f"state machine {state_machine_id} unsupported transition local_effect: {kind}")
    for transition in state_machine.get("transitions", []):
        if not _transition_has_audit_content(state_machine, transition):
            raise ContractError(
                f"state machine {state_machine_id} transition {_signal_label(transition['trigger'])} from {transition['from']} "
                f"to {transition['to']} must declare rationale, data, or local_effects"
            )


def _validate_signals(state_machine_id: str, state_machine: dict[str, Any]) -> None:
    local_signals = state_machine.get("local_signals", _empty_signals())
    _lint_signal_names(state_machine_id, state_machine, local_signals)
    declared_accepts = _declared_signal_keys(local_signals, "accepts")
    declared_emits = _declared_signal_keys(local_signals, "emits")
    ambiguous = sorted(declared_accepts & declared_emits)
    if ambiguous:
        raise ContractError(f"state machine {state_machine_id} declares state-machine signal as both accepted and emitted: {[_signal_label(item) for item in ambiguous]}")
    accepted = _state_machine_accepts(state_machine)
    emitted = _state_machine_emits(state_machine)
    orphan_accepts = sorted(declared_accepts - accepted)
    if orphan_accepts:
        raise ContractError(f"state machine {state_machine_id} declares accepted state-machine signal without transition: {[_signal_label(item) for item in orphan_accepts]}")
    orphan_emits = sorted(declared_emits - emitted)
    if orphan_emits:
        raise ContractError(f"state machine {state_machine_id} declares emitted state-machine signal without emit local_effect: {[_signal_label(item) for item in orphan_emits]}")
    undeclared_accepts = sorted(accepted - declared_accepts)
    if undeclared_accepts:
        raise ContractError(f"state machine {state_machine_id} accepts state-machine signal without declaring it: {[_signal_label(item) for item in undeclared_accepts]}")
    undeclared_emits = sorted(emitted - declared_emits)
    if undeclared_emits:
        raise ContractError(f"state machine {state_machine_id} emits state-machine signal without declaring it: {[_signal_label(item) for item in undeclared_emits]}")


def _lint_signal_names(state_machine_id: str, state_machine: dict[str, Any], local_signals: dict[str, Any]) -> None:
    states = set(state_machine.get("states", {}))
    local_signal_names = set(local_signals.get("accepts", {}).get("local_signals", {})) | set(local_signals.get("emits", {}).get("local_signals", {}))
    data_refresh_signal_specs = local_signals.get("accepts", {}).get("data_refresh_signals", {}) or {}
    data_refresh_signals = set(data_refresh_signal_specs)
    for name in sorted((local_signal_names | data_refresh_signals) & states):
        warnings.warn(
            f"state machine {state_machine_id} signal {name!r} also names a state; prefer occurrence-like names such as project_loaded, project_load_failed, collection_empty, or command_failed",
            ContractLintWarning,
            stacklevel=3,
        )
    for name, signal in sorted(data_refresh_signal_specs.items()):
        if name in {"ready", "error", "empty", "loaded"} and not signal.get("rationale"):
            warnings.warn(
                f"state machine {state_machine_id} data-refresh signal {name!r} is state-like; prefer occurrence-like names such as project_loaded, project_load_failed, collection_empty, or command_failed",
                ContractLintWarning,
                stacklevel=3,
            )
    for transition in state_machine.get("transitions", []):
        _, trigger_name = _signal_selector_key(transition["trigger"])
        if trigger_name == transition["to"]:
            warnings.warn(
                f"state machine {state_machine_id} transition trigger {trigger_name!r} matches state; prefer an occurrence-like trigger name",
                ContractLintWarning,
                stacklevel=3,
            )


def _declared_signal_keys(local_signals: dict[str, Any], direction: str) -> set[tuple[str, str]]:
    body = local_signals.get(direction) or {}
    keys = {("local_signal", name) for name in (body.get("local_signals") or {})}
    if direction == "accepts":
        keys.update(("data_refresh_signal", name) for name in (body.get("data_refresh_signals") or {}))
    return keys


def _validate_state_machine_signal_payload_consistency(contract: dict[str, Any]) -> None:
    declared: dict[str, tuple[str, str, dict[str, Any]]] = {}
    domain_events = set(contract.get("domain_events", {}))
    for state_machine_id, state_machine in contract.get("state_machines", {}).items():
        local_signals = state_machine.get("local_signals", _empty_signals())
        for direction, groups in (("accepts", ("local_signals", "data_refresh_signals")), ("emits", ("local_signals",))):
            for group in groups:
                for signal_id, signal in (local_signals.get(direction, {}).get(group) or {}).items():
                    kind = "local_signal" if group == "local_signals" else "data_refresh_signal"
                    signal_key = f"{kind}.{signal_id}"
                    if signal_key in domain_events:
                        raise ContractError(f"state-machine signal {signal_key} conflicts with domain event {signal_key}")
                    payload_schema = signal["payload_schema"]
                    payload = _signal_payload_fields(payload_schema)
                    existing = declared.get(signal_key)
                    if existing and (
                        set(existing[2]) != set(payload)
                        or any(not type_equals(existing[2][key], payload[key]) for key in payload)
                    ):
                        first_state_machine_id, first_direction, first_payload = existing
                        raise ContractError(
                            f"state-machine signal {signal_key} payload_schema differs between {first_state_machine_id}.{first_direction} "
                            f"and {state_machine_id}.{direction}: "
                            f"{ {key: type_display(value) for key, value in first_payload.items()} } vs "
                            f"{ {key: type_display(value) for key, value in payload.items()} }"
                        )
                    declared[signal_key] = (state_machine_id, direction, payload)


def _validate_state_composition(contract: dict[str, Any], state_machine_id: str, state_machine: dict[str, Any], state_name: str, state: dict[str, Any]) -> None:
    label = f"{state_machine_id}.{state_name}"
    parent_state_machine_id = state_machine_id
    parent_state_machine = state_machine
    if not any(renderer.get("layout") for renderer in (state.get("renderers") or {}).values()):
        raise ContractError(f"composed state machine state {label} must declare renderer layout")
    if not state.get("child_state_machines"):
        raise ContractError(f"composed state machine state {label} must mount at least one state machine")
    html_regions = set(renderer_html_regions(state))
    textual_containers = set(renderer_textual_containers(state))
    if not html_regions and not textual_containers:
        raise ContractError(f"composed state machine state {label} must declare renderer layout regions or containers")
    mounts: dict[str, dict[str, Any]] = {}
    for mount in state["child_state_machines"]:
        if mount["id"] in mounts:
            raise ContractError(f"composed state machine state {label} has duplicate state machine mount: {mount['id']}")
        mounts[mount["id"]] = mount
        if html_regions:
            html_region = mount.get("html_region")
            if html_region not in html_regions:
                raise ContractError(f"composed state machine state {label} mounts state machine in undeclared HTML region: {html_region}")
        if textual_containers:
            textual_container = mount.get("textual_container")
            if textual_container not in textual_containers:
                raise ContractError(f"composed state machine state {label} mounts state machine in undeclared Textual container: {textual_container}")
        child_state_machine_id = mount["state_machine"]
        if child_state_machine_id not in contract["state_machines"]:
            raise ContractError(f"composed state machine state {label} mounts unknown state machine: {child_state_machine_id}")
        child_state_machine = contract["state_machines"][child_state_machine_id]
        if mount["initial_state"] not in child_state_machine["states"]:
            raise ContractError(f"composed state machine state {label}.{mount['id']} initial state is unknown: {mount['initial_state']}")
        selected = mount.get("selected")
        if selected and selected["state"] not in child_state_machine["states"]:
            raise ContractError(f"composed state machine state {label}.{mount['id']} selected state is unknown: {selected['state']}")
        if selected:
            _validate_condition_context(contract, label, _state_machine_context(parent_state_machine), selected["condition"])
        mount_context = mount.get("context_bindings", {})
        child_context = _state_machine_context(child_state_machine)
        expected_context = _schema_required_fields(child_state_machine.get("context_schema"))
        unknown_context = sorted(set(mount_context) - set(child_context))
        missing_context = sorted(expected_context - set(mount_context))
        if unknown_context or missing_context:
            parts = []
            if missing_context:
                parts.append("missing required: " + ", ".join(missing_context))
            if unknown_context:
                parts.append("unknown: " + ", ".join(unknown_context))
            raise ContractError(
                f"composed state machine state {label}.{mount['id']} context bindings must satisfy state machine context"
                + (": " + "; ".join(parts) if parts else "")
            )
        _validate_state_machine_context_refs(
            contract,
            label,
            _state_machine_context(parent_state_machine),
            child_context,
            mount_context,
        )
    used_html_regions = {mount.get("html_region") for mount in state["child_state_machines"]}
    missing_html = [region for region, spec in renderer_html_regions(state).items() if spec.get("must_render") and region not in used_html_regions]
    if missing_html:
        raise ContractError(f"composed state machine state {label} missing must_render HTML regions: {missing_html}")
    used_textual_containers = {mount.get("textual_container") for mount in state["child_state_machines"]}
    missing_textual = [container for container, spec in renderer_textual_containers(state).items() if spec.get("must_render") and container not in used_textual_containers]
    if missing_textual:
        raise ContractError(f"composed state machine state {label} missing must_render Textual containers: {missing_textual}")
    _validate_renderer_layouts(label, state)
    _validate_sync_rules(contract, parent_state_machine_id, state_name, parent_state_machine, state, mounts)


def _validate_renderer_layouts(state_machine_id: str, state: dict[str, Any]) -> None:
    return None


def _validate_condition_context(contract: dict[str, Any], state_machine_id: str, context: dict[str, Any], condition: Any) -> None:
    comparisons: list[tuple[str, Any]] = []
    if isinstance(condition, dict):
        if "context_non_null" in condition:
            keys = [condition["context_non_null"]]
        elif "context_equals" in condition:
            keys = [condition["context_equals"]["field"]]
            comparisons.append((condition["context_equals"]["field"], condition["context_equals"]["value"]))
        else:
            keys = []
    elif is_binding_expression(condition):
        try:
            ref = parse_binding_expression(condition)
        except BindingExpressionError as exc:
            raise ContractError(f"composed state machine {state_machine_id} condition has malformed binding expression: {condition}") from exc
        if ref.root != "state_machine":
            raise ContractError(f"composed state machine {state_machine_id} condition references unavailable binding root: ${ref.root}")
        keys = [ref.path[0]]
    else:
        keys = []
    for key in keys:
        if key not in context:
            raise ContractError(f"composed state machine {state_machine_id} condition references undeclared context: {key}")
    for key, value in comparisons:
        _validate_expression_type(
            contract,
            f"composed state machine {state_machine_id} condition context_equals.{key}",
            {"value": value},
            context[key],
            {},
        )


def _validate_state_machine_context_refs(
    contract: dict[str, Any],
    state_machine_id: str,
    parent_context: dict[str, Any],
    child_context: dict[str, Any],
    mapping: dict[str, Any],
) -> None:
    scopes = {"state_machine": _type_scope(parent_context)}
    for key, value in mapping.items():
        actual_type = _expression_type(contract, value, scopes, f"composed state machine {state_machine_id} context {key}")
        if actual_type and _type_allows_null(actual_type) and not _type_allows_null(child_context[key]):
            raise ContractError(
                f"composed state machine {state_machine_id} context {key} cannot bind a source that allows null "
                f"to child context that does not allow null"
            )
        _validate_expression_type(
            contract,
            f"composed state machine {state_machine_id} context {key}",
            value,
            child_context[key],
            scopes,
        )


def _state_machine_emits(state_machine: dict[str, Any]) -> set[tuple[str, str]]:
    emits: set[tuple[str, str]] = set()
    for transition in state_machine.get("transitions", []):
        for effect in transition.get("local_effects", []):
            kind, body = _one(effect, "state_machine transition local_effect")
            if kind == "emit":
                emits.add(("local_signal", body["local_signal"]))
    return emits


def _state_machine_accepts(state_machine: dict[str, Any]) -> set[tuple[str, str]]:
    accepts = {_signal_selector_key(transition["trigger"]) for transition in state_machine.get("transitions", [])}
    for invocation in (state_machine.get("query_bindings") or {}).values():
        for trigger in (invocation.get("load") or {}).get("refresh_on", []):
            accepts.add(_signal_selector_key(trigger))
    for state in state_machine.get("states", {}).values():
        for invocation in (state.get("query_bindings") or {}).values():
            for trigger in (invocation.get("load") or {}).get("refresh_on", []):
                accepts.add(_signal_selector_key(trigger))
    return accepts


def _state_machine_signal_payload(state_machine: dict[str, Any], direction: str, selector: dict[str, str], label: str) -> dict[str, Any]:
    kind, signal_id = _signal_selector_key(selector)
    group = "local_signals" if kind == "local_signal" else "data_refresh_signals"
    signal = state_machine.get("local_signals", {}).get(direction, {}).get(group, {}).get(signal_id)
    if not signal:
        raise ContractError(f"{label} references undeclared state-machine signal: {_signal_label((kind, signal_id))}")
    return _signal_payload_fields(signal.get("payload_schema"))


def _validate_payload_bindings(
    contract: dict[str, Any] | None,
    label: str,
    bindings: dict[str, Any],
    payload: dict[str, Any],
    scopes: TypeScopes,
) -> None:
    actual = set(bindings)
    expected = set(payload)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        parts = []
        if missing:
            parts.append("missing: " + ", ".join(missing))
        if extra:
            parts.append("extra: " + ", ".join(extra))
        raise ContractError(f"{label} must exactly match payload fields" + (": " + "; ".join(parts) if parts else ""))
    for field, expected_type in payload.items():
        _validate_expression_type(contract, f"{label}.{field}", bindings[field], expected_type, scopes)


def _validate_optional_payload_bindings(
    contract: dict[str, Any] | None,
    label: str,
    bindings: dict[str, Any] | None,
    payload: dict[str, Any],
    scopes: TypeScopes,
) -> None:
    if not payload:
        if bindings:
            raise ContractError(f"{label} must be absent or empty because the signal has no payload_schema")
        return
    if bindings is None:
        raise ContractError(f"{label} must exactly match payload fields: missing: {', '.join(sorted(payload))}")
    _validate_payload_bindings(contract, label, bindings, payload, scopes)


def _validate_expression_type(
    contract: dict[str, Any] | None,
    label: str,
    expression: Any,
    expected_type: Any,
    scopes: TypeScopes,
    *,
    allow_null_source: bool = True,
) -> None:
    if _is_null_expression(expression):
        if not _type_allows_null(expected_type):
            raise ContractError(f"{label} cannot assign null to {type_display(_effective_type(expected_type))}, which does not allow null")
        return
    literal = _literal_expression_value(expression)
    if literal is not _NO_LITERAL and not _literal_value_compatible(literal, expected_type):
        raise ContractError(f"{label} literal value is not compatible with {type_display(_effective_type(expected_type))}")
    actual_type = _expression_type(contract, expression, scopes, label)
    if actual_type and not allow_null_source and _type_allows_null(actual_type) and not _type_allows_null(expected_type):
        raise ContractError(f"{label} cannot assign a source that allows null to {type_display(_effective_type(expected_type))}, which does not allow null")
    if actual_type and not _type_assignable(actual_type, expected_type):
        raise ContractError(f"{label} type mismatch: expected {type_display(_effective_type(expected_type))}, got {type_display(_effective_type(actual_type))}")


def _effective_type(type_name: Any) -> Any:
    return effective_property_schema(type_name)


def _type_allows_null(type_name: Any) -> bool:
    schema = normalize_schema(type_name)
    type_value = schema.get("type")
    if type_value == "null" or (isinstance(type_value, list) and "null" in type_value):
        return True
    return any(member.get("type") == "null" for member in schema.get("anyOf", []))


def _type_assignable(actual_type: Any, expected_type: Any) -> bool:
    actual = _effective_type(actual_type)
    expected = _effective_type(expected_type)
    if type_equals(actual, expected):
        return True
    if _type_allows_null(expected) or _type_allows_null(actual):
        return type_equals(schema_without_null(actual), schema_without_null(expected))
    return type_equals(actual, expected)


def _is_null_expression(expression: Any) -> bool:
    return expression is None or (isinstance(expression, dict) and set(expression) == {"value"} and expression["value"] is None)


_NO_LITERAL = object()


def _literal_expression_value(expression: Any) -> Any:
    if isinstance(expression, dict) and set(expression) == {"from"}:
        return _NO_LITERAL
    if isinstance(expression, dict) and set(expression) == {"value"}:
        return expression["value"]
    if is_binding_expression(expression):
        return _NO_LITERAL
    return expression


def _literal_value_compatible(value: Any, expected_type: Any) -> bool:
    if value is None:
        return _type_allows_null(expected_type)
    expected = schema_without_null(_effective_type(expected_type))
    if "const" in expected:
        return value == expected["const"]
    if "enum" in expected:
        return value in expected["enum"]
    if "$ref" in expected:
        return isinstance(value, dict)
    type_value = expected.get("type")
    if isinstance(type_value, list):
        return any(_literal_value_compatible(value, {**expected, "type": item}) for item in type_value if item != "null")
    if type_value == "string":
        return isinstance(value, str)
    if type_value == "boolean":
        return isinstance(value, bool)
    if type_value == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if type_value == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if type_value == "array":
        return isinstance(value, list)
    if type_value == "object":
        return isinstance(value, dict)
    return False


def _expression_type(contract: dict[str, Any] | None, expression: Any, scopes: TypeScopes, label: str) -> Any | None:
    if isinstance(expression, dict) and set(expression) == {"from"}:
        return _reference_expression_type(contract, label, expression["from"], scopes)
    if isinstance(expression, dict) and set(expression) == {"value"}:
        return _literal_type(expression["value"])
    if is_binding_expression(expression):
        return _reference_expression_type(contract, label, expression, scopes)
    return _literal_type(expression)


def _reference_expression_type(
    contract: dict[str, Any] | None,
    label: str,
    expression: str,
    scopes: TypeScopes,
) -> Any:
    try:
        ref = parse_binding_expression(expression)
    except BindingExpressionError as exc:
        raise ContractError(f"{label} references unsupported expression: {expression}") from exc
    if ref.root not in scopes:
        raise ContractError(f"{label} references unavailable binding root: ${ref.root}")
    return _resolve_reference_type(contract, label, ref.root, ref.path, scopes[ref.root])


def _resolve_reference_type(
    contract: dict[str, Any] | None,
    label: str,
    root: str,
    path: tuple[str, ...],
    scope: TypeScope,
) -> Any:
    for prefix_len in range(len(path), 0, -1):
        prefix = path[:prefix_len]
        if prefix in scope:
            return _resolve_nested_type(
                contract,
                label,
                scope[prefix],
                path[prefix_len:],
                "$" + ".".join((root, *path)),
            )
    raise ContractError(f"{label} references unknown ${root} field: {path[0]}")


def _resolve_nested_type(
    contract: dict[str, Any] | None,
    label: str,
    type_name: Any,
    nested_path: tuple[str, ...],
    source: str,
) -> Any:
    try:
        return dereference_type(contract, type_name, nested_path, source)
    except SchemaExpressionError as exc:
        raise ContractError(f"{label} references {exc}") from exc


def _literal_type(value: Any) -> Any | None:
    # String/null literals can represent several contract scalar types, so schema
    # validation accepts them and semantic validation only type-checks references.
    return literal_schema(value)


def _signal_selector_key(selector: dict[str, str]) -> tuple[str, str]:
    kind, name = _one(selector, "state-machine signal selector")
    return kind, name


def _signal_raise_selector_key(selector: dict[str, Any]) -> tuple[str, str]:
    if "local_signal" in selector:
        return "local_signal", selector["local_signal"]
    if "data_refresh_signal" in selector:
        return "data_refresh_signal", selector["data_refresh_signal"]
    raise ContractError(f"state-machine signal raise must declare local_signal or data_refresh_signal: {selector}")


def _signal_raise_selector(selector: dict[str, Any]) -> dict[str, str]:
    kind, name = _signal_raise_selector_key(selector)
    return {kind: name}


def _signal_label(selector: dict[str, str] | tuple[str, str]) -> str:
    kind, name = selector if isinstance(selector, tuple) else _signal_selector_key(selector)
    return f"{kind}.{name}"


def _is_data_refresh_signal(signal: dict[str, str]) -> bool:
    return _signal_selector_key(signal)[0] == "data_refresh_signal"


def _transition_data_bindings(state_machine: dict[str, Any], transition: dict[str, Any]) -> dict[str, Any]:
    source_state = state_machine.get("states", {}).get(transition["from"], {})
    return source_state.get("query_bindings", {}) or state_machine.get("query_bindings", {})


def _transition_target_data_bindings(state_machine: dict[str, Any], transition: dict[str, Any]) -> dict[str, Any]:
    target_state = state_machine.get("states", {}).get(transition["to"], {})
    return target_state.get("query_bindings", {})


def _transition_has_audit_content(state_machine: dict[str, Any], transition: dict[str, Any]) -> bool:
    if transition.get("rationale") or transition.get("local_effects"):
        return True
    if _is_data_refresh_signal(transition["trigger"]):
        return bool(_transition_data_bindings(state_machine, transition))
    return bool(_transition_target_data_bindings(state_machine, transition))


def _validate_sync_rules(
    contract: dict[str, Any],
    state_machine_id: str,
    state_name: str,
    state_machine: dict[str, Any],
    state: dict[str, Any],
    mounts: dict[str, dict[str, Any]],
) -> None:
    label = f"{state_machine_id}.{state_name}"
    seen: set[str] = set()
    context = _state_machine_context(state_machine)
    for rule in state.get("local_signal_sync_rules", []):
        if rule["id"] in seen:
            raise ContractError(f"composed state machine state {label} has duplicate sync rule: {rule['id']}")
        seen.add(rule["id"])
        source_id = rule["trigger"]["instance"]
        if source_id not in mounts:
            raise ContractError(f"composed state machine state {label} sync source instance is unknown: {source_id}")
        source_state_machine = contract["state_machines"][mounts[source_id]["state_machine"]]
        signal_id = rule["trigger"]["local_signal"]
        if ("local_signal", signal_id) not in _state_machine_emits(source_state_machine):
            raise ContractError(f"composed state machine state {label} sync listens for signal the source does not emit: {signal_id}")
        source_payload = _state_machine_signal_payload(source_state_machine, "emits", {"local_signal": signal_id}, f"composed state machine state {label} sync trigger")
        for effect in rule["local_effects"]:
            kind, body = _one(effect, f"composed state machine state {label} sync local_effect")
            if kind == "set":
                if body["context"] not in context:
                    raise ContractError(f"composed state machine state {label} sync sets undeclared context: {body['context']}")
                binding = body["from"] if "from" in body else {"value": body.get("value")}
                _validate_expression_type(
                    contract,
                    f"composed state machine state {label} sync set {body['context']}",
                    binding,
                    context[body["context"]],
                    {"trigger": _prefixed_type_scope(("payload",), source_payload), "state_machine": _type_scope(context)},
                    allow_null_source=False,
                )
            elif kind == "send":
                target_id = body["instance"]
                if target_id not in mounts:
                    raise ContractError(f"composed state machine state {label} sync sends to unknown instance: {target_id}")
                target_state_machine = contract["state_machines"][mounts[target_id]["state_machine"]]
                if ("local_signal", body["local_signal"]) not in _state_machine_accepts(target_state_machine):
                    raise ContractError(f"composed state machine state {label} sync sends local_signal the target does not accept: {body['local_signal']}")
                target_payload = _state_machine_signal_payload(target_state_machine, "accepts", {"local_signal": body["local_signal"]}, f"composed state machine state {label} sync send")
                _validate_payload_bindings(
                    contract=contract,
                    label=f"composed state machine state {label} sync send {body['local_signal']} to {target_id} payload_bindings",
                    bindings=body["payload_bindings"],
                    payload=target_payload,
                    scopes={"trigger": _prefixed_type_scope(("payload",), source_payload), "state_machine": _type_scope(context)},
                )
            else:  # pragma: no cover - schema prevents this.
                raise ContractError(f"composed state machine state {label} unsupported sync local_effect: {kind}")


def _validate_presentation(contract: dict[str, Any], owner_label: str, field_names: set[str], state_name: str, state: dict[str, Any]) -> None:
    renderers = state.get("renderers") or {}
    if not renderers:
        return
    text_slots = {ref.rsplit(".", 1)[-1] for ref in state["text_resources"]}
    media_asset_slots = {ref.rsplit(".", 1)[-1] for ref in state["media_assets"]}
    field_slots = set(state.get("fields", []))
    command_bindings = set(state["command_bindings"])
    html_regions = set(renderer_html_regions(state))
    textual_containers = set(renderer_textual_containers(state))
    mounts = {mount["id"] for mount in state.get("child_state_machines", [])}

    html_contract = renderer_html_presentation(state)
    for slot in html_contract.get("slots", []):
        if slot["region"] not in html_regions:
            raise ContractError(f"{owner_label}.{state_name} HTML slot references undeclared layout region: {slot['region']}")
        bind_kind, bind_value = _one(slot["binding"], f"{owner_label}.{state_name} html slot binding")
        _validate_slot_binding(owner_label, state_name, "HTML slot", bind_kind, bind_value, text_slots, media_asset_slots, field_slots, command_bindings)

    for rule in renderer_html_style(state).get("rules", []):
        _validate_renderer_style_selector(
            owner_label,
            state_name,
            rule["selector"],
            text_slots,
            media_asset_slots,
            field_slots,
            command_bindings,
            html_regions,
            mounts,
            "html style",
        )

    textual = renderer_textual_presentation(state)
    widgets = textual.get("widgets", [])
    widget_ids = [widget["id"] for widget in widgets]
    if len(widget_ids) != len(set(widget_ids)):
        raise ContractError(f"{owner_label}.{state_name} Textual widgets contain duplicate ids")
    widget_targets = {"text_slot": set(), "media_asset_slot": set(), "field_slot": set(), "command_binding": set()}
    for widget in widgets:
        if widget["container"] not in textual_containers:
            raise ContractError(f"{owner_label}.{state_name} Textual widget references undeclared layout container: {widget['container']}")
        bind_kind, bind_value = _one(widget["binding"], f"{owner_label}.{state_name} textual widget binding")
        _validate_slot_binding(owner_label, state_name, "Textual widget", bind_kind, bind_value, text_slots, media_asset_slots, field_slots, command_bindings)
        if bind_kind in widget_targets:
            widget_targets[bind_kind].add(bind_value)
    for rule in renderer_textual_style(state).get("rules", []):
        selector = rule["selector"]
        _validate_renderer_style_selector(
            owner_label,
            state_name,
            selector,
            text_slots,
            media_asset_slots,
            field_slots,
            command_bindings,
            textual_containers,
            mounts,
            "textual style",
        )
        if widgets and selector.startswith("slot."):
            name = selector[len("slot."):]
            if name not in widget_targets["text_slot"] and name not in widget_targets["media_asset_slot"] and name not in widget_targets["field_slot"]:
                raise ContractError(f"{owner_label}.{state_name} textual style selector has no matching Textual widget: {selector}")
        if widgets and selector.startswith("command_binding."):
            command_binding = selector[len("command_binding."):]
            if command_binding not in widget_targets["command_binding"]:
                raise ContractError(f"{owner_label}.{state_name} textual style selector has no matching Textual widget: {selector}")


def _validate_slot_binding(
    owner_label: str,
    state_name: str,
    label: str,
    bind_kind: str,
    bind_value: str,
    text_slots: set[str],
    media_asset_slots: set[str],
    field_slots: set[str],
    command_bindings: set[str],
) -> None:
    if bind_kind == "text_slot" and bind_value not in text_slots:
        raise ContractError(f"{owner_label}.{state_name} {label} text_slot binding is not declared: {bind_value}")
    if bind_kind == "media_asset_slot" and bind_value not in media_asset_slots:
        raise ContractError(f"{owner_label}.{state_name} {label} media_asset_slot binding is not declared: {bind_value}")
    if bind_kind == "command_binding" and bind_value not in command_bindings:
        raise ContractError(f"{owner_label}.{state_name} {label} command_binding binding is not declared: {bind_value}")
    if bind_kind == "field_slot" and bind_value not in field_slots:
        raise ContractError(f"{owner_label}.{state_name} {label} field_slot binding is not declared: {bind_value}")


def _validate_renderer_style_selector(
    owner_label: str,
    state_name: str,
    selector: str,
    text_slots: set[str],
    media_asset_slots: set[str],
    field_slots: set[str],
    command_bindings: set[str],
    regions: set[str],
    mounts: set[str],
    label: str,
) -> None:
    if selector.startswith("region.") or selector.startswith("container.") or selector.startswith("child_state_machine."):
        _validate_composition_selector(f"{owner_label}.{state_name}", selector, regions, mounts, label)
        return
    _validate_style_selector(owner_label, state_name, selector, text_slots, media_asset_slots, field_slots, command_bindings, label)


def _validate_style_selector(
    owner_label: str,
    state_name: str,
    selector: str,
    text_slots: set[str],
    media_asset_slots: set[str],
    field_slots: set[str],
    command_bindings: set[str],
    label: str,
) -> None:
    if selector == "root" and label.startswith("html"):
        return
    if selector == "screen" and label.startswith("textual"):
        return
    if selector.startswith("slot."):
        name = selector[len("slot."):]
        if name not in text_slots and name not in media_asset_slots and name not in field_slots:
            raise ContractError(f"{owner_label}.{state_name} {label} selector references undeclared slot: {selector}")
        return
    if selector.startswith("command_binding."):
        ref = selector[len("command_binding."):]
        if ref not in command_bindings:
            raise ContractError(f"{owner_label}.{state_name} {label} selector references undeclared command_binding: {ref}")
        return
    raise ContractError(f"{owner_label}.{state_name} {label} selector is not supported: {selector}")


def _validate_composition_selector(state_machine_id: str, selector: str, regions: set[str], mounts: set[str], label: str) -> None:
    if selector == "root" and label.startswith("html"):
        return
    if selector == "screen" and label.startswith("textual"):
        return
    if selector.startswith("region."):
        if label.startswith("textual"):
            raise ContractError(f"composed state machine {state_machine_id} {label} selector uses HTML region syntax: {selector}")
        region = selector[len("region."):]
        if region not in regions:
            raise ContractError(f"composed state machine {state_machine_id} {label} selector references undeclared layout region: {selector}")
        return
    if selector.startswith("container."):
        if not label.startswith("textual"):
            raise ContractError(f"composed state machine {state_machine_id} {label} selector uses Textual container syntax: {selector}")
        container = selector[len("container."):]
        if container not in regions:
            raise ContractError(f"composed state machine {state_machine_id} {label} selector references undeclared Textual container: {selector}")
        return
    if selector.startswith("child_state_machine."):
        mount = selector[len("child_state_machine."):]
        if mount not in mounts:
            raise ContractError(f"composed state machine {state_machine_id} {label} selector references undeclared child state machine: {selector}")
        return
    raise ContractError(f"composed state machine {state_machine_id} {label} selector is not supported: {selector}")


def _validate_external_interfaces(contract: dict[str, Any]) -> None:
    _validate_external_interface_delegation_graph(contract)
    for eid, external_interface in contract["external_interfaces"].items():
        adapter_kind, adapter = external_interface_adapter_pair(external_interface)
        invoked_kind, invoked = external_interface_invokes_pair(external_interface)
        kind = "state_machine" if invoked_kind == "state_machine" else invoked_kind
        value = invoked["ref"]
        _validate_external_interface_fields(eid, external_interface, adapter_kind)
        _validate_external_interface_input_shape(eid, external_interface, adapter_kind)
        if kind == "external_interface":
            _validate_delegating_external_interface_adapter_surface(eid, external_interface, adapter_kind, adapter)
            _validate_external_interface_delegate_target(contract, eid, external_interface, value)
            if adapter_kind == "cli":
                _validate_cli_delegated_response_handlers(contract, eid, external_interface, value)
            continue
        if adapter_kind == "html_route":
            if kind != "state_machine" or value not in contract["state_machines"]:
                raise ContractError(f"HTML external interface {eid} must invoke a known state machine")
            _validate_state_machine_target_renderer(contract, eid, external_interface, value, allowed_renderers={"html"})
            _require_adapter(adapter, eid, "path")
            _validate_path_params(external_interface, eid)
            declared = {**_external_interface_input_map(external_interface, "path_params"), **_external_interface_input_map(external_interface, "query_params")}
            _validate_state_machine_external_interface_inputs(contract, eid, value, declared=declared, input_label="input")
            _validate_target_bindings(contract, eid, external_interface, declared)
        elif adapter_kind == "http_api":
            if kind not in {"command", "query"} or value not in _command_query_map(contract):
                raise ContractError(f"HTTP API external interface {eid} must invoke a known command")
            _require_adapter(adapter, eid, "method")
            _require_adapter(adapter, eid, "path")
            _validate_path_params(external_interface, eid)
            behavior = _command_query_map(contract)[value]
            path_params = _external_interface_input_map(external_interface, "path_params")
            query_params = _external_interface_input_map(external_interface, "query_params")
            body = _external_interface_input_map(external_interface, "body")
            _validate_api_external_interface_input(eid, external_interface, behavior, path_params, query_params, body)
            _validate_target_bindings(contract, eid, external_interface, {**path_params, **query_params, **body})
            _validate_api_external_interface_output_responses(eid, external_interface, behavior)
        elif adapter_kind == "cli":
            _require_adapter(adapter, eid, "cli_command")
            args = _external_interface_input_map(external_interface, "args")
            if kind in {"command", "query"}:
                if value not in _command_query_map(contract):
                    raise ContractError(f"CLI external interface {eid} must invoke a known command")
                behavior = _command_query_map(contract)[value]
                _validate_exact_external_interface_inputs(eid, "input.args", args, _command_input(behavior))
                _validate_target_bindings(contract, eid, external_interface, args)
                _validate_cli_command_response_handlers(contract, eid, external_interface, behavior)
            elif kind == "state_machine":
                if value not in contract["state_machines"]:
                    raise ContractError(f"CLI external interface {eid} must invoke a known state machine")
                _validate_state_machine_target_renderer(contract, eid, external_interface, value, allowed_renderers=set(STATE_MACHINE_RENDERERS))
                _validate_state_machine_external_interface_inputs(contract, eid, value, declared=args, input_label="input.args")
                _validate_target_bindings(contract, eid, external_interface, args)
                target_renderer = external_interface_state_machine_renderer(external_interface)
                assert target_renderer is not None
                if external_interface_output_response_handlers(external_interface):
                    raise ContractError(f"CLI external interface {eid} targeting a state machine must not declare response_handlers")
            elif kind == "workflow":
                if value not in contract["workflows"]:
                    raise ContractError(f"CLI external interface {eid} must invoke a known workflow")
                _validate_workflow_external_interface_target_source(contract, eid, external_interface, value)
                if args:
                    raise ContractError(f"CLI external interface {eid} targeting a workflow must not declare input.args")
                _validate_async_external_interface_output_responses(eid, external_interface, require_failure_disposition=False)
            else:
                raise ContractError(f"CLI external interface {eid} cannot invoke raw {kind}")
        elif adapter_kind in {"worker", "scheduled"}:
            if kind != "workflow" or value not in contract["workflows"]:
                raise ContractError(f"{adapter_kind} external interface {eid} must invoke a known workflow")
            if adapter_kind == "scheduled":
                _require_adapter(adapter, eid, "schedule_expression")
                if external_interface_input_mapping(external_interface):
                    raise ContractError(f"Scheduled external interface {eid} must not declare input")
            else:
                _validate_domain_event_payload_external_interface_input(contract, eid, external_interface, value)
            _validate_workflow_external_interface_target_source(contract, eid, external_interface, value)
            _validate_async_external_interface_output_responses(eid, external_interface, require_failure_disposition=adapter_kind == "worker")
        elif adapter_kind == "webhook":
            if kind != "workflow" or value not in contract["workflows"]:
                raise ContractError(f"Webhook external interface {eid} must invoke a known workflow")
            _require_adapter(adapter, eid, "path")
            _validate_path_params(external_interface, eid)
            _validate_domain_event_payload_external_interface_input(contract, eid, external_interface, value)
            _validate_workflow_external_interface_target_source(contract, eid, external_interface, value)
            _validate_webhook_external_interface_output_responses(eid, external_interface)


def _validate_external_interface_delegation_graph(contract: dict[str, Any]) -> None:
    graph: dict[str, str] = {}
    for external_interface_id, external_interface in contract.get("external_interfaces", {}).items():
        target_kind, target_ref = external_interface_invoked_ref_pair(external_interface)
        if target_kind != "external_interface":
            continue
        if target_ref not in contract["external_interfaces"]:
            raise ContractError(f"External interface {external_interface_id} delegates to unknown external interface {target_ref}")
        if target_ref == external_interface_id:
            raise ContractError(f"External interface {external_interface_id} must not delegate to itself")
        graph[external_interface_id] = target_ref

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(external_interface_id: str, path: list[str]) -> None:
        if external_interface_id in visited or external_interface_id not in graph:
            return
        if external_interface_id in visiting:
            cycle_start = path.index(external_interface_id)
            cycle = path[cycle_start:] + [external_interface_id]
            raise ContractError("External interface delegation cycle is invalid: " + " -> ".join(cycle))
        visiting.add(external_interface_id)
        visit(graph[external_interface_id], [*path, external_interface_id])
        visiting.remove(external_interface_id)
        visited.add(external_interface_id)

    for external_interface_id in graph:
        visit(external_interface_id, [])


def _validate_external_interface_response_maps(contract: dict[str, Any]) -> None:
    """Validate synchronous invoked command/query response keys before local effects depend on them."""
    for external_interface_id, external_interface in contract.get("external_interfaces", {}).items():
        adapter_kind, _adapter = external_interface_adapter_pair(external_interface)
        invoked_kind, invoked = external_interface_invokes_pair(external_interface)
        invoked_ref = invoked["ref"]
        if adapter_kind == "http_api" and invoked_kind in {"command", "query"} and invoked_ref in _command_query_map(contract):
            _command_external_interface_output_responses(external_interface_id, external_interface, _command_query_map(contract)[invoked_ref])
        elif adapter_kind == "cli" and invoked_kind in {"command", "query"} and invoked_ref in _command_query_map(contract):
            _command_external_interface_output_response_handlers(external_interface_id, external_interface, _command_query_map(contract)[invoked_ref])


def _validate_delegating_external_interface_adapter_surface(
    external_interface_id: str,
    external_interface: dict[str, Any],
    adapter_kind: str,
    adapter: dict[str, Any],
) -> None:
    if adapter_kind == "html_route":
        _require_adapter(adapter, external_interface_id, "path")
        _validate_path_params(external_interface, external_interface_id)
    elif adapter_kind == "http_api":
        _require_adapter(adapter, external_interface_id, "method")
        _require_adapter(adapter, external_interface_id, "path")
        _validate_path_params(external_interface, external_interface_id)
    elif adapter_kind == "cli":
        _require_adapter(adapter, external_interface_id, "cli_command")
    elif adapter_kind == "scheduled":
        _require_adapter(adapter, external_interface_id, "schedule_expression")
        if external_interface_input_mapping(external_interface):
            raise ContractError(f"Scheduled external interface {external_interface_id} must not declare input")
    elif adapter_kind == "webhook":
        _require_adapter(adapter, external_interface_id, "path")
        _validate_path_params(external_interface, external_interface_id)


def _validate_external_interface_delegate_target(
    contract: dict[str, Any],
    external_interface_id: str,
    external_interface: dict[str, Any],
    delegated_external_interface_id: str,
) -> None:
    delegated_external_interface = contract["external_interfaces"][delegated_external_interface_id]
    bindings = external_interface_invocation_input_mapping(external_interface)
    expected_input = {
        section: value
        for section, value in external_interface_input_mapping(delegated_external_interface).items()
        if section not in {"bindings", "delegated_input"}
    }
    expected_sections = set(expected_input)
    actual_sections = set(bindings)
    if actual_sections != expected_sections:
        missing = sorted(expected_sections - actual_sections)
        extra = sorted(actual_sections - expected_sections)
        parts = []
        if missing:
            parts.append("missing sections: " + ", ".join(missing))
        if extra:
            parts.append("extra sections: " + ", ".join(extra))
        raise ContractError(
            f"External interface {external_interface_id} input_mapping.delegated_input must exactly bind delegated external interface input"
            + (": " + "; ".join(parts) if parts else "")
        )
    source_scopes: TypeScopes = {"adapter_input": _external_interface_input_source_types(contract, external_interface)}
    for section, expected in expected_input.items():
        section_bindings = bindings.get(section)
        label = f"External interface {external_interface_id} input_mapping.delegated_input.{section}"
        if section == "payload":
            _validate_delegated_payload_binding(contract, label, section_bindings, expected, source_scopes)
            continue
        if not isinstance(expected, dict):
            raise ContractError(f"External interface {external_interface_id} delegated input section {section} must be an object-shaped adapter input")
        if not isinstance(section_bindings, dict):
            raise ContractError(f"{label} must declare field bindings")
        _validate_binding_map(contract, label, section_bindings, expected, source_scopes)


def _validate_delegated_payload_binding(
    contract: dict[str, Any],
    label: str,
    binding: Any,
    expected_type: Any,
    source_scopes: TypeScopes,
) -> None:
    if isinstance(binding, dict) and set(binding) in ({"from"}, {"value"}):
        actual_type = _expression_type(contract, binding, source_scopes, label)
        if actual_type and not _type_assignable(actual_type, expected_type):
            raise ContractError(f"{label} type mismatch: expected {type_display(_effective_type(expected_type))}, got {type_display(_effective_type(actual_type))}")
        return
    expected_fields = object_fields_for_type(contract, expected_type)
    if not expected_fields:
        raise ContractError(f"{label} must bind payload as a single binding value for {type_display(expected_type)}")
    if not isinstance(binding, dict):
        raise ContractError(f"{label} must declare payload field bindings")
    _validate_binding_map(contract, label, binding, expected_fields, source_scopes)


def _validate_binding_map(
    contract: dict[str, Any],
    label: str,
    bindings: dict[str, Any],
    expected: dict[str, Any],
    source_scopes: TypeScopes,
) -> None:
    if set(bindings) != set(expected):
        missing = sorted(set(expected) - set(bindings))
        extra = sorted(set(bindings) - set(expected))
        parts = []
        if missing:
            parts.append("missing: " + ", ".join(missing))
        if extra:
            parts.append("extra: " + ", ".join(extra))
        raise ContractError(f"{label} must exactly bind invoked input" + (": " + "; ".join(parts) if parts else ""))
    for name, source in bindings.items():
        actual_type = _expression_type(contract, source, source_scopes, f"{label}.{name}")
        expected_type = expected[name]
        if actual_type and not _type_assignable(actual_type, expected_type):
            raise ContractError(
                f"{label}.{name} type mismatch: expected {type_display(_effective_type(expected_type))}, "
                f"got {type_display(_effective_type(actual_type))} from {source}"
            )


def _validate_external_interface_fields(external_interface_id: str, external_interface: dict[str, Any], adapter_kind: str) -> None:
    allowed = {"adapter", "invokes", "input_mapping", "output_mapping", "rationale", "access_policy", "idempotent", "retryable"}
    generated = {
        "html_route": {"html_route"},
        "http_api": {"http_operation"},
        "cli": {"cli_command_ref"},
        "worker": {"workflow_ref"},
        "scheduled": {"workflow_ref"},
        "webhook": set(),
    }[adapter_kind]
    allowed.update(generated)
    extra = sorted(set(external_interface) - allowed)
    if extra:
        raise ContractError(f"External interface {external_interface_id} adapter {adapter_kind} has unsupported fields: {extra}")


def _validate_external_interface_input_shape(external_interface_id: str, external_interface: dict[str, Any], adapter_kind: str) -> None:
    allowed = {
        "html_route": {"path_params", "query_params"},
        "http_api": {"path_params", "query_params", "body"},
        "cli": {"args"},
        "worker": {"payload"},
        "scheduled": set(),
        "webhook": {"path_params", "query_params", "payload"},
    }[adapter_kind]
    input_spec = external_interface_input_mapping(external_interface)
    mapping_keys = {"bindings", "delegated_input"}
    extra = sorted(set(input_spec) - allowed - mapping_keys)
    if extra:
        raise ContractError(f"External interface {external_interface_id} adapter {adapter_kind} has unsupported input sections: {extra}")
    seen: dict[str, Any] = {}
    for section in ("path_params", "query_params", "body", "args"):
        for name, type_name in _external_interface_input_map(external_interface, section).items():
            previous = seen.get(name)
            if previous and not type_equals(previous, type_name):
                raise ContractError(
                    f"External interface {external_interface_id} input field {name} has conflicting types: "
                    f"{type_display(previous)} vs {type_display(type_name)}"
                )
            seen[name] = type_name


def _validate_state_machine_target_renderer(
    contract: dict[str, Any],
    external_interface_id: str,
    external_interface: dict[str, Any],
    state_machine_id: str,
    *,
    allowed_renderers: set[str],
) -> None:
    renderer = external_interface_state_machine_renderer(external_interface)
    if renderer is None:
        raise ContractError(f"External interface {external_interface_id} state machine invocation must declare renderer")
    if renderer not in allowed_renderers:
        raise ContractError(f"External interface {external_interface_id} cannot invoke state machine renderer {renderer!r}")
    if not _state_machine_supports_renderer(contract["state_machines"][state_machine_id], renderer):
        raise ContractError(f"External interface {external_interface_id} invokes state machine {state_machine_id} renderer {renderer} but that state machine does not declare it")


def _state_machine_supports_renderer(state_machine: dict[str, Any], renderer: str) -> bool:
    return any(
        bool((state.get("renderers") or {}).get(renderer, {}).get("layout"))
        or (not state.get("child_state_machines") and bool((state.get("renderers") or {}).get(renderer, {}).get("presentation")))
        for state in state_machine.get("states", {}).values()
    )


def _validate_workflow_external_interface_target_source(contract: dict[str, Any], external_interface_id: str, external_interface: dict[str, Any], workflow_id: str) -> None:
    bindings = external_interface_workflow_input_mapping(external_interface)
    if not bindings:
        raise ContractError(f"External interface {external_interface_id} workflow invocation must declare input_mapping.bindings")
    expected = _workflow_input_payload_fields(contract, workflow_id, contract["workflows"][workflow_id])
    if set(bindings) != set(expected):
        missing = sorted(set(expected) - set(bindings))
        extra = sorted(set(bindings) - set(expected))
        parts = []
        if missing:
            parts.append("missing: " + ", ".join(missing))
        if extra:
            parts.append("extra: " + ", ".join(extra))
        raise ContractError(f"External interface {external_interface_id} input_mapping.bindings must exactly bind workflow input" + (": " + "; ".join(parts) if parts else ""))
    scopes: TypeScopes = {"adapter_input": _external_interface_input_source_types(contract, external_interface)}
    for name, binding in bindings.items():
        actual_type = _expression_type(contract, binding, scopes, f"External interface {external_interface_id} input_mapping.bindings.{name}")
        expected_type = expected[name]
        if actual_type and not _type_assignable(actual_type, expected_type):
            raise ContractError(
                f"External interface {external_interface_id} input_mapping.bindings.{name} type mismatch: "
                f"expected {type_display(_effective_type(expected_type))}, got {type_display(_effective_type(actual_type))} from {binding}"
            )


def _validate_api_external_interface_input(
    external_interface_id: str,
    external_interface: dict[str, Any],
    behavior: dict[str, Any],
    path_params: dict[str, Any],
    query_params: dict[str, Any],
    body: dict[str, Any],
) -> None:
    cap_input = _command_input(behavior)
    all_params = {**path_params, **query_params}
    all_input = {**all_params, **body}
    if set(path_params) - set(cap_input):
        raise ContractError(f"API external interface {external_interface_id} input.path_params must be command/query input fields")
    if set(query_params) - set(cap_input):
        raise ContractError(f"API external interface {external_interface_id} input.query_params must be command/query input fields")
    if set(body) - set(cap_input):
        raise ContractError(f"API external interface {external_interface_id} input.body must be command/query input fields")
    if set(path_params) & set(query_params) or set(all_params) & set(body):
        raise ContractError(f"API external interface {external_interface_id} input fields cannot appear in multiple input sections")
    _validate_external_interface_input_types(external_interface_id, "input.path_params", path_params, cap_input)
    _validate_external_interface_input_types(external_interface_id, "input.query_params", query_params, cap_input)
    _validate_external_interface_input_types(external_interface_id, "input.body", body, cap_input)
    method = (external_interface_method(external_interface) or "").lower()
    if method in {"get", "delete"}:
        if body:
            raise ContractError(f"API external interface {external_interface_id} {external_interface_method(external_interface)} must not declare input.body")
        if set(all_params) != set(cap_input):
            missing_params = sorted(set(cap_input) - set(all_params))
            raise ContractError(f"API external interface {external_interface_id} {external_interface_method(external_interface)} must declare all command/query inputs as path_params or query_params: {missing_params}")
    missing = sorted(set(cap_input) - set(all_input))
    if missing:
        raise ContractError(f"API external interface {external_interface_id} input must include every command/query input: {missing}")


def _validate_domain_event_payload_external_interface_input(contract: dict[str, Any], external_interface_id: str, external_interface: dict[str, Any], workflow_id: str) -> None:
    trigger = contract["workflows"][workflow_id]["inputs"]
    if "domain_event" not in trigger:
        return
    domain_event_id = trigger["domain_event"]
    domain_event = contract["domain_events"].get(domain_event_id)
    if not domain_event:
        raise ContractError(f"External interface {external_interface_id} workflow invocation source references unknown domain event {domain_event_id}")
    payload_type = external_interface_input_mapping(external_interface).get("payload")
    if not type_equals(payload_type, domain_event["payload_schema"]):
        raise ContractError(f"External interface {external_interface_id} input.payload must be {type_display(domain_event['payload_schema'])}, got {type_display(payload_type)}")


def _validate_target_bindings(
    contract: dict[str, Any],
    external_interface_id: str,
    external_interface: dict[str, Any],
    target_input_types: dict[str, Any],
) -> None:
    kind, value = external_interface_invoked_ref_pair(external_interface)
    bindings = external_interface_invocation_input_mapping(external_interface)
    if kind in {"command", "query"}:
        expected = _command_input(_command_query_map(contract)[value])
    elif kind == "state_machine":
        context = _state_machine_context(contract["state_machines"][value])
        expected = {name: context[name] for name in target_input_types}
    else:
        if bindings:
            raise ContractError(f"External interface {external_interface_id} input_mapping.bindings is not supported for workflow invocations")
        return
    if set(bindings) != set(expected):
        missing = sorted(set(expected) - set(bindings))
        extra = sorted(set(bindings) - set(expected))
        parts = []
        if missing:
            parts.append("missing: " + ", ".join(missing))
        if extra:
            parts.append("extra: " + ", ".join(extra))
        raise ContractError(f"External interface {external_interface_id} input_mapping.bindings must exactly bind invoked input" + (": " + "; ".join(parts) if parts else ""))
    source_scopes: TypeScopes = {"adapter_input": _external_interface_input_source_types(contract, external_interface)}
    for target_name, source in bindings.items():
        actual_type = _expression_type(
            contract,
            source,
            source_scopes,
            f"External interface {external_interface_id} input_mapping.bindings.{target_name}",
        )
        expected_type = expected[target_name]
        if actual_type and not _type_assignable(actual_type, expected_type):
            raise ContractError(
                f"External interface {external_interface_id} input_mapping.bindings.{target_name} type mismatch: "
                f"expected {type_display(_effective_type(expected_type))}, got {type_display(_effective_type(actual_type))} from {source}"
            )


def _validate_api_external_interface_output_responses(external_interface_id: str, external_interface: dict[str, Any], command: dict[str, Any]) -> None:
    responses = _command_external_interface_output_responses(external_interface_id, external_interface, command)
    statuses: dict[int, str] = {}
    for outcome_id, response in responses.items():
        outcome = command["outcomes"][outcome_id]
        if set(response) != {"status", "body"}:
            raise ContractError(f"API external interface {external_interface_id} response {outcome_id} must declare exactly status and body")
        status = response["status"]
        if status in statuses:
            raise ContractError(
                f"API external interface {external_interface_id} responses {statuses[status]} and {outcome_id} cannot share HTTP status {status}"
            )
        statuses[status] = outcome_id
        if outcome["kind"] == "success":
            expected = 201 if command.get("creates") else 200
            if status != expected:
                raise ContractError(f"API external interface {external_interface_id} success response {outcome_id} status must be {expected}")
        elif status < 400:
            raise ContractError(f"API external interface {external_interface_id} failure response {outcome_id} status must be 4xx or 5xx")
        body = response["body"]
        _validate_response_value(
            f"API external interface {external_interface_id} response {outcome_id}.body",
            body,
            outcome["result"],
        )


def _validate_cli_command_response_handlers(
    contract: dict[str, Any],
    external_interface_id: str,
    external_interface: dict[str, Any],
    command: dict[str, Any],
) -> None:
    responses = _command_external_interface_output_response_handlers(external_interface_id, external_interface, command)
    exit_codes: dict[int, str] = {}
    for outcome_id, response in responses.items():
        outcome = command["outcomes"][outcome_id]
        _validate_cli_response_handler(
            contract,
            external_interface_id,
            outcome_id,
            response,
            outcome_kind=outcome["kind"],
            source_scopes={
                "adapter_input": _external_interface_input_source_types(contract, external_interface),
                "invocation_outcome": _typed_source_paths(contract, ("result",), outcome["result"]),
            },
            delegated_external_interface_id=None,
            retry_allowed=_command_retryable(command),
            retry_error=f"CLI external interface {external_interface_id} response handler {outcome_id} retry_policy requires a query or retryable invoked behavior",
            exit_codes=exit_codes,
        )


def _validate_cli_delegated_response_handlers(
    contract: dict[str, Any],
    external_interface_id: str,
    external_interface: dict[str, Any],
    delegated_external_interface_id: str,
) -> None:
    delegated_external_interface = contract["external_interfaces"][delegated_external_interface_id]
    expected = _external_interface_named_response_outcomes(contract, delegated_external_interface_id)
    handlers = external_interface_output_response_handlers(external_interface)
    if set(handlers) != expected:
        missing = sorted(expected - set(handlers))
        extra = sorted(set(handlers) - expected)
        parts = []
        if missing:
            parts.append("missing: " + ", ".join(missing))
        if extra:
            parts.append("extra: " + ", ".join(extra))
        raise ContractError(
            f"CLI external interface {external_interface_id} response_handlers must exactly map delegated external-interface outcomes"
            + (": " + "; ".join(parts) if parts else "")
        )
    exit_codes: dict[int, str] = {}
    outcome_kinds = _external_interface_outcome_kinds(contract, delegated_external_interface_id)
    response_types = _external_interface_response_body_types(contract, delegated_external_interface_id)
    retry_allowed = _external_interface_retryable(contract, delegated_external_interface_id)
    for outcome_id, handler in handlers.items():
        if handler.get("retry_policy") and not retry_allowed:
            raise ContractError(
                f"CLI external interface {external_interface_id} response handler {outcome_id} retry_policy requires delegated external interface "
                f"{delegated_external_interface_id} and its final invocation to be retryable or query"
            )
        source_scopes: TypeScopes = {"adapter_input": _external_interface_input_source_types(contract, external_interface)}
        response_type = response_types.get(outcome_id)
        if response_type is not None:
            source_scopes["adapter_response"] = _typed_source_paths(contract, ("body",), response_type)
        _validate_cli_response_handler(
            contract,
            external_interface_id,
            outcome_id,
            handler,
            outcome_kind=outcome_kinds.get(outcome_id),
            source_scopes=source_scopes,
            delegated_external_interface_id=delegated_external_interface_id,
            retry_allowed=retry_allowed,
            retry_error=(
                f"CLI external interface {external_interface_id} response handler {outcome_id} retry_policy requires delegated external interface "
                f"{delegated_external_interface_id} and its final invocation to be retryable or query"
            ),
            exit_codes=exit_codes,
        )


def _validate_cli_response_handler(
    contract: dict[str, Any],
    external_interface_id: str,
    outcome_id: str,
    handler: dict[str, Any],
    *,
    outcome_kind: str | None,
    source_scopes: TypeScopes,
    delegated_external_interface_id: str | None,
    retry_allowed: bool,
    retry_error: str,
    exit_codes: dict[int, str],
) -> None:
    exit_code = handler["exit_code"]
    streams = [stream for stream in ("stdout", "stderr") if stream in handler]
    if len(streams) != 1:
        raise ContractError(f"CLI external interface {external_interface_id} response handler {outcome_id} must declare exactly one of stdout or stderr")
    if outcome_kind == "success" and streams[0] != "stdout":
        raise ContractError(f"CLI external interface {external_interface_id} success response handler {outcome_id} must declare stdout")
    if outcome_kind == "success" and exit_code != 0:
        raise ContractError(f"CLI external interface {external_interface_id} success response handler {outcome_id} exit_code must be 0")
    if outcome_kind == "failure" and streams[0] != "stderr":
        raise ContractError(f"CLI external interface {external_interface_id} failure response handler {outcome_id} must declare stderr")
    if outcome_kind == "failure" and exit_code == 0:
        raise ContractError(f"CLI external interface {external_interface_id} failure response handler {outcome_id} exit_code must be nonzero")
    if handler.get("retry_policy") and not retry_allowed:
        raise ContractError(retry_error)
    if exit_code in exit_codes:
        raise ContractError(
            f"CLI external interface {external_interface_id} response handlers {exit_codes[exit_code]} and {outcome_id} cannot share exit_code {exit_code}"
        )
    exit_codes[exit_code] = outcome_id
    output = handler[streams[0]]
    text_resource_ref = output["text"]
    if text_resource_ref not in contract.get("text_resources", {}):
        raise ContractError(f"CLI external interface {external_interface_id} response handler {outcome_id} references unknown text resource {text_resource_ref}")
    bindings = output.get("bindings") or {}
    expected_text_args = contract["text_resources"][text_resource_ref].get("args", {})
    if set(bindings) != set(expected_text_args):
        missing = sorted(set(expected_text_args) - set(bindings))
        extra = sorted(set(bindings) - set(expected_text_args))
        parts = []
        if missing:
            parts.append("missing: " + ", ".join(missing))
        if extra:
            parts.append("extra: " + ", ".join(extra))
        raise ContractError(
            f"CLI external interface {external_interface_id} response handler {outcome_id} bindings must match text args"
            + (": " + "; ".join(parts) if parts else "")
        )
    for binding_name, binding in bindings.items():
        actual_type = _expression_type(contract, binding, source_scopes, f"CLI external interface {external_interface_id} response handler {outcome_id}.{streams[0]}.bindings.{binding_name}")
        expected_type = expected_text_args[binding_name]
        if actual_type and not _type_assignable(actual_type, expected_type):
            raise ContractError(
                f"CLI external interface {external_interface_id} response handler {outcome_id}.{streams[0]}.bindings.{binding_name} "
                f"type mismatch: expected {type_display(_effective_type(expected_type))}, got {type_display(_effective_type(actual_type))}"
            )


def _command_external_interface_output_responses(external_interface_id: str, external_interface: dict[str, Any], command: dict[str, Any]) -> dict[str, Any]:
    responses = external_interface_output_responses(external_interface)
    if set(responses) != set(command["outcomes"]):
        missing = sorted(set(command["outcomes"]) - set(responses))
        extra = sorted(set(responses) - set(command["outcomes"]))
        parts = []
        if missing:
            parts.append("missing: " + ", ".join(missing))
        if extra:
            parts.append("extra: " + ", ".join(extra))
        raise ContractError(f"External interface {external_interface_id} responses must exactly map command outcomes" + (": " + "; ".join(parts) if parts else ""))
    return responses


def _command_external_interface_output_response_handlers(external_interface_id: str, external_interface: dict[str, Any], command: dict[str, Any]) -> dict[str, Any]:
    handlers = external_interface_output_response_handlers(external_interface)
    if set(handlers) != set(command["outcomes"]):
        missing = sorted(set(command["outcomes"]) - set(handlers))
        extra = sorted(set(handlers) - set(command["outcomes"]))
        parts = []
        if missing:
            parts.append("missing: " + ", ".join(missing))
        if extra:
            parts.append("extra: " + ", ".join(extra))
        raise ContractError(f"External interface {external_interface_id} response_handlers must exactly map command outcomes" + (": " + "; ".join(parts) if parts else ""))
    return handlers


def _external_interface_named_response_outcomes(contract: dict[str, Any], external_interface_id: str) -> set[str]:
    external_interface = contract["external_interfaces"][external_interface_id]
    handlers = external_interface_output_response_handlers(external_interface)
    if handlers:
        return set(handlers)
    responses = external_interface_output_responses(external_interface)
    if responses:
        return set(responses)
    target_kind, target_ref = external_interface_invoked_ref_pair(external_interface)
    if target_kind in {"command", "query"}:
        return set(_command_query_map(contract)[target_ref]["outcomes"])
    if target_kind == "workflow":
        return set(contract["workflows"][target_ref]["outputs"])
    if target_kind == "external_interface":
        return _external_interface_named_response_outcomes(contract, target_ref)
    return set()


def _external_interface_outcome_kinds(contract: dict[str, Any], external_interface_id: str) -> dict[str, str]:
    target_kind, target_ref = external_interface_invoked_ref_pair(contract["external_interfaces"][external_interface_id])
    if target_kind in {"command", "query"}:
        return {name: outcome["kind"] for name, outcome in _command_query_map(contract)[target_ref]["outcomes"].items()}
    if target_kind == "workflow":
        return {name: outcome["kind"] for name, outcome in contract["workflows"][target_ref]["outputs"].items()}
    if target_kind == "external_interface":
        return _external_interface_outcome_kinds(contract, target_ref)
    return {}


def _external_interface_response_body_types(contract: dict[str, Any], external_interface_id: str) -> dict[str, Any]:
    external_interface = contract["external_interfaces"][external_interface_id]
    responses = external_interface_output_responses(external_interface)
    result: dict[str, Any] = {}
    for outcome_id, response in responses.items():
        body = response.get("body")
        if body:
            result[outcome_id] = body["type"]
    if result:
        return result
    target_kind, target_ref = external_interface_invoked_ref_pair(external_interface)
    if target_kind in {"command", "query"}:
        return {name: outcome["result"] for name, outcome in _command_query_map(contract)[target_ref]["outcomes"].items()}
    if target_kind == "workflow":
        return {name: outcome["result"] for name, outcome in contract["workflows"][target_ref]["outputs"].items()}
    if target_kind == "external_interface":
        return _external_interface_response_body_types(contract, target_ref)
    return {}


def _validate_response_value(label: str, value: dict[str, Any], expected_type: Any) -> None:
    if set(value) != {"type", "from"} or value["from"] != "$invocation_outcome.result" or not type_equals(value["type"], expected_type):
        raise ContractError(f"{label} must expose $invocation_outcome.result as {type_display(expected_type)}")


def _validate_async_external_interface_output_responses(external_interface_id: str, external_interface: dict[str, Any], *, require_failure_disposition: bool) -> None:
    if "responses" in external_interface_output_mapping(external_interface):
        raise ContractError(f"External interface {external_interface_id} async adapter must use output_mapping.ingress_responses, not responses")
    responses = external_interface_output_responses(external_interface)
    accepted = responses.get("accepted")
    if accepted != {"disposition": "acknowledge"}:
        raise ContractError(f"External interface {external_interface_id} ingress_responses.accepted must declare disposition: acknowledge")
    failure_responses = {name: response for name, response in responses.items() if name != "accepted"}
    if require_failure_disposition and not failure_responses:
        raise ContractError(f"External interface {external_interface_id} must declare at least one non-acknowledge ingress disposition such as retry, reject, or dead_letter")
    for response_id, response in failure_responses.items():
        if set(response) != {"disposition", "problem"}:
            raise ContractError(f"External interface {external_interface_id} ingress disposition {response_id} must declare exactly disposition and problem")
        if response["disposition"] not in {"retry", "reject", "dead_letter"}:
            raise ContractError(f"External interface {external_interface_id} ingress disposition {response_id} must be retry, reject, or dead_letter")
        _validate_problem_type(f"External interface {external_interface_id} disposition {response_id} problem", response["problem"])
    if require_failure_disposition and not any(response["disposition"] in {"reject", "dead_letter"} for response in failure_responses.values()):
        raise ContractError(f"External interface {external_interface_id} must declare a reject or dead_letter ingress disposition for malformed or poison messages")


def _validate_webhook_external_interface_output_responses(external_interface_id: str, external_interface: dict[str, Any]) -> None:
    if "responses" in external_interface_output_mapping(external_interface):
        raise ContractError(f"Webhook external interface {external_interface_id} must use output_mapping.ingress_responses, not responses")
    if external_interface_output_responses(external_interface) != {"accepted": {"status": 202}}:
        raise ContractError(f"Webhook external interface {external_interface_id} ingress_responses.accepted.status must be 202")


def _validate_state_machine_external_interface_inputs(
    contract: dict[str, Any],
    external_interface_id: str,
    state_machine_id: str,
    *,
    declared: dict[str, Any],
    input_label: str,
) -> None:
    state_machine = contract["state_machines"][state_machine_id]
    state_machine_context = _state_machine_context(state_machine)
    extra = sorted(set(declared) - set(state_machine_context))
    if extra:
        raise ContractError(f"External interface {external_interface_id} {input_label} must be declared state machine context fields: {extra}")
    _validate_external_interface_input_types(external_interface_id, input_label, declared, state_machine_context)
    required = _required_external_interface_state_machine_context(contract, state_machine_id)
    missing = sorted(set(required) - set(declared))
    if missing:
        raise ContractError(f"External interface {external_interface_id} {input_label} must include required state machine context inputs: {missing}")


def _required_external_interface_state_machine_context(contract: dict[str, Any], state_machine_id: str) -> dict[str, Any]:
    state_machine = contract["state_machines"][state_machine_id]
    required: dict[str, Any] = {
        name: field
        for name, field in _state_machine_context(state_machine).items()
        if name in _schema_required_fields(state_machine.get("context_schema"))
    }
    _add_query_context_requirements(
        contract,
        f"state machine {state_machine_id}",
        state_machine.get("query_bindings", {}),
        _state_machine_context(state_machine),
        required,
    )
    for state_name, state in state_machine.get("states", {}).items():
        _add_query_context_requirements(
            contract,
            f"state machine {state_machine_id}.{state_name}",
            state.get("query_bindings", {}),
            _state_machine_context(state_machine),
            required,
        )
        for mount in state.get("child_state_machines", []):
            child_state_machine = contract["state_machines"][mount["state_machine"]]
            initial_state = child_state_machine["states"][mount["initial_state"]]
            _add_mount_context_requirements(
                contract,
                state_machine_id,
                mount,
                child_state_machine,
                child_state_machine.get("query_bindings", {}),
                required,
            )
            _add_mount_context_requirements(
                contract,
                state_machine_id,
                mount,
                child_state_machine,
                initial_state.get("query_bindings", {}),
                required,
            )
    return required


def _add_query_context_requirements(
    contract: dict[str, Any],
    label: str,
    invocations: dict[str, Any],
    context: dict[str, Any],
    required: dict[str, Any],
) -> None:
    for invocation_id, invocation in sorted((invocations or {}).items()):
        for key in _context_roots_from_input_mapping(f"{label} query_binding {invocation_id}", invocation.get("input_mapping") or {}):
            if key not in context:
                raise ContractError(f"{label} query_binding {invocation_id} references undeclared context field: {key}")
            _add_required_external_interface_context(required, key, context[key], label)


def _add_mount_context_requirements(
    contract: dict[str, Any],
    state_machine_id: str,
    mount: dict[str, Any],
    state_machine: dict[str, Any],
    invocations: dict[str, Any],
    required: dict[str, Any],
) -> None:
    mount_context = mount.get("context_bindings", {})
    child_state_machine_context = _state_machine_context(state_machine)
    parent_state_machine_context = _state_machine_context(contract["state_machines"][state_machine_id])
    for invocation_id, invocation in sorted((invocations or {}).items()):
        label = f"composed state machine {state_machine_id}.{mount['id']} query_binding {invocation_id}"
        for child_key in _context_roots_from_input_mapping(label, invocation.get("input_mapping") or {}):
            if child_key not in child_state_machine_context:
                raise ContractError(f"{label} references undeclared child context field: {child_key}")
            expected_type = child_state_machine_context[child_key]
            value = mount_context.get(child_key)
            if not (isinstance(value, dict) and "from" in value and is_binding_expression(value["from"])):
                continue
            try:
                ref = parse_binding_expression(value["from"])
            except BindingExpressionError as exc:
                raise ContractError(f"composed state machine {state_machine_id}.{mount['id']} has malformed binding expression: {value}") from exc
            if ref.root != "state_machine":
                continue
            parent_key = ref.path[0]
            actual_type = _expression_type(
                contract,
                value,
                {"state_machine": _type_scope(parent_state_machine_context)},
                f"composed state machine {state_machine_id}.{mount['id']} parent context {parent_key}",
            )
            if not _type_assignable(actual_type, expected_type):
                raise ContractError(
                    f"composed state machine {state_machine_id}.{mount['id']} parent context {parent_key} type must be "
                    f"{type_display(_effective_type(expected_type))}, got {type_display(_effective_type(actual_type))}"
                )
            _add_required_external_interface_context(
                required,
                parent_key,
                parent_state_machine_context[parent_key],
                label,
            )


def _context_roots_from_input_mapping(label: str, bindings: dict[str, Any]) -> set[str]:
    roots: set[str] = set()
    for field, binding in bindings.items():
        if not (isinstance(binding, dict) and set(binding) == {"from"}):
            continue
        try:
            ref = parse_binding_expression(binding["from"])
        except BindingExpressionError as exc:
            raise ContractError(f"{label} input_mapping.{field} references unsupported expression: {binding['from']}") from exc
        if ref.root == "state_context" and ref.path:
            roots.add(ref.path[0])
    return roots


def _add_required_external_interface_context(required: dict[str, Any], key: str, type_name: Any, label: str) -> None:
    existing = required.get(key)
    if existing and not type_equals(schema_without_null(_effective_type(existing)), schema_without_null(_effective_type(type_name))):
        raise ContractError(
            f"{label} requires conflicting external interface input type for {key}: "
            f"{type_display(_effective_type(existing))} vs {type_display(_effective_type(type_name))}"
        )
    required[key] = type_name


def _validate_exact_external_interface_inputs(external_interface_id: str, field: str, actual: dict[str, Any], expected: dict[str, Any]) -> None:
    if set(actual) != set(expected):
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        parts = []
        if missing:
            parts.append("missing: " + ", ".join(missing))
        if extra:
            parts.append("extra: " + ", ".join(extra))
        raise ContractError(f"External interface {external_interface_id} {field} must exactly match invoked input" + (": " + "; ".join(parts) if parts else ""))
    _validate_external_interface_input_types(external_interface_id, field, actual, expected)


def _validate_external_interface_input_types(external_interface_id: str, field: str, actual: dict[str, Any], expected: dict[str, Any]) -> None:
    for name, type_name in actual.items():
        expected_type = expected.get(name)
        if not _type_assignable(type_name, expected_type):
            raise ContractError(
                f"External interface {external_interface_id} {field}.{name} type mismatch: "
                f"expected {type_display(_effective_type(expected_type))}, got {type_display(_effective_type(type_name))}"
            )


def _external_interface_input_map(external_interface: dict[str, Any], section: str) -> dict[str, Any]:
    value = external_interface_input_mapping(external_interface).get(section, {})
    return value if isinstance(value, dict) else {}


def _external_interface_input_source_types(contract: dict[str, Any], external_interface: dict[str, Any]) -> TypeScope:
    source_types: TypeScope = {}
    for section in ("path_params", "query_params", "body", "args"):
        for name, type_name in _external_interface_input_map(external_interface, section).items():
            source_types[(section, name)] = type_name
    payload = external_interface_input_mapping(external_interface).get("payload")
    if payload is not None:
        source_types.update(_typed_source_paths(contract, ("payload",), payload))
    return source_types


def _base_type(type_name: Any) -> str | None:
    return base_entity_type_id(type_name)


def _validate_problem_type(label: str, type_name: Any) -> None:
    if not is_problem_type(type_name):
        raise ContractError(f"{label} must be Problem or a *Problem type")


def _type_scope(types: dict[str, Any]) -> TypeScope:
    return {(name,): _effective_type(type_name) for name, type_name in types.items()}


def _prefixed_type_scope(prefix: tuple[str, ...], types: dict[str, Any]) -> TypeScope:
    return {(*prefix, name): _effective_type(type_name) for name, type_name in types.items()}


def _typed_source_paths(contract: dict[str, Any], prefix: tuple[str, ...], type_name: Any) -> TypeScope:
    return {prefix: type_name}


def _merge_type_scopes(target: TypeScopes, source: TypeScopes) -> None:
    for root, paths in source.items():
        target.setdefault(root, {}).update(paths)


def _validate_mapping_to_type(
    contract: dict[str, Any],
    label: str,
    mapping: dict[str, Any],
    target_type: Any,
    source_scopes: TypeScopes,
) -> None:
    expected = object_fields_for_type(contract, target_type)
    if not expected:
        raise ContractError(f"{label} field mapping requires object payload type, got {type_display(target_type)}")
    if set(mapping) != set(expected):
        missing = sorted(set(expected) - set(mapping))
        extra = sorted(set(mapping) - set(expected))
        parts = []
        if missing:
            parts.append("missing: " + ", ".join(missing))
        if extra:
            parts.append("extra: " + ", ".join(extra))
        raise ContractError(f"{label} mapping must exactly cover {target_type} fields" + (": " + "; ".join(parts) if parts else ""))
    for field, source in mapping.items():
        actual_type = _expression_type(contract, source, source_scopes, f"{label} mapping {field}")
        expected_type = expected[field]
        if actual_type and not _type_assignable(actual_type, expected_type):
            raise ContractError(
                f"{label} mapping {field} source {source} type must be "
                f"{type_display(_effective_type(expected_type))}, got {type_display(_effective_type(actual_type))}"
            )


def _success_outcomes(behavior: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {name: outcome for name, outcome in behavior["outcomes"].items() if outcome["kind"] == "success"}


def _failure_outcomes(behavior: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {name: outcome for name, outcome in behavior["outcomes"].items() if outcome["kind"] == "failure"}


def _primary_success_outcome(behavior: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    successes = _success_outcomes(behavior)
    if len(successes) != 1:
        raise ContractError("Command must declare exactly one success outcome")
    return next(iter(successes.items()))


def _success_result_type(behavior: dict[str, Any]) -> Any:
    return _primary_success_outcome(behavior)[1]["result"]


def _validate_workflows(contract: dict[str, Any]) -> None:
    for wid, workflow in contract["workflows"].items():
        kind, value = _one(workflow["inputs"], f"workflow {wid} trigger")
        if kind == "domain_event" and value not in contract["domain_events"]:
            raise ContractError(f"Workflow {wid} trigger references unknown domain event {value}")
        if kind in {"command", "query"} and value not in _command_query_map(contract):
            raise ContractError(f"Workflow {wid} trigger references unknown command {value}")
        _validate_workflow_outputs(wid, workflow)
        activity_ids = [activity["id"] for activity in workflow["activities"]]
        if len(activity_ids) != len(set(activity_ids)):
            raise ContractError(f"Workflow {wid} activity ids must be unique")
        activity_id_set = set(activity_ids)
        gateway_id_set = set(workflow["gateways"])
        for sequence_flow_id, sequence_flow in workflow["sequence_flows"].items():
            _validate_workflow_sequence_flow_refs(wid, sequence_flow_id, sequence_flow, activity_id_set, gateway_id_set, set(workflow["outputs"]))
        source_types = _workflow_input_source_types(contract, wid, workflow)
        condition_source_types = copy.deepcopy(source_types)
        for activity in workflow["activities"]:
            if activity["command"] in _command_query_map(contract):
                _merge_type_scopes(condition_source_types, _workflow_activity_source_types(contract, activity, _command_query_map(contract)[activity["command"]]))
        terminal_outcomes: set[str] = set()
        for activity in workflow["activities"]:
            if activity["command"] not in _command_query_map(contract):
                raise ContractError(f"Workflow {wid} activity references unknown command {activity['command']}")
            behavior = _command_query_map(contract)[activity["command"]]
            _validate_workflow_activity_bindings(contract, wid, activity, behavior, source_types)
            terminal_outcomes.update(_validate_workflow_activity_sequence_flows(wid, workflow, activity, behavior, activity_id_set, gateway_id_set))
            _merge_type_scopes(source_types, _workflow_activity_source_types(contract, activity, behavior))
        terminal_outcomes.update(_validate_workflow_gateway_sequence_flows(contract, wid, workflow, gateway_id_set, condition_source_types))
        if terminal_outcomes != set(workflow["outputs"]):
            missing = sorted(set(workflow["outputs"]) - terminal_outcomes)
            extra = sorted(terminal_outcomes - set(workflow["outputs"]))
            parts = []
            if missing:
                parts.append("missing output sequence_flows: " + ", ".join(missing))
            if extra:
                parts.append("unknown output sequence_flows: " + ", ".join(extra))
            raise ContractError(f"Workflow {wid} outputs must be reachable from sequence_flows" + (": " + "; ".join(parts) if parts else ""))


def _validate_workflow_outputs(workflow_id: str, workflow: dict[str, Any]) -> None:
    outcomes = workflow["outputs"]
    successes = {name: outcome for name, outcome in outcomes.items() if outcome["kind"] == "success"}
    failures = {name: outcome for name, outcome in outcomes.items() if outcome["kind"] == "failure"}
    if len(successes) != 1:
        raise ContractError(f"Workflow {workflow_id} must declare exactly one success outcome")
    if not failures:
        raise ContractError(f"Workflow {workflow_id} must declare at least one failure outcome")
    for outcome_id, outcome in failures.items():
        _validate_problem_type(f"Workflow {workflow_id} failure outcome {outcome_id} result", outcome["result"])


def _workflow_input_source_types(contract: dict[str, Any], workflow_id: str, workflow: dict[str, Any]) -> TypeScopes:
    payload_type = _workflow_input_payload_type(contract, workflow_id, workflow)
    return {"workflow_input": _typed_source_paths(contract, ("payload",), payload_type)}


def _workflow_input_payload_type(contract: dict[str, Any], workflow_id: str, workflow: dict[str, Any]) -> Any:
    kind, value = _one(workflow["inputs"], f"workflow {workflow_id} trigger")
    if kind == "domain_event":
        return contract["domain_events"][value]["payload_schema"]
    return _success_result_type(_command_query_map(contract)[value])


def _workflow_input_payload_fields(contract: dict[str, Any], workflow_id: str, workflow: dict[str, Any]) -> dict[str, Any]:
    payload_type = _workflow_input_payload_type(contract, workflow_id, workflow)
    fields = object_fields_for_type(contract, payload_type)
    if fields:
        return fields
    return {"payload": payload_type}


def _workflow_activity_source_types(contract: dict[str, Any], activity: dict[str, Any], command: dict[str, Any]) -> TypeScopes:
    sources: TypeScope = {}
    for outcome_id, outcome in command["outcomes"].items():
        sources.update(_typed_source_paths(contract, (activity["id"], outcome_id, "result"), outcome["result"]))
    return {"activity_outcome": sources}


def _workflow_sequence_flow_source_ref(sequence_flow: dict[str, Any]) -> tuple[str, str]:
    return _one(sequence_flow["source_ref"], "workflow sequence_flow source_ref")


def _workflow_sequence_flow_target_ref(sequence_flow: dict[str, Any]) -> tuple[str, str]:
    return _one(sequence_flow["target_ref"], "workflow sequence_flow target_ref")


def _validate_workflow_sequence_flow_refs(
    workflow_id: str,
    sequence_flow_id: str,
    sequence_flow: dict[str, Any],
    activity_ids: set[str],
    gateway_ids: set[str],
    output_ids: set[str],
) -> None:
    source_kind, source_id = _workflow_sequence_flow_source_ref(sequence_flow)
    if source_kind == "activity" and source_id not in activity_ids:
        raise ContractError(f"Workflow {workflow_id} sequence_flow {sequence_flow_id} references unknown source activity {source_id}")
    if source_kind == "gateway" and source_id not in gateway_ids:
        raise ContractError(f"Workflow {workflow_id} sequence_flow {sequence_flow_id} references unknown source gateway {source_id}")
    target_kind, target_id = _workflow_sequence_flow_target_ref(sequence_flow)
    if target_kind == "activity" and target_id not in activity_ids:
        raise ContractError(f"Workflow {workflow_id} sequence_flow {sequence_flow_id} references unknown target activity {target_id}")
    if target_kind == "gateway" and target_id not in gateway_ids:
        raise ContractError(f"Workflow {workflow_id} sequence_flow {sequence_flow_id} references unknown target gateway {target_id}")
    if target_kind == "terminal" and target_id not in output_ids:
        raise ContractError(f"Workflow {workflow_id} sequence_flow {sequence_flow_id} references unknown workflow outcome {target_id}")
    if source_kind == "gateway" and "source_outcome" in sequence_flow:
        raise ContractError(f"Workflow {workflow_id} sequence_flow {sequence_flow_id} source_outcome is only valid for activity sources")
    if source_kind == "activity" and "source_outcome" not in sequence_flow:
        raise ContractError(f"Workflow {workflow_id} sequence_flow {sequence_flow_id} activity source requires source_outcome")
    if source_kind == target_kind and source_id == target_id:
        raise ContractError(f"Workflow {workflow_id} sequence_flow {sequence_flow_id} cannot loop to itself")


def _workflow_sequence_flow_terminal(sequence_flow: dict[str, Any]) -> str | None:
    target_kind, target_id = _workflow_sequence_flow_target_ref(sequence_flow)
    if target_kind == "terminal":
        return target_id
    return None


def _validate_workflow_activity_bindings(
    contract: dict[str, Any],
    workflow_id: str,
    activity: dict[str, Any],
    command: dict[str, Any],
    source_types: TypeScopes,
) -> None:
    bindings = activity["input_mapping"]
    expected = _command_input(command)
    if set(bindings) != set(expected):
        missing = sorted(set(expected) - set(bindings))
        extra = sorted(set(bindings) - set(expected))
        parts = []
        if missing:
            parts.append("missing: " + ", ".join(missing))
        if extra:
            parts.append("extra: " + ", ".join(extra))
        raise ContractError(f"Workflow {workflow_id} activity {activity['id']} input_mapping must exactly map command input" + (": " + "; ".join(parts) if parts else ""))
    for name, source in bindings.items():
        actual_type = _expression_type(
            contract,
            source,
            source_types,
            f"Workflow {workflow_id} activity {activity['id']} input {name}",
        )
        expected_type = expected[name]
        if actual_type and not _type_assignable(actual_type, expected_type):
            raise ContractError(
                f"Workflow {workflow_id} activity {activity['id']} input {name} source {source} type must be "
                f"{type_display(_effective_type(expected_type))}, got {type_display(_effective_type(actual_type))}"
            )


def _validate_workflow_activity_sequence_flows(
    workflow_id: str,
    workflow: dict[str, Any],
    activity: dict[str, Any],
    command: dict[str, Any],
    activity_ids: set[str],
    gateway_ids: set[str],
) -> set[str]:
    sequence_flows = {
        sequence_flow_id: sequence_flow
        for sequence_flow_id, sequence_flow in workflow["sequence_flows"].items()
        if sequence_flow["source_ref"].get("activity") == activity["id"]
    }
    flow_by_outcome: dict[str, tuple[str, dict[str, Any]]] = {}
    duplicate_outcomes: list[str] = []
    for sequence_flow_id, sequence_flow in sequence_flows.items():
        source_outcome = sequence_flow["source_outcome"]
        if source_outcome in flow_by_outcome:
            duplicate_outcomes.append(source_outcome)
        flow_by_outcome[source_outcome] = (sequence_flow_id, sequence_flow)
    if duplicate_outcomes:
        raise ContractError(f"Workflow {workflow_id} activity {activity['id']} sequence_flows duplicate source_outcome: {', '.join(sorted(duplicate_outcomes))}")
    if set(flow_by_outcome) != set(command["outcomes"]):
        missing = sorted(set(command["outcomes"]) - set(flow_by_outcome))
        extra = sorted(set(flow_by_outcome) - set(command["outcomes"]))
        parts = []
        if missing:
            parts.append("missing: " + ", ".join(missing))
        if extra:
            parts.append("extra: " + ", ".join(extra))
        raise ContractError(f"Workflow {workflow_id} activity {activity['id']} sequence_flows must exactly map command outcomes" + (": " + "; ".join(parts) if parts else ""))

    terminal_outcomes: set[str] = set()
    for outcome_id, (sequence_flow_id, sequence_flow) in flow_by_outcome.items():
        outcome = command["outcomes"][outcome_id]
        if "condition" in sequence_flow:
            raise ContractError(f"Workflow {workflow_id} activity {activity['id']} sequence_flow {sequence_flow_id} condition is only valid for gateway sources")
        target_kind, target_id = _workflow_sequence_flow_target_ref(sequence_flow)
        if target_kind == "activity":
            if target_id not in activity_ids:
                raise ContractError(f"Workflow {workflow_id} activity {activity['id']} sequence_flow {sequence_flow_id} references unknown target activity {target_id}")
            if target_id == activity["id"]:
                raise ContractError(f"Workflow {workflow_id} activity {activity['id']} sequence_flow {sequence_flow_id} cannot loop to itself")
        elif target_kind == "gateway":
            if target_id not in gateway_ids:
                raise ContractError(f"Workflow {workflow_id} activity {activity['id']} sequence_flow {sequence_flow_id} references unknown target gateway {target_id}")
        else:
            routed_outcome_id = target_id
            routed_outcome = workflow["outputs"].get(routed_outcome_id)
            if not routed_outcome:
                raise ContractError(f"Workflow {workflow_id} activity {activity['id']} sequence_flow {sequence_flow_id} references unknown workflow outcome {routed_outcome_id}")
            if outcome["kind"] != routed_outcome["kind"]:
                raise ContractError(f"Workflow {workflow_id} activity {activity['id']} sequence_flow {sequence_flow_id} must preserve {outcome['kind']} outcome semantics")
            if not type_equals(routed_outcome["result"], outcome["result"]):
                raise ContractError(
                    f"Workflow {workflow_id} outcome {routed_outcome_id} result must be "
                    f"{type_display(outcome['result'])} to receive activity outcome {outcome_id}"
                )
            if outcome_id in _command_authorization_outcomes(command) and not _is_explicit_authorization_workflow_outcome(routed_outcome_id) and not sequence_flow.get("rationale"):
                raise ContractError(
                    f"Workflow {workflow_id} activity {activity['id']} sequence_flow {sequence_flow_id} collapses authorization failure into {routed_outcome_id}; declare an explicit authorization outcome or add rationale"
                )
            terminal_outcomes.add(routed_outcome_id)
        if "retry_policy" in sequence_flow:
            if outcome["kind"] != "failure":
                raise ContractError(f"Workflow {workflow_id} activity {activity['id']} sequence_flow {sequence_flow_id} retry_policy is only valid for failure outcomes")
            if target_kind != "terminal":
                raise ContractError(f"Workflow {workflow_id} activity {activity['id']} sequence_flow {sequence_flow_id} retry_policy requires a terminal target_ref")
            if not _command_retryable(command):
                raise ContractError(
                    f"Workflow {workflow_id} activity {activity['id']} sequence_flow {sequence_flow_id} retry_policy requires "
                    "a query or retryable invoked behavior"
                )
            retry = sequence_flow["retry_policy"]
            if retry["attempts"] < 1 or retry["attempts"] > 10:
                raise ContractError(f"Workflow {workflow_id} activity {activity['id']} sequence_flow {sequence_flow_id} retry_policy attempts must be between 1 and 10")
    return terminal_outcomes


def _validate_workflow_gateway_sequence_flows(
    contract: dict[str, Any],
    workflow_id: str,
    workflow: dict[str, Any],
    gateway_ids: set[str],
    source_types: TypeScopes,
) -> set[str]:
    terminal_outcomes: set[str] = set()
    incoming = {gateway_id: 0 for gateway_id in gateway_ids}
    outgoing: dict[str, list[tuple[str, dict[str, Any]]]] = {gateway_id: [] for gateway_id in gateway_ids}
    for sequence_flow_id, sequence_flow in workflow["sequence_flows"].items():
        source_kind, source_id = _workflow_sequence_flow_source_ref(sequence_flow)
        target_kind, target_id = _workflow_sequence_flow_target_ref(sequence_flow)
        if target_kind == "gateway":
            incoming[target_id] = incoming.get(target_id, 0) + 1
        if source_kind == "gateway":
            outgoing.setdefault(source_id, []).append((sequence_flow_id, sequence_flow))
        terminal = _workflow_sequence_flow_terminal(sequence_flow)
        if terminal is not None:
            terminal_outcomes.add(terminal)
    for gateway_id in sorted(gateway_ids):
        if incoming.get(gateway_id, 0) == 0:
            raise ContractError(f"Workflow {workflow_id} gateway {gateway_id} must have at least one incoming sequence_flow")
        if not outgoing.get(gateway_id):
            raise ContractError(f"Workflow {workflow_id} gateway {gateway_id} must have at least one outgoing sequence_flow")
    for gateway_id, sequence_flows in outgoing.items():
        unconditional = [sequence_flow_id for sequence_flow_id, sequence_flow in sequence_flows if "condition" not in sequence_flow]
        if len(unconditional) > 1:
            raise ContractError(f"Workflow {workflow_id} gateway {gateway_id} sequence_flows must not declare multiple unconditional branches")
        for sequence_flow_id, sequence_flow in sequence_flows:
            if "condition" in sequence_flow:
                _expression_type(
                    contract,
                    sequence_flow["condition"],
                    source_types,
                    f"Workflow {workflow_id} gateway {gateway_id} sequence_flow {sequence_flow_id} condition",
                )
            if "retry_policy" in sequence_flow:
                raise ContractError(f"Workflow {workflow_id} gateway {gateway_id} sequence_flow {sequence_flow_id} retry_policy is only valid for activity result sequence_flows")
    return terminal_outcomes


def _is_explicit_authorization_workflow_outcome(outcome_id: str) -> bool:
    return any(token in outcome_id for token in ("authorization", "authentication_required", "access_denied"))


def _validate_fixtures(contract: dict[str, Any]) -> None:
    for fixture_id, fixture in contract["fixtures"].items():
        if not fixture_id.startswith("fixture."):
            raise ContractError(f"Fixture id must start with fixture.: {fixture_id}")
        if not isinstance(fixture["values"], dict) or not fixture["values"]:
            raise ContractError(f"Fixture {fixture_id} must declare non-empty values")


def _validate_preconditions(contract: dict[str, Any]) -> None:
    for precondition_id, precondition in contract["preconditions"].items():
        if not precondition_id.startswith("precondition."):
            raise ContractError(f"Precondition id must start with precondition.: {precondition_id}")
        _validate_entity_predicate(contract, precondition, f"Precondition {precondition_id}")


def _validate_assertions(contract: dict[str, Any]) -> None:
    for assertion_id, assertion in contract["assertions"].items():
        if not assertion_id.startswith("assertion."):
            raise ContractError(f"Assertion id must start with assertion.: {assertion_id}")
        _validate_entity_predicate(contract, assertion, f"Assertion {assertion_id}")


def _validate_behavior_scenarios(contract: dict[str, Any]) -> None:
    for behavior_scenario_id, behavior_scenario in contract["behavior_scenarios"].items():
        fixture_ids = behavior_scenario["given"].get("seed_fixtures", [])
        for fixture_id in fixture_ids:
            if fixture_id not in contract["fixtures"]:
                raise ContractError(f"Behavior scenario {behavior_scenario_id} references unknown seed fixture {fixture_id}")
        fixture_values = _fixture_namespace(contract, fixture_ids, behavior_scenario_id)
        _validate_fixture_templates(behavior_scenario, fixture_values, behavior_scenario_id)
        for precondition in behavior_scenario["given"].get("preconditions", []):
            _validate_entity_predicate(contract, precondition, f"Behavior scenario {behavior_scenario_id} given.preconditions")
        for assertion in behavior_scenario["then"].get("postconditions", []):
            _validate_entity_predicate(contract, assertion, f"Behavior scenario {behavior_scenario_id} then.postconditions")
        _validate_behavior_scenario_when(contract, behavior_scenario_id, behavior_scenario)
        _validate_behavior_scenario_system_under_test(contract, behavior_scenario_id, behavior_scenario)
        _validate_behavior_scenario_then(contract, behavior_scenario_id, behavior_scenario)
        _validate_behavior_scenario_archetype(behavior_scenario_id, behavior_scenario)


def _validate_entity_predicate(contract: dict[str, Any], predicate: dict[str, Any], label: str) -> None:
    kind, body = _one_predicate(predicate, label)
    entity_type_id = body["entity_type"]
    if entity_type_id not in contract["entity_types"]:
        raise ContractError(f"{label} references unknown entity_type {entity_type_id}")
    entity_type_name = type_display({"$ref": entity_type_id})
    fields = set(_schema_fields(contract["entity_types"][entity_type_id]["schema"]))
    if kind == "present":
        unknown = set(body["values"]) - fields
        if unknown:
            raise ContractError(f"{label} uses unknown {entity_type_name} fields: {sorted(unknown)}")
    elif kind == "absent":
        unknown = set(body["where"]) - fields
        if unknown:
            raise ContractError(f"{label} filters unknown {entity_type_name} fields: {sorted(unknown)}")
    else:  # pragma: no cover - schema prevents this.
        raise ContractError(f"{label} uses unsupported predicate kind {kind}")


def _fixture_namespace(contract: dict[str, Any], fixture_ids: list[str], behavior_scenario_id: str) -> dict[str, Any]:
    namespace: dict[str, Any] = {}
    for fixture_id in fixture_ids:
        _deep_merge(namespace, copy.deepcopy(contract["fixtures"][fixture_id]["values"]), f"behavior scenario {behavior_scenario_id} fixture {fixture_id}")
    return namespace


def _deep_merge(target: dict[str, Any], source: dict[str, Any], label: str) -> None:
    for key, value in source.items():
        if key not in target:
            target[key] = value
            continue
        existing = target[key]
        if isinstance(existing, dict) and isinstance(value, dict):
            _deep_merge(existing, value, label)
        elif existing != value:
            raise ContractError(f"Conflicting fixture value at {key} in {label}")


def _validate_fixture_templates(node: Any, fixture_values: dict[str, Any], behavior_scenario_id: str) -> None:
    for ref in _fixture_refs(node):
        _resolve_fixture_path(fixture_values, ref, behavior_scenario_id)


def _fixture_refs(node: Any) -> list[str]:
    refs: list[str] = []
    if isinstance(node, dict):
        if set(node) == {"from"} and is_binding_expression(node["from"]):
            refs.append(node["from"])
            return refs
        if set(node) == {"value"}:
            return refs
        for value in node.values():
            refs.extend(_fixture_refs(value))
    elif isinstance(node, list):
        for value in node:
            refs.extend(_fixture_refs(value))
    return refs


def _resolve_fixture_path(fixture_values: dict[str, Any], ref: str, behavior_scenario_id: str) -> Any:
    try:
        expression = parse_binding_expression(ref)
    except BindingExpressionError as exc:
        raise ContractError(f"Behavior scenario {behavior_scenario_id} has malformed binding expression {ref}") from exc
    if expression.root != "fixture":
        raise ContractError(f"Behavior scenario {behavior_scenario_id} references unavailable binding root: ${expression.root}")
    current: Any = fixture_values
    traversed: list[str] = []
    for part in expression.path:
        traversed.append(part)
        if not isinstance(current, dict) or part not in current:
            path = ".".join(traversed)
            raise ContractError(f"Behavior scenario {behavior_scenario_id} fixture ref {ref} cannot resolve at {path}")
        current = current[part]
    return current


def _validate_behavior_scenario_when(contract: dict[str, Any], behavior_scenario_id: str, behavior_scenario: dict[str, Any]) -> None:
    kind, body = _one(behavior_scenario["when"], f"behavior scenario {behavior_scenario_id} when")
    ref = body["ref"]
    if kind in {"open_external_interface", "call_external_interface"}:
        if ref not in contract["external_interfaces"]:
            raise ContractError(f"Behavior scenario {behavior_scenario_id} references unknown external interface {ref}")
        external_interface = contract["external_interfaces"][ref]
        adapter_kind, _ = external_interface_adapter_pair(external_interface)
        external_interface_target_kind, _ = external_interface_invoked_ref_pair(external_interface)
        if kind == "open_external_interface" and not (adapter_kind in {"html_route", "cli"} and external_interface_target_kind == "state_machine"):
            raise ContractError(f"Behavior scenario {behavior_scenario_id} open_external_interface must reference an HTML route or CLI state machine external interface")
        if kind == "call_external_interface" and not (adapter_kind in {"http_api", "cli"} and _external_interface_effective_command_ref(contract, ref)):
            raise ContractError(f"Behavior scenario {behavior_scenario_id} call_external_interface must reference an HTTP API or CLI command external interface")
        _validate_behavior_scenario_external_interface_input(behavior_scenario_id, kind, body, external_interface)
    elif kind == "invoke_command":
        if ref not in _command_query_map(contract):
            raise ContractError(f"Behavior scenario {behavior_scenario_id} references unknown command {ref}")
    elif kind == "emit_domain_event":
        if ref not in contract["domain_events"]:
            raise ContractError(f"Behavior scenario {behavior_scenario_id} references unknown domain event {ref}")
        _validate_behavior_scenario_domain_event_payload(contract, behavior_scenario_id, ref, body.get("payload", {}))
    _validate_behavior_scenario_outcome(contract, behavior_scenario_id, behavior_scenario)


def _validate_behavior_scenario_domain_event_payload(contract: dict[str, Any], behavior_scenario_id: str, domain_event_id: str, payload: dict[str, Any]) -> None:
    domain_event = contract["domain_events"][domain_event_id]
    fields = object_fields_for_type(contract, domain_event["payload_schema"])
    if not fields:
        return
    expected = set(fields)
    actual = set(payload)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        parts = []
        if missing:
            parts.append("missing: " + ", ".join(missing))
        if extra:
            parts.append("extra: " + ", ".join(extra))
        raise ContractError(
            f"Behavior scenario {behavior_scenario_id} emit_domain_event.payload must exactly match domain event {domain_event_id} payload "
            f"{type_display(domain_event['payload_schema'])}" + (": " + "; ".join(parts) if parts else "")
        )


def _validate_behavior_scenario_external_interface_input(behavior_scenario_id: str, kind: str, body: dict[str, Any], external_interface: dict[str, Any]) -> None:
    expected = _external_interface_external_input_types(external_interface)
    actual = body.get("input", {})
    if set(actual) != set(expected):
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        parts = []
        if missing:
            parts.append("missing: " + ", ".join(missing))
        if extra:
            parts.append("extra: " + ", ".join(extra))
        raise ContractError(f"Behavior scenario {behavior_scenario_id} {kind}.input must exactly match external interface input" + (": " + "; ".join(parts) if parts else ""))


def _external_interface_external_input_types(external_interface: dict[str, Any]) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for section in ("path_params", "query_params", "body", "args"):
        fields.update(_external_interface_input_map(external_interface, section))
    return fields


def _system_under_test_ref(system_under_test_ref: dict[str, str]) -> tuple[str, str]:
    return next(iter(system_under_test_ref.items()))


def _validate_behavior_scenario_system_under_test(contract: dict[str, Any], behavior_scenario_id: str, behavior_scenario: dict[str, Any]) -> None:
    sut_kind, sut_ref = _system_under_test_ref(behavior_scenario["system_under_test_ref"])
    collections = {
        "external_interface": "external_interfaces",
        "domain_event": "domain_events",
        "command": "commands", "query": "queries",
        "state_machine": "state_machines",
        "workflow": "workflows",
    }
    if sut_ref not in contract[collections[sut_kind]]:
        raise ContractError(f"Behavior scenario {behavior_scenario_id} system_under_test_ref references unknown {sut_kind} {sut_ref}")

    when_kind, when_body = _one(behavior_scenario["when"], f"behavior scenario {behavior_scenario_id} when")
    then = behavior_scenario["then"]
    command_ref = _behavior_scenario_command_ref(contract, when_kind, when_body)
    external_interface_ref = when_body["ref"] if when_kind in {"open_external_interface", "call_external_interface"} else None
    domain_event_ref = when_body["ref"] if when_kind == "emit_domain_event" else None
    state_machine_ref = _behavior_scenario_state_machine_ref(contract, when_kind, when_body)

    if sut_kind == "external_interface" and external_interface_ref != sut_ref:
        raise ContractError(f"Behavior scenario {behavior_scenario_id} system_under_test_ref.external_interface must match the external interface under test")
    if sut_kind in {"command", "query"} and command_ref != sut_ref:
        raise ContractError(f"Behavior scenario {behavior_scenario_id} system_under_test_ref.command must match the command under test")
    if sut_kind == "domain_event" and domain_event_ref != sut_ref and sut_ref not in (then.get("domain_events") or {}).get("emitted", []):
        raise ContractError(f"Behavior scenario {behavior_scenario_id} system_under_test_ref.domain_event must match the emitted domain event under test")
    if sut_kind == "state_machine":
        asserted = (then.get("state_machine") or {}).get("ref")
        if sut_ref not in {state_machine_ref, asserted}:
            raise ContractError(f"Behavior scenario {behavior_scenario_id} system_under_test_ref.state_machine must match the state machine under test")
    if sut_kind == "workflow":
        workflow = then.get("workflow") or {}
        if workflow.get("ref") != sut_ref:
            raise ContractError(f"Behavior scenario {behavior_scenario_id} system_under_test_ref.workflow must match then.workflow.ref")


def _behavior_scenario_command_ref(contract: dict[str, Any], when_kind: str, when_body: dict[str, Any]) -> str | None:
    if when_kind == "invoke_command":
        return when_body["ref"]
    if when_kind == "call_external_interface":
        return _external_interface_effective_command_ref(contract, when_body["ref"])
    return None


def _external_interface_effective_command_ref(contract: dict[str, Any], external_interface_id: str) -> str | None:
    target_kind, target_ref = external_interface_invoked_ref_pair(contract["external_interfaces"][external_interface_id])
    if target_kind in {"command", "query"}:
        return target_ref
    if target_kind == "external_interface":
        return _external_interface_effective_command_ref(contract, target_ref)
    return None


def _behavior_scenario_state_machine_ref(contract: dict[str, Any], when_kind: str, when_body: dict[str, Any]) -> str | None:
    if when_kind != "open_external_interface":
        return None
    target_kind, target_ref = external_interface_invoked_ref_pair(contract["external_interfaces"][when_body["ref"]])
    if target_kind == "state_machine":
        return target_ref
    return None


def _validate_behavior_scenario_then(contract: dict[str, Any], behavior_scenario_id: str, behavior_scenario: dict[str, Any]) -> None:
    then = behavior_scenario["then"]
    if "state_machine" in then:
        expected_state_machine = then["state_machine"]
        state_machine_id = expected_state_machine["ref"]
        if state_machine_id not in contract["state_machines"]:
            raise ContractError(f"Behavior scenario {behavior_scenario_id} references unknown state machine {state_machine_id}")
        state_machine = contract["state_machines"][state_machine_id]
        if "state" in expected_state_machine:
            state = expected_state_machine["state"]
            if state not in state_machine.get("states", {}):
                raise ContractError(f"Behavior scenario {behavior_scenario_id} references unknown state machine state {state_machine_id}.{state}")
        if "instances" in expected_state_machine:
            state_name = expected_state_machine.get("state")
            selected_state = state_machine.get("states", {}).get(state_name, {}) if state_name else {}
            mounted_instances = {mount["id"]: mount for mount in selected_state.get("child_state_machines", [])}
            if not mounted_instances:
                raise ContractError(f"Behavior scenario {behavior_scenario_id} asserts instance states for non-composed state machine state {state_machine_id}.{state_name}")
            for instance_id, expectation in expected_state_machine["instances"].items():
                if instance_id not in mounted_instances:
                    raise ContractError(f"Behavior scenario {behavior_scenario_id} references unknown state machine instance {state_machine_id}.{instance_id}")
                child_state_machine_id = mounted_instances[instance_id]["state_machine"]
                if expectation["state"] not in contract["state_machines"][child_state_machine_id]["states"]:
                    raise ContractError(f"Behavior scenario {behavior_scenario_id} references unknown state machine state {child_state_machine_id}.{expectation['state']}")
        for sync_id in (expected_state_machine.get("local_signal_sync_rules") or {}).get("observed_rules", []):
            state_name = expected_state_machine.get("state")
            selected_state = state_machine.get("states", {}).get(state_name, {}) if state_name else {}
            if sync_id not in {rule["id"] for rule in selected_state.get("local_signal_sync_rules", [])}:
                raise ContractError(f"Behavior scenario {behavior_scenario_id} references unknown sync rule {state_machine_id}.{sync_id}")
        for key in (expected_state_machine.get("context_schema") or {}):
            if key not in _state_machine_context(state_machine):
                raise ContractError(f"Behavior scenario {behavior_scenario_id} asserts undeclared state machine context {state_machine_id}.{key}")
    for field in ["enables", "forbids", "invoked"]:
        for behavior_ref in then.get(field, []):
            if behavior_ref not in _command_query_map(contract):
                raise ContractError(f"Behavior scenario {behavior_scenario_id} {field} unknown command {behavior_ref}")
    authorization_assertion = then.get("authorization") or {}
    for effect in ("allowed", "denied"):
        for assertion in authorization_assertion.get(effect, []):
            kind, ref = _authorization_assertion_resource(assertion, f"Behavior scenario {behavior_scenario_id} access_policy.{effect}")
            if kind in {"command", "query"} and ref not in _command_query_map(contract):
                raise ContractError(f"Behavior scenario {behavior_scenario_id} access_policy.{effect} unknown command {ref}")
            if kind == "external_interface" and ref not in contract["external_interfaces"]:
                raise ContractError(f"Behavior scenario {behavior_scenario_id} access_policy.{effect} unknown external interface {ref}")
            access_policy = assertion.get("access_policy")
            if access_policy and access_policy not in contract["access_policies"]:
                raise ContractError(f"Behavior scenario {behavior_scenario_id} access_policy.{effect} unknown access_policy {access_policy}")
    entity_exists = (then.get("entity") or {}).get("exists")
    if entity_exists:
        entity_type_id = entity_exists["entity_type"]
        if entity_type_id not in contract["entity_types"]:
            raise ContractError(f"Behavior scenario {behavior_scenario_id} asserts unknown entity_type {entity_type_id}")
        unknown_fields = sorted(set(entity_exists["where"]) - set(_schema_fields(contract["entity_types"][entity_type_id]["schema"])))
        if unknown_fields:
            entity_type_name = type_display({"$ref": entity_type_id})
            raise ContractError(f"Behavior scenario {behavior_scenario_id} entity.exists filters unknown {entity_type_name} fields: {unknown_fields}")
    domain_events = then.get("domain_events") or {}
    emitted = set(domain_events.get("emitted", []))
    not_emitted = set(domain_events.get("not_emitted", []))
    overlap = sorted(emitted & not_emitted)
    if overlap:
        raise ContractError(f"Behavior scenario {behavior_scenario_id} asserts domain events as both emitted and not_emitted: {overlap}")
    for domain_event_id in list(emitted) + list(not_emitted):
        if domain_event_id not in contract["domain_events"]:
            raise ContractError(f"Behavior scenario {behavior_scenario_id} asserts unknown domain event {domain_event_id}")
    _validate_behavior_scenario_domain_event_emissions(contract, behavior_scenario_id, behavior_scenario, emitted, not_emitted)
    _validate_behavior_scenario_invocations(contract, behavior_scenario_id, behavior_scenario)
    workflow = then.get("workflow")
    if workflow and workflow["ref"] not in contract["workflows"]:
        raise ContractError(f"Behavior scenario {behavior_scenario_id} asserts unknown workflow {workflow['ref']}")
    if workflow and workflow.get("outcome"):
        workflow_contract = contract["workflows"][workflow["ref"]]
        if workflow["outcome"] not in workflow_contract["outputs"]:
            raise ContractError(f"Behavior scenario {behavior_scenario_id} asserts unknown workflow outcome {workflow['ref']}.{workflow['outcome']}")
    if workflow and workflow.get("executed") and not _workflow_can_run_from_behavior_scenario(contract, behavior_scenario):
        raise ContractError(f"Behavior scenario {behavior_scenario_id} asserts workflow executed but when does not trigger workflow {workflow['ref']}")
    if "response" in then:
        when_kind, _ = _one(behavior_scenario["when"], f"behavior scenario {behavior_scenario_id} when")
        if when_kind != "call_external_interface":
            raise ContractError(f"Behavior scenario {behavior_scenario_id} response assertions require call_external_interface")
    _validate_authorization_denied_assertion_archetype_outcome(contract, behavior_scenario_id, behavior_scenario)


def _validate_authorization_denied_assertion_archetype_outcome(contract: dict[str, Any], behavior_scenario_id: str, behavior_scenario: dict[str, Any]) -> None:
    if behavior_scenario["archetype"] != "authorization_denied_assertion":
        return
    outcome_id = behavior_scenario["then"].get("outcome")
    if not outcome_id:
        return
    when_kind, when_body = _one(behavior_scenario["when"], f"behavior scenario {behavior_scenario_id} when")
    command_id = _behavior_scenario_command_ref(contract, when_kind, when_body)
    if not command_id:
        raise ContractError(f"Behavior scenario {behavior_scenario_id} authorization_denied_assertion archetype outcome requires a command or query binding")
    authorization = _command_query_map(contract)[command_id].get("authorization")
    if not authorization:
        raise ContractError(f"Behavior scenario {behavior_scenario_id} authorization_denied_assertion archetype outcome requires command authorization")
    mapped = {authorization["authentication_required_as"], authorization["access_denied_as"]}
    if outcome_id not in mapped:
        raise ContractError(
            f"Behavior scenario {behavior_scenario_id} authorization_denied_assertion archetype outcome must be one of command authorization failure outcomes: "
            + ", ".join(sorted(mapped))
        )


def _validate_behavior_scenario_domain_event_emissions(
    contract: dict[str, Any],
    behavior_scenario_id: str,
    behavior_scenario: dict[str, Any],
    emitted: set[str],
    not_emitted: set[str],
) -> None:
    when_kind, when_body = _one(behavior_scenario["when"], f"behavior scenario {behavior_scenario_id} when")
    then = behavior_scenario["then"]
    if when_kind == "emit_domain_event":
        if when_body["ref"] in emitted:
            return
        return
    command_id = _behavior_scenario_command_ref(contract, when_kind, when_body)
    outcome_id = then.get("outcome")
    if not command_id or not outcome_id or outcome_id not in _command_query_map(contract)[command_id]["outcomes"]:
        return
    possible = {
        _emit_domain_event_id(emit)
        for emit in _command_query_map(contract)[command_id]["outcomes"][outcome_id].get("emits", [])
    }
    unexpected = sorted(emitted - possible)
    if unexpected:
        raise ContractError(f"Behavior scenario {behavior_scenario_id} asserts domain events not emitted by {command_id}.{outcome_id}: {unexpected}")
    contradicted = sorted(not_emitted & possible)
    if contradicted:
        raise ContractError(f"Behavior scenario {behavior_scenario_id} asserts not_emitted domain events emitted by {command_id}.{outcome_id}: {contradicted}")


def _validate_behavior_scenario_invocations(contract: dict[str, Any], behavior_scenario_id: str, behavior_scenario: dict[str, Any]) -> None:
    invoked = set(behavior_scenario["then"].get("invoked", []))
    if not invoked:
        return
    when_kind, when_body = _one(behavior_scenario["when"], f"behavior scenario {behavior_scenario_id} when")
    direct = _behavior_scenario_command_ref(contract, when_kind, when_body)
    expected = {direct} if direct else set()
    if when_kind == "emit_domain_event":
        domain_event_id = when_body["ref"]
        for workflow in contract["workflows"].values():
            if workflow["inputs"] == {"domain_event": domain_event_id}:
                expected.update(activity["command"] for activity in workflow["activities"])
    unexpected = sorted(invoked - expected)
    if unexpected:
        raise ContractError(f"Behavior scenario {behavior_scenario_id} asserts command/query bindings unrelated to when: {unexpected}")


def _workflow_can_run_from_behavior_scenario(contract: dict[str, Any], behavior_scenario: dict[str, Any]) -> bool:
    workflow_assertion = behavior_scenario["then"].get("workflow") or {}
    workflow_id = workflow_assertion.get("ref")
    if not workflow_id or workflow_id not in contract["workflows"]:
        return False
    workflow = contract["workflows"][workflow_id]
    when_kind, when_body = _one(behavior_scenario["when"], "behavior scenario when")
    trigger_kind, trigger_ref = _one(workflow["inputs"], f"workflow {workflow_id} trigger")
    if when_kind == "emit_domain_event" and trigger_kind == "domain_event":
        return when_body["ref"] == trigger_ref
    command_id = _behavior_scenario_command_ref(contract, when_kind, when_body)
    return trigger_kind in {"command", "query"} and command_id == trigger_ref


def _validate_behavior_scenario_outcome(contract: dict[str, Any], behavior_scenario_id: str, behavior_scenario: dict[str, Any]) -> None:
    when_kind, when_body = _one(behavior_scenario["when"], f"behavior scenario {behavior_scenario_id} when")
    then = behavior_scenario["then"]
    outcome_id = then.get("outcome")
    behavior: dict[str, Any] | None = None
    external_interface: dict[str, Any] | None = None
    if when_kind == "invoke_command":
        behavior = _command_query_map(contract)[when_body["ref"]]
    elif when_kind == "call_external_interface":
        external_interface = contract["external_interfaces"][when_body["ref"]]
        target_ref = _external_interface_effective_command_ref(contract, when_body["ref"])
        if target_ref:
            behavior = _command_query_map(contract)[target_ref]
    if behavior is None:
        if outcome_id:
            raise ContractError(f"Behavior scenario {behavior_scenario_id} asserts outcome but does not execute an command")
        return
    if not outcome_id:
        raise ContractError(f"Behavior scenario {behavior_scenario_id} must assert an command outcome")
    if outcome_id not in behavior["outcomes"]:
        raise ContractError(f"Behavior scenario {behavior_scenario_id} asserts unknown outcome {outcome_id}")
    if external_interface is None:
        return
    if outcome_id not in _external_interface_named_response_outcomes(contract, when_body["ref"]):
        raise ContractError(f"Behavior scenario {behavior_scenario_id} outcome {outcome_id} is not mapped by external interface {when_body['ref']}")
    response_assertion = then.get("response")
    if response_assertion:
        response = _external_interface_test_response_projection(external_interface, outcome_id)
        for key in ("status", "exit_code"):
            if key in response_assertion and response.get(key) != response_assertion[key]:
                raise ContractError(f"Behavior scenario {behavior_scenario_id} response.{key} does not match external interface response for outcome {outcome_id}")


def _external_interface_test_response_projection(external_interface: dict[str, Any], outcome_id: str) -> dict[str, Any]:
    responses = external_interface_output_responses(external_interface)
    if outcome_id in responses:
        return responses[outcome_id]
    handlers = external_interface_output_response_handlers(external_interface)
    if outcome_id in handlers:
        return handlers[outcome_id]
    return {}


def _validate_behavior_scenario_archetype(behavior_scenario_id: str, behavior_scenario: dict[str, Any]) -> None:
    archetype = behavior_scenario["archetype"]
    when_kind, _ = _one(behavior_scenario["when"], f"behavior scenario {behavior_scenario_id} when")
    then = behavior_scenario["then"]
    if archetype == "empty_collection_state_machine":
        if when_kind != "open_external_interface" or then.get("state_machine", {}).get("state") != "empty":
            raise ContractError(f"Behavior scenario {behavior_scenario_id} empty_collection_state_machine requires open_external_interface and state_machine.state=empty")
    elif archetype == "ready_collection_state_machine":
        if when_kind != "open_external_interface" or then.get("state_machine", {}).get("state") != "ready":
            raise ContractError(f"Behavior scenario {behavior_scenario_id} ready_collection_state_machine requires open_external_interface and state_machine.state=ready")
    elif archetype == "state_machine_composition_sync":
        state_machine_assert = then.get("state_machine", {})
        if when_kind != "open_external_interface" or not state_machine_assert.get("instances"):
            raise ContractError(f"Behavior scenario {behavior_scenario_id} state_machine_composition_sync requires open_external_interface and state_machine.instances")
    elif archetype == "state_machine_composition":
        state_machine_assert = then.get("state_machine", {})
        if when_kind != "open_external_interface" or not state_machine_assert.get("instances"):
            raise ContractError(f"Behavior scenario {behavior_scenario_id} state_machine_composition requires open_external_interface and state_machine.instances")
    elif archetype == "command_outcome":
        if when_kind != "invoke_command" or "outcome" not in then:
            raise ContractError(f"Behavior scenario {behavior_scenario_id} command_outcome requires invoke_command and outcome")
    elif archetype == "external_interface_response":
        if when_kind != "call_external_interface" or "outcome" not in then or "response" not in then:
            raise ContractError(f"Behavior scenario {behavior_scenario_id} external_interface_response requires call_external_interface, outcome, and response")
    elif archetype == "workflow_execution_success":
        workflow = then.get("workflow", {})
        if when_kind != "emit_domain_event" or not workflow.get("executed") or "outcome" not in workflow:
            raise ContractError(f"Behavior scenario {behavior_scenario_id} workflow_execution_success requires emit_domain_event, workflow.executed=true, and workflow.outcome")
    elif archetype == "authorization_denied_assertion":
        if not then.get("authorization", {}).get("denied"):
            raise ContractError(f"Behavior scenario {behavior_scenario_id} authorization_denied_assertion requires authorization.denied")


def _expand_behavior_scenario_predicate_refs(contract: dict[str, Any]) -> tuple[set[str], set[str]]:
    used_preconditions: set[str] = set()
    used_assertions: set[str] = set()
    for behavior_scenario_id, behavior_scenario in contract["behavior_scenarios"].items():
        used_preconditions.update(_expand_precondition_refs(
            contract,
            behavior_scenario["given"],
            "preconditions",
            f"Behavior scenario {behavior_scenario_id}",
        ))
        used_assertions.update(_expand_assertion_refs(
            contract,
            behavior_scenario["then"],
            "postconditions",
            f"Behavior scenario {behavior_scenario_id}",
        ))
    for case_id, case in render_examples(contract).items():
        case_uses: set[str] = set()
        for precondition_use in case.get("precondition_refs", []):
            precondition_id = precondition_use["ref"]
            if precondition_id not in contract["preconditions"]:
                raise ContractError(f"Render example {case_id} references unknown precondition {precondition_id}")
            if precondition_id in case_uses:
                raise ContractError(f"Render example {case_id} uses precondition {precondition_id} more than once")
            case_uses.add(precondition_id)
            used_preconditions.add(precondition_id)
    return used_preconditions, used_assertions


def _expand_precondition_refs(contract: dict[str, Any], owner: dict[str, Any], field: str, label: str) -> set[str]:
    return _expand_predicate_refs(contract, owner, field, label, "preconditions", "precondition", _precondition_body)


def _expand_assertion_refs(contract: dict[str, Any], owner: dict[str, Any], field: str, label: str) -> set[str]:
    return _expand_predicate_refs(contract, owner, field, label, "assertions", "assertion", _assertion_body)


def _expand_predicate_refs(
    contract: dict[str, Any],
    owner: dict[str, Any],
    field: str,
    label: str,
    collection: str,
    kind_label: str,
    body_factory: Callable[[dict[str, Any], str], dict[str, Any]],
) -> set[str]:
    if field not in owner:
        return set()
    expanded: list[dict[str, Any]] = []
    used: set[str] = set()
    for predicate in owner[field]:
        if "ref" not in predicate:
            expanded.append(predicate)
            continue
        predicate_id = predicate["ref"]
        if predicate_id not in contract[collection]:
            raise ContractError(f"{label} references unknown {kind_label} {predicate_id}")
        if predicate_id in used:
            raise ContractError(f"{label} uses {kind_label} {predicate_id} more than once")
        used.add(predicate_id)
        expanded.append(body_factory(contract[collection][predicate_id], predicate_id))
    owner[field] = expanded
    return used


def _precondition_body(precondition: dict[str, Any], label: str) -> dict[str, Any]:
    kind, body = _one_predicate(precondition, f"Precondition {label}")
    return {kind: copy.deepcopy(body)}


def _assertion_body(assertion: dict[str, Any], label: str) -> dict[str, Any]:
    kind, body = _one_predicate(assertion, f"Assertion {label}")
    return {kind: copy.deepcopy(body)}


def _validate_preconditions_are_used(contract: dict[str, Any], used: set[str]) -> None:
    unused = sorted(set(contract["preconditions"]) - used)
    if unused:
        raise ContractError("Unused preconditions: " + ", ".join(unused))


def _validate_assertions_are_used(contract: dict[str, Any], used: set[str]) -> None:
    unused = sorted(set(contract["assertions"]) - used)
    if unused:
        raise ContractError("Unused assertions: " + ", ".join(unused))


def _expand_behavior_scenarios(contract: dict[str, Any]) -> None:
    for behavior_scenario in contract["behavior_scenarios"].values():
        assertions = behavior_scenario["then"]
        if "state_machine" in assertions:
            state_machine_assertion = assertions["state_machine"]
            state_machine_id = state_machine_assertion["ref"]
            state_machine = contract["state_machines"][state_machine_id]
            if "instances" in state_machine_assertion:
                state_name = state_machine_assertion["state"]
                parent_state_machine = state_machine
                parent_state = parent_state_machine["states"][state_name]
                mounts = {mount["id"]: mount for mount in parent_state.get("child_state_machines", [])}
                required = {
                    "query_bindings": list(parent_state_machine.get("query_bindings", {})),
                    "renderer_surfaces": [],
                    "text_resources": [],
                    "media_assets": [],
                    "command_bindings": [],
                }
                state_machine_assertion["renderer_surface"] = parent_state["renderer_surface"]
                required["renderer_surfaces"].append(parent_state["renderer_surface"])
                required["query_bindings"].extend(parent_state.get("query_bindings", {}))
                required["text_resources"].extend(parent_state["text_resources"])
                required["media_assets"].extend(parent_state["media_assets"])
                required["command_bindings"].extend(parent_state["command_bindings"])
                for instance_id, expected in state_machine_assertion["instances"].items():
                    mount = mounts[instance_id]
                    mounted_state_machine = contract["state_machines"][mount["state_machine"]]
                    mounted_state = mounted_state_machine["states"][expected["state"]]
                    expected["renderer_surface"] = mounted_state["renderer_surface"]
                    expected["source"] = mount["state_machine"]
                    required["query_bindings"].extend(mounted_state_machine.get("query_bindings", {}))
                    required["query_bindings"].extend(mounted_state.get("query_bindings", {}))
                    required["renderer_surfaces"].append(mounted_state["renderer_surface"])
                    required["text_resources"].extend(mounted_state["text_resources"])
                    required["media_assets"].extend(mounted_state["media_assets"])
                    required["command_bindings"].extend(mounted_state["command_bindings"])
                state_machine_assertion["state_machine_composition"] = {
                    "renderers": parent_state.get("renderers", {}),
                    "child_state_machines": parent_state.get("child_state_machines", []),
                    "local_signal_sync_rules": parent_state.get("local_signal_sync_rules", []),
                }
                assertions["requires"] = {key: list(dict.fromkeys(values)) for key, values in required.items()}
            elif "state" in state_machine_assertion:
                state_name = state_machine_assertion["state"]
                state = state_machine["states"][state_name]
                state_machine_assertion["renderer_surface"] = state["renderer_surface"]
                assertions["requires"] = {
                    "query_bindings": list(state_machine.get("query_bindings", {})) + list(state.get("query_bindings", {})),
                    "renderer_surfaces": [state["renderer_surface"]],
                    "text_resources": list(state["text_resources"]),
                    "media_assets": list(state["media_assets"]),
                    "command_bindings": list(state["command_bindings"]),
                }
        when_kind, when_body = _one(behavior_scenario["when"], "behavior scenario when")
        behavior_ref = None
        if when_kind == "invoke_command":
            behavior_ref = when_body["ref"]
        elif when_kind == "call_external_interface":
            behavior_ref = _external_interface_effective_command_ref(contract, when_body["ref"])
        if behavior_ref:
            assertions.setdefault("authorization", {"allowed": [{"command": behavior_ref}]})
        _expand_authorization_assertions(contract, assertions)


def _expand_authorization_assertions(contract: dict[str, Any], assertions: dict[str, Any]) -> None:
    policy = assertions.get("authorization")
    if not policy:
        return
    for effect in ("allowed", "denied"):
        for assertion in policy.get(effect, []):
            if "access_policy" in assertion:
                continue
            kind, ref = _authorization_assertion_resource(assertion, f"access_policy.{effect}")
            if kind in {"command", "query"}:
                authorization = _command_query_map(contract)[ref].get("authorization")
                if authorization:
                    assertion["access_policy"] = authorization["policy"]
            elif kind == "external_interface":
                access_policy = contract["external_interfaces"][ref].get("access_policy")
                if access_policy:
                    assertion["access_policy"] = access_policy


def _stash_generated_tree(root: Path) -> tuple[Path | None, Path | None]:
    generated = root / GENERATED_SPEC_DIR
    if not generated.exists():
        return None, None
    stash_parent_root = root / SOURCE_SPEC_PATH.parent
    stash_parent_root.mkdir(parents=True, exist_ok=True)
    backup_parent = Path(tempfile.mkdtemp(prefix=".pyspec-generated-backup-", dir=str(stash_parent_root)))
    backup = backup_parent / "generated"
    shutil.move(str(generated), str(backup))
    return backup_parent, backup


def _restore_generated_tree(root: Path, backup: Path | None) -> None:
    generated = root / GENERATED_SPEC_DIR
    if generated.exists():
        shutil.rmtree(generated)
    if backup and backup.exists():
        shutil.move(str(backup), str(generated))


def _cleanup_generated_backup(backup_parent: Path | None) -> None:
    if backup_parent and backup_parent.exists():
        shutil.rmtree(backup_parent, ignore_errors=True)


def write_compiled(root: Path, source_path: Path, tools_root: Path | None = None, render_audit: bool = True, layers: set[str] | None = None) -> dict[str, Any]:
    source = read_yaml(source_path)
    author = author_from_source(source, layers=layers)
    contract = compile_author(author, layers=layers)
    backup_parent, backup = _stash_generated_tree(root)
    try:
        source_output = root / SOURCE_SPEC_PATH
        source_output.parent.mkdir(parents=True, exist_ok=True)
        write_yaml(source_output, author, sort_keys=False)
        compiled_path = root / COMPILED_SPEC_PATH
        compiled_path.parent.mkdir(parents=True, exist_ok=True)
        write_yaml(compiled_path, contract)
        for relative, content, kind in projection_files(contract, layers=layers):
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            if kind == "json":
                write_json(path, content)
            elif kind == "yaml":
                write_yaml(path, content)
            elif kind == "text":
                path.write_text(content, encoding="utf-8")
            else:  # pragma: no cover
                raise ContractError(f"Unknown projection kind: {kind}")
        if render_audit:
            from .audit import generate_audit
            previous_audit_root = backup / "audit_evidence" if backup else None
            generate_audit(root, contract, tools_root=tools_root, previous_audit_root=previous_audit_root)
    except BaseException:
        _restore_generated_tree(root, backup)
        _cleanup_generated_backup(backup_parent)
        raise
    _cleanup_generated_backup(backup_parent)
    return contract


def default_source_path(root: Path) -> Path:
    authored = root / SOURCE_SPEC_PATH
    if authored.exists():
        return authored
    raise ContractError(f"Missing {SOURCE_SPEC_PATH}")



def _diff_message(label: str, expected: set[Any], actual: set[Any]) -> str:
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    parts = []
    if missing:
        parts.append("missing: " + ", ".join(map(str, missing)))
    if extra:
        parts.append("extra: " + ", ".join(map(str, extra)))
    return f"{label} drift" + (": " + "; ".join(parts) if parts else "")

def _one(mapping: dict[str, Any], label: str) -> tuple[str, Any]:
    if len(mapping) != 1:
        raise ContractError(f"{label} must contain exactly one selector")
    return next(iter(mapping.items()))


def _one_predicate(mapping: dict[str, Any], label: str) -> tuple[str, Any]:
    items = [(key, mapping[key]) for key in ("absent", "present") if key in mapping]
    if len(items) != 1:
        raise ContractError(f"{label} must contain exactly one predicate selector")
    return items[0]


def _require(mapping: dict[str, Any], owner: str, field: str) -> None:
    if field not in mapping:
        raise ContractError(f"External interface {owner} must declare {field}")


def _require_adapter(adapter: dict[str, Any], owner: str, field: str) -> None:
    if field not in adapter:
        raise ContractError(f"External interface {owner} adapter must declare {field}")


def _path_params(path: str | None) -> set[str]:
    return set(re.findall(r"{([a-z][a-z0-9_]*)}", path or ""))


def _validate_path_params(external_interface: dict[str, Any], external_interface_id: str) -> None:
    placeholders = _path_params(external_interface_path(external_interface))
    declared = set(_external_interface_input_map(external_interface, "path_params"))
    if placeholders != declared:
        raise ContractError(
            f"External interface {external_interface_id} path params {sorted(placeholders)} must exactly match input.path_params {sorted(declared)}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compile spec/spec.yaml into spec/generated/compiled/spec.yaml and projections.")
    parser.add_argument("source", nargs="?", default=None, help="authored spec file; defaults to spec/spec.yaml")
    parser.add_argument("--out", default=".")
    parser.add_argument("--layers", default=None, help="Comma-separated authoring layers, e.g. core,http or core,ui,textual. Omit for unrestricted mode.")
    parser.add_argument("--no-audit", action="store_true", help="Regenerate spec/projections without visual audit renders.")
    args = parser.parse_args(argv)
    try:
        out = Path(args.out).resolve()
        source = Path(args.source).resolve() if args.source else default_source_path(out).resolve()
        write_compiled(out, source, layers=parse_layers(args.layers), render_audit=not args.no_audit)
        os._exit(0)
    except (ContractError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
