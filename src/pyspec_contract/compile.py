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
from typing import Any

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
from .runtime_refs import ReferenceExpressionError, is_reference_expression, parse_reference_expression
from .targets import (
    STATE_MACHINE_RENDERERS,
    entry_state_machine_renderer,
    entry_point_adapter_pair,
    entry_point_input_bindings,
    entry_point_cli_command,
    entry_point_input,
    entry_point_method,
    entry_point_path,
    entry_point_response_handlers,
    entry_point_responses,
    entry_point_schedule_expression,
    entry_point_target_pair,
    entry_target_pair,
    entry_workflow_trigger_bindings,
)
from .type_expr import (
    TypeExpressionError,
    array_of,
    base_model_name,
    dereference_type,
    effective_field_type,
    is_array_of_model,
    is_problem_type,
    literal_type_expr,
    normalize_field_map,
    normalize_type_expr,
    normalize_type_map,
    model_name,
    object_fields_for_type,
    type_display,
    type_equals,
    unwrap_nullable,
)

ROOT = Path(__file__).resolve().parent


class ContractError(ValueError):
    pass


class ContractLintWarning(UserWarning):
    pass


TypeScope = dict[tuple[str, ...], Any]
TypeScopes = dict[str, TypeScope]


ACTOR_SOURCE_SCOPE: TypeScope = {
    ("id",): {"primitive": "ID"},
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
    "asset",
    "content_case",
    "render_profile",
    "fixture",
    "fact",
    "data_contract",
    "model",
    "authorization_policy",
    "application_action",
    "domain_event",
    "state_machine",
    "entry_point",
    "workflow",
    "test_case",
)



ENTITY_SECTIONS: dict[str, str] = {
    "text_resource": "text_resources",
    "asset": "assets",
    "content_case": "content_cases",
    "render_profile": "render_profiles",
    "fixture": "fixtures",
    "fact": "facts",
    "data_contract": "data_contracts",
    "model": "models",
    "authorization_policy": "authorization_policies",
    "application_action": "application_actions",
    "domain_event": "domain_events",
    "state_machine": "state_machines",
    "entry_point": "entry_points",
    "workflow": "workflows",
    "test_case": "test_cases",
}


REF_KINDS = [
    "asset",
    "authorization_policy",
    "cli_command",
    "cli_response_handler",
    "endpoint",
    "entry_point_delegate",
    "entry_point_target",
    "local_signal_raise",
    "action_binding",
    "action_outcome_effect",
    "data_loader",
    "data_loader_outcome_effect",
    "route",
    "runtime_response",
    "screen",
    "state_machine",
    "surface",
    "text",
    "workflow",
]


def empty_compiled_contract(project: str) -> dict[str, Any]:
    return {
        "project": project,
        "text_resources": {},
        "assets": {},
        "content_cases": {},
        "render_profiles": {},
        "fixtures": {},
        "facts": {},
        "data_contracts": {},
        "models": {},
        "authorization_policies": {},
        "application_actions": {},
        "domain_events": {},
        "state_machines": {},
        "entry_points": {},
        "workflows": {},
        "test_cases": {},
        "refs": {},
    }


AUTHOR_SECTION_ORDER = (
    "fixtures",
    "facts",
    "data_contracts",
    "models",
    "authorization_policies",
    "application_actions",
    "domain_events",
    "state_machines",
    "entry_points",
    "workflows",
    "test_cases",
    "text_resources",
    "assets",
    "content_cases",
    "render_profiles",
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


def _normalize_signals(signals: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    signals = signals or {}
    normalized = _empty_signals()
    accepts = signals.get("accepts") or {}
    for signal_name, signal in (accepts.get("local_signals") or {}).items():
        signal_spec = copy.deepcopy(signal)
        signal_spec["payload_schema"] = normalize_type_map(signal_spec.get("payload_schema"))
        normalized["accepts"]["local_signals"][signal_name] = signal_spec
    for signal_name, signal in (accepts.get("data_refresh_signals") or {}).items():
        signal_spec = copy.deepcopy(signal)
        signal_spec["payload_schema"] = normalize_type_map(signal_spec.get("payload_schema"))
        normalized["accepts"]["data_refresh_signals"][signal_name] = signal_spec
    emits = signals.get("emits") or {}
    for signal_name, signal in (emits.get("local_signals") or {}).items():
        signal_spec = copy.deepcopy(signal)
        signal_spec["payload_schema"] = normalize_type_map(signal_spec.get("payload_schema"))
        normalized["emits"]["local_signals"][signal_name] = signal_spec
    return normalized


def _prune_empty_author_state_machine_signal_directions(author: dict[str, Any]) -> None:
    for state_machine in (author.get("state_machines") or {}).values():
        signals = state_machine.get("signals")
        if not isinstance(signals, dict):
            continue
        for direction, groups in (("accepts", ("local_signals", "data_refresh_signals")), ("emits", ("local_signals",))):
            direction_body = signals.get(direction)
            if not isinstance(direction_body, dict):
                continue
            for group in groups:
                for signal in (direction_body.get(group) or {}).values():
                    if isinstance(signal, dict) and signal.get("payload_schema") == {}:
                        signal.pop("payload_schema")
                if direction_body.get(group) == {}:
                    direction_body.pop(group)
            if not direction_body:
                signals.pop(direction)
        if not signals:
            state_machine.pop("signals", None)


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

    _derive_application_action_transitions(contract)
    contract["domain_events"] = _derive_domain_events(contract)
    contract["refs"] = _derive_refs(contract)
    used_facts = _expand_test_case_fact_uses(contract)
    _semantic_validate(contract, used_facts)
    _expand_test_cases(contract)
    validate_against_schema(contract, "spec.schema.json")
    return contract


def _apply_author_defaults(entity: str, spec: dict[str, Any]) -> None:
    spec.setdefault("rationale", _default_rationale(entity, spec["id"]))
    if entity == "state_machine":
        spec.setdefault("context", {})
        spec.setdefault("data_loaders", {})
        spec["signals"] = _normalize_signals(spec.get("signals"))
        spec.setdefault("transitions", [])
    elif entity == "application_action":
        for outcome in spec.get("outcomes", {}).values():
            outcome.setdefault("emits", [])


def _compile_entity(entity: str, spec: dict[str, Any] | None, contract: dict[str, Any]) -> dict[str, Any]:
    if spec is None:  # pragma: no cover - delete never compiles an entity.
        raise ContractError(f"Cannot compile missing {entity} spec")

    if entity == "text_resource":
        item = {"placeholder": spec["placeholder"], "rationale": spec["rationale"]}
        for field in ["max_chars", "intent", "args", "source_ref"]:
            if field in spec:
                item[field] = spec[field]
        return item

    if entity == "asset":
        item = {"media_kind": spec["media_kind"], "placeholder": spec["placeholder"], "rationale": spec["rationale"]}
        for field in ["asset_role", "alt_text", "args", "source_ref"]:
            if field in spec:
                item[field] = spec[field]
        return item

    if entity == "content_case":
        item = {"ref": spec["ref"], "args": spec["args"], "rationale": spec["rationale"]}
        if "seed_fixtures" in spec:
            item["seed_fixtures"] = spec["seed_fixtures"]
        return item

    if entity == "render_profile":
        item = {"rationale": spec["rationale"]}
        for field in ["html_viewports", "textual_viewports"]:
            if field in spec:
                item[field] = spec[field]
        return item

    if entity == "fixture":
        return {"values": spec["values"], "rationale": spec["rationale"]}

    if entity == "fact":
        kind, body = _one_fact(spec, f"Fact {spec['id']}")
        return {kind: body, "rationale": spec["rationale"]}

    if entity == "model":
        item = {
            "fields": normalize_field_map(spec["fields"]),
            "lifecycle": spec.get("lifecycle"),
            "rationale": spec["rationale"],
        }
        return item

    if entity == "data_contract":
        return {
            "fields": normalize_field_map(spec["fields"]),
            "rationale": spec["rationale"],
        }

    if entity == "application_action":
        outcomes = {}
        for outcome_id, outcome in spec["outcomes"].items():
            normalized_outcome = copy.deepcopy(outcome)
            normalized_outcome["result"] = normalize_type_expr(normalized_outcome["result"])
            normalized_outcome.setdefault("emits", [])
            outcomes[outcome_id] = normalized_outcome
        application_action: dict[str, Any] = {
            "action_kind": spec["action_kind"],
            "input": normalize_type_map(spec.get("input", {})),
            "outcomes": outcomes,
            "reads": list(spec.get("reads", [])),
            "creates": list(spec.get("creates", [])),
            "updates": list(spec.get("updates", [])),
            "deletes": list(spec.get("deletes", [])),
            "rationale": spec["rationale"],
        }
        if spec.get("retry_safe"):
            application_action["retry_safe"] = True
        if "authorization" in spec:
            application_action["authorization"] = copy.deepcopy(spec["authorization"])
        return application_action

    if entity == "authorization_policy":
        return {
            "subjects": copy.deepcopy(spec["subjects"]),
            "targets": copy.deepcopy(spec["targets"]),
            "effect": spec["effect"],
            "conditions": copy.deepcopy(spec.get("conditions", [])),
            "rationale": spec["rationale"],
        }

    if entity == "domain_event":
        return {
            "payload_schema": normalize_type_expr(spec["payload_schema"]),
            "emitted_by": [],
            "rationale": spec["rationale"],
        }

    if entity == "state_machine":
        state_machine_id = spec["id"]
        state_machine: dict[str, Any] = {
            "context": normalize_field_map(spec["context"]),
            "data_loaders": _compile_data_loaders(spec.get("data_loaders", {}), scope="state_machine"),
            "signals": _normalize_signals(spec.get("signals")),
            "initial_view_state": spec["initial_view_state"],
            "view_states": _compile_view_states(state_machine_id, spec.get("view_states", {})),
            "transitions": spec.get("transitions", []),
            "rationale": spec["rationale"],
        }
        if "model" in spec:
            state_machine["model"] = spec["model"]
        if "archetype" in spec:
            state_machine["archetype"] = spec["archetype"]
        return state_machine

    if entity == "entry_point":
        entry: dict[str, Any] = {
            "adapter": spec["adapter"],
            "target": spec["target"],
            "rationale": spec["rationale"],
        }
        if "authorization_policy" in spec:
            entry["authorization_policy"] = copy.deepcopy(spec["authorization_policy"])
        if spec.get("retry_safe"):
            entry["retry_safe"] = True
        adapter_kind, _ = entry_point_adapter_pair(entry)
        target_kind, target = entry_point_target_pair(entry)
        if adapter_kind == "html_route" and target_kind == "state_machine":
            entry["route"] = rules.route_ref(target["ref"])
        elif adapter_kind == "http_api" and target_kind == "application_action":
            entry["endpoint"] = rules.endpoint_ref(target["ref"])
            if target["ref"] in contract["application_actions"]:
                action_authorization = contract["application_actions"][target["ref"]].get("authorization")
                if action_authorization:
                    entry.setdefault("authorization_policy", copy.deepcopy(action_authorization["policy"]))
        elif adapter_kind == "cli":
            entry_id = spec["id"]
            command_ref_source = entry_id[len("entry_point.cli."):] if target_kind == "entry_point" and entry_id.startswith("entry_point.cli.") else target["ref"]
            entry["cli_command_ref"] = rules.cli_command_ref(command_ref_source)
            if target_kind == "application_action" and target["ref"] in contract["application_actions"]:
                action_authorization = contract["application_actions"][target["ref"]].get("authorization")
                if action_authorization:
                    entry.setdefault("authorization_policy", copy.deepcopy(action_authorization["policy"]))
        elif adapter_kind in {"worker", "scheduled"} and target_kind == "workflow":
            entry["workflow_ref"] = rules.workflow_ref(target["ref"])
        return entry

    if entity == "workflow":
        return {
            "trigger": spec["trigger"],
            "outcomes": spec["outcomes"],
            "steps": spec["steps"],
            "ref": rules.workflow_ref(spec["id"]),
            "rationale": spec["rationale"],
        }

    if entity == "test_case":
        return {
            "feature_tag": spec["feature_tag"],
            "title": spec["title"],
            "archetype": spec["archetype"],
            "subject_ref": spec["subject_ref"],
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


def _compile_data_loaders(invocations: dict[str, Any], *, scope: str) -> dict[str, Any]:
    compiled = copy.deepcopy(invocations or {})
    for invocation in compiled.values():
        default_load = {"on_start": True} if scope == "state_machine" else {"on_enter": True}
        invocation.setdefault("load", default_load)
    return compiled


def _compile_view_states(owner_id: str, states: dict[str, Any]) -> dict[str, Any]:
    subject = _ref_subject(owner_id)
    compiled = {}
    for state_name, state in states.items():
        item = {
            "surface": _state_surface_ref(owner_id, state_name),
            "data_loaders": _compile_data_loaders(state.get("data_loaders", {}), scope="view_state"),
            "text": [rules.text_ref(subject, state_name, slot) for slot in state.get("text_slots", [])],
            "assets": [rules.asset_ref(subject, state_name, slot) for slot in state.get("asset_slots", [])],
            "fields": state.get("field_slots", []),
            "action_bindings": copy.deepcopy(state.get("action_bindings", {})),
        }
        if "renderers" in state:
            item["renderers"] = state["renderers"]
        for field in ["child_state_machines", "signal_sync_rules"]:
            if field in state:
                item[field] = state[field]
        if state.get("render_audit_cases"):
            item["render_audit_cases"] = {
                case_name: _compile_audit_case(owner_id, state_name, case_name, case)
                for case_name, case in state["render_audit_cases"].items()
            }
        compiled[state_name] = item
    return compiled


def _compile_audit_case(state_machine_id: str, state_name: str, case_name: str, case: dict[str, Any]) -> dict[str, Any]:
    item = {
        "seed_fixtures": case["seed_fixtures"],
        "rationale": case.get("rationale", _default_rationale("render_audit_case", f"{state_machine_id}.{state_name}.{case_name}")),
    }
    for field in ["context", "fact_refs", "instances"]:
        if field in case:
            item[field] = case[field]
    return item


def audit_cases(contract: dict[str, Any]) -> dict[str, dict[str, Any]]:
    cases: dict[str, dict[str, Any]] = {}
    for state_machine_id, state_machine in sorted(contract.get("state_machines", {}).items()):
        for state_name, state in sorted(state_machine.get("view_states", {}).items()):
            for case_name, case in sorted((state.get("render_audit_cases") or {}).items()):
                case_id = f"{state_machine_id}.{state_name}.{case_name}.audit"
                cases[case_id] = {"state_machine": state_machine_id, "view_state": state_name, "name": case_name, **case}
    return cases


def _derive_application_action_transitions(contract: dict[str, Any]) -> None:
    """Derive transition application action details from model lifecycle declarations.

    Authored sources should not have to repeat the same state transition in both
    the model lifecycle and the application_action. The compiled contract remains
    explicit for downstream projections and validators.
    """
    by_application_action: dict[str, dict[str, Any]] = {}
    for model_id, model in contract.get("models", {}).items():
        lifecycle = model.get("lifecycle")
        if not lifecycle:
            continue
        field = lifecycle["field"]
        for transition in lifecycle.get("transitions", []):
            application_action_id = transition["triggered_by"]
            if application_action_id in by_application_action:
                raise ContractError(f"Application action {application_action_id} is used by multiple lifecycle transitions")
            by_application_action[application_action_id] = {
                "model": model_id,
                "field": field,
                "from": transition["from"],
                "to": transition["to"],
            }

    for application_action_id, application_action in contract.get("application_actions", {}).items():
        if application_action.get("action_kind") != "transition" or "transition" in application_action:
            continue
        derived = by_application_action.get(application_action_id)
        if not derived:
            continue
        application_action["transition"] = derived


def _derive_domain_events(contract: dict[str, Any]) -> dict[str, Any]:
    domain_events: dict[str, Any] = copy.deepcopy(contract.get("domain_events", {}))
    for application_action_id, operation in sorted(contract["application_actions"].items()):
        for outcome_id, outcome in sorted(operation["outcomes"].items()):
            for emit in outcome.get("emits", []):
                event_id = _emit_domain_event_id(emit)
                if outcome["kind"] != "success":
                    raise ContractError(f"Application action {application_action_id} failure outcome {outcome_id} must not emit domain events")
                payload_type = domain_events.get(event_id, {}).get("payload_schema", outcome["result"])
                event = domain_events.setdefault(event_id, {
                    "emitted_by": [],
                    "payload_schema": payload_type,
                    "rationale": operation["rationale"],
                })
                _validate_emit_payload_mapping(contract, application_action_id, operation, outcome_id, outcome, event_id, event["payload_schema"], emit)
                event["emitted_by"].append(application_action_id)
    return domain_events


def _emit_domain_event_id(emit: Any) -> str:
    if isinstance(emit, str):
        return emit
    return emit["domain_event"]


def _derive_refs(contract: dict[str, Any]) -> dict[str, list[str]]:
    refs: dict[str, set[str]] = {kind: set() for kind in REF_KINDS}
    refs["authorization_policy"].update(contract.get("authorization_policies", {}))
    refs["text"].update(contract.get("text_resources", {}))
    refs["asset"].update(contract.get("assets", {}))
    for state_machine_id in contract["state_machines"]:
        refs["state_machine"].add(state_machine_id)
    for state_machine_id, owner in contract["state_machines"].items():
        for invocation_id, invocation in sorted((owner.get("data_loaders") or {}).items()):
            refs["data_loader"].add(_generated_data_loader_ref(state_machine_id, None, invocation_id))
            for outcome_id, effect in sorted(invocation.get("outcome_effects", {}).items()):
                refs["data_loader_outcome_effect"].add(_generated_data_loader_outcome_effect_ref(state_machine_id, None, invocation_id, outcome_id))
                for branch in _query_outcome_effect_branches(effect):
                    signal = branch.get("raise")
                    if signal:
                        kind, signal_id = _signal_raise_selector_key(signal)
                        refs["local_signal_raise"].add(
                            _generated_query_local_signal_raise_ref(state_machine_id, None, invocation_id, outcome_id, kind, signal_id)
                        )
        for state_name, state in owner.get("view_states", {}).items():
            refs["surface"].add(state["surface"])
            refs["text"].update(state["text"])
            refs["asset"].update(state["assets"])
            for invocation_id, invocation in sorted((state.get("data_loaders") or {}).items()):
                refs["data_loader"].add(_generated_data_loader_ref(state_machine_id, state_name, invocation_id))
                for outcome_id, effect in sorted(invocation.get("outcome_effects", {}).items()):
                    refs["data_loader_outcome_effect"].add(_generated_data_loader_outcome_effect_ref(state_machine_id, state_name, invocation_id, outcome_id))
                    for branch in _query_outcome_effect_branches(effect):
                        signal = branch.get("raise")
                        if signal:
                            kind, signal_id = _signal_raise_selector_key(signal)
                            refs["local_signal_raise"].add(
                                _generated_query_local_signal_raise_ref(state_machine_id, state_name, invocation_id, outcome_id, kind, signal_id)
                            )
            for invocation_id, invocation in sorted((state.get("action_bindings") or {}).items()):
                refs["action_binding"].add(_generated_action_binding_ref(state_machine_id, state_name, invocation_id))
                for outcome_id, effect in sorted(invocation.get("outcome_effects", {}).items()):
                    refs["action_outcome_effect"].add(_generated_action_outcome_effect_ref(state_machine_id, state_name, invocation_id, outcome_id))
                    signal = effect.get("raise")
                    if signal:
                        kind, signal_id = _signal_raise_selector_key(signal)
                        refs["local_signal_raise"].add(
                            _generated_application_action_local_signal_raise_ref(state_machine_id, state_name, invocation_id, outcome_id, kind, signal_id)
                        )
    for entry_id, entry in contract["entry_points"].items():
        target_kind, target_ref = entry_target_pair(entry)
        refs["entry_point_target"].add(_generated_entry_point_target_ref(entry_id, target_kind, target_ref))
        if target_kind == "entry_point":
            refs["entry_point_delegate"].add(_generated_entry_point_delegate_ref(entry_id, target_ref))
        if entry_point_adapter_pair(entry)[0] == "cli":
            for outcome_id, handler in sorted(entry_point_response_handlers(entry).items()):
                refs["cli_response_handler"].add(_generated_cli_response_handler_ref(entry_id, outcome_id))
                for stream_name in ("stdout", "stderr"):
                    output = handler.get(stream_name) or {}
                    bindings = output.get("bindings") or {}
                    for binding_name, binding in sorted(bindings.items()):
                        if _binding_references_root(binding, "response"):
                            refs["runtime_response"].add(_generated_runtime_response_ref(entry_id, outcome_id, stream_name, binding_name))
        for ref_kind, field in [
            ("route", "route"),
            ("endpoint", "endpoint"),
            ("cli_command", "cli_command_ref"),
            ("workflow", "workflow_ref"),
        ]:
            if field in entry:
                refs[ref_kind].add(entry[field])
    for state_machine_id, state_machine in contract["state_machines"].items():
        if _state_machine_has_textual_screen(state_machine):
            refs["screen"].add(rules.screen_ref(state_machine_id))
    for workflow in contract["workflows"].values():
        refs["workflow"].add(workflow["ref"])
    return {kind: sorted(values) for kind, values in sorted(refs.items()) if values}


def _generated_entry_point_target_ref(entry_id: str, target_kind: str, target_ref: str) -> str:
    return f"entry_point_target.{rules.resource_tail(entry_id)}.{target_kind}.{rules.resource_tail(target_ref)}"


def _generated_entry_point_delegate_ref(entry_id: str, delegated_entry_id: str) -> str:
    return f"entry_point_delegate.{rules.resource_tail(entry_id)}.to.{rules.resource_tail(delegated_entry_id)}"


def _generated_cli_response_handler_ref(entry_id: str, outcome_id: str) -> str:
    return f"cli_response_handler.{rules.resource_tail(entry_id)}.{outcome_id}"


def _generated_runtime_response_ref(entry_id: str, outcome_id: str, stream_name: str, binding_name: str) -> str:
    return f"runtime_response.{rules.resource_tail(entry_id)}.{outcome_id}.{stream_name}.{binding_name}"


def _generated_action_binding_ref(state_machine_id: str, state_name: str, invocation_id: str) -> str:
    return f"action_binding.{rules.resource_tail(state_machine_id)}.{state_name}.{invocation_id}"


def _generated_action_outcome_effect_ref(state_machine_id: str, state_name: str, invocation_id: str, outcome_id: str) -> str:
    return f"action_outcome_effect.{rules.resource_tail(state_machine_id)}.{state_name}.{invocation_id}.{outcome_id}"


def _generated_data_loader_ref(state_machine_id: str, state_name: str | None, invocation_id: str) -> str:
    state_part = f".{state_name}" if state_name else ""
    return f"data_loader.{rules.resource_tail(state_machine_id)}{state_part}.{invocation_id}"


def _generated_data_loader_outcome_effect_ref(state_machine_id: str, state_name: str | None, invocation_id: str, outcome_id: str) -> str:
    state_part = f".{state_name}" if state_name else ""
    return f"data_loader_outcome_effect.{rules.resource_tail(state_machine_id)}{state_part}.{invocation_id}.{outcome_id}"


def _generated_application_action_local_signal_raise_ref(
    state_machine_id: str,
    state_name: str,
    invocation_id: str,
    outcome_id: str,
    signal_kind: str,
    signal_id: str,
) -> str:
    return f"local_signal_raise.{rules.resource_tail(state_machine_id)}.{state_name}.action_binding.{invocation_id}.{outcome_id}.{signal_kind}.{signal_id}"


def _generated_query_local_signal_raise_ref(
    state_machine_id: str,
    state_name: str | None,
    invocation_id: str,
    outcome_id: str,
    signal_kind: str,
    signal_id: str,
) -> str:
    state_part = f".{state_name}" if state_name else ""
    return f"local_signal_raise.{rules.resource_tail(state_machine_id)}{state_part}.data_loader.{invocation_id}.{outcome_id}.{signal_kind}.{signal_id}"


def _binding_references_root(binding: Any, root: str) -> bool:
    if not isinstance(binding, dict) or "from" not in binding:
        return False
    try:
        return parse_reference_expression(binding["from"]).root == root
    except ReferenceExpressionError:
        return False


def _state_machine_has_textual_screen(state_machine: dict[str, Any]) -> bool:
    return any(
        bool(renderer_textual(state).get("layout"))
        or (not state.get("child_state_machines") and bool(renderer_textual(state).get("presentation")))
        for state in state_machine.get("view_states", {}).values()
    )


def _semantic_validate(contract: dict[str, Any], used_facts: set[str]) -> None:
    _validate_text_assets(contract)
    _validate_content_cases(contract)
    _validate_render_profiles(contract)
    _validate_data_contracts(contract)
    _validate_models(contract)
    _validate_type_references(contract)
    _validate_application_actions(contract)
    _validate_entry_point_delegation_graph(contract)
    _validate_entry_point_response_maps(contract)
    _validate_state_machines(contract)
    _validate_state_machine_signal_payload_consistency(contract)
    _validate_entries(contract)
    _validate_authorization_policies(contract)
    _validate_workflows(contract)
    _validate_fixtures(contract)
    _validate_facts(contract)
    _validate_test_cases(contract)
    _validate_audit_cases(contract)
    _validate_facts_are_used(contract, used_facts)



def _validate_text_assets(contract: dict[str, Any]) -> None:
    used_text: set[str] = set()
    used_assets: set[str] = set()
    for owner in contract.get("state_machines", {}).values():
        for state in owner.get("view_states", {}).values():
            used_text.update(state.get("text", []))
            used_assets.update(state.get("assets", []))
    for entry in contract.get("entry_points", {}).values():
        for handler in entry_point_response_handlers(entry).values():
            for stream in ("stdout", "stderr"):
                output = handler.get(stream) or {}
                if output.get("text"):
                    used_text.add(output["text"])
    declared_text = set(contract.get("text_resources", {}))
    declared_assets = set(contract.get("assets", {}))
    if declared_text != used_text:
        raise ContractError(_diff_message("text resources", used_text, declared_text))
    if declared_assets != used_assets:
        raise ContractError(_diff_message("asset placeholders", used_assets, declared_assets))
    for text_id, item in contract.get("text_resources", {}).items():
        max_chars = item.get("max_chars")
        if max_chars is not None and len(item["placeholder"]) > max_chars:
            raise ContractError(f"Text resource {text_id} placeholder exceeds max_chars")
    for asset_id, item in contract.get("assets", {}).items():
        alt_text = item.get("alt_text")
        if alt_text and alt_text not in declared_text:
            raise ContractError(f"Asset {asset_id} alt_text references unknown text resource {alt_text}")




def _validate_content_cases(contract: dict[str, Any]) -> None:
    final_refs = {
        ref
        for section in ["text_resources", "assets"]
        for ref, item in contract.get(section, {}).items()
        if item.get("source_ref")
    }
    declared_case_refs: set[str] = set()
    for ref, item in list(contract.get("text_resources", {}).items()) + list(contract.get("assets", {}).items()):
        source_ref = item.get("source_ref")
        if source_ref:
            if source_ref != ref:
                raise ContractError(f"Content source_ref for {ref} must equal the content id")
            if not item.get("args"):
                # Arg-less resolvers are allowed, but declaring args is preferred for dynamic content.
                pass
    for case_id, case in contract.get("content_cases", {}).items():
        ref = case["ref"]
        section = "text_resources" if ref.startswith("text.") else "assets"
        if ref not in contract.get(section, {}):
            label = "text resource" if section == "text_resources" else "asset"
            raise ContractError(f"Content case {case_id} references unknown {label} {ref}")
        for fixture_id in case.get("seed_fixtures", []):
            if fixture_id not in contract["fixtures"]:
                raise ContractError(f"Content case {case_id} references unknown fixture {fixture_id}")
        fixture_values = _fixture_namespace(contract, case.get("seed_fixtures", []), f"content case {case_id}")
        _validate_fixture_templates(case, fixture_values, f"content case {case_id}")
        expected = set(contract[section][ref].get("args", {}))
        actual = set(case.get("args", {}))
        if expected != actual:
            raise ContractError(_diff_message(f"content case {case_id} args", expected, actual))
        declared_case_refs.add(ref)
    missing = sorted(final_refs - declared_case_refs)
    if missing:
        raise ContractError("Final content resolvers require content_case coverage: " + ", ".join(missing))


def _validate_render_profiles(contract: dict[str, Any]) -> None:
    required_renderers = {
        renderer
        for state_machine in contract.get("state_machines", {}).values()
        for state in state_machine.get("view_states", {}).values()
        for renderer in _view_state_renderers(state)
    }
    if required_renderers and not contract.get("render_profiles"):
        raise ContractError("At least one render_profile is required when renderable state_machines are declared")
    available_renderers = set()
    for profile in contract.get("render_profiles", {}).values():
        if profile.get("html_viewports"):
            available_renderers.add("html")
        if profile.get("textual_viewports"):
            available_renderers.add("textual")
    missing = sorted(required_renderers - available_renderers)
    if missing:
        raise ContractError("Renderable state_machines require render_profile viewports for: " + ", ".join(missing))


def _validate_audit_cases(contract: dict[str, Any]) -> None:
    cases = audit_cases(contract)
    composable_states = {
        (state_machine_id, state_name)
        for state_machine_id, state_machine in contract.get("state_machines", {}).items()
        for state_name, state in state_machine.get("view_states", {}).items()
        if state.get("renderers") or state.get("child_state_machines")
    }
    covered_composable_states: set[tuple[str, str]] = set()
    for case_id, case in cases.items():
        state_machine_id = case["state_machine"]
        state_name = case["view_state"]
        state_machine = contract["state_machines"][state_machine_id]
        state = state_machine["view_states"][state_name]
        model = state_machine.get("model")
        if not _view_state_renderers(state):
            raise ContractError(f"Render audit case {case_id} references view state {state_machine_id}.{state_name} with no visual renderer")
        for fixture_id in case.get("seed_fixtures", []):
            if fixture_id not in contract["fixtures"]:
                raise ContractError(f"Render audit case {case_id} references unknown fixture {fixture_id}")
        fixture_values = _fixture_namespace(contract, case.get("seed_fixtures", []), f"render audit case {case_id}")
        _validate_fixture_templates(case, fixture_values, f"render audit case {case_id}")
        for fact_use in case.get("fact_refs", []):
            fact_id = fact_use["ref"]
            _validate_fixture_templates(contract["facts"][fact_id], fixture_values, f"render audit case {case_id} fact {fact_id}")
        if model and state.get("fields") and not set(state.get("fields", [])) <= set(state_machine.get("context", {})) and not _setup_has_model(contract, case.get("seed_fixtures", []), case.get("fact_refs", []), model):
            raise ContractError(f"Render audit case {case_id} renders fields for {state_machine_id}.{state_name} but does not include a {model} fixture or fact")
        if state.get("child_state_machines"):
            mounted_instances = {mount["id"]: mount for mount in state["child_state_machines"]}
            expected_instances = case.get("instances")
            if not expected_instances:
                raise ContractError(f"Render audit case {case_id} for composed state machine state {state_machine_id}.{state_name} must declare instances")
            if set(expected_instances) != set(mounted_instances):
                raise ContractError(f"Render audit case {case_id} instance state vector must exactly cover mounted state machine instances")
            for instance_id, expected in expected_instances.items():
                child_state_machine_id = mounted_instances[instance_id]["state_machine"]
                if expected["view_state"] not in contract["state_machines"][child_state_machine_id]["view_states"]:
                    raise ContractError(f"Render audit case {case_id} references unknown state machine view state {child_state_machine_id}.{expected['view_state']}")
                selected_state = contract["state_machines"][child_state_machine_id]["view_states"][expected["view_state"]]
                child_model = contract["state_machines"][child_state_machine_id].get("model")
                child_context = set(contract["state_machines"][child_state_machine_id].get("context", {}))
                if child_model and selected_state.get("fields") and not set(selected_state.get("fields", [])) <= child_context and not _setup_has_model(contract, case.get("seed_fixtures", []), case.get("fact_refs", []), child_model):
                    raise ContractError(f"Render audit case {case_id} renders fields for {child_state_machine_id}.{expected['view_state']} but does not include a {child_model} fixture or fact")
            covered_composable_states.add((state_machine_id, state_name))
    missing_composed = sorted(f"{state_machine_id}.{state_name}" for state_machine_id, state_name in composable_states - covered_composable_states)
    if missing_composed:
        raise ContractError("Missing render audit coverage for composed state machine states: " + ", ".join(missing_composed))
    _validate_state_machine_view_state_fixture_coverage(contract)


def _view_state_renderers(state: dict[str, Any]) -> set[str]:
    renderers = state.get("renderers") or {}
    result: set[str] = set()
    if renderers.get("html"):
        result.add("html")
    if renderers.get("textual"):
        result.add("textual")
    return result


def _validate_state_machine_view_state_fixture_coverage(contract: dict[str, Any]) -> None:
    for state_machine_id, state_machine in contract.get("state_machines", {}).items():
        model = state_machine.get("model")
        for state_name, state in state_machine.get("view_states", {}).items():
            if model and state.get("fields") and not set(state.get("fields", [])) <= set(state_machine.get("context", {})) and not _setup_has_model(contract, list(contract.get("fixtures", {})), _all_fact_uses(contract), model):
                raise ContractError(f"Rendered fields for {state_machine_id}.{state_name} require at least one {model} fixture or fact")


def _setup_has_model(contract: dict[str, Any], fixture_ids: list[str], fact_uses: list[dict[str, str]], model_id: str) -> bool:
    return _fixtures_include_model(contract, fixture_ids, model_id) or _fact_uses_include_model(contract, fact_uses, model_id)


def _fixtures_include_model(contract: dict[str, Any], fixture_ids: list[str], model_id: str) -> bool:
    for fixture_id in fixture_ids:
        if fixture_id in contract.get("fixtures", {}) and _value_contains_model(contract["fixtures"][fixture_id]["values"], model_id):
            return True
    return False


def _fact_uses_include_model(contract: dict[str, Any], fact_uses: list[dict[str, str]], model_id: str) -> bool:
    for fact_use in fact_uses:
        fact_id = fact_use["ref"]
        fact = contract["facts"].get(fact_id)
        if not fact:
            continue
        kind, body = _one_fact(fact, f"Fact {fact_id}")
        if kind == "present" and body["model"] == model_id:
            return True
    return False


def _all_fact_uses(contract: dict[str, Any]) -> list[dict[str, str]]:
    return [{"ref": fact_id} for fact_id in contract.get("facts", {})]


def _value_contains_model(value: Any, model_id: str) -> bool:
    if isinstance(value, dict):
        if value.get("model") == model_id:
            return True
        return any(_value_contains_model(child, model_id) for child in value.values())
    if isinstance(value, list):
        return any(_value_contains_model(item, model_id) for item in value)
    return False


def _validate_models(contract: dict[str, Any]) -> None:
    for rid, model in contract["models"].items():
        lifecycle = model.get("lifecycle")
        if not lifecycle:
            continue
        if lifecycle["field"] not in model["fields"]:
            raise ContractError(f"Model {rid} lifecycle field is not a field: {lifecycle['field']}")
        states = set(lifecycle["states"])
        if lifecycle["initial"] not in states:
            raise ContractError(f"Model {rid} lifecycle initial state is not declared: {lifecycle['initial']}")
        for transition in lifecycle.get("transitions", []):
            if transition["from"] not in states or transition["to"] not in states:
                raise ContractError(f"Model {rid} lifecycle transition uses unknown state: {transition}")
            if transition["triggered_by"] not in contract["application_actions"]:
                raise ContractError(
                    f"Model {rid} lifecycle transition references unknown application action {transition['triggered_by']}"
                )


def _validate_data_contracts(contract: dict[str, Any]) -> None:
    for data_contract_id, data_contract in contract.get("data_contracts", {}).items():
        if not data_contract_id.startswith("data_contract."):
            raise ContractError(f"Data contract id must start with data_contract.: {data_contract_id}")
        if not data_contract.get("fields"):
            raise ContractError(f"Data contract {data_contract_id} must declare fields")


def _validate_type_references(contract: dict[str, Any]) -> None:
    for model_id, model in contract.get("models", {}).items():
        for field_name, field in model.get("fields", {}).items():
            _validate_type_reference(contract, f"Model {model_id}.{field_name}", field["type"])
    for data_contract_id, data_contract in contract.get("data_contracts", {}).items():
        for field_name, field in data_contract.get("fields", {}).items():
            _validate_type_reference(contract, f"Data contract {data_contract_id}.{field_name}", field["type"])
    for application_action_id, application_action in contract.get("application_actions", {}).items():
        for field_name, type_expr in application_action.get("input", {}).items():
            _validate_type_reference(contract, f"Application action {application_action_id} input {field_name}", type_expr)
        for outcome_id, outcome in application_action.get("outcomes", {}).items():
            _validate_type_reference(contract, f"Application action {application_action_id} outcome {outcome_id}", outcome["result"])
    for state_machine_id, state_machine in contract.get("state_machines", {}).items():
        for field_name, field in state_machine.get("context", {}).items():
            _validate_type_reference(contract, f"State machine {state_machine_id} context {field_name}", field["type"])
    for event_id, event in contract.get("domain_events", {}).items():
        _validate_type_reference(contract, f"Domain event {event_id} payload_schema", event["payload_schema"])


def _validate_type_reference(contract: dict[str, Any], label: str, expr: Any) -> None:
    normalized = normalize_type_expr(expr)
    kind, value = next(iter(normalized.items()))
    if kind == "model":
        if value not in contract["models"]:
            raise ContractError(f"{label} references unknown model {value}")
        return
    if kind == "data_contract":
        if value not in contract.get("data_contracts", {}):
            raise ContractError(f"{label} references unknown data contract {value}")
        return
    if kind in {"array", "map", "nullable"}:
        _validate_type_reference(contract, label, value)
        return
    if kind == "object":
        for field_name, field in normalize_field_map(value.get("fields", value)).items():
            _validate_type_reference(contract, f"{label}.{field_name}", field["type"])


def _validate_application_actions(contract: dict[str, Any]) -> None:
    models = contract["models"]
    application_actions = contract["application_actions"]
    for cid, cap in application_actions.items():
        _validate_application_action_relationships(cid, cap, models)
        _validate_action_authorization_outcomes(cid, cap)
        transition = cap.get("transition")
        if transition:
            model_id = transition["model"]
            lifecycle = models[model_id].get("lifecycle")
            if not lifecycle:
                raise ContractError(f"Application action {cid} declares transition but {model_id} has no lifecycle")
            if transition["field"] != lifecycle["field"]:
                raise ContractError(f"Application action {cid} transition field does not match model lifecycle")
            if transition["from"] not in lifecycle["states"] or transition["to"] not in lifecycle["states"]:
                raise ContractError(f"Application action {cid} transition references unknown lifecycle state")
    for rid, model in models.items():
        lifecycle = model.get("lifecycle")
        if not lifecycle:
            continue
        for transition in lifecycle.get("transitions", []):
            triggered_by = transition["triggered_by"]
            operation = application_actions[triggered_by]
            if operation["action_kind"] != "transition":
                raise ContractError(
                    f"Model {rid} lifecycle transition {triggered_by} must reference a transition application action"
                )
            invalid_state = operation["outcomes"].get("invalid_state")
            if not invalid_state or invalid_state["kind"] != "failure":
                raise ContractError(
                    f"Transition application action {triggered_by} referenced by model lifecycle must declare invalid_state failure outcome"
                )
            cap_transition = operation.get("transition")
            if not cap_transition:
                raise ContractError(f"Transition application action {triggered_by} must be referenced by model lifecycle declarations")
            if (
                cap_transition["model"] != rid
                or cap_transition["from"] != transition["from"]
                or cap_transition["to"] != transition["to"]
            ):
                raise ContractError(f"Model {rid} lifecycle and application action {triggered_by} disagree")
    for event_id, event in contract["domain_events"].items():
        for cap_id in event["emitted_by"]:
            if cap_id not in application_actions:
                raise ContractError(f"Domain event {event_id} emitted by unknown application action {cap_id}")


def _validate_application_action_relationships(cid: str, cap: dict[str, Any], models: dict[str, Any]) -> None:
    _validate_action_outcomes(cid, cap)
    for field in ["creates", "reads", "updates", "deletes"]:
        for model_id in cap.get(field, []):
            if model_id not in models:
                raise ContractError(f"Application action {cid} {field} unknown model {model_id}")

    if "transition" in cap:
        model_id = cap["transition"]["model"]
        if model_id not in models:
            raise ContractError(f"Application action {cid} transition references unknown model {model_id}")

    action_kind = cap["action_kind"]
    if action_kind == "query":
        _require_relationship(cid, cap, "reads")
        _reject_non_empty_relationships(cid, cap, {"creates", "updates", "deletes"})
        if "transition" in cap:
            raise ContractError(f"Query application action {cid} must not declare transition")
        emitting_outcomes = sorted(outcome_id for outcome_id, outcome in cap["outcomes"].items() if outcome.get("emits"))
        if emitting_outcomes:
            raise ContractError(f"Query application action {cid} must not emit domain events: {emitting_outcomes}")
        _validate_query_success_result(cid, cap)
    elif action_kind == "command":
        if "transition" in cap:
            raise ContractError(f"Only transition application_actions may declare transition: {cid}")
    elif action_kind == "transition":
        if "transition" not in cap:
            raise ContractError(f"Transition application action {cid} must be referenced by model lifecycle declarations")
        _reject_non_empty_relationships(cid, cap, {"creates", "reads", "updates", "deletes"})
        _require_output_model(cid, cap, cap["transition"]["model"])
    else:  # pragma: no cover - schema prevents this.
        raise ContractError(f"Unsupported action_kind {action_kind}: {cid}")


def _require_relationship(cid: str, cap: dict[str, Any], field: str) -> None:
    if not cap.get(field):
        raise ContractError(f"Application action {cid} action_kind {cap['action_kind']} must declare {field}")


def _require_exact_relationship(cid: str, cap: dict[str, Any], field: str, count: int) -> None:
    _require_relationship(cid, cap, field)
    actual = len(cap[field])
    if actual != count:
        raise ContractError(f"Application action {cid} action_kind {cap['action_kind']} must declare exactly {count} {field}")


def _reject_non_empty_relationships(cid: str, cap: dict[str, Any], fields: set[str]) -> None:
    extras = sorted(field for field in fields if cap.get(field))
    if extras:
        raise ContractError(f"Application action {cid} action_kind {cap['action_kind']} does not support effects: {extras}")


def _require_output_model(cid: str, cap: dict[str, Any], model_id: str) -> None:
    if model_name(_success_result_type(cap)) != model_id:
        raise ContractError(f"Application action {cid} success outcome result must be {model_id}")


def _validate_query_success_result(cid: str, cap: dict[str, Any]) -> None:
    reads = cap.get("reads", [])
    if len(reads) != 1:
        return
    expected_model = reads[0]
    result_type = _success_result_type(cap)
    if model_name(result_type) == expected_model or is_array_of_model(result_type, expected_model):
        return
    raise ContractError(
        f"Application action {cid} query success outcome result must be {expected_model} "
        f"or {type_display(array_of({'model': expected_model}))}"
    )


def _validate_action_outcomes(cid: str, cap: dict[str, Any]) -> None:
    outcomes = cap["outcomes"]
    successes = _success_outcomes(cap)
    failures = _failure_outcomes(cap)
    if len(successes) != 1:
        raise ContractError(f"Application action {cid} must declare exactly one success outcome")
    if not failures:
        raise ContractError(f"Application action {cid} must declare at least one failure outcome")
    unknown_kinds = sorted(
        f"{name}:{outcome['kind']}" for name, outcome in outcomes.items() if outcome["kind"] not in {"success", "failure"}
    )
    if unknown_kinds:
        raise ContractError(f"Application action {cid} has unsupported outcome kinds: {unknown_kinds}")
    for outcome_id, outcome in outcomes.items():
        emits = outcome.get("emits", [])
        emit_ids = [_emit_domain_event_id(emit) for emit in emits]
        if len(emit_ids) != len(set(emit_ids)):
            raise ContractError(f"Application action {cid} outcome {outcome_id} emits duplicate domain events")
        if outcome["kind"] == "failure":
            if emits:
                raise ContractError(f"Application action {cid} failure outcome {outcome_id} must not emit domain events")
            if not is_problem_type(outcome["result"]):
                raise ContractError(f"Application action {cid} failure outcome {outcome_id} result must be Problem or a *Problem type")


def _validate_action_authorization_outcomes(application_action_id: str, application_action: dict[str, Any]) -> None:
    authorization = application_action.get("authorization")
    if not authorization:
        return
    unauthenticated_as = authorization["unauthenticated_as"]
    forbidden_as = authorization["forbidden_as"]
    if unauthenticated_as == forbidden_as:
        raise ContractError(
            f"Application action {application_action_id} authorization unauthenticated_as and forbidden_as must be distinct outcomes"
        )
    for field in ("unauthenticated_as", "forbidden_as"):
        outcome_id = authorization[field]
        outcome = application_action["outcomes"].get(outcome_id)
        if not outcome:
            raise ContractError(
                f"Application action {application_action_id} authorization.{field} references unknown outcome {outcome_id}"
            )
        if outcome["kind"] != "failure":
            raise ContractError(
                f"Application action {application_action_id} authorization.{field} must map to a failure outcome: {outcome_id}"
            )
        if outcome.get("emits"):
            raise ContractError(
                f"Application action {application_action_id} authorization.{field} outcome {outcome_id} must not emit domain events"
            )


def _validate_authorization_policies(contract: dict[str, Any]) -> None:
    authorization_policies = contract["authorization_policies"]
    application_actions = contract["application_actions"]
    entry_points = contract["entry_points"]
    _validate_authorization_policy_reuse(authorization_policies)
    for application_action_id, application_action in application_actions.items():
        authorization = application_action.get("authorization")
        if not authorization:
            continue
        policy_id = authorization["policy"]
        if policy_id not in authorization_policies:
            raise ContractError(f"Application action {application_action_id} authorization.policy references unknown authorization policy {policy_id}")
        if not _authorization_policy_covers_target(authorization_policies[policy_id], "application_action", application_action_id):
            raise ContractError(f"Application action {application_action_id} authorization.policy {policy_id} must cover application action target")
    for entry_id, entry in entry_points.items():
        policy_id = entry.get("authorization_policy")
        if not policy_id:
            continue
        if policy_id not in authorization_policies:
            raise ContractError(f"Entry point {entry_id} references unknown authorization policy {policy_id}")
        target_kind, target_ref = entry_target_pair(entry)
        if not _authorization_policy_covers_target(authorization_policies[policy_id], "entry_point", entry_id) and not _authorization_policy_covers_target(authorization_policies[policy_id], target_kind, target_ref):
            raise ContractError(f"Entry point {entry_id} authorization_policy {policy_id} must cover entry point or invoked target")
    for policy_id, policy in authorization_policies.items():
        for target in policy["targets"]:
            kind, ref = _one(target, f"Authorization policy {policy_id} target")
            if kind == "model" and ref not in contract["models"]:
                raise ContractError(f"Authorization policy {policy_id} target references unknown model {ref}")
            if kind == "application_action" and ref not in application_actions:
                raise ContractError(f"Authorization policy {policy_id} target references unknown application action {ref}")
            if kind == "entry_point" and ref not in entry_points:
                raise ContractError(f"Authorization policy {policy_id} target references unknown entry point {ref}")
        for condition in policy.get("conditions", []):
            kind, body = _one(condition, f"Authorization policy {policy_id} condition")
            if kind in {"unconditional", "input_present", "subject_has_role", "value_equals"}:
                continue
            if kind in {"model_exists", "model_state"}:
                model_id = body["model"]
                if model_id not in contract["models"]:
                    raise ContractError(f"Authorization policy {policy_id} condition references unknown model {model_id}")
                if kind == "model_state" and body["field"] not in contract["models"][model_id]["fields"]:
                    raise ContractError(f"Authorization policy {policy_id} condition references unknown {model_id} field {body['field']}")
                continue
            raise ContractError(f"Authorization policy {policy_id} condition is unsupported: {kind}")


def _validate_authorization_policy_reuse(authorization_policies: dict[str, Any]) -> None:
    fingerprints: dict[str, str] = {}
    for policy_id, policy in authorization_policies.items():
        fingerprint = _authorization_policy_rule_fingerprint(policy)
        existing = fingerprints.get(fingerprint)
        if existing:
            raise ContractError(
                f"Authorization policies {existing} and {policy_id} have identical subjects, effect, and conditions; "
                "reuse one authorization_policy with combined targets instead of duplicating rule sets"
            )
        fingerprints[fingerprint] = policy_id


def _authorization_policy_rule_fingerprint(policy: dict[str, Any]) -> str:
    subjects = sorted(_canonical_json(subject) for subject in policy.get("subjects", []))
    conditions = sorted(_canonical_json(condition) for condition in policy.get("conditions", []))
    return _canonical_json(
        {
            "subjects": subjects,
            "effect": policy.get("effect"),
            "conditions": conditions,
        }
    )


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _authorization_policy_covers_target(policy: dict[str, Any], kind: str, ref: str) -> bool:
    return any(target == {kind: ref} for target in policy.get("targets", []))


def _authorization_assertion_target(assertion: dict[str, Any], label: str) -> tuple[str, str]:
    items = [(key, assertion[key]) for key in ("application_action", "entry_point") if key in assertion]
    if len(items) != 1:
        raise ContractError(f"{label} must contain exactly one authorization target")
    return items[0]


def _validate_emit_payload_mapping(
    contract: dict[str, Any],
    application_action_id: str,
    application_action: dict[str, Any],
    outcome_id: str,
    outcome: dict[str, Any],
    event_id: str,
    event_payload: Any,
    emit: Any,
) -> None:
    label = f"Application action {application_action_id} outcome {outcome_id} emit {event_id}"
    source_scopes: TypeScopes = {
        "input": _type_scope(application_action["input"]),
        "outcome": _typed_source_paths(contract, ("result",), outcome["result"]),
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
        model = state_machine.get("model")
        if model and model not in contract["models"]:
            raise ContractError(f"state machine {state_machine_id} references unknown model {model}")
        _validate_data_loaders(
            contract,
            f"state machine {state_machine_id}",
            state_machine,
            state_machine.get("data_loaders", {}),
            scope="state_machine",
            model=model,
        )
        if state_machine["initial_view_state"] not in state_machine["view_states"]:
            raise ContractError(f"state machine {state_machine_id} initial view state is not declared: {state_machine['initial_view_state']}")
        model_fields = set(contract["models"][model]["fields"]) if model else set()
        field_names = model_fields | set(state_machine.get("context", {}))
        for state_name, state in state_machine["view_states"].items():
            _validate_state_machine_view_state(
                contract,
                f"state machine {state_machine_id}",
                state_machine,
                state_name,
                state,
                field_names=field_names,
                data_context=state_machine.get("context", {}),
                model=model,
            )
            if state.get("child_state_machines") or state.get("renderers") or state.get("signal_sync_rules"):
                _validate_state_composition(contract, state_machine_id, state_machine, state_name, state)
        _validate_data_loader_id_scope(state_machine_id, state_machine)
        _validate_field_state_data_sources(
            contract,
            f"state machine {state_machine_id}",
            state_machine,
            state_machine["view_states"],
            state_machine.get("data_loaders", {}),
            set(state_machine.get("context", {})),
        )
        _validate_collection_empty_signal_effects(state_machine_id, state_machine)
        _validate_machine_query_ownership(contract, state_machine_id, state_machine)
        _validate_state_machine_transitions(contract, state_machine_id, state_machine)
        _validate_signals(state_machine_id, state_machine)


def _validate_state_machine_view_state(
    contract: dict[str, Any],
    owner_label: str,
    state_machine: dict[str, Any],
    state_name: str,
    state: dict[str, Any],
    field_names: set[str],
    data_context: dict[str, Any] | None = None,
    model: str | None = None,
) -> None:
    _validate_data_loaders(
        contract,
        f"{owner_label}.{state_name}",
        state_machine,
        state.get("data_loaders", {}),
        scope="view_state",
        model=model,
        view_state=state,
    )
    for field in state.get("fields", []):
        if field not in field_names:
            raise ContractError(f"{owner_label}.{state_name} field slot is not declared on the model/context: {field}")
    _validate_action_bindings(contract, owner_label, state_machine, state_name, state)
    _validate_presentation(contract, owner_label, field_names, state_name, state)


def _validate_action_bindings(
    contract: dict[str, Any],
    owner_label: str,
    state_machine: dict[str, Any],
    state_name: str,
    state: dict[str, Any],
) -> None:
    context = state_machine.get("context", {})
    for invocation_id, invocation in sorted((state.get("action_bindings") or {}).items()):
        label = f"{owner_label}.{state_name} action_binding {invocation_id}"
        application_action_id = invocation["application_action"]
        if application_action_id not in contract["application_actions"]:
            raise ContractError(f"{label} references unknown application action {application_action_id}")
        application_action = contract["application_actions"][application_action_id]
        expected_input = application_action.get("input") or {}
        bindings = invocation.get("input_bindings") or {}
        _validate_runtime_binding_map(
            contract,
            f"{label} input_bindings",
            bindings,
            expected_input,
            {"context": _type_scope(context), "actor": ACTOR_SOURCE_SCOPE},
        )
        _lint_literal_actor_bindings(label, bindings)
        _validate_action_binding_outcome_effects(contract, label, state_machine, invocation, application_action_id, application_action)


def _lint_literal_actor_bindings(label: str, bindings: dict[str, Any]) -> None:
    for field_name, binding in sorted(bindings.items()):
        if field_name not in ACTOR_LITERAL_FIELD_NAMES:
            continue
        if isinstance(binding, dict) and set(binding) == {"value"} and isinstance(binding["value"], str):
            warnings.warn(
                f"{label} input_bindings.{field_name} uses a literal actor/user id; prefer $actor.id or an explicit context binding",
                ContractLintWarning,
                stacklevel=3,
            )


def _validate_action_binding_outcome_effects(
    contract: dict[str, Any],
    label: str,
    state_machine: dict[str, Any],
    invocation: dict[str, Any],
    application_action_id: str,
    application_action: dict[str, Any],
) -> None:
    effects = invocation["outcome_effects"]
    expected_outcomes = set(application_action["outcomes"])
    actual_outcomes = set(effects)
    if actual_outcomes != expected_outcomes:
        missing = sorted(expected_outcomes - actual_outcomes)
        extra = sorted(actual_outcomes - expected_outcomes)
        parts = []
        if missing:
            parts.append("missing: " + ", ".join(missing))
        if extra:
            parts.append("extra: " + ", ".join(extra))
        raise ContractError(f"{label} outcome_effects must exactly map application action outcomes" + (": " + "; ".join(parts) if parts else ""))

    for outcome_id, effect in sorted(effects.items()):
        effect_label = f"{label} outcome_effects.{outcome_id}"
        outcome = application_action["outcomes"][outcome_id]
        if _validate_no_local_effect(
            effect_label,
            outcome,
            effect,
            effect_scope="action_binding",
            has_response_surface=_application_action_has_response_surface(contract, application_action_id, outcome_id),
            authorization_outcome=outcome_id in _action_authorization_outcomes(application_action),
        ):
            continue
        signal = effect.get("raise")
        if not signal:
            raise ContractError(f"{effect_label} must raise a local signal or declare no_local_effect")
        _lint_mutation_loaded_signal(effect_label, application_action, signal, effect)
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
            scopes=_action_outcome_effect_scopes(state_machine, application_action, outcome),
        )


def _lint_mutation_loaded_signal(label: str, application_action: dict[str, Any], signal: dict[str, Any], effect: dict[str, Any]) -> None:
    data_refresh_signal = signal.get("data_refresh_signal")
    if application_action.get("action_kind") not in {"command", "transition"} or not data_refresh_signal:
        return
    if data_refresh_signal == "loaded" or data_refresh_signal.endswith("_loaded"):
        has_loaded_payload = bool(signal.get("payload_bindings")) or "result_binding" in effect or "context_updates" in effect
        if not has_loaded_payload:
            warnings.warn(
                f"{label} raises data-refresh signal {data_refresh_signal!r} from a mutation without binding loaded data; prefer changed/invalidated/completed signals and query refresh",
                ContractLintWarning,
                stacklevel=3,
            )


def _validate_no_local_effect(
    label: str,
    outcome: dict[str, Any],
    effect: dict[str, Any],
    *,
    effect_scope: str,
    has_response_surface: bool = False,
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
        raise ContractError(f"{label} no_local_effect must not suppress durable action_outcome.emits")
    if reason == "handled_by_response_surface" and not has_response_surface:
        raise ContractError(f"{label} no_local_effect.reason handled_by_response_surface requires an adapter or renderer response surface for this outcome")
    if reason == "handled_by_query_refresh" and not has_query_refresh:
        raise ContractError(f"{label} no_local_effect.reason handled_by_query_refresh requires an explicit query result binding or context refresh")
    if reason == "result_bound_without_signal" and not (has_result_binding or has_data_effect):
        raise ContractError(f"{label} no_local_effect.reason result_bound_without_signal requires result_binding or context/cache update")
    if authorization_outcome and effect_scope == "action_binding" and reason != "handled_by_response_surface":
        raise ContractError(f"{label} authorization failure no_local_effect requires handled_by_response_surface")
    if outcome.get("kind") == "failure":
        if reason == "handled_by_response_surface":
            if not has_response_surface:
                raise ContractError(f"{label} failure outcome no_local_effect handled_by_response_surface requires a proven response surface")
            return True
        if reason != "intentionally_unobservable":
            raise ContractError(
                f"{label} failure outcome no_local_effect must use reason handled_by_response_surface with a proven response surface or intentionally_unobservable with rationale"
            )
        if not no_local_effect.get("rationale"):
            raise ContractError(f"{label} failure outcome no_local_effect must declare rationale")
    return True


def _action_authorization_outcomes(application_action: dict[str, Any]) -> set[str]:
    authorization = application_action.get("authorization") or {}
    return {value for key, value in authorization.items() if key in {"unauthenticated_as", "forbidden_as"}}


def _application_action_has_response_surface(contract: dict[str, Any], application_action_id: str, outcome_id: str) -> bool:
    for entry_id in contract.get("entry_points", {}):
        if _entry_point_effective_application_action_ref(contract, entry_id) != application_action_id:
            continue
        if outcome_id in _entry_point_named_response_outcomes(contract, entry_id):
            return True
    return False


def _application_action_retry_safe(application_action: dict[str, Any]) -> bool:
    return application_action.get("action_kind") == "query" or bool(application_action.get("retry_safe"))


def _entry_point_retry_safe(contract: dict[str, Any], entry_id: str) -> bool:
    entry = contract["entry_points"][entry_id]
    target_kind, target_ref = entry_target_pair(entry)
    if target_kind == "application_action":
        return _application_action_retry_safe(contract["application_actions"][target_ref]) and (
            contract["application_actions"][target_ref]["action_kind"] == "query" or bool(entry.get("retry_safe"))
        )
    if target_kind == "entry_point":
        return bool(entry.get("retry_safe")) and _entry_point_retry_safe(contract, target_ref)
    if target_kind == "workflow":
        return bool(entry.get("retry_safe"))
    return bool(entry.get("retry_safe"))


def _action_outcome_effect_scopes(
    state_machine: dict[str, Any],
    application_action: dict[str, Any],
    outcome: dict[str, Any],
) -> TypeScopes:
    application_action_input = application_action.get("input") or {}
    invocation_scope = {("input",): {"object": application_action_input}}
    invocation_scope.update(_prefixed_type_scope(("input",), application_action_input))
    return {
        "outcome": {
            ("kind",): {"primitive": "Text"},
            ("result",): outcome["result"],
        },
        "invocation": invocation_scope,
        "context": _type_scope(state_machine.get("context", {})),
    }


def _validate_data_loader_id_scope(state_machine_id: str, state_machine: dict[str, Any]) -> None:
    owner_ids = set(state_machine.get("data_loaders", {}))
    for state_name, state in state_machine.get("view_states", {}).items():
        overlap = sorted(owner_ids & set(state.get("data_loaders", {})))
        if overlap:
            raise ContractError(
                f"state machine {state_machine_id}.{state_name} data_loaders duplicate state-machine-scope ids: {overlap}"
            )


def _validate_data_loaders(
    contract: dict[str, Any],
    owner_label: str,
    state_machine: dict[str, Any],
    invocations: dict[str, Any],
    *,
    scope: str,
    model: str | None = None,
    view_state: dict[str, Any] | None = None,
) -> None:
    context = state_machine.get("context", {})
    for invocation_id, invocation in sorted((invocations or {}).items()):
        label = f"{owner_label} data_loader {invocation_id}"
        if scope == "state_machine" and "result_scope" not in invocation:
            raise ContractError(f"{label} state-machine-level data_loader must declare result_scope")
        if invocation.get("result_scope") in {"shared", "prefetch"} and not invocation.get("rationale"):
            raise ContractError(f"{label} result_scope {invocation['result_scope']} must declare rationale")
        if scope == "state_machine" and _data_loader_has_result_bound_no_local_effect(invocation) and invocation.get("result_scope") not in {"shared", "prefetch"}:
            raise ContractError(f"{label} result_binding with no_local_effect must declare result_scope shared or prefetch")
        application_action_id = invocation["application_action"]
        if application_action_id not in contract["application_actions"]:
            raise ContractError(f"{label} references unknown application action {application_action_id}")
        application_action = contract["application_actions"][application_action_id]
        if application_action["action_kind"] != "query":
            raise ContractError(f"{label} application action must have action_kind: query")
        if application_action.get("creates") or application_action.get("updates") or application_action.get("deletes"):
            raise ContractError(f"{label} query application action must not create, update, or delete models")
        if application_action.get("transition"):
            raise ContractError(f"{label} query application action must not be a lifecycle transition")
        emitting_outcomes = sorted(
            outcome_id
            for outcome_id, outcome in application_action.get("outcomes", {}).items()
            if outcome.get("emits")
        )
        if emitting_outcomes:
            raise ContractError(f"{label} query application action outcomes must not emit durable domain events: {emitting_outcomes}")
        if model and model not in application_action.get("reads", []):
            raise ContractError(f"{label} application action must read model {model}")
        _validate_runtime_binding_map(
            contract,
            f"{label} input_bindings",
            invocation.get("input_bindings") or {},
            application_action.get("input") or {},
            {"context": _type_scope(context), "actor": ACTOR_SOURCE_SCOPE},
        )
        _validate_query_load_policy(contract, label, state_machine, invocation.get("load") or {}, scope=scope)
        _validate_data_loader_outcome_effects(contract, label, state_machine, invocation, application_action, scope=scope, view_state=view_state)


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
    if scope == "view_state" and (load.get("on_start") or load.get("on_mount")):
        raise ContractError(f"{label} view-state-level load policy must use on_enter, not on_start or on_mount")
    for trigger in load.get("refresh_on", []):
        _state_machine_signal_payload(state_machine, "accepts", trigger, f"{label} load.refresh_on")


def _validate_data_loader_outcome_effects(
    contract: dict[str, Any],
    label: str,
    state_machine: dict[str, Any],
    invocation: dict[str, Any],
    application_action: dict[str, Any],
    *,
    scope: str,
    view_state: dict[str, Any] | None,
) -> None:
    effects = invocation["outcome_effects"]
    expected_outcomes = set(application_action["outcomes"])
    actual_outcomes = set(effects)
    if actual_outcomes != expected_outcomes:
        missing = sorted(expected_outcomes - actual_outcomes)
        extra = sorted(actual_outcomes - expected_outcomes)
        parts = []
        if missing:
            parts.append("missing: " + ", ".join(missing))
        if extra:
            parts.append("extra: " + ", ".join(extra))
        raise ContractError(f"{label} outcome_effects must exactly map query application action outcomes" + (": " + "; ".join(parts) if parts else ""))

    for outcome_id, effect in sorted(effects.items()):
        outcome = application_action["outcomes"][outcome_id]
        effect_label = f"{label} outcome_effects.{outcome_id}"
        if "conditional_effects" in effect:
            if any(key in effect for key in ("context_updates", "result_binding", "raise", "no_local_effect")):
                raise ContractError(f"{effect_label} conditional_effects must not be mixed with top-level outcome effects")
            _validate_query_conditional_effects(
                contract,
                effect_label,
                state_machine,
                invocation,
                application_action,
                outcome_id,
                outcome,
                scope=scope,
                view_state=view_state,
            )
            continue
        _validate_query_outcome_effect(
            contract,
            effect_label,
            state_machine,
            invocation,
            application_action,
            outcome_id,
            outcome,
            effect,
            scope=scope,
            view_state=view_state,
        )
    if all(_query_outcome_is_only_no_local_effect(effect) for effect in effects.values()):
        raise ContractError(f"{label} data_loader has only no_local_effect outcome effects and no explicit result binding, context update, or signal")


def _validate_query_conditional_effects(
    contract: dict[str, Any],
    effect_label: str,
    state_machine: dict[str, Any],
    invocation: dict[str, Any],
    application_action: dict[str, Any],
    outcome_id: str,
    outcome: dict[str, Any],
    *,
    scope: str,
    view_state: dict[str, Any] | None,
) -> None:
    conditions: list[str] = []
    for index, branch in enumerate(invocation["outcome_effects"][outcome_id]["conditional_effects"]):
        condition = _query_result_condition_key(branch["when"])
        branch_label = f"{effect_label}.conditional_effects[{index}].{condition}"
        if condition in conditions:
            raise ContractError(f"{effect_label} conditional_effects duplicate condition: {condition}")
        conditions.append(condition)
        if condition in {"result_empty", "result_non_empty"} and not _type_supports_emptiness(outcome["result"]):
            raise ContractError(f"{branch_label} is valid only for array/list query results")
        _validate_query_outcome_effect(
            contract,
            branch_label,
            state_machine,
            invocation,
            application_action,
            outcome_id,
            outcome,
            branch,
            scope=scope,
            view_state=view_state,
        )
    if set(conditions) != {"result_empty", "result_non_empty"}:
        raise ContractError(f"{effect_label} conditional_effects for empty/non-empty result handling must declare both result_empty and result_non_empty branches")


def _validate_query_outcome_effect(
    contract: dict[str, Any],
    effect_label: str,
    state_machine: dict[str, Any],
    invocation: dict[str, Any],
    application_action: dict[str, Any],
    outcome_id: str,
    outcome: dict[str, Any],
    effect: dict[str, Any],
    *,
    scope: str,
    view_state: dict[str, Any] | None,
) -> None:
        scopes = _action_outcome_effect_scopes(state_machine, application_action, outcome)
        has_context_updates = bool(effect.get("context_updates"))
        has_result_binding = "result_binding" in effect
        has_raise = "raise" in effect
        if not any((has_context_updates, has_result_binding, has_raise, "no_local_effect" in effect)):
            raise ContractError(f"{effect_label} must declare context_updates, result_binding, raise, or no_local_effect")
        for field, binding in (effect.get("context_updates") or {}).items():
            context = state_machine.get("context", {})
            if field not in context:
                raise ContractError(f"{effect_label} context_updates references undeclared context field: {field}")
            _validate_expression_type(
                contract,
                f"{effect_label} context_updates.{field}",
                binding,
                context[field],
                scopes,
                allow_nullable_source=False,
            )
        result_binding = effect.get("result_binding")
        if result_binding:
            data_key = result_binding["data_key"]
            if data_key in state_machine.get("context", {}):
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
            view_state=view_state,
        )
        has_query_refresh = has_result_binding or has_context_updates
        _validate_no_local_effect(
            effect_label,
            outcome,
            effect,
            effect_scope="data_loader",
            has_response_surface=_application_action_has_response_surface(contract, invocation["application_action"], outcome_id),
            has_query_refresh=has_query_refresh,
            has_result_binding=has_result_binding,
            has_data_effect=has_context_updates,
            authorization_outcome=outcome_id in _action_authorization_outcomes(application_action),
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


def _query_result_condition_key(condition: dict[str, Any]) -> str:
    return next(iter(condition))


def _query_outcome_is_only_no_local_effect(effect: dict[str, Any]) -> bool:
    branches = effect.get("conditional_effects") or [effect]
    return all("no_local_effect" in branch and not any(key in branch for key in ("context_updates", "result_binding", "raise")) for branch in branches)


def _type_supports_emptiness(type_expr: Any) -> bool:
    return "array" in unwrap_nullable(_effective_type(type_expr))


def _result_type_has_field(contract: dict[str, Any], result_type: Any, field: str) -> bool:
    effective = unwrap_nullable(_effective_type(result_type))
    if "array" in effective:
        effective = unwrap_nullable(_effective_type(effective["array"]))
    return field in object_fields_for_type(contract, effective)


def _query_result_binding_consumed(
    contract: dict[str, Any],
    state_machine: dict[str, Any],
    invocation: dict[str, Any],
    outcome: dict[str, Any],
    result_binding: dict[str, Any],
    *,
    scope: str,
    view_state: dict[str, Any] | None,
) -> bool:
    if invocation.get("result_scope") in {"shared", "prefetch"} and invocation.get("rationale"):
        return True
    if scope == "view_state" and view_state:
        return any(_result_type_has_field(contract, outcome["result"], field) for field in view_state.get("fields", []))
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
        view_sources_by_field = _query_result_field_sources(contract, state.get("data_loaders", {}))
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
    application_actions = contract.get("application_actions", {})
    for invocation_id, invocation in sorted((invocations or {}).items()):
        application_action = application_actions.get(invocation.get("application_action"))
        if not application_action:
            continue
        for outcome_id, effect in sorted((invocation.get("outcome_effects") or {}).items()):
            outcome = application_action.get("outcomes", {}).get(outcome_id)
            if not outcome:
                continue
            fields = object_fields_for_type(contract, _query_result_item_type(outcome["result"]))
            for branch in _query_outcome_effect_branches(effect):
                result_binding = branch.get("result_binding")
                if not result_binding:
                    continue
                source_label = f"data_loader {invocation_id} result_binding {result_binding['data_key']}"
                for field in fields:
                    sources.setdefault(field, set()).add(source_label)
    return sources


def _query_outcome_effect_branches(effect: dict[str, Any]) -> list[dict[str, Any]]:
    return list(effect.get("conditional_effects") or [effect])


def _query_result_item_type(result_type: Any) -> Any:
    effective = unwrap_nullable(_effective_type(result_type))
    if "array" in effective:
        return unwrap_nullable(_effective_type(effective["array"]))
    return effective


def _validate_collection_empty_signal_effects(state_machine_id: str, state_machine: dict[str, Any]) -> None:
    for transition in state_machine.get("transitions", []):
        if not _is_data_refresh_signal(transition["on"]):
            continue
        signal_name = transition["on"]["data_refresh_signal"]
        if not _is_empty_collection_signal(signal_name):
            continue
        if not _query_effects_raise_data_refresh_signal(state_machine, signal_name):
            raise ContractError(
                f"state machine {state_machine_id} transition uses empty-collection signal data_refresh_signal.{signal_name} "
                "without an explicit query outcome effect raising it"
            )


def _is_empty_collection_signal(signal_name: str) -> bool:
    return signal_name.endswith("_empty") or "collection_empty" in signal_name


def _query_effects_raise_data_refresh_signal(state_machine: dict[str, Any], signal_name: str) -> bool:
    for invocation in (state_machine.get("data_loaders") or {}).values():
        if _data_loader_raises_data_refresh_signal(invocation, signal_name):
            return True
    for state in state_machine.get("view_states", {}).values():
        for invocation in (state.get("data_loaders") or {}).values():
            if _data_loader_raises_data_refresh_signal(invocation, signal_name):
                return True
    return False


def _data_loader_raises_data_refresh_signal(invocation: dict[str, Any], signal_name: str) -> bool:
    for effect in (invocation.get("outcome_effects") or {}).values():
        for branch in _query_outcome_effect_branches(effect):
            signal = branch.get("raise") or {}
            if signal.get("data_refresh_signal") == signal_name:
                return True
    return False


def _validate_machine_query_ownership(contract: dict[str, Any], state_machine_id: str, state_machine: dict[str, Any]) -> None:
    owner_queries = state_machine.get("data_loaders") or {}
    if not owner_queries:
        return
    child_query_application_actions = _child_query_application_actions(contract, state_machine)
    for invocation_id, invocation in sorted(owner_queries.items()):
        label = f"state machine {state_machine_id} data_loader {invocation_id}"
        result_scope = invocation.get("result_scope")
        if _data_loader_has_result_bound_no_local_effect(invocation) and result_scope not in {"shared", "prefetch"}:
            raise ContractError(f"{label} result_binding with no_local_effect must declare result_scope shared or prefetch")
        if invocation["application_action"] in child_query_application_actions and result_scope not in {"shared", "prefetch"}:
            raise ContractError(f"{label} duplicates child-owned query loading and must declare result_scope shared or prefetch")


def _child_query_application_actions(contract: dict[str, Any], state_machine: dict[str, Any]) -> set[str]:
    application_actions: set[str] = set()
    for state in state_machine.get("view_states", {}).values():
        for mount in state.get("child_state_machines", []):
            child = contract["state_machines"].get(mount["state_machine"])
            if not child:
                continue
            for invocation in (child.get("data_loaders") or {}).values():
                application_actions.add(invocation["application_action"])
            for child_state in child.get("view_states", {}).values():
                for invocation in (child_state.get("data_loaders") or {}).values():
                    application_actions.add(invocation["application_action"])
    return application_actions


def _data_loader_has_result_bound_no_local_effect(invocation: dict[str, Any]) -> bool:
    for effect in (invocation.get("outcome_effects") or {}).values():
        for branch in _query_outcome_effect_branches(effect):
            no_local_effect = branch.get("no_local_effect") or {}
            if branch.get("result_binding") and no_local_effect.get("reason") == "result_bound_without_signal":
                return True
    return False


def _validate_state_machine_transitions(contract: dict[str, Any], state_machine_id: str, state_machine: dict[str, Any]) -> None:
    states = set(state_machine["view_states"])
    for transition in state_machine.get("transitions", []):
        if transition["from"] not in states or transition["to"] not in states:
            raise ContractError(f"state machine {state_machine_id} transition uses unknown state: {transition}")
        if _is_data_refresh_signal(transition["on"]) and not _transition_data_bindings(state_machine, transition):
            raise ContractError(
                f"state machine {state_machine_id} transition uses data-refresh signal without state machine or source-state data: {_signal_label(transition['on'])}"
            )
        local_signal_payload = _state_machine_signal_payload(state_machine, "accepts", transition["on"], f"state machine {state_machine_id} transition signal")
        for effect in transition.get("effects", []):
            kind, body = _one(effect, f"state machine {state_machine_id} transition effect")
            if kind == "set":
                if body["context"] not in state_machine.get("context", {}):
                    raise ContractError(f"state machine {state_machine_id} transition sets undeclared context: {body['context']}")
                binding = body["from"] if "from" in body else {"value": body.get("value")}
                _validate_expression_type(
                    contract,
                    f"state machine {state_machine_id} transition set {body['context']}",
                    binding,
                    state_machine["context"][body["context"]],
                    {"local_signal": _type_scope(local_signal_payload), "context": _type_scope(state_machine.get("context", {}))},
                    allow_nullable_source=False,
                )
            elif kind == "emit":
                emitted_payload = _state_machine_signal_payload(state_machine, "emits", {"local_signal": body["local_signal"]}, f"state machine {state_machine_id} transition emit")
                _validate_payload_bindings(
                    contract=contract,
                    label=f"state machine {state_machine_id} transition emit {body['local_signal']} payload_bindings",
                    bindings=body["payload_bindings"],
                    payload=emitted_payload,
                    scopes={"local_signal": _type_scope(local_signal_payload), "context": _type_scope(state_machine.get("context", {}))},
                )
            else:  # pragma: no cover - schema prevents this.
                raise ContractError(f"state machine {state_machine_id} unsupported transition effect: {kind}")
    for transition in state_machine.get("transitions", []):
        if not _transition_has_audit_content(state_machine, transition):
            raise ContractError(
                f"state machine {state_machine_id} transition {_signal_label(transition['on'])} from {transition['from']} "
                f"to {transition['to']} must declare rationale, data, or effects"
            )


def _validate_signals(state_machine_id: str, state_machine: dict[str, Any]) -> None:
    signals = state_machine.get("signals", _empty_signals())
    _lint_signal_names(state_machine_id, state_machine, signals)
    declared_accepts = _declared_signal_keys(signals, "accepts")
    declared_emits = _declared_signal_keys(signals, "emits")
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
        raise ContractError(f"state machine {state_machine_id} declares emitted state-machine signal without emit effect: {[_signal_label(item) for item in orphan_emits]}")
    undeclared_accepts = sorted(accepted - declared_accepts)
    if undeclared_accepts:
        raise ContractError(f"state machine {state_machine_id} accepts state-machine signal without declaring it: {[_signal_label(item) for item in undeclared_accepts]}")
    undeclared_emits = sorted(emitted - declared_emits)
    if undeclared_emits:
        raise ContractError(f"state machine {state_machine_id} emits state-machine signal without declaring it: {[_signal_label(item) for item in undeclared_emits]}")


def _lint_signal_names(state_machine_id: str, state_machine: dict[str, Any], signals: dict[str, Any]) -> None:
    view_states = set(state_machine.get("view_states", {}))
    local_signals = set(signals.get("accepts", {}).get("local_signals", {})) | set(signals.get("emits", {}).get("local_signals", {}))
    data_refresh_signal_specs = signals.get("accepts", {}).get("data_refresh_signals", {}) or {}
    data_refresh_signals = set(data_refresh_signal_specs)
    for name in sorted((local_signals | data_refresh_signals) & view_states):
        warnings.warn(
            f"state machine {state_machine_id} signal {name!r} also names a view state; prefer event-like names such as project_loaded, project_load_failed, collection_empty, or application_action_failed",
            ContractLintWarning,
            stacklevel=3,
        )
    for name, signal in sorted(data_refresh_signal_specs.items()):
        if name in {"ready", "error", "empty", "loaded"} and not signal.get("rationale"):
            warnings.warn(
                f"state machine {state_machine_id} data-refresh signal {name!r} is state-like; prefer event-like names such as project_loaded, project_load_failed, collection_empty, or application_action_failed",
                ContractLintWarning,
                stacklevel=3,
            )
    for transition in state_machine.get("transitions", []):
        _, trigger_name = _signal_selector_key(transition["on"])
        if trigger_name == transition["to"]:
            warnings.warn(
                f"state machine {state_machine_id} transition trigger {trigger_name!r} matches target view state; prefer an event-like trigger name",
                ContractLintWarning,
                stacklevel=3,
            )


def _declared_signal_keys(signals: dict[str, Any], direction: str) -> set[tuple[str, str]]:
    body = signals.get(direction) or {}
    keys = {("local_signal", name) for name in (body.get("local_signals") or {})}
    if direction == "accepts":
        keys.update(("data_refresh_signal", name) for name in (body.get("data_refresh_signals") or {}))
    return keys


def _validate_state_machine_signal_payload_consistency(contract: dict[str, Any]) -> None:
    declared: dict[str, tuple[str, str, dict[str, Any]]] = {}
    domain_events = set(contract.get("domain_events", {}))
    for state_machine_id, state_machine in contract.get("state_machines", {}).items():
        signals = state_machine.get("signals", _empty_signals())
        for direction, groups in (("accepts", ("local_signals", "data_refresh_signals")), ("emits", ("local_signals",))):
            for group in groups:
                for signal_id, signal in (signals.get(direction, {}).get(group) or {}).items():
                    kind = "local_signal" if group == "local_signals" else "data_refresh_signal"
                    signal_key = f"{kind}.{signal_id}"
                    if signal_key in domain_events:
                        raise ContractError(f"state-machine signal {signal_key} conflicts with domain event {signal_key}")
                    payload = signal["payload_schema"]
                    existing = declared.get(signal_key)
                    if existing and (
                        set(existing[2]) != set(payload)
                        or any(not type_equals(existing[2][key], payload[key]) for key in payload)
                    ):
                        first_fsm, first_direction, first_payload = existing
                        raise ContractError(
                            f"state-machine signal {signal_key} payload_schema differs between {first_fsm}.{first_direction} "
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
        if mount["initial_view_state"] not in child_state_machine["view_states"]:
            raise ContractError(f"composed state machine view state {label}.{mount['id']} initial view state is unknown: {mount['initial_view_state']}")
        selected = mount.get("selected")
        if selected and selected["view_state"] not in child_state_machine["view_states"]:
            raise ContractError(f"composed state machine view state {label}.{mount['id']} selected view state is unknown: {selected['view_state']}")
        if selected:
            _validate_condition_context(contract, label, parent_state_machine.get("context", {}), selected["when"])
        mount_context = mount.get("context_bindings", {})
        child_context = child_state_machine.get("context", {})
        expected_context = {name for name, field in child_context.items() if field.get("required", True)}
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
            parent_state_machine.get("context", {}),
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
        if "context_present" in condition:
            keys = [condition["context_present"]]
        elif "context_equals" in condition:
            keys = [condition["context_equals"]["field"]]
            comparisons.append((condition["context_equals"]["field"], condition["context_equals"]["value"]))
        else:
            keys = []
    elif is_reference_expression(condition):
        try:
            ref = parse_reference_expression(condition)
        except ReferenceExpressionError as exc:
            raise ContractError(f"composed state machine {state_machine_id} condition has malformed runtime reference: {condition}") from exc
        if ref.root != "state_machine":
            raise ContractError(f"composed state machine {state_machine_id} condition references unavailable runtime root: ${ref.root}")
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
                f"composed state machine {state_machine_id} context {key} cannot bind nullable source "
                f"to non-nullable child context"
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
        for effect in transition.get("effects", []):
            kind, body = _one(effect, "state_machine transition effect")
            if kind == "emit":
                emits.add(("local_signal", body["local_signal"]))
    return emits


def _state_machine_accepts(state_machine: dict[str, Any]) -> set[tuple[str, str]]:
    accepts = {_signal_selector_key(transition["on"]) for transition in state_machine.get("transitions", [])}
    for invocation in (state_machine.get("data_loaders") or {}).values():
        for trigger in (invocation.get("load") or {}).get("refresh_on", []):
            accepts.add(_signal_selector_key(trigger))
    for state in state_machine.get("view_states", {}).values():
        for invocation in (state.get("data_loaders") or {}).values():
            for trigger in (invocation.get("load") or {}).get("refresh_on", []):
                accepts.add(_signal_selector_key(trigger))
    return accepts


def _state_machine_signal_payload(state_machine: dict[str, Any], direction: str, selector: dict[str, str], label: str) -> dict[str, Any]:
    kind, signal_id = _signal_selector_key(selector)
    group = "local_signals" if kind == "local_signal" else "data_refresh_signals"
    signal = state_machine.get("signals", {}).get(direction, {}).get(group, {}).get(signal_id)
    if not signal:
        raise ContractError(f"{label} references undeclared state-machine signal: {_signal_label((kind, signal_id))}")
    return signal.get("payload_schema", {})


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
    allow_nullable_source: bool = True,
) -> None:
    if _is_null_expression(expression):
        if not _type_allows_null(expected_type):
            raise ContractError(f"{label} cannot assign null to non-nullable {type_display(_effective_type(expected_type))}")
        return
    literal = _literal_expression_value(expression)
    if literal is not _NO_LITERAL and not _literal_value_compatible(literal, expected_type):
        raise ContractError(f"{label} literal value is not compatible with {type_display(_effective_type(expected_type))}")
    actual_type = _expression_type(contract, expression, scopes, label)
    if actual_type and not allow_nullable_source and _type_allows_null(actual_type) and not _type_allows_null(expected_type):
        raise ContractError(f"{label} cannot assign nullable source to non-nullable {type_display(_effective_type(expected_type))}")
    if actual_type and not _type_assignable(actual_type, expected_type):
        raise ContractError(f"{label} type mismatch: expected {type_display(_effective_type(expected_type))}, got {type_display(_effective_type(actual_type))}")


def _effective_type(type_name: Any) -> Any:
    if isinstance(type_name, dict) and len(type_name) == 1 and next(iter(type_name)) in {"primitive", "model", "data_contract", "array", "map", "nullable", "enum", "object"}:
        return normalize_type_expr(type_name)
    if isinstance(type_name, dict) and "type" in type_name and isinstance(type_name["type"], dict) and "nullable" in type_name["type"]:
        return normalize_type_expr(type_name["type"])
    return effective_field_type(type_name)


def _type_allows_null(type_name: Any) -> bool:
    if isinstance(type_name, dict) and "type" in type_name and "nullable" in type_name:
        return bool(type_name["nullable"])
    return "nullable" in normalize_type_expr(type_name)


def _type_assignable(actual_type: Any, expected_type: Any) -> bool:
    actual = _effective_type(actual_type)
    expected = _effective_type(expected_type)
    if type_equals(actual, expected):
        return True
    if _type_allows_null(expected) or _type_allows_null(actual):
        return type_equals(unwrap_nullable(actual), unwrap_nullable(expected))
    return type_equals(actual, expected)


def _is_null_expression(expression: Any) -> bool:
    return expression is None or (isinstance(expression, dict) and set(expression) == {"value"} and expression["value"] is None)


_NO_LITERAL = object()


def _literal_expression_value(expression: Any) -> Any:
    if isinstance(expression, dict) and set(expression) == {"from"}:
        return _NO_LITERAL
    if isinstance(expression, dict) and set(expression) == {"value"}:
        return expression["value"]
    if is_reference_expression(expression):
        return _NO_LITERAL
    return expression


def _literal_value_compatible(value: Any, expected_type: Any) -> bool:
    if value is None:
        return _type_allows_null(expected_type)
    expected = unwrap_nullable(_effective_type(expected_type))
    kind, body = next(iter(expected.items()))
    if kind == "primitive":
        if body in {"ID", "Text", "Markdown", "Date", "Timestamp"}:
            return isinstance(value, str)
        if body == "Boolean":
            return isinstance(value, bool)
        if body == "Integer":
            return isinstance(value, int) and not isinstance(value, bool)
        if body == "Decimal":
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        if body == "JSON":
            return isinstance(value, (dict, list))
    if kind == "enum":
        return isinstance(value, str) and value in body
    if kind == "array":
        return isinstance(value, list)
    if kind in {"map", "object", "model", "data_contract"}:
        return isinstance(value, dict)
    return False


def _expression_type(contract: dict[str, Any] | None, expression: Any, scopes: TypeScopes, label: str) -> Any | None:
    if isinstance(expression, dict) and set(expression) == {"from"}:
        return _reference_expression_type(contract, label, expression["from"], scopes)
    if isinstance(expression, dict) and set(expression) == {"value"}:
        return _literal_type(expression["value"])
    if is_reference_expression(expression):
        return _reference_expression_type(contract, label, expression, scopes)
    return _literal_type(expression)


def _reference_expression_type(
    contract: dict[str, Any] | None,
    label: str,
    expression: str,
    scopes: TypeScopes,
) -> Any:
    try:
        ref = parse_reference_expression(expression)
    except ReferenceExpressionError as exc:
        raise ContractError(f"{label} references unsupported expression: {expression}") from exc
    if ref.root not in scopes:
        raise ContractError(f"{label} references unavailable runtime root: ${ref.root}")
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
    except TypeExpressionError as exc:
        raise ContractError(f"{label} references {exc}") from exc


def _literal_type(value: Any) -> Any | None:
    # String/null literals can represent several contract scalar types, so schema
    # validation accepts them and semantic validation only type-checks references.
    return literal_type_expr(value)


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
    source_state = state_machine.get("view_states", {}).get(transition["from"], {})
    return source_state.get("data_loaders", {}) or state_machine.get("data_loaders", {})


def _transition_target_data_bindings(state_machine: dict[str, Any], transition: dict[str, Any]) -> dict[str, Any]:
    target_state = state_machine.get("view_states", {}).get(transition["to"], {})
    return target_state.get("data_loaders", {})


def _transition_has_audit_content(state_machine: dict[str, Any], transition: dict[str, Any]) -> bool:
    if transition.get("rationale") or transition.get("effects"):
        return True
    if _is_data_refresh_signal(transition["on"]):
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
    context = state_machine.get("context", {})
    for rule in state.get("signal_sync_rules", []):
        if rule["id"] in seen:
            raise ContractError(f"composed state machine state {label} has duplicate sync rule: {rule['id']}")
        seen.add(rule["id"])
        source_id = rule["when"]["instance"]
        if source_id not in mounts:
            raise ContractError(f"composed state machine state {label} sync source instance is unknown: {source_id}")
        source_fsm = contract["state_machines"][mounts[source_id]["state_machine"]]
        signal_id = rule["when"]["local_signal"]
        if ("local_signal", signal_id) not in _state_machine_emits(source_fsm):
            raise ContractError(f"composed state machine state {label} sync listens for signal the source does not emit: {signal_id}")
        source_payload = _state_machine_signal_payload(source_fsm, "emits", {"local_signal": signal_id}, f"composed state machine state {label} sync trigger")
        for effect in rule["effects"]:
            kind, body = _one(effect, f"composed state machine state {label} sync effect")
            if kind == "set":
                if body["context"] not in context:
                    raise ContractError(f"composed state machine state {label} sync sets undeclared context: {body['context']}")
                binding = body["from"] if "from" in body else {"value": body.get("value")}
                _validate_expression_type(
                    contract,
                    f"composed state machine state {label} sync set {body['context']}",
                    binding,
                    context[body["context"]],
                    {"local_signal": _type_scope(source_payload), "state_machine": _type_scope(context)},
                    allow_nullable_source=False,
                )
            elif kind == "send":
                target_id = body["instance"]
                if target_id not in mounts:
                    raise ContractError(f"composed state machine state {label} sync sends to unknown instance: {target_id}")
                target_fsm = contract["state_machines"][mounts[target_id]["state_machine"]]
                if ("local_signal", body["local_signal"]) not in _state_machine_accepts(target_fsm):
                    raise ContractError(f"composed state machine state {label} sync sends local_signal the target does not accept: {body['local_signal']}")
                target_payload = _state_machine_signal_payload(target_fsm, "accepts", {"local_signal": body["local_signal"]}, f"composed state machine state {label} sync send")
                _validate_payload_bindings(
                    contract=contract,
                    label=f"composed state machine state {label} sync send {body['local_signal']} to {target_id} payload_bindings",
                    bindings=body["payload_bindings"],
                    payload=target_payload,
                    scopes={"local_signal": _type_scope(source_payload), "state_machine": _type_scope(context)},
                )
            else:  # pragma: no cover - schema prevents this.
                raise ContractError(f"composed state machine state {label} unsupported sync effect: {kind}")


def _validate_presentation(contract: dict[str, Any], owner_label: str, field_names: set[str], state_name: str, state: dict[str, Any]) -> None:
    renderers = state.get("renderers") or {}
    if not renderers:
        return
    text_slots = {ref.rsplit(".", 1)[-1] for ref in state["text"]}
    asset_slots = {ref.rsplit(".", 1)[-1] for ref in state["assets"]}
    field_slots = set(state.get("fields", []))
    action_bindings = set(state["action_bindings"])
    html_regions = set(renderer_html_regions(state))
    textual_containers = set(renderer_textual_containers(state))
    mounts = {mount["id"] for mount in state.get("child_state_machines", [])}

    html_contract = renderer_html_presentation(state)
    for slot in html_contract.get("slots", []):
        if slot["region"] not in html_regions:
            raise ContractError(f"{owner_label}.{state_name} HTML slot references undeclared layout region: {slot['region']}")
        bind_kind, bind_value = _one(slot["binding"], f"{owner_label}.{state_name} html slot binding")
        _validate_slot_binding(owner_label, state_name, "HTML slot", bind_kind, bind_value, text_slots, asset_slots, field_slots, action_bindings)

    for rule in renderer_html_style(state).get("rules", []):
        _validate_renderer_style_selector(
            owner_label,
            state_name,
            rule["selector"],
            text_slots,
            asset_slots,
            field_slots,
            action_bindings,
            html_regions,
            mounts,
            "html style",
        )

    textual = renderer_textual_presentation(state)
    widgets = textual.get("widgets", [])
    widget_ids = [widget["id"] for widget in widgets]
    if len(widget_ids) != len(set(widget_ids)):
        raise ContractError(f"{owner_label}.{state_name} Textual widgets contain duplicate ids")
    widget_targets = {"text_slot": set(), "asset_slot": set(), "field_slot": set(), "action_binding": set()}
    for widget in widgets:
        if widget["container"] not in textual_containers:
            raise ContractError(f"{owner_label}.{state_name} Textual widget references undeclared layout container: {widget['container']}")
        bind_kind, bind_value = _one(widget["binding"], f"{owner_label}.{state_name} textual widget binding")
        _validate_slot_binding(owner_label, state_name, "Textual widget", bind_kind, bind_value, text_slots, asset_slots, field_slots, action_bindings)
        if bind_kind in widget_targets:
            widget_targets[bind_kind].add(bind_value)
    for rule in renderer_textual_style(state).get("rules", []):
        selector = rule["selector"]
        _validate_renderer_style_selector(
            owner_label,
            state_name,
            selector,
            text_slots,
            asset_slots,
            field_slots,
            action_bindings,
            textual_containers,
            mounts,
            "textual style",
        )
        if widgets and selector.startswith("slot."):
            name = selector[len("slot."):]
            if name not in widget_targets["text_slot"] and name not in widget_targets["asset_slot"] and name not in widget_targets["field_slot"]:
                raise ContractError(f"{owner_label}.{state_name} textual style selector has no matching Textual widget: {selector}")
        if widgets and selector.startswith("action_binding."):
            action_binding = selector[len("action_binding."):]
            if action_binding not in widget_targets["action_binding"]:
                raise ContractError(f"{owner_label}.{state_name} textual style selector has no matching Textual widget: {selector}")


def _validate_slot_binding(
    owner_label: str,
    state_name: str,
    label: str,
    bind_kind: str,
    bind_value: str,
    text_slots: set[str],
    asset_slots: set[str],
    field_slots: set[str],
    action_bindings: set[str],
) -> None:
    if bind_kind == "text_slot" and bind_value not in text_slots:
        raise ContractError(f"{owner_label}.{state_name} {label} text_slot binding is not declared: {bind_value}")
    if bind_kind == "asset_slot" and bind_value not in asset_slots:
        raise ContractError(f"{owner_label}.{state_name} {label} asset_slot binding is not declared: {bind_value}")
    if bind_kind == "action_binding" and bind_value not in action_bindings:
        raise ContractError(f"{owner_label}.{state_name} {label} action_binding binding is not declared: {bind_value}")
    if bind_kind == "field_slot" and bind_value not in field_slots:
        raise ContractError(f"{owner_label}.{state_name} {label} field_slot binding is not declared: {bind_value}")


def _validate_renderer_style_selector(
    owner_label: str,
    state_name: str,
    selector: str,
    text_slots: set[str],
    asset_slots: set[str],
    field_slots: set[str],
    action_bindings: set[str],
    regions: set[str],
    mounts: set[str],
    label: str,
) -> None:
    if selector.startswith("region.") or selector.startswith("container.") or selector.startswith("child_state_machine."):
        _validate_composition_selector(f"{owner_label}.{state_name}", selector, regions, mounts, label)
        return
    _validate_style_selector(owner_label, state_name, selector, text_slots, asset_slots, field_slots, action_bindings, label)


def _validate_style_selector(
    owner_label: str,
    state_name: str,
    selector: str,
    text_slots: set[str],
    asset_slots: set[str],
    field_slots: set[str],
    action_bindings: set[str],
    label: str,
) -> None:
    if selector == "root" and label.startswith("html"):
        return
    if selector == "screen" and label.startswith("textual"):
        return
    if selector.startswith("slot."):
        name = selector[len("slot."):]
        if name not in text_slots and name not in asset_slots and name not in field_slots:
            raise ContractError(f"{owner_label}.{state_name} {label} selector references undeclared slot: {selector}")
        return
    if selector.startswith("action_binding."):
        ref = selector[len("action_binding."):]
        if ref not in action_bindings:
            raise ContractError(f"{owner_label}.{state_name} {label} selector references undeclared action_binding: {ref}")
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


def _validate_entries(contract: dict[str, Any]) -> None:
    _validate_entry_point_delegation_graph(contract)
    for eid, entry in contract["entry_points"].items():
        adapter_kind, adapter = entry_point_adapter_pair(entry)
        target_kind, target = entry_point_target_pair(entry)
        kind = "state_machine" if target_kind == "state_machine" else target_kind
        value = target["ref"]
        _validate_entry_point_fields(eid, entry, adapter_kind)
        _validate_entry_input_shape(eid, entry, adapter_kind)
        if kind == "entry_point":
            _validate_delegating_entry_adapter_surface(eid, entry, adapter_kind, adapter)
            _validate_entry_point_delegate_target(contract, eid, entry, value)
            if adapter_kind == "cli":
                _validate_cli_delegated_response_handlers(contract, eid, entry, value)
            continue
        if adapter_kind == "html_route":
            if kind != "state_machine" or value not in contract["state_machines"]:
                raise ContractError(f"UI entry point {eid} must target a known state machine")
            renderer = adapter.get("renderer")
            if renderer and "renderer" not in target:
                target["renderer"] = renderer
            _validate_state_machine_target_renderer(contract, eid, entry, value, allowed_renderers={"html"})
            _require_adapter(adapter, eid, "path")
            _validate_path_params(entry, eid)
            declared = {**_entry_input_map(entry, "path_params"), **_entry_input_map(entry, "query_params")}
            _validate_state_machine_entry_inputs(contract, eid, value, declared=declared, input_label="input")
            _validate_target_bindings(contract, eid, entry, declared)
        elif adapter_kind == "http_api":
            if kind != "application_action" or value not in contract["application_actions"]:
                raise ContractError(f"HTTP API entry point {eid} must target a known application action")
            _require_adapter(adapter, eid, "method")
            _require_adapter(adapter, eid, "path")
            _validate_path_params(entry, eid)
            operation = contract["application_actions"][value]
            path_params = _entry_input_map(entry, "path_params")
            query_params = _entry_input_map(entry, "query_params")
            body = _entry_input_map(entry, "body")
            _validate_api_entry_input(eid, entry, operation, path_params, query_params, body)
            _validate_target_bindings(contract, eid, entry, {**path_params, **query_params, **body})
            _validate_api_entry_point_responses(eid, entry, operation)
        elif adapter_kind == "cli":
            _require_adapter(adapter, eid, "cli_command")
            args = _entry_input_map(entry, "args")
            if kind == "application_action":
                if value not in contract["application_actions"]:
                    raise ContractError(f"CLI entry point {eid} must target a known application action")
                operation = contract["application_actions"][value]
                _validate_exact_entry_inputs(eid, "input.args", args, operation["input"])
                _validate_target_bindings(contract, eid, entry, args)
                _validate_cli_application_action_response_handlers(contract, eid, entry, operation)
            elif kind == "state_machine":
                if value not in contract["state_machines"]:
                    raise ContractError(f"CLI entry point {eid} must target a known state machine")
                _validate_state_machine_target_renderer(contract, eid, entry, value, allowed_renderers=set(STATE_MACHINE_RENDERERS))
                _validate_state_machine_entry_inputs(contract, eid, value, declared=args, input_label="input.args")
                _validate_target_bindings(contract, eid, entry, args)
                target_renderer = entry_state_machine_renderer(entry)
                assert target_renderer is not None
                if entry_point_response_handlers(entry):
                    raise ContractError(f"CLI entry point {eid} targeting a state machine must not declare response_handlers")
            elif kind == "workflow":
                if value not in contract["workflows"]:
                    raise ContractError(f"CLI entry point {eid} must target a known workflow")
                _validate_workflow_entry_target_source(contract, eid, entry, value)
                if args:
                    raise ContractError(f"CLI entry point {eid} targeting a workflow must not declare input.args")
                _validate_async_entry_point_responses(eid, entry, require_failure_disposition=False)
            else:
                raise ContractError(f"CLI entry point {eid} cannot target raw {kind}")
        elif adapter_kind in {"worker", "scheduled"}:
            if kind != "workflow" or value not in contract["workflows"]:
                raise ContractError(f"{adapter_kind} entry point {eid} must target a known workflow")
            if adapter_kind == "scheduled":
                _require_adapter(adapter, eid, "schedule_expression")
                if entry_point_input(entry):
                    raise ContractError(f"Scheduled entry point {eid} must not declare input")
            else:
                _validate_event_payload_entry_input(contract, eid, entry, value)
            _validate_workflow_entry_target_source(contract, eid, entry, value)
            _validate_async_entry_point_responses(eid, entry, require_failure_disposition=adapter_kind == "worker")
        elif adapter_kind == "webhook":
            if kind != "workflow" or value not in contract["workflows"]:
                raise ContractError(f"Webhook entry point {eid} must target a known workflow")
            _require_adapter(adapter, eid, "path")
            _validate_path_params(entry, eid)
            _validate_event_payload_entry_input(contract, eid, entry, value)
            _validate_workflow_entry_target_source(contract, eid, entry, value)
            _validate_webhook_entry_point_responses(eid, entry)


def _validate_entry_point_delegation_graph(contract: dict[str, Any]) -> None:
    graph: dict[str, str] = {}
    for entry_id, entry in contract.get("entry_points", {}).items():
        target_kind, target_ref = entry_target_pair(entry)
        if target_kind != "entry_point":
            continue
        if target_ref not in contract["entry_points"]:
            raise ContractError(f"Entry point {entry_id} delegates to unknown entry point {target_ref}")
        if target_ref == entry_id:
            raise ContractError(f"Entry point {entry_id} must not delegate to itself")
        graph[entry_id] = target_ref

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(entry_id: str, path: list[str]) -> None:
        if entry_id in visited or entry_id not in graph:
            return
        if entry_id in visiting:
            cycle_start = path.index(entry_id)
            cycle = path[cycle_start:] + [entry_id]
            raise ContractError("Entry point delegation cycle is invalid: " + " -> ".join(cycle))
        visiting.add(entry_id)
        visit(graph[entry_id], [*path, entry_id])
        visiting.remove(entry_id)
        visited.add(entry_id)

    for entry_id in graph:
        visit(entry_id, [])


def _validate_entry_point_response_maps(contract: dict[str, Any]) -> None:
    """Validate synchronous target response keys before local outcome effects depend on them."""
    for entry_id, entry in contract.get("entry_points", {}).items():
        adapter_kind, _adapter = entry_point_adapter_pair(entry)
        target_kind, target = entry_point_target_pair(entry)
        target_ref = target["ref"]
        if adapter_kind == "http_api" and target_kind == "application_action" and target_ref in contract["application_actions"]:
            _application_action_entry_point_responses(entry_id, entry, contract["application_actions"][target_ref])
        elif adapter_kind == "cli" and target_kind == "application_action" and target_ref in contract["application_actions"]:
            _application_action_entry_point_response_handlers(entry_id, entry, contract["application_actions"][target_ref])


def _validate_delegating_entry_adapter_surface(
    entry_id: str,
    entry: dict[str, Any],
    adapter_kind: str,
    adapter: dict[str, Any],
) -> None:
    if adapter_kind == "html_route":
        _require_adapter(adapter, entry_id, "path")
        _validate_path_params(entry, entry_id)
    elif adapter_kind == "http_api":
        _require_adapter(adapter, entry_id, "method")
        _require_adapter(adapter, entry_id, "path")
        _validate_path_params(entry, entry_id)
    elif adapter_kind == "cli":
        _require_adapter(adapter, entry_id, "cli_command")
    elif adapter_kind == "scheduled":
        _require_adapter(adapter, entry_id, "schedule_expression")
        if entry_point_input(entry):
            raise ContractError(f"Scheduled entry point {entry_id} must not declare input")
    elif adapter_kind == "webhook":
        _require_adapter(adapter, entry_id, "path")
        _validate_path_params(entry, entry_id)


def _validate_entry_point_delegate_target(
    contract: dict[str, Any],
    entry_id: str,
    entry: dict[str, Any],
    delegated_entry_id: str,
) -> None:
    delegated_entry = contract["entry_points"][delegated_entry_id]
    bindings = entry_point_input_bindings(entry)
    expected_input = entry_point_input(delegated_entry)
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
            f"Entry {entry_id} target.entry_point.input_bindings must exactly bind delegated entry input"
            + (": " + "; ".join(parts) if parts else "")
        )
    source_scopes: TypeScopes = {"input": _entry_input_source_types(contract, entry)}
    for section, expected in expected_input.items():
        section_bindings = bindings.get(section)
        label = f"Entry {entry_id} target.entry_point.input_bindings.{section}"
        if section == "payload":
            _validate_delegated_payload_binding(contract, label, section_bindings, expected, source_scopes)
            continue
        if not isinstance(expected, dict):
            raise ContractError(f"Entry {entry_id} delegated input section {section} must be an object-shaped adapter input")
        if not isinstance(section_bindings, dict):
            raise ContractError(f"{label} must declare field bindings")
        _validate_runtime_binding_map(contract, label, section_bindings, expected, source_scopes)


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
    _validate_runtime_binding_map(contract, label, binding, expected_fields, source_scopes)


def _validate_runtime_binding_map(
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
        raise ContractError(f"{label} must exactly bind target input" + (": " + "; ".join(parts) if parts else ""))
    for name, source in bindings.items():
        actual_type = _expression_type(contract, source, source_scopes, f"{label}.{name}")
        expected_type = expected[name]
        if actual_type and not _type_assignable(actual_type, expected_type):
            raise ContractError(
                f"{label}.{name} type mismatch: expected {type_display(_effective_type(expected_type))}, "
                f"got {type_display(_effective_type(actual_type))} from {source}"
            )


def _validate_entry_point_fields(entry_id: str, entry: dict[str, Any], adapter_kind: str) -> None:
    allowed = {"adapter", "target", "rationale", "authorization_policy", "retry_safe"}
    generated = {
        "html_route": {"route"},
        "http_api": {"endpoint"},
        "cli": {"cli_command_ref"},
        "worker": {"workflow_ref"},
        "scheduled": {"workflow_ref"},
        "webhook": set(),
    }[adapter_kind]
    allowed.update(generated)
    extra = sorted(set(entry) - allowed)
    if extra:
        raise ContractError(f"Entry point {entry_id} adapter {adapter_kind} has unsupported fields: {extra}")


def _validate_entry_input_shape(entry_id: str, entry: dict[str, Any], adapter_kind: str) -> None:
    allowed = {
        "html_route": {"path_params", "query_params"},
        "http_api": {"path_params", "query_params", "body"},
        "cli": {"args"},
        "worker": {"payload"},
        "scheduled": set(),
        "webhook": {"path_params", "query_params", "payload"},
    }[adapter_kind]
    input_spec = entry_point_input(entry)
    extra = sorted(set(input_spec) - allowed)
    if extra:
        raise ContractError(f"Entry point {entry_id} adapter {adapter_kind} has unsupported input sections: {extra}")
    seen: dict[str, Any] = {}
    for section in ("path_params", "query_params", "body", "args"):
        for name, type_name in _entry_input_map(entry, section).items():
            previous = seen.get(name)
            if previous and not type_equals(previous, type_name):
                raise ContractError(
                    f"Entry {entry_id} input field {name} has conflicting types: "
                    f"{type_display(previous)} vs {type_display(type_name)}"
                )
            seen[name] = type_name


def _validate_state_machine_target_renderer(
    contract: dict[str, Any],
    entry_id: str,
    entry: dict[str, Any],
    state_machine_id: str,
    *,
    allowed_renderers: set[str],
) -> None:
    renderer = entry_state_machine_renderer(entry)
    if renderer is None:
        raise ContractError(f"Entry {entry_id} state machine target must declare renderer")
    if renderer not in allowed_renderers:
        raise ContractError(f"Entry {entry_id} cannot target state machine renderer {renderer!r}")
    if not _state_machine_supports_renderer(contract["state_machines"][state_machine_id], renderer):
        raise ContractError(f"Entry {entry_id} targets state machine {state_machine_id} renderer {renderer} but that state machine does not declare it")


def _state_machine_supports_renderer(state_machine: dict[str, Any], renderer: str) -> bool:
    return any(
        bool((state.get("renderers") or {}).get(renderer, {}).get("layout"))
        or (not state.get("child_state_machines") and bool((state.get("renderers") or {}).get(renderer, {}).get("presentation")))
        for state in state_machine.get("view_states", {}).values()
    )


def _validate_workflow_entry_target_source(contract: dict[str, Any], entry_id: str, entry: dict[str, Any], workflow_id: str) -> None:
    bindings = entry_workflow_trigger_bindings(entry)
    if not bindings:
        raise ContractError(f"Entry {entry_id} workflow target must declare trigger_bindings")
    expected = _workflow_trigger_payload_fields(contract, workflow_id, contract["workflows"][workflow_id])
    if set(bindings) != set(expected):
        missing = sorted(set(expected) - set(bindings))
        extra = sorted(set(bindings) - set(expected))
        parts = []
        if missing:
            parts.append("missing: " + ", ".join(missing))
        if extra:
            parts.append("extra: " + ", ".join(extra))
        raise ContractError(f"Entry {entry_id} target.trigger_bindings must exactly bind workflow trigger" + (": " + "; ".join(parts) if parts else ""))
    scopes: TypeScopes = {"input": _entry_input_source_types(contract, entry)}
    for name, binding in bindings.items():
        actual_type = _expression_type(contract, binding, scopes, f"Entry {entry_id} target.trigger_bindings.{name}")
        expected_type = expected[name]
        if actual_type and not _type_assignable(actual_type, expected_type):
            raise ContractError(
                f"Entry {entry_id} target.trigger_bindings.{name} type mismatch: "
                f"expected {type_display(_effective_type(expected_type))}, got {type_display(_effective_type(actual_type))} from {binding}"
            )


def _validate_api_entry_input(
    entry_id: str,
    entry: dict[str, Any],
    application_action: dict[str, Any],
    path_params: dict[str, Any],
    query_params: dict[str, Any],
    body: dict[str, Any],
) -> None:
    cap_input = application_action["input"]
    all_params = {**path_params, **query_params}
    all_input = {**all_params, **body}
    if set(path_params) - set(cap_input):
        raise ContractError(f"API entry {entry_id} input.path_params must be application action input fields")
    if set(query_params) - set(cap_input):
        raise ContractError(f"API entry {entry_id} input.query_params must be application action input fields")
    if set(body) - set(cap_input):
        raise ContractError(f"API entry {entry_id} input.body must be application action input fields")
    if set(path_params) & set(query_params) or set(all_params) & set(body):
        raise ContractError(f"API entry {entry_id} input fields cannot appear in multiple input sections")
    _validate_entry_input_types(entry_id, "input.path_params", path_params, cap_input)
    _validate_entry_input_types(entry_id, "input.query_params", query_params, cap_input)
    _validate_entry_input_types(entry_id, "input.body", body, cap_input)
    method = (entry_point_method(entry) or "").lower()
    if method in {"get", "delete"}:
        if body:
            raise ContractError(f"API entry {entry_id} {entry_point_method(entry)} must not declare input.body")
        if set(all_params) != set(cap_input):
            missing_params = sorted(set(cap_input) - set(all_params))
            raise ContractError(f"API entry {entry_id} {entry_point_method(entry)} must declare all application action inputs as path_params or query_params: {missing_params}")
    missing = sorted(set(cap_input) - set(all_input))
    if missing:
        raise ContractError(f"API entry {entry_id} input must include every application action input: {missing}")


def _validate_event_payload_entry_input(contract: dict[str, Any], entry_id: str, entry: dict[str, Any], workflow_id: str) -> None:
    trigger = contract["workflows"][workflow_id]["trigger"]
    if "domain_event" not in trigger:
        return
    event_id = trigger["domain_event"]
    event = contract["domain_events"].get(event_id)
    if not event:
        raise ContractError(f"Entry {entry_id} workflow target source references unknown domain event {event_id}")
    payload_type = entry_point_input(entry).get("payload")
    if not type_equals(payload_type, event["payload_schema"]):
        raise ContractError(f"Entry {entry_id} input.payload must be {type_display(event['payload_schema'])}, got {type_display(payload_type)}")


def _validate_target_bindings(
    contract: dict[str, Any],
    entry_id: str,
    entry: dict[str, Any],
    target_input_types: dict[str, Any],
) -> None:
    kind, value = entry_target_pair(entry)
    bindings = entry_point_input_bindings(entry)
    if kind == "application_action":
        expected = contract["application_actions"][value]["input"]
    elif kind == "state_machine":
        expected = {name: contract["state_machines"][value].get("context", {})[name] for name in target_input_types}
    else:
        if bindings:
            raise ContractError(f"Entry {entry_id} target.input_bindings is not supported for workflow targets")
        return
    if set(bindings) != set(expected):
        missing = sorted(set(expected) - set(bindings))
        extra = sorted(set(bindings) - set(expected))
        parts = []
        if missing:
            parts.append("missing: " + ", ".join(missing))
        if extra:
            parts.append("extra: " + ", ".join(extra))
        raise ContractError(f"Entry {entry_id} target.input_bindings must exactly bind target input" + (": " + "; ".join(parts) if parts else ""))
    source_scopes: TypeScopes = {"input": _entry_input_source_types(contract, entry)}
    for target_name, source in bindings.items():
        actual_type = _expression_type(
            contract,
            source,
            source_scopes,
            f"Entry {entry_id} target.input_bindings.{target_name}",
        )
        expected_type = expected[target_name]
        if actual_type and not _type_assignable(actual_type, expected_type):
            raise ContractError(
                f"Entry {entry_id} target.input_bindings.{target_name} type mismatch: "
                f"expected {type_display(_effective_type(expected_type))}, got {type_display(_effective_type(actual_type))} from {source}"
            )


def _validate_api_entry_point_responses(entry_id: str, entry: dict[str, Any], application_action: dict[str, Any]) -> None:
    responses = _application_action_entry_point_responses(entry_id, entry, application_action)
    statuses: dict[int, str] = {}
    for outcome_id, response in responses.items():
        outcome = application_action["outcomes"][outcome_id]
        if set(response) != {"status", "body"}:
            raise ContractError(f"API entry {entry_id} response {outcome_id} must declare exactly status and body")
        status = response["status"]
        if status in statuses:
            raise ContractError(
                f"API entry {entry_id} responses {statuses[status]} and {outcome_id} cannot share HTTP status {status}"
            )
        statuses[status] = outcome_id
        if outcome["kind"] == "success":
            expected = 201 if application_action.get("creates") else 200
            if status != expected:
                raise ContractError(f"API entry {entry_id} success response {outcome_id} status must be {expected}")
        elif status < 400:
            raise ContractError(f"API entry {entry_id} failure response {outcome_id} status must be 4xx or 5xx")
        body = response["body"]
        _validate_response_value(
            f"API entry {entry_id} response {outcome_id}.body",
            body,
            outcome["result"],
        )


def _validate_cli_application_action_response_handlers(
    contract: dict[str, Any],
    entry_id: str,
    entry: dict[str, Any],
    application_action: dict[str, Any],
) -> None:
    responses = _application_action_entry_point_response_handlers(entry_id, entry, application_action)
    exit_codes: dict[int, str] = {}
    for outcome_id, response in responses.items():
        outcome = application_action["outcomes"][outcome_id]
        _validate_cli_response_handler(
            contract,
            entry_id,
            outcome_id,
            response,
            outcome_kind=outcome["kind"],
            source_scopes={
                "input": _entry_input_source_types(contract, entry),
                "outcome": _typed_source_paths(contract, ("result",), outcome["result"]),
            },
            delegated_entry_id=None,
            retry_allowed=_application_action_retry_safe(application_action),
            retry_error=f"CLI entry {entry_id} response handler {outcome_id} retry_policy requires a query or retry_safe target operation",
            exit_codes=exit_codes,
        )


def _validate_cli_delegated_response_handlers(
    contract: dict[str, Any],
    entry_id: str,
    entry: dict[str, Any],
    delegated_entry_id: str,
) -> None:
    delegated_entry = contract["entry_points"][delegated_entry_id]
    expected = _entry_point_named_response_outcomes(contract, delegated_entry_id)
    handlers = entry_point_response_handlers(entry)
    if set(handlers) != expected:
        missing = sorted(expected - set(handlers))
        extra = sorted(set(handlers) - expected)
        parts = []
        if missing:
            parts.append("missing: " + ", ".join(missing))
        if extra:
            parts.append("extra: " + ", ".join(extra))
        raise ContractError(
            f"CLI entry {entry_id} response_handlers must exactly map delegated entry outcomes"
            + (": " + "; ".join(parts) if parts else "")
        )
    exit_codes: dict[int, str] = {}
    outcome_kinds = _entry_point_outcome_kinds(contract, delegated_entry_id)
    response_types = _entry_point_response_body_types(contract, delegated_entry_id)
    retry_allowed = _entry_point_retry_safe(contract, delegated_entry_id)
    for outcome_id, handler in handlers.items():
        if handler.get("retry_policy") and not retry_allowed:
            raise ContractError(
                f"CLI entry {entry_id} response handler {outcome_id} retry_policy requires delegated entry point "
                f"{delegated_entry_id} and its final target to be retry_safe or query"
            )
        source_scopes: TypeScopes = {"input": _entry_input_source_types(contract, entry)}
        response_type = response_types.get(outcome_id)
        if response_type is not None:
            source_scopes["response"] = _typed_source_paths(contract, ("body",), response_type)
        _validate_cli_response_handler(
            contract,
            entry_id,
            outcome_id,
            handler,
            outcome_kind=outcome_kinds.get(outcome_id),
            source_scopes=source_scopes,
            delegated_entry_id=delegated_entry_id,
            retry_allowed=retry_allowed,
            retry_error=(
                f"CLI entry {entry_id} response handler {outcome_id} retry_policy requires delegated entry point "
                f"{delegated_entry_id} and its final target to be retry_safe or query"
            ),
            exit_codes=exit_codes,
        )


def _validate_cli_response_handler(
    contract: dict[str, Any],
    entry_id: str,
    outcome_id: str,
    handler: dict[str, Any],
    *,
    outcome_kind: str | None,
    source_scopes: TypeScopes,
    delegated_entry_id: str | None,
    retry_allowed: bool,
    retry_error: str,
    exit_codes: dict[int, str],
) -> None:
    exit_code = handler["exit_code"]
    streams = [stream for stream in ("stdout", "stderr") if stream in handler]
    if len(streams) != 1:
        raise ContractError(f"CLI entry {entry_id} response handler {outcome_id} must declare exactly one of stdout or stderr")
    if outcome_kind == "success" and streams[0] != "stdout":
        raise ContractError(f"CLI entry {entry_id} success response handler {outcome_id} must declare stdout")
    if outcome_kind == "success" and exit_code != 0:
        raise ContractError(f"CLI entry {entry_id} success response handler {outcome_id} exit_code must be 0")
    if outcome_kind == "failure" and streams[0] != "stderr":
        raise ContractError(f"CLI entry {entry_id} failure response handler {outcome_id} must declare stderr")
    if outcome_kind == "failure" and exit_code == 0:
        raise ContractError(f"CLI entry {entry_id} failure response handler {outcome_id} exit_code must be nonzero")
    if handler.get("retry_policy") and not retry_allowed:
        raise ContractError(retry_error)
    if exit_code in exit_codes:
        raise ContractError(
            f"CLI entry {entry_id} response handlers {exit_codes[exit_code]} and {outcome_id} cannot share exit_code {exit_code}"
        )
    exit_codes[exit_code] = outcome_id
    output = handler[streams[0]]
    text_ref = output["text"]
    if text_ref not in contract.get("text_resources", {}):
        raise ContractError(f"CLI entry {entry_id} response handler {outcome_id} references unknown text resource {text_ref}")
    bindings = output.get("bindings") or {}
    expected_text_args = contract["text_resources"][text_ref].get("args", {})
    if set(bindings) != set(expected_text_args):
        missing = sorted(set(expected_text_args) - set(bindings))
        extra = sorted(set(bindings) - set(expected_text_args))
        parts = []
        if missing:
            parts.append("missing: " + ", ".join(missing))
        if extra:
            parts.append("extra: " + ", ".join(extra))
        raise ContractError(
            f"CLI entry {entry_id} response handler {outcome_id} bindings must match text args"
            + (": " + "; ".join(parts) if parts else "")
        )
    for binding_name, binding in bindings.items():
        actual_type = _expression_type(contract, binding, source_scopes, f"CLI entry {entry_id} response handler {outcome_id}.{streams[0]}.bindings.{binding_name}")
        expected_type = expected_text_args[binding_name]
        if actual_type and not _type_assignable(actual_type, expected_type):
            raise ContractError(
                f"CLI entry {entry_id} response handler {outcome_id}.{streams[0]}.bindings.{binding_name} "
                f"type mismatch: expected {type_display(_effective_type(expected_type))}, got {type_display(_effective_type(actual_type))}"
            )


def _application_action_entry_point_responses(entry_id: str, entry: dict[str, Any], application_action: dict[str, Any]) -> dict[str, Any]:
    responses = entry_point_responses(entry)
    if set(responses) != set(application_action["outcomes"]):
        missing = sorted(set(application_action["outcomes"]) - set(responses))
        extra = sorted(set(responses) - set(application_action["outcomes"]))
        parts = []
        if missing:
            parts.append("missing: " + ", ".join(missing))
        if extra:
            parts.append("extra: " + ", ".join(extra))
        raise ContractError(f"Entry {entry_id} responses must exactly map application action outcomes" + (": " + "; ".join(parts) if parts else ""))
    return responses


def _application_action_entry_point_response_handlers(entry_id: str, entry: dict[str, Any], application_action: dict[str, Any]) -> dict[str, Any]:
    handlers = entry_point_response_handlers(entry)
    if set(handlers) != set(application_action["outcomes"]):
        missing = sorted(set(application_action["outcomes"]) - set(handlers))
        extra = sorted(set(handlers) - set(application_action["outcomes"]))
        parts = []
        if missing:
            parts.append("missing: " + ", ".join(missing))
        if extra:
            parts.append("extra: " + ", ".join(extra))
        raise ContractError(f"Entry {entry_id} response_handlers must exactly map application action outcomes" + (": " + "; ".join(parts) if parts else ""))
    return handlers


def _entry_point_named_response_outcomes(contract: dict[str, Any], entry_id: str) -> set[str]:
    entry = contract["entry_points"][entry_id]
    handlers = entry_point_response_handlers(entry)
    if handlers:
        return set(handlers)
    responses = entry_point_responses(entry)
    if responses:
        return set(responses)
    target_kind, target_ref = entry_target_pair(entry)
    if target_kind == "application_action":
        return set(contract["application_actions"][target_ref]["outcomes"])
    if target_kind == "workflow":
        return set(contract["workflows"][target_ref]["outcomes"])
    if target_kind == "entry_point":
        return _entry_point_named_response_outcomes(contract, target_ref)
    return set()


def _entry_point_outcome_kinds(contract: dict[str, Any], entry_id: str) -> dict[str, str]:
    target_kind, target_ref = entry_target_pair(contract["entry_points"][entry_id])
    if target_kind == "application_action":
        return {name: outcome["kind"] for name, outcome in contract["application_actions"][target_ref]["outcomes"].items()}
    if target_kind == "workflow":
        return {name: outcome["kind"] for name, outcome in contract["workflows"][target_ref]["outcomes"].items()}
    if target_kind == "entry_point":
        return _entry_point_outcome_kinds(contract, target_ref)
    return {}


def _entry_point_response_body_types(contract: dict[str, Any], entry_id: str) -> dict[str, Any]:
    entry = contract["entry_points"][entry_id]
    responses = entry_point_responses(entry)
    result: dict[str, Any] = {}
    for outcome_id, response in responses.items():
        body = response.get("body")
        if body:
            result[outcome_id] = body["type"]
    if result:
        return result
    target_kind, target_ref = entry_target_pair(entry)
    if target_kind == "application_action":
        return {name: outcome["result"] for name, outcome in contract["application_actions"][target_ref]["outcomes"].items()}
    if target_kind == "workflow":
        return {name: outcome["result"] for name, outcome in contract["workflows"][target_ref]["outcomes"].items()}
    if target_kind == "entry_point":
        return _entry_point_response_body_types(contract, target_ref)
    return {}


def _validate_response_value(label: str, value: dict[str, Any], expected_type: Any) -> None:
    if set(value) != {"type", "from"} or value["from"] != "$outcome.result" or not type_equals(value["type"], expected_type):
        raise ContractError(f"{label} must expose $outcome.result as {type_display(expected_type)}")


def _validate_async_entry_point_responses(entry_id: str, entry: dict[str, Any], *, require_failure_disposition: bool) -> None:
    responses = entry_point_responses(entry)
    accepted = responses.get("accepted")
    if accepted != {"disposition": "acknowledge"}:
        raise ContractError(f"Entry {entry_id} ingress_responses.accepted must declare disposition: acknowledge")
    failure_responses = {name: response for name, response in responses.items() if name != "accepted"}
    if require_failure_disposition and not failure_responses:
        raise ContractError(f"Entry {entry_id} must declare at least one non-acknowledge ingress disposition such as retry, reject, or dead_letter")
    for response_id, response in failure_responses.items():
        if set(response) != {"disposition", "problem"}:
            raise ContractError(f"Entry {entry_id} ingress disposition {response_id} must declare exactly disposition and problem")
        if response["disposition"] not in {"retry", "reject", "dead_letter"}:
            raise ContractError(f"Entry {entry_id} ingress disposition {response_id} must be retry, reject, or dead_letter")
        _validate_problem_type(f"Entry {entry_id} disposition {response_id} problem", response["problem"])
    if require_failure_disposition and not any(response["disposition"] in {"reject", "dead_letter"} for response in failure_responses.values()):
        raise ContractError(f"Entry {entry_id} must declare a reject or dead_letter ingress disposition for malformed or poison messages")


def _validate_webhook_entry_point_responses(entry_id: str, entry: dict[str, Any]) -> None:
    if entry_point_responses(entry) != {"accepted": {"status": 202}}:
        raise ContractError(f"Webhook entry {entry_id} ingress_responses.accepted.status must be 202")


def _validate_state_machine_entry_inputs(
    contract: dict[str, Any],
    entry_id: str,
    state_machine_id: str,
    *,
    declared: dict[str, Any],
    input_label: str,
) -> None:
    state_machine = contract["state_machines"][state_machine_id]
    state_machine_context = state_machine.get("context", {})
    extra = sorted(set(declared) - set(state_machine_context))
    if extra:
        raise ContractError(f"Entry {entry_id} {input_label} must be declared state machine context fields: {extra}")
    _validate_entry_input_types(entry_id, input_label, declared, state_machine_context)
    required = _required_entry_state_machine_context(contract, state_machine_id)
    missing = sorted(set(required) - set(declared))
    if missing:
        raise ContractError(f"Entry {entry_id} {input_label} must include required state machine context inputs: {missing}")


def _required_entry_state_machine_context(contract: dict[str, Any], state_machine_id: str) -> dict[str, Any]:
    state_machine = contract["state_machines"][state_machine_id]
    required: dict[str, Any] = {
        name: field
        for name, field in state_machine.get("context", {}).items()
        if field.get("required", True)
    }
    _add_query_context_requirements(
        contract,
        f"state machine {state_machine_id}",
        state_machine.get("data_loaders", {}),
        state_machine.get("context", {}),
        required,
    )
    for state_name, state in state_machine.get("view_states", {}).items():
        _add_query_context_requirements(
            contract,
            f"state machine {state_machine_id}.{state_name}",
            state.get("data_loaders", {}),
            state_machine.get("context", {}),
            required,
        )
        for mount in state.get("child_state_machines", []):
            child_state_machine = contract["state_machines"][mount["state_machine"]]
            initial_state = child_state_machine["view_states"][mount["initial_view_state"]]
            _add_mount_context_requirements(
                contract,
                state_machine_id,
                mount,
                child_state_machine,
                child_state_machine.get("data_loaders", {}),
                required,
            )
            _add_mount_context_requirements(
                contract,
                state_machine_id,
                mount,
                child_state_machine,
                initial_state.get("data_loaders", {}),
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
        for key in _context_roots_from_input_bindings(f"{label} data_loader {invocation_id}", invocation.get("input_bindings") or {}):
            if key not in context:
                raise ContractError(f"{label} data_loader {invocation_id} references undeclared context field: {key}")
            _add_required_entry_context(required, key, context[key], label)


def _add_mount_context_requirements(
    contract: dict[str, Any],
    state_machine_id: str,
    mount: dict[str, Any],
    state_machine: dict[str, Any],
    invocations: dict[str, Any],
    required: dict[str, Any],
) -> None:
    mount_context = mount.get("context_bindings", {})
    child_state_machine_context = state_machine.get("context", {})
    parent_state_machine_context = contract["state_machines"][state_machine_id].get("context", {})
    for invocation_id, invocation in sorted((invocations or {}).items()):
        label = f"composed state machine {state_machine_id}.{mount['id']} data_loader {invocation_id}"
        for child_key in _context_roots_from_input_bindings(label, invocation.get("input_bindings") or {}):
            if child_key not in child_state_machine_context:
                raise ContractError(f"{label} references undeclared child context field: {child_key}")
            expected_type = child_state_machine_context[child_key]
            value = mount_context.get(child_key)
            if not (isinstance(value, dict) and "from" in value and is_reference_expression(value["from"])):
                continue
            try:
                ref = parse_reference_expression(value["from"])
            except ReferenceExpressionError as exc:
                raise ContractError(f"composed state machine {state_machine_id}.{mount['id']} has malformed runtime reference: {value}") from exc
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
            _add_required_entry_context(
                required,
                parent_key,
                parent_state_machine_context[parent_key],
                label,
            )


def _context_roots_from_input_bindings(label: str, bindings: dict[str, Any]) -> set[str]:
    roots: set[str] = set()
    for field, binding in bindings.items():
        if not (isinstance(binding, dict) and set(binding) == {"from"}):
            continue
        try:
            ref = parse_reference_expression(binding["from"])
        except ReferenceExpressionError as exc:
            raise ContractError(f"{label} input_bindings.{field} references unsupported expression: {binding['from']}") from exc
        if ref.root == "context" and ref.path:
            roots.add(ref.path[0])
    return roots


def _add_required_entry_context(required: dict[str, Any], key: str, type_name: Any, label: str) -> None:
    existing = required.get(key)
    if existing and not type_equals(unwrap_nullable(_effective_type(existing)), unwrap_nullable(_effective_type(type_name))):
        raise ContractError(
            f"{label} requires conflicting entry input type for {key}: "
            f"{type_display(_effective_type(existing))} vs {type_display(_effective_type(type_name))}"
        )
    required[key] = type_name


def _validate_exact_entry_inputs(entry_id: str, field: str, actual: dict[str, Any], expected: dict[str, Any]) -> None:
    if set(actual) != set(expected):
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        parts = []
        if missing:
            parts.append("missing: " + ", ".join(missing))
        if extra:
            parts.append("extra: " + ", ".join(extra))
        raise ContractError(f"Entry {entry_id} {field} must exactly match target input" + (": " + "; ".join(parts) if parts else ""))
    _validate_entry_input_types(entry_id, field, actual, expected)


def _validate_entry_input_types(entry_id: str, field: str, actual: dict[str, Any], expected: dict[str, Any]) -> None:
    for name, type_name in actual.items():
        expected_type = expected.get(name)
        if not _type_assignable(type_name, expected_type):
            raise ContractError(
                f"Entry {entry_id} {field}.{name} type mismatch: "
                f"expected {type_display(_effective_type(expected_type))}, got {type_display(_effective_type(type_name))}"
            )


def _entry_input_map(entry: dict[str, Any], section: str) -> dict[str, Any]:
    value = entry_point_input(entry).get(section, {})
    return value if isinstance(value, dict) else {}


def _entry_input_source_types(contract: dict[str, Any], entry: dict[str, Any]) -> TypeScope:
    source_types: TypeScope = {}
    for section in ("path_params", "query_params", "body", "args"):
        for name, type_name in _entry_input_map(entry, section).items():
            source_types[(section, name)] = type_name
    payload = entry_point_input(entry).get("payload")
    if payload is not None:
        source_types.update(_typed_source_paths(contract, ("payload",), payload))
    return source_types


def _base_type(type_name: Any) -> str | None:
    return base_model_name(type_name)


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
    for root, entries in source.items():
        target.setdefault(root, {}).update(entries)


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


def _success_outcomes(cap: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {name: outcome for name, outcome in cap["outcomes"].items() if outcome["kind"] == "success"}


def _failure_outcomes(cap: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {name: outcome for name, outcome in cap["outcomes"].items() if outcome["kind"] == "failure"}


def _primary_success_outcome(cap: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    successes = _success_outcomes(cap)
    if len(successes) != 1:
        raise ContractError("Application action must declare exactly one success outcome")
    return next(iter(successes.items()))


def _success_result_type(cap: dict[str, Any]) -> Any:
    return _primary_success_outcome(cap)[1]["result"]


def _validate_workflows(contract: dict[str, Any]) -> None:
    for wid, workflow in contract["workflows"].items():
        kind, value = _one(workflow["trigger"], f"workflow {wid} trigger")
        if kind == "domain_event" and value not in contract["domain_events"]:
            raise ContractError(f"Workflow {wid} trigger references unknown domain event {value}")
        if kind == "application_action" and value not in contract["application_actions"]:
            raise ContractError(f"Workflow {wid} trigger references unknown application action {value}")
        _validate_workflow_outcomes(wid, workflow)
        step_ids = [step["id"] for step in workflow["steps"]]
        if len(step_ids) != len(set(step_ids)):
            raise ContractError(f"Workflow {wid} step ids must be unique")
        step_id_set = set(step_ids)
        source_types = _workflow_trigger_source_types(contract, wid, workflow)
        terminal_outcomes: set[str] = set()
        for step in workflow["steps"]:
            if step["application_action"] not in contract["application_actions"]:
                raise ContractError(f"Workflow {wid} step references unknown application action {step['application_action']}")
            operation = contract["application_actions"][step["application_action"]]
            _validate_workflow_step_bindings(contract, wid, step, operation, source_types)
            terminal_outcomes.update(_validate_workflow_step_transitions(wid, workflow, step, operation, step_id_set))
            _merge_type_scopes(source_types, _workflow_step_source_types(contract, step, operation))
        if terminal_outcomes != set(workflow["outcomes"]):
            missing = sorted(set(workflow["outcomes"]) - terminal_outcomes)
            extra = sorted(terminal_outcomes - set(workflow["outcomes"]))
            parts = []
            if missing:
                parts.append("missing outcome transitions: " + ", ".join(missing))
            if extra:
                parts.append("unknown outcome transitions: " + ", ".join(extra))
            raise ContractError(f"Workflow {wid} outcomes must be reachable from step transitions" + (": " + "; ".join(parts) if parts else ""))


def _validate_workflow_outcomes(workflow_id: str, workflow: dict[str, Any]) -> None:
    outcomes = workflow["outcomes"]
    successes = {name: outcome for name, outcome in outcomes.items() if outcome["kind"] == "success"}
    failures = {name: outcome for name, outcome in outcomes.items() if outcome["kind"] == "failure"}
    if len(successes) != 1:
        raise ContractError(f"Workflow {workflow_id} must declare exactly one success outcome")
    if not failures:
        raise ContractError(f"Workflow {workflow_id} must declare at least one failure outcome")
    for outcome_id, outcome in failures.items():
        _validate_problem_type(f"Workflow {workflow_id} failure outcome {outcome_id} result", outcome["result"])


def _workflow_trigger_source_types(contract: dict[str, Any], workflow_id: str, workflow: dict[str, Any]) -> TypeScopes:
    payload_type = _workflow_trigger_payload_type(contract, workflow_id, workflow)
    return {"trigger": _typed_source_paths(contract, ("payload",), payload_type)}


def _workflow_trigger_payload_type(contract: dict[str, Any], workflow_id: str, workflow: dict[str, Any]) -> Any:
    kind, value = _one(workflow["trigger"], f"workflow {workflow_id} trigger")
    if kind == "domain_event":
        return contract["domain_events"][value]["payload_schema"]
    return _success_result_type(contract["application_actions"][value])


def _workflow_trigger_payload_fields(contract: dict[str, Any], workflow_id: str, workflow: dict[str, Any]) -> dict[str, Any]:
    payload_type = _workflow_trigger_payload_type(contract, workflow_id, workflow)
    fields = object_fields_for_type(contract, payload_type)
    if fields:
        return fields
    return {"payload": payload_type}


def _workflow_step_source_types(contract: dict[str, Any], step: dict[str, Any], application_action: dict[str, Any]) -> TypeScopes:
    sources: TypeScope = {}
    for outcome_id, outcome in application_action["outcomes"].items():
        sources.update(_typed_source_paths(contract, (step["id"], "outcomes", outcome_id, "result"), outcome["result"]))
    return {"steps": sources}


WORKFLOW_TRANSITION_ACTIONS = ("next_step", "complete_as", "fail_as", "retry_policy", "dead_letter_as")


def _workflow_transition_action(transition: dict[str, Any]) -> tuple[str, Any]:
    actions = [action for action in WORKFLOW_TRANSITION_ACTIONS if action in transition]
    if len(actions) != 1:
        raise ContractError(
            "workflow transition must declare exactly one of "
            + ", ".join(WORKFLOW_TRANSITION_ACTIONS)
        )
    action = actions[0]
    return action, transition[action]


def _workflow_transition_outcome(action: str, value: Any) -> str | None:
    if action in {"complete_as", "fail_as", "dead_letter_as"}:
        return value
    if action == "retry_policy":
        return value["fail_as"]
    return None


def _validate_workflow_step_bindings(
    contract: dict[str, Any],
    workflow_id: str,
    step: dict[str, Any],
    application_action: dict[str, Any],
    source_types: TypeScopes,
) -> None:
    bindings = step["input_bindings"]
    expected = application_action["input"]
    if set(bindings) != set(expected):
        missing = sorted(set(expected) - set(bindings))
        extra = sorted(set(bindings) - set(expected))
        parts = []
        if missing:
            parts.append("missing: " + ", ".join(missing))
        if extra:
            parts.append("extra: " + ", ".join(extra))
        raise ContractError(f"Workflow {workflow_id} step {step['id']} input_bindings must exactly map application action input" + (": " + "; ".join(parts) if parts else ""))
    for name, source in bindings.items():
        actual_type = _expression_type(
            contract,
            source,
            source_types,
            f"Workflow {workflow_id} step {step['id']} input {name}",
        )
        expected_type = expected[name]
        if actual_type and not _type_assignable(actual_type, expected_type):
            raise ContractError(
                f"Workflow {workflow_id} step {step['id']} input {name} source {source} type must be "
                f"{type_display(_effective_type(expected_type))}, got {type_display(_effective_type(actual_type))}"
            )


def _validate_workflow_step_transitions(
    workflow_id: str,
    workflow: dict[str, Any],
    step: dict[str, Any],
    application_action: dict[str, Any],
    step_ids: set[str],
) -> set[str]:
    transitions = step["outcome_transitions"]
    if set(transitions) != set(application_action["outcomes"]):
        missing = sorted(set(application_action["outcomes"]) - set(transitions))
        extra = sorted(set(transitions) - set(application_action["outcomes"]))
        parts = []
        if missing:
            parts.append("missing: " + ", ".join(missing))
        if extra:
            parts.append("extra: " + ", ".join(extra))
        raise ContractError(f"Workflow {workflow_id} step {step['id']} outcome_transitions must exactly map application action outcomes" + (": " + "; ".join(parts) if parts else ""))

    terminal_outcomes: set[str] = set()
    for outcome_id, transition in transitions.items():
        try:
            action, value = _workflow_transition_action(transition)
        except ContractError as exc:
            raise ContractError(f"Workflow {workflow_id} step {step['id']} transition {outcome_id} {exc}") from exc
        outcome = application_action["outcomes"][outcome_id]
        if action == "next_step":
            next_step = value
            if next_step not in step_ids:
                raise ContractError(f"Workflow {workflow_id} step {step['id']} transition {outcome_id} references unknown next step {next_step}")
            if next_step == step["id"]:
                raise ContractError(f"Workflow {workflow_id} step {step['id']} transition {outcome_id} cannot loop to itself")
        else:
            routed_outcome_id = _workflow_transition_outcome(action, value)
            assert routed_outcome_id is not None
            routed_outcome = workflow["outcomes"].get(routed_outcome_id)
            if not routed_outcome:
                raise ContractError(f"Workflow {workflow_id} step {step['id']} transition {outcome_id} references unknown workflow outcome {routed_outcome_id}")
            expected_kind = "success" if action == "complete_as" else "failure"
            if outcome["kind"] != expected_kind or routed_outcome["kind"] != expected_kind:
                raise ContractError(f"Workflow {workflow_id} step {step['id']} transition {outcome_id} must preserve {outcome['kind']} outcome semantics")
            if not type_equals(routed_outcome["result"], outcome["result"]):
                raise ContractError(
                    f"Workflow {workflow_id} outcome {routed_outcome_id} result must be "
                    f"{type_display(outcome['result'])} to receive step outcome {outcome_id}"
                )
            if outcome_id in _action_authorization_outcomes(application_action) and not _is_explicit_authorization_workflow_outcome(routed_outcome_id) and not transition.get("rationale"):
                raise ContractError(
                    f"Workflow {workflow_id} step {step['id']} transition {outcome_id} collapses authorization failure into {routed_outcome_id}; declare an explicit authorization outcome or add rationale"
                )
            terminal_outcomes.add(routed_outcome_id)
        if action == "retry_policy":
            if outcome["kind"] != "failure":
                raise ContractError(f"Workflow {workflow_id} step {step['id']} transition {outcome_id} retry_policy is only valid for failure outcomes")
            if not _application_action_retry_safe(application_action):
                raise ContractError(
                    f"Workflow {workflow_id} step {step['id']} transition {outcome_id} retry_policy requires "
                    "a query or retry_safe target operation"
                )
            retry = value
            if retry["attempts"] < 1 or retry["attempts"] > 10:
                raise ContractError(f"Workflow {workflow_id} step {step['id']} transition {outcome_id} retry_policy attempts must be between 1 and 10")
        if action == "dead_letter_as" and outcome["kind"] != "failure":
            raise ContractError(f"Workflow {workflow_id} step {step['id']} transition {outcome_id} dead_letter_as is only valid for failure outcomes")
    return terminal_outcomes


def _is_explicit_authorization_workflow_outcome(outcome_id: str) -> bool:
    return any(token in outcome_id for token in ("authorization", "unauthenticated", "forbidden"))


def _validate_fixtures(contract: dict[str, Any]) -> None:
    for fixture_id, fixture in contract["fixtures"].items():
        if not fixture_id.startswith("fixture."):
            raise ContractError(f"Fixture id must start with fixture.: {fixture_id}")
        if not isinstance(fixture["values"], dict) or not fixture["values"]:
            raise ContractError(f"Fixture {fixture_id} must declare non-empty values")


def _validate_facts(contract: dict[str, Any]) -> None:
    for fact_id, fact in contract["facts"].items():
        if not fact_id.startswith("fact."):
            raise ContractError(f"Fact id must start with fact.: {fact_id}")
        _validate_fact_body(contract, fact, f"Fact {fact_id}")


def _validate_test_cases(contract: dict[str, Any]) -> None:
    for test_case_id, test_case in contract["test_cases"].items():
        fixture_ids = test_case["given"].get("seed_fixtures", [])
        for fixture_id in fixture_ids:
            if fixture_id not in contract["fixtures"]:
                raise ContractError(f"Test case {test_case_id} references unknown seed fixture {fixture_id}")
        fixture_values = _fixture_namespace(contract, fixture_ids, test_case_id)
        _validate_fixture_templates(test_case, fixture_values, test_case_id)
        for fact in test_case["given"].get("domain_facts", []):
            _validate_fact_body(contract, fact, f"Test case {test_case_id} given.domain_facts")
        for fact in test_case["then"].get("expected_facts", []):
            _validate_fact_body(contract, fact, f"Test case {test_case_id} then.expected_facts")
        _validate_test_case_when(contract, test_case_id, test_case)
        _validate_test_case_subject(contract, test_case_id, test_case)
        _validate_test_case_then(contract, test_case_id, test_case)
        _validate_test_case_archetype(test_case_id, test_case)


def _validate_fact_body(contract: dict[str, Any], fact: dict[str, Any], label: str) -> None:
    kind, body = _one_fact(fact, label)
    model_id = body["model"]
    if model_id not in contract["models"]:
        raise ContractError(f"{label} references unknown model {model_id}")
    fields = set(contract["models"][model_id]["fields"])
    if kind == "present":
        unknown = set(body["values"]) - fields
        if unknown:
            raise ContractError(f"{label} seeds unknown {model_id} fields: {sorted(unknown)}")
    elif kind == "absent":
        unknown = set(body["where"]) - fields
        if unknown:
            raise ContractError(f"{label} filters unknown {model_id} fields: {sorted(unknown)}")
    else:  # pragma: no cover - schema prevents this.
        raise ContractError(f"{label} uses unsupported fact kind {kind}")


def _fixture_namespace(contract: dict[str, Any], fixture_ids: list[str], test_case_id: str) -> dict[str, Any]:
    namespace: dict[str, Any] = {}
    for fixture_id in fixture_ids:
        _deep_merge(namespace, copy.deepcopy(contract["fixtures"][fixture_id]["values"]), f"test case {test_case_id} fixture {fixture_id}")
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


def _validate_fixture_templates(node: Any, fixture_values: dict[str, Any], test_case_id: str) -> None:
    for ref in _fixture_refs(node):
        _resolve_fixture_path(fixture_values, ref, test_case_id)


def _fixture_refs(node: Any) -> list[str]:
    refs: list[str] = []
    if isinstance(node, dict):
        if set(node) == {"from"} and is_reference_expression(node["from"]):
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


def _resolve_fixture_path(fixture_values: dict[str, Any], ref: str, test_case_id: str) -> Any:
    try:
        expression = parse_reference_expression(ref)
    except ReferenceExpressionError as exc:
        raise ContractError(f"Test case {test_case_id} has malformed runtime reference {ref}") from exc
    if expression.root != "fixture":
        raise ContractError(f"Test case {test_case_id} references unavailable runtime root: ${expression.root}")
    current: Any = fixture_values
    traversed: list[str] = []
    for part in expression.path:
        traversed.append(part)
        if not isinstance(current, dict) or part not in current:
            path = ".".join(traversed)
            raise ContractError(f"Test case {test_case_id} fixture ref {ref} cannot resolve at {path}")
        current = current[part]
    return current


def _validate_test_case_when(contract: dict[str, Any], test_case_id: str, test_case: dict[str, Any]) -> None:
    kind, body = _one(test_case["when"], f"test case {test_case_id} when")
    ref = body["ref"]
    if kind in {"open_entry_point", "call_entry_point"}:
        if ref not in contract["entry_points"]:
            raise ContractError(f"Test case {test_case_id} references unknown entry point {ref}")
        entry = contract["entry_points"][ref]
        adapter_kind, _ = entry_point_adapter_pair(entry)
        entry_target_kind, _ = entry_target_pair(entry)
        if kind == "open_entry_point" and not (adapter_kind in {"html_route", "cli"} and entry_target_kind == "state_machine"):
            raise ContractError(f"Test case {test_case_id} open_entry_point must reference an HTML route or CLI state machine entry point")
        if kind == "call_entry_point" and not (adapter_kind in {"http_api", "cli"} and _entry_point_effective_application_action_ref(contract, ref)):
            raise ContractError(f"Test case {test_case_id} call_entry_point must reference an HTTP API or CLI application action entry point")
        _validate_test_case_entry_input(test_case_id, kind, body, entry)
    elif kind == "invoke_application_action":
        if ref not in contract["application_actions"]:
            raise ContractError(f"Test case {test_case_id} references unknown application action {ref}")
    elif kind == "emit_domain_event":
        if ref not in contract["domain_events"]:
            raise ContractError(f"Test case {test_case_id} references unknown domain event {ref}")
        _validate_test_case_event_payload(contract, test_case_id, ref, body.get("payload", {}))
    _validate_test_case_outcome(contract, test_case_id, test_case)


def _validate_test_case_event_payload(contract: dict[str, Any], test_case_id: str, event_id: str, payload: dict[str, Any]) -> None:
    event = contract["domain_events"][event_id]
    fields = object_fields_for_type(contract, event["payload_schema"])
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
            f"Test case {test_case_id} emit_domain_event.payload must exactly match domain event {event_id} payload "
            f"{type_display(event['payload_schema'])}" + (": " + "; ".join(parts) if parts else "")
        )


def _validate_test_case_entry_input(test_case_id: str, kind: str, body: dict[str, Any], entry: dict[str, Any]) -> None:
    expected = _entry_external_input_types(entry)
    actual = body.get("input", {})
    if set(actual) != set(expected):
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        parts = []
        if missing:
            parts.append("missing: " + ", ".join(missing))
        if extra:
            parts.append("extra: " + ", ".join(extra))
        raise ContractError(f"Test case {test_case_id} {kind}.input must exactly match entry input" + (": " + "; ".join(parts) if parts else ""))


def _entry_external_input_types(entry: dict[str, Any]) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for section in ("path_params", "query_params", "body", "args"):
        fields.update(_entry_input_map(entry, section))
    return fields


def _subject_ref(subject_ref: dict[str, str]) -> tuple[str, str]:
    return next(iter(subject_ref.items()))


def _validate_test_case_subject(contract: dict[str, Any], test_case_id: str, test_case: dict[str, Any]) -> None:
    subject_kind, subject_value = _subject_ref(test_case["subject_ref"])
    collections = {
        "entry_point": "entry_points",
        "domain_event": "domain_events",
        "application_action": "application_actions",
        "state_machine": "state_machines",
        "workflow": "workflows",
    }
    if subject_value not in contract[collections[subject_kind]]:
        raise ContractError(f"Test case {test_case_id} subject_ref references unknown {subject_kind} {subject_value}")

    when_kind, when_body = _one(test_case["when"], f"test case {test_case_id} when")
    then = test_case["then"]
    application_action_ref = _test_case_application_action_ref(contract, when_kind, when_body)
    entry_ref = when_body["ref"] if when_kind in {"open_entry_point", "call_entry_point"} else None
    domain_event_ref = when_body["ref"] if when_kind == "emit_domain_event" else None
    state_machine_ref = _test_case_state_machine_ref(contract, when_kind, when_body)

    if subject_kind == "entry_point" and entry_ref != subject_value:
        raise ContractError(f"Test case {test_case_id} subject_ref.entry_point must match the entry point under test")
    if subject_kind == "application_action" and application_action_ref != subject_value:
        raise ContractError(f"Test case {test_case_id} subject_ref.application_action must match the application action under test")
    if subject_kind == "domain_event" and domain_event_ref != subject_value and subject_value not in (then.get("domain_events") or {}).get("emitted", []):
        raise ContractError(f"Test case {test_case_id} subject_ref.domain_event must match the emitted domain event under test")
    if subject_kind == "state_machine":
        asserted = (then.get("state_machine") or {}).get("ref")
        if subject_value not in {state_machine_ref, asserted}:
            raise ContractError(f"Test case {test_case_id} subject_ref.state_machine must match the state machine under test")
    if subject_kind == "workflow":
        workflow = then.get("workflow") or {}
        if workflow.get("ref") != subject_value:
            raise ContractError(f"Test case {test_case_id} subject_ref.workflow must match then.workflow.ref")


def _test_case_application_action_ref(contract: dict[str, Any], when_kind: str, when_body: dict[str, Any]) -> str | None:
    if when_kind == "invoke_application_action":
        return when_body["ref"]
    if when_kind == "call_entry_point":
        return _entry_point_effective_application_action_ref(contract, when_body["ref"])
    return None


def _entry_point_effective_application_action_ref(contract: dict[str, Any], entry_id: str) -> str | None:
    target_kind, target_ref = entry_target_pair(contract["entry_points"][entry_id])
    if target_kind == "application_action":
        return target_ref
    if target_kind == "entry_point":
        return _entry_point_effective_application_action_ref(contract, target_ref)
    return None


def _test_case_state_machine_ref(contract: dict[str, Any], when_kind: str, when_body: dict[str, Any]) -> str | None:
    if when_kind != "open_entry_point":
        return None
    target_kind, target_ref = entry_target_pair(contract["entry_points"][when_body["ref"]])
    if target_kind == "state_machine":
        return target_ref
    return None


def _validate_test_case_then(contract: dict[str, Any], test_case_id: str, test_case: dict[str, Any]) -> None:
    then = test_case["then"]
    if "state_machine" in then:
        expected_state_machine = then["state_machine"]
        state_machine_id = expected_state_machine["ref"]
        if state_machine_id not in contract["state_machines"]:
            raise ContractError(f"Test case {test_case_id} references unknown state machine {state_machine_id}")
        state_machine = contract["state_machines"][state_machine_id]
        if "view_state" in expected_state_machine:
            state = expected_state_machine["view_state"]
            if state not in state_machine.get("view_states", {}):
                raise ContractError(f"Test case {test_case_id} references unknown state machine view state {state_machine_id}.{state}")
        if "instances" in expected_state_machine:
            state_name = expected_state_machine.get("view_state")
            selected_state = state_machine.get("view_states", {}).get(state_name, {}) if state_name else {}
            mounted_instances = {mount["id"]: mount for mount in selected_state.get("child_state_machines", [])}
            if not mounted_instances:
                raise ContractError(f"Test case {test_case_id} asserts instance view states for non-composed state machine view state {state_machine_id}.{state_name}")
            for instance_id, expectation in expected_state_machine["instances"].items():
                if instance_id not in mounted_instances:
                    raise ContractError(f"Test case {test_case_id} references unknown state machine instance {state_machine_id}.{instance_id}")
                child_state_machine_id = mounted_instances[instance_id]["state_machine"]
                if expectation["view_state"] not in contract["state_machines"][child_state_machine_id]["view_states"]:
                    raise ContractError(f"Test case {test_case_id} references unknown state machine view state {child_state_machine_id}.{expectation['view_state']}")
        for sync_id in (expected_state_machine.get("signal_sync_rules") or {}).get("observed_rules", []):
            state_name = expected_state_machine.get("view_state")
            selected_state = state_machine.get("view_states", {}).get(state_name, {}) if state_name else {}
            if sync_id not in {rule["id"] for rule in selected_state.get("signal_sync_rules", [])}:
                raise ContractError(f"Test case {test_case_id} references unknown sync rule {state_machine_id}.{sync_id}")
        for key in (expected_state_machine.get("context") or {}):
            if key not in state_machine.get("context", {}):
                raise ContractError(f"Test case {test_case_id} asserts undeclared state machine context {state_machine_id}.{key}")
    for field in ["enables", "forbids", "invoked"]:
        for cap_id in then.get(field, []):
            if cap_id not in contract["application_actions"]:
                raise ContractError(f"Test case {test_case_id} {field} unknown application action {cap_id}")
    authorization_assertion = then.get("authorization") or {}
    for effect in ("allowed", "denied"):
        for assertion in authorization_assertion.get(effect, []):
            kind, ref = _authorization_assertion_target(assertion, f"Test case {test_case_id} authorization_policy.{effect}")
            if kind == "application_action" and ref not in contract["application_actions"]:
                raise ContractError(f"Test case {test_case_id} authorization_policy.{effect} unknown application action {ref}")
            if kind == "entry_point" and ref not in contract["entry_points"]:
                raise ContractError(f"Test case {test_case_id} authorization_policy.{effect} unknown entry point {ref}")
            authorization_policy = assertion.get("authorization_policy")
            if authorization_policy and authorization_policy not in contract["authorization_policies"]:
                raise ContractError(f"Test case {test_case_id} authorization_policy.{effect} unknown authorization_policy {authorization_policy}")
    model_exists = (then.get("model") or {}).get("exists")
    if model_exists:
        model_id = model_exists["model"]
        if model_id not in contract["models"]:
            raise ContractError(f"Test case {test_case_id} asserts unknown model {model_id}")
        unknown_fields = sorted(set(model_exists["where"]) - set(contract["models"][model_id]["fields"]))
        if unknown_fields:
            raise ContractError(f"Test case {test_case_id} model.exists filters unknown {model_id} fields: {unknown_fields}")
    domain_events = then.get("domain_events") or {}
    emitted = set(domain_events.get("emitted", []))
    not_emitted = set(domain_events.get("not_emitted", []))
    overlap = sorted(emitted & not_emitted)
    if overlap:
        raise ContractError(f"Test case {test_case_id} asserts domain events as both emitted and not_emitted: {overlap}")
    for event_id in list(emitted) + list(not_emitted):
        if event_id not in contract["domain_events"]:
            raise ContractError(f"Test case {test_case_id} asserts unknown domain event {event_id}")
    _validate_test_case_event_emissions(contract, test_case_id, test_case, emitted, not_emitted)
    _validate_test_case_invocations(contract, test_case_id, test_case)
    workflow = then.get("workflow")
    if workflow and workflow["ref"] not in contract["workflows"]:
        raise ContractError(f"Test case {test_case_id} asserts unknown workflow {workflow['ref']}")
    if workflow and workflow.get("outcome"):
        workflow_contract = contract["workflows"][workflow["ref"]]
        if workflow["outcome"] not in workflow_contract["outcomes"]:
            raise ContractError(f"Test case {test_case_id} asserts unknown workflow outcome {workflow['ref']}.{workflow['outcome']}")
    if workflow and workflow.get("executed") and not _workflow_can_run_from_test_case(contract, test_case):
        raise ContractError(f"Test case {test_case_id} asserts workflow executed but when does not trigger workflow {workflow['ref']}")
    if "response" in then:
        when_kind, _ = _one(test_case["when"], f"test case {test_case_id} when")
        if when_kind != "call_entry_point":
            raise ContractError(f"Test case {test_case_id} response assertions require call_entry_point")
    _validate_authorization_denial_outcome(contract, test_case_id, test_case)


def _validate_authorization_denial_outcome(contract: dict[str, Any], test_case_id: str, test_case: dict[str, Any]) -> None:
    if test_case["archetype"] != "authorization_denial":
        return
    outcome_id = test_case["then"].get("outcome")
    if not outcome_id:
        return
    when_kind, when_body = _one(test_case["when"], f"test case {test_case_id} when")
    application_action_id = _test_case_application_action_ref(contract, when_kind, when_body)
    if not application_action_id:
        raise ContractError(f"Test case {test_case_id} authorization_denial outcome requires an action binding")
    authorization = contract["application_actions"][application_action_id].get("authorization")
    if not authorization:
        raise ContractError(f"Test case {test_case_id} authorization_denial outcome requires application action authorization")
    mapped = {authorization["unauthenticated_as"], authorization["forbidden_as"]}
    if outcome_id not in mapped:
        raise ContractError(
            f"Test case {test_case_id} authorization_denial outcome must be one of application action authorization failure outcomes: "
            + ", ".join(sorted(mapped))
        )


def _validate_test_case_event_emissions(
    contract: dict[str, Any],
    test_case_id: str,
    test_case: dict[str, Any],
    emitted: set[str],
    not_emitted: set[str],
) -> None:
    when_kind, when_body = _one(test_case["when"], f"test case {test_case_id} when")
    then = test_case["then"]
    if when_kind == "emit_domain_event":
        if when_body["ref"] in emitted:
            return
        return
    application_action_id = _test_case_application_action_ref(contract, when_kind, when_body)
    outcome_id = then.get("outcome")
    if not application_action_id or not outcome_id or outcome_id not in contract["application_actions"][application_action_id]["outcomes"]:
        return
    possible = {
        _emit_domain_event_id(emit)
        for emit in contract["application_actions"][application_action_id]["outcomes"][outcome_id].get("emits", [])
    }
    unexpected = sorted(emitted - possible)
    if unexpected:
        raise ContractError(f"Test case {test_case_id} asserts domain events not emitted by {application_action_id}.{outcome_id}: {unexpected}")
    contradicted = sorted(not_emitted & possible)
    if contradicted:
        raise ContractError(f"Test case {test_case_id} asserts not_emitted domain events emitted by {application_action_id}.{outcome_id}: {contradicted}")


def _validate_test_case_invocations(contract: dict[str, Any], test_case_id: str, test_case: dict[str, Any]) -> None:
    invoked = set(test_case["then"].get("invoked", []))
    if not invoked:
        return
    when_kind, when_body = _one(test_case["when"], f"test case {test_case_id} when")
    direct = _test_case_application_action_ref(contract, when_kind, when_body)
    expected = {direct} if direct else set()
    if when_kind == "emit_domain_event":
        event_id = when_body["ref"]
        for workflow in contract["workflows"].values():
            if workflow["trigger"] == {"domain_event": event_id}:
                expected.update(step["application_action"] for step in workflow["steps"])
    unexpected = sorted(invoked - expected)
    if unexpected:
        raise ContractError(f"Test case {test_case_id} asserts action bindings unrelated to when: {unexpected}")


def _workflow_can_run_from_test_case(contract: dict[str, Any], test_case: dict[str, Any]) -> bool:
    workflow_assertion = test_case["then"].get("workflow") or {}
    workflow_id = workflow_assertion.get("ref")
    if not workflow_id or workflow_id not in contract["workflows"]:
        return False
    workflow = contract["workflows"][workflow_id]
    when_kind, when_body = _one(test_case["when"], "test case when")
    trigger_kind, trigger_ref = _one(workflow["trigger"], f"workflow {workflow_id} trigger")
    if when_kind == "emit_domain_event" and trigger_kind == "domain_event":
        return when_body["ref"] == trigger_ref
    application_action_id = _test_case_application_action_ref(contract, when_kind, when_body)
    return trigger_kind == "application_action" and application_action_id == trigger_ref


def _validate_test_case_outcome(contract: dict[str, Any], test_case_id: str, test_case: dict[str, Any]) -> None:
    when_kind, when_body = _one(test_case["when"], f"test case {test_case_id} when")
    then = test_case["then"]
    outcome_id = then.get("outcome")
    cap: dict[str, Any] | None = None
    entry: dict[str, Any] | None = None
    if when_kind == "invoke_application_action":
        cap = contract["application_actions"][when_body["ref"]]
    elif when_kind == "call_entry_point":
        entry = contract["entry_points"][when_body["ref"]]
        target_ref = _entry_point_effective_application_action_ref(contract, when_body["ref"])
        if target_ref:
            cap = contract["application_actions"][target_ref]
    if cap is None:
        if outcome_id:
            raise ContractError(f"Test case {test_case_id} asserts outcome but does not execute an application action")
        return
    if not outcome_id:
        raise ContractError(f"Test case {test_case_id} must assert an application action outcome")
    if outcome_id not in cap["outcomes"]:
        raise ContractError(f"Test case {test_case_id} asserts unknown outcome {outcome_id}")
    if entry is None:
        return
    if outcome_id not in _entry_point_named_response_outcomes(contract, when_body["ref"]):
        raise ContractError(f"Test case {test_case_id} outcome {outcome_id} is not mapped by entry point {when_body['ref']}")
    response_assertion = then.get("response")
    if response_assertion:
        response = _entry_point_test_response_projection(entry, outcome_id)
        for key in ("status", "exit_code"):
            if key in response_assertion and response.get(key) != response_assertion[key]:
                raise ContractError(f"Test case {test_case_id} response.{key} does not match entry point response for outcome {outcome_id}")


def _entry_point_test_response_projection(entry: dict[str, Any], outcome_id: str) -> dict[str, Any]:
    responses = entry_point_responses(entry)
    if outcome_id in responses:
        return responses[outcome_id]
    handlers = entry_point_response_handlers(entry)
    if outcome_id in handlers:
        return handlers[outcome_id]
    return {}


def _validate_test_case_archetype(test_case_id: str, test_case: dict[str, Any]) -> None:
    archetype = test_case["archetype"]
    when_kind, _ = _one(test_case["when"], f"test case {test_case_id} when")
    then = test_case["then"]
    if archetype == "empty_collection_state_machine":
        if when_kind != "open_entry_point" or then.get("state_machine", {}).get("view_state") != "empty":
            raise ContractError(f"Test case {test_case_id} empty_collection_state_machine requires open_entry_point and state_machine.view_state=empty")
    elif archetype == "ready_collection_state_machine":
        if when_kind != "open_entry_point" or then.get("state_machine", {}).get("view_state") != "ready":
            raise ContractError(f"Test case {test_case_id} ready_collection_state_machine requires open_entry_point and state_machine.view_state=ready")
    elif archetype == "state_machine_composition_sync":
        state_machine_assert = then.get("state_machine", {})
        if when_kind != "open_entry_point" or not state_machine_assert.get("instances"):
            raise ContractError(f"Test case {test_case_id} state_machine_composition_sync requires open_entry_point and state_machine.instances")
    elif archetype == "state_machine_composition":
        state_machine_assert = then.get("state_machine", {})
        if when_kind != "open_entry_point" or not state_machine_assert.get("instances"):
            raise ContractError(f"Test case {test_case_id} state_machine_composition requires open_entry_point and state_machine.instances")
    elif archetype == "action_outcome":
        if when_kind != "invoke_application_action" or "outcome" not in then:
            raise ContractError(f"Test case {test_case_id} action_outcome requires invoke_application_action and outcome")
    elif archetype == "entry_point_response":
        if when_kind != "call_entry_point" or "outcome" not in then or "response" not in then:
            raise ContractError(f"Test case {test_case_id} entry_point_response requires call_entry_point, outcome, and response")
    elif archetype == "workflow_trigger_success":
        workflow = then.get("workflow", {})
        if when_kind != "emit_domain_event" or not workflow.get("executed") or "outcome" not in workflow:
            raise ContractError(f"Test case {test_case_id} workflow_trigger_success requires emit_domain_event, workflow.executed=true, and workflow.outcome")
    elif archetype == "authorization_denial":
        if not then.get("authorization", {}).get("denied"):
            raise ContractError(f"Test case {test_case_id} authorization_denial requires authorization.denied")


def _expand_test_case_fact_uses(contract: dict[str, Any]) -> set[str]:
    used: set[str] = set()
    for test_case_id, test_case in contract["test_cases"].items():
        used.update(_expand_fact_uses(
            contract,
            test_case["given"],
            "domain_facts",
            f"Test case {test_case_id}",
        ))
        used.update(_expand_fact_uses(
            contract,
            test_case["then"],
            "expected_facts",
            f"Test case {test_case_id}",
        ))
    for case_id, case in audit_cases(contract).items():
        case_uses: set[str] = set()
        for fact_use in case.get("fact_refs", []):
            fact_id = fact_use["ref"]
            if fact_id not in contract["facts"]:
                raise ContractError(f"Render audit case {case_id} references unknown fact {fact_id}")
            if fact_id in case_uses:
                raise ContractError(f"Render audit case {case_id} uses fact {fact_id} more than once")
            case_uses.add(fact_id)
            used.add(fact_id)
    return used


def _expand_fact_uses(contract: dict[str, Any], owner: dict[str, Any], field: str, label: str) -> set[str]:
    if field not in owner:
        return set()
    expanded: list[dict[str, Any]] = []
    used: set[str] = set()
    for fact in owner[field]:
        if "ref" not in fact:
            expanded.append(fact)
            continue
        fact_id = fact["ref"]
        if fact_id not in contract["facts"]:
            raise ContractError(f"{label} references unknown fact {fact_id}")
        if fact_id in used:
            raise ContractError(f"{label} uses fact {fact_id} more than once")
        used.add(fact_id)
        expanded.append(_fact_body(contract["facts"][fact_id], fact_id))
    owner[field] = expanded
    return used


def _fact_body(fact: dict[str, Any], label: str) -> dict[str, Any]:
    kind, body = _one_fact(fact, f"Fact {label}")
    return {kind: copy.deepcopy(body)}


def _validate_facts_are_used(contract: dict[str, Any], used: set[str]) -> None:
    unused = sorted(set(contract["facts"]) - used)
    if unused:
        raise ContractError("Unused facts: " + ", ".join(unused))


def _expand_test_cases(contract: dict[str, Any]) -> None:
    for test_case in contract["test_cases"].values():
        assertions = test_case["then"]
        if "state_machine" in assertions:
            state_machine_assertion = assertions["state_machine"]
            state_machine_id = state_machine_assertion["ref"]
            state_machine = contract["state_machines"][state_machine_id]
            if "instances" in state_machine_assertion:
                state_name = state_machine_assertion["view_state"]
                parent_state_machine = state_machine
                parent_state = parent_state_machine["view_states"][state_name]
                mounts = {mount["id"]: mount for mount in parent_state.get("child_state_machines", [])}
                required = {
                    "data_loaders": list(parent_state_machine.get("data_loaders", {})),
                    "surfaces": [],
                    "text": [],
                    "assets": [],
                    "action_bindings": [],
                }
                state_machine_assertion["surface"] = parent_state["surface"]
                required["surfaces"].append(parent_state["surface"])
                required["data_loaders"].extend(parent_state.get("data_loaders", {}))
                required["text"].extend(parent_state["text"])
                required["assets"].extend(parent_state["assets"])
                required["action_bindings"].extend(parent_state["action_bindings"])
                for instance_id, expected in state_machine_assertion["instances"].items():
                    mount = mounts[instance_id]
                    mounted_state_machine = contract["state_machines"][mount["state_machine"]]
                    mounted_state = mounted_state_machine["view_states"][expected["view_state"]]
                    expected["surface"] = mounted_state["surface"]
                    expected["source"] = mount["state_machine"]
                    required["data_loaders"].extend(mounted_state_machine.get("data_loaders", {}))
                    required["data_loaders"].extend(mounted_state.get("data_loaders", {}))
                    required["surfaces"].append(mounted_state["surface"])
                    required["text"].extend(mounted_state["text"])
                    required["assets"].extend(mounted_state["assets"])
                    required["action_bindings"].extend(mounted_state["action_bindings"])
                state_machine_assertion["composition"] = {
                    "renderers": parent_state.get("renderers", {}),
                    "child_state_machines": parent_state.get("child_state_machines", []),
                    "signal_sync_rules": parent_state.get("signal_sync_rules", []),
                }
                assertions["requires"] = {key: list(dict.fromkeys(values)) for key, values in required.items()}
            elif "view_state" in state_machine_assertion:
                state_name = state_machine_assertion["view_state"]
                state = state_machine["view_states"][state_name]
                state_machine_assertion["surface"] = state["surface"]
                assertions["requires"] = {
                    "data_loaders": list(state_machine.get("data_loaders", {})) + list(state.get("data_loaders", {})),
                    "surfaces": [state["surface"]],
                    "text": list(state["text"]),
                    "assets": list(state["assets"]),
                    "action_bindings": list(state["action_bindings"]),
                }
        when_kind, when_body = _one(test_case["when"], "test case when")
        cap_id = None
        if when_kind == "invoke_application_action":
            cap_id = when_body["ref"]
        elif when_kind == "call_entry_point":
            cap_id = _entry_point_effective_application_action_ref(contract, when_body["ref"])
        if cap_id:
            assertions.setdefault("authorization", {"allowed": [{"application_action": cap_id}]})
        _expand_authorization_assertions(contract, assertions)


def _expand_authorization_assertions(contract: dict[str, Any], assertions: dict[str, Any]) -> None:
    policy = assertions.get("authorization")
    if not policy:
        return
    for effect in ("allowed", "denied"):
        for assertion in policy.get(effect, []):
            if "authorization_policy" in assertion:
                continue
            kind, ref = _authorization_assertion_target(assertion, f"authorization_policy.{effect}")
            if kind == "application_action":
                authorization = contract["application_actions"][ref].get("authorization")
                if authorization:
                    assertion["authorization_policy"] = authorization["policy"]
            elif kind == "entry_point":
                authorization_policy = contract["entry_points"][ref].get("authorization_policy")
                if authorization_policy:
                    assertion["authorization_policy"] = authorization_policy


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


def _one_fact(mapping: dict[str, Any], label: str) -> tuple[str, Any]:
    items = [(key, mapping[key]) for key in ("absent", "present") if key in mapping]
    if len(items) != 1:
        raise ContractError(f"{label} must contain exactly one fact selector")
    return items[0]


def _require(mapping: dict[str, Any], owner: str, field: str) -> None:
    if field not in mapping:
        raise ContractError(f"Entry {owner} must declare {field}")


def _require_adapter(adapter: dict[str, Any], owner: str, field: str) -> None:
    if field not in adapter:
        raise ContractError(f"Entry point {owner} adapter must declare {field}")


def _path_params(path: str | None) -> set[str]:
    return set(re.findall(r"{([a-z][a-z0-9_]*)}", path or ""))


def _validate_path_params(entry: dict[str, Any], entry_id: str) -> None:
    placeholders = _path_params(entry_point_path(entry))
    declared = set(_entry_input_map(entry, "path_params"))
    if placeholders != declared:
        raise ContractError(
            f"Entry {entry_id} path params {sorted(placeholders)} must exactly match input.path_params {sorted(declared)}"
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
