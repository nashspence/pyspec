from __future__ import annotations

import argparse
import copy
import os
from functools import lru_cache
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

import fastjsonschema

from . import rules
from .layers import LayerError, parse_layers, validate_author_layers
from .io import read_json, read_yaml, write_json, write_yaml
from .layout import (
    renderer_regions,
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
    entry_point_responses,
    entry_point_schedule_expression,
    entry_point_target_pair,
    entry_target_pair,
    entry_workflow_target_source,
)
from .type_expr import (
    TypeExpressionError,
    array_of,
    base_model_name,
    dereference_type,
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
)

ROOT = Path(__file__).resolve().parent


class ContractError(ValueError):
    pass


TypeScope = dict[tuple[str, ...], Any]
TypeScopes = dict[str, TypeScope]


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
    "policy",
    "operation",
    "event",
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
    "policy": "policies",
    "operation": "operations",
    "event": "events",
    "state_machine": "state_machines",
    "entry_point": "entry_points",
    "workflow": "workflows",
    "test_case": "test_cases",
}


REF_KINDS = ["asset", "cli_command", "endpoint", "policy", "query", "route", "screen", "state_machine", "surface", "text", "workflow"]


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
        "policies": {},
        "operations": {},
        "events": {},
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
    "policies",
    "operations",
    "events",
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


def _empty_messages() -> dict[str, dict[str, Any]]:
    return {"accepts": {}, "emits": {}}


def _normalize_messages(messages: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    messages = messages or {}
    normalized: dict[str, dict[str, Any]] = {}
    for direction in ("accepts", "emits"):
        normalized[direction] = {}
        for message_id, message in (messages.get(direction) or {}).items():
            message_spec = copy.deepcopy(message)
            message_spec["payload_schema"] = normalize_type_map(message_spec.get("payload_schema"))
            normalized[direction][message_id] = message_spec
    return {
        "accepts": normalized["accepts"],
        "emits": normalized["emits"],
    }


def _prune_redundant_author_transitions(author: dict[str, Any]) -> None:
    """Let model lifecycles be the source of truth for simple transitions."""
    operations = author.get("operations") or {}
    for model_id, model in (author.get("models") or {}).items():
        lifecycle = model.get("lifecycle") if isinstance(model, dict) else None
        if not lifecycle:
            continue
        field = lifecycle["field"]
        for transition in lifecycle.get("transitions", []):
            operation = operations.get(transition["triggered_by"])
            if not isinstance(operation, dict):
                continue
            declared = operation.get("transition")
            if declared == {"model": model_id, "field": field, "from": transition["from"], "to": transition["to"]}:
                operation.pop("transition", None)


def _prune_empty_author_state_machine_message_directions(author: dict[str, Any]) -> None:
    for state_machine in (author.get("state_machines") or {}).values():
        messages = state_machine.get("messages")
        if not isinstance(messages, dict):
            continue
        for direction in ("accepts", "emits"):
            for message in (messages.get(direction) or {}).values():
                if isinstance(message, dict) and message.get("payload_schema") == {}:
                    message.pop("payload_schema")
            if messages.get(direction) == {}:
                messages.pop(direction)
        if not messages:
            state_machine.pop("messages", None)


def author_from_source(source: dict[str, Any], layers: set[str] | None = None) -> dict[str, Any]:
    validate_against_schema(source, "author.schema.json")
    try:
        validate_author_layers(source, layers)
    except LayerError as exc:
        raise ContractError(str(exc)) from exc
    author = _prune_empty_author_sections(copy.deepcopy(source))
    _prune_redundant_author_transitions(author)
    _prune_empty_author_state_machine_message_directions(author)
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

    _derive_operation_transitions(contract)
    _derive_policies(contract)
    contract["events"] = _derive_events(contract)
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
        spec.setdefault("data_dependencies", [])
        spec["messages"] = _normalize_messages(spec.get("messages"))
        spec.setdefault("transitions", [])
    elif entity == "operation":
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
        if "fixtures" in spec:
            item["fixtures"] = spec["fixtures"]
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

    if entity == "operation":
        authorization_policy = copy.deepcopy(spec.get("authorization_policy", {"policy": rules.policy_ref(spec["id"])}))
        outcomes = {}
        for outcome_id, outcome in spec["outcomes"].items():
            normalized_outcome = copy.deepcopy(outcome)
            normalized_outcome["result"] = normalize_type_expr(normalized_outcome["result"])
            normalized_outcome.setdefault("emits", [])
            outcomes[outcome_id] = normalized_outcome
        operation: dict[str, Any] = {
            "operation_kind": spec["operation_kind"],
            "input": normalize_type_map(spec.get("input", {})),
            "outcomes": outcomes,
            "reads": list(spec.get("reads", [])),
            "creates": list(spec.get("creates", [])),
            "updates": list(spec.get("updates", [])),
            "deletes": list(spec.get("deletes", [])),
            "authorization_policy": authorization_policy,
            "rationale": spec["rationale"],
        }
        for field in ["transition"]:
            if field in spec:
                operation[field] = spec[field]
        return operation

    if entity == "policy":
        return {
            "subjects": copy.deepcopy(spec["subjects"]),
            "targets": copy.deepcopy(spec["targets"]),
            "effect": spec["effect"],
            "conditions": copy.deepcopy(spec.get("conditions", [])),
            "rationale": spec["rationale"],
        }

    if entity == "event":
        return {
            "payload_schema": normalize_type_expr(spec["payload_schema"]),
            "emitted_by": [],
            "rationale": spec["rationale"],
        }

    if entity == "state_machine":
        state_machine_id = spec["id"]
        state_machine: dict[str, Any] = {
            "model": spec["model"],
            "context": spec["context"],
            "data_dependencies": _compile_data_dependencies(state_machine_id, spec.get("data_dependencies", [])),
            "messages": _normalize_messages(spec.get("messages")),
            "initial_view_state": spec["initial_view_state"],
            "view_states": _compile_view_states(state_machine_id, spec.get("view_states", {})),
            "transitions": spec.get("transitions", []),
            "rationale": spec["rationale"],
        }
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
        adapter_kind, _ = entry_point_adapter_pair(entry)
        target_kind, target = entry_point_target_pair(entry)
        if adapter_kind == "ui" and target_kind == "state_machine":
            entry["route"] = rules.route_ref(target["ref"])
        elif adapter_kind == "http" and target_kind == "operation":
            entry["endpoint"] = rules.endpoint_ref(target["ref"])
            if target["ref"] in contract["operations"]:
                entry.setdefault("authorization_policy", copy.deepcopy(contract["operations"][target["ref"]]["authorization_policy"]))
        elif adapter_kind == "cli":
            entry["cli_command_ref"] = rules.cli_command_ref(target["ref"])
            if target_kind == "operation" and target["ref"] in contract["operations"]:
                entry.setdefault("authorization_policy", copy.deepcopy(contract["operations"][target["ref"]]["authorization_policy"]))
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


def _compile_data_dependencies(owner_id: str, operation_ids: list[str]) -> list[dict[str, str]]:
    subject = _ref_subject(owner_id)
    data = []
    for cap_id in operation_ids:
        qref = rules.query_ref(subject, cap_id, many=len(operation_ids) > 1)
        data.append({"query": qref, "operation": cap_id})
    return data


def _compile_view_states(owner_id: str, states: dict[str, Any]) -> dict[str, Any]:
    subject = _ref_subject(owner_id)
    compiled = {}
    for state_name, state in states.items():
        item = {
            "surface": _state_surface_ref(owner_id, state_name),
            "data_dependencies": _compile_data_dependencies(owner_id, state.get("data_dependencies", [])),
            "text": [rules.text_ref(subject, state_name, slot) for slot in state.get("text_slots", [])],
            "assets": [rules.asset_ref(subject, state_name, slot) for slot in state.get("asset_slots", [])],
            "fields": state.get("field_slots", []),
            "available_operations": state.get("available_operations", []),
        }
        if "renderers" in state:
            item["renderers"] = state["renderers"]
        for field in ["child_state_machines", "message_sync_rules"]:
            if field in state:
                item[field] = state[field]
        if state.get("audit"):
            item["audit"] = {
                case_name: _compile_audit_case(owner_id, state_name, case_name, case)
                for case_name, case in state["audit"].items()
            }
        compiled[state_name] = item
    return compiled


def _compile_audit_case(state_machine_id: str, state_name: str, case_name: str, case: dict[str, Any]) -> dict[str, Any]:
    item = {
        "fixtures": case["fixtures"],
        "rationale": case.get("rationale", _default_rationale("audit_case", f"{state_machine_id}.{state_name}.{case_name}")),
    }
    for field in ["context", "facts", "instances"]:
        if field in case:
            item[field] = case[field]
    return item


def audit_cases(contract: dict[str, Any]) -> dict[str, dict[str, Any]]:
    cases: dict[str, dict[str, Any]] = {}
    for state_machine_id, state_machine in sorted(contract.get("state_machines", {}).items()):
        for state_name, state in sorted(state_machine.get("view_states", {}).items()):
            for case_name, case in sorted((state.get("audit") or {}).items()):
                case_id = f"{state_machine_id}.{state_name}.{case_name}.audit"
                cases[case_id] = {"state_machine": state_machine_id, "view_state": state_name, "name": case_name, **case}
    return cases


def _derive_operation_transitions(contract: dict[str, Any]) -> None:
    """Derive transition operation details from model lifecycle declarations.

    Authored sources should not have to repeat the same state transition in both
    the model lifecycle and the operation. The compiled contract remains
    explicit for downstream projections and validators.
    """
    by_operation: dict[str, dict[str, Any]] = {}
    for model_id, model in contract.get("models", {}).items():
        lifecycle = model.get("lifecycle")
        if not lifecycle:
            continue
        field = lifecycle["field"]
        for transition in lifecycle.get("transitions", []):
            operation_id = transition["triggered_by"]
            if operation_id in by_operation:
                raise ContractError(f"Operation {operation_id} is used by multiple lifecycle transitions")
            by_operation[operation_id] = {
                "model": model_id,
                "field": field,
                "from": transition["from"],
                "to": transition["to"],
            }

    for operation_id, operation in contract.get("operations", {}).items():
        if operation.get("operation_kind") != "transition" or "transition" in operation:
            continue
        derived = by_operation.get(operation_id)
        if not derived:
            continue
        operation["transition"] = derived


def _derive_policies(contract: dict[str, Any]) -> None:
    for operation_id, operation in sorted(contract["operations"].items()):
        policy_id = operation["authorization_policy"]["policy"]
        contract["policies"].setdefault(policy_id, _default_operation_policy(operation_id, operation))


def _default_operation_policy(operation_id: str, operation: dict[str, Any]) -> dict[str, Any]:
    targets = [{"operation": operation_id}, *_operation_policy_targets(operation_id, operation)]
    conditions: list[dict[str, Any]] = []
    transition = operation.get("transition")
    if transition:
        conditions.append({
            "resource_state": {
                "model": transition["model"],
                "field": transition["field"],
                "equals": transition["from"],
            }
        })
    return {
        "subjects": [_operation_policy_subject(operation)],
        "targets": targets,
        "effect": "allow",
        "conditions": conditions or [{"always": True}],
        "rationale": operation["rationale"],
    }


def _operation_policy_subject(operation: dict[str, Any]) -> dict[str, Any]:
    for field in sorted(operation.get("input", {})):
        if field.endswith("_by"):
            return {"kind": "actor", "source": f"$input.{field}"}
    return {"kind": "actor"}


def _operation_policy_targets(operation_id: str, operation: dict[str, Any]) -> list[dict[str, str]]:
    models: list[str] = []
    transition = operation.get("transition")
    if transition:
        models.append(transition["model"])
    for field in ("reads", "creates", "updates", "deletes"):
        models.extend(operation.get(field, []))
    unique_models = list(dict.fromkeys(models))
    if unique_models:
        return [{"model": model_id} for model_id in unique_models]
    return []


def _derive_events(contract: dict[str, Any]) -> dict[str, Any]:
    events: dict[str, Any] = copy.deepcopy(contract.get("events", {}))
    for operation_id, operation in sorted(contract["operations"].items()):
        for outcome_id, outcome in sorted(operation["outcomes"].items()):
            for emit in outcome.get("emits", []):
                event_id = _emit_event_id(emit)
                if outcome["kind"] != "success":
                    raise ContractError(f"Operation {operation_id} failure outcome {outcome_id} must not emit events")
                payload_type = events.get(event_id, {}).get("payload_schema", outcome["result"])
                event = events.setdefault(event_id, {
                    "emitted_by": [],
                    "payload_schema": payload_type,
                    "rationale": operation["rationale"],
                })
                _validate_emit_payload_mapping(contract, operation_id, operation, outcome_id, outcome, event_id, event["payload_schema"], emit)
                event["emitted_by"].append(operation_id)
    return events


def _emit_event_id(emit: Any) -> str:
    if isinstance(emit, str):
        return emit
    return emit["event"]


def _derive_refs(contract: dict[str, Any]) -> dict[str, list[str]]:
    refs: dict[str, set[str]] = {kind: set() for kind in REF_KINDS}
    refs["policy"].update(contract.get("policies", {}))
    refs["text"].update(contract.get("text_resources", {}))
    refs["asset"].update(contract.get("assets", {}))
    for state_machine_id in contract["state_machines"]:
        refs["state_machine"].add(state_machine_id)
    for owner in contract["state_machines"].values():
        for datum in owner.get("data_dependencies", []):
            refs["query"].add(datum["query"])
        for state in owner.get("view_states", {}).values():
            for datum in state.get("data_dependencies", []):
                refs["query"].add(datum["query"])
            refs["surface"].add(state["surface"])
            refs["text"].update(state["text"])
            refs["asset"].update(state["assets"])
    for entry in contract["entry_points"].values():
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
    _validate_operations(contract)
    _validate_state_machines(contract)
    _validate_state_machine_message_payload_consistency(contract)
    _validate_entries(contract)
    _validate_policies(contract)
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
        for fixture_id in case.get("fixtures", []):
            if fixture_id not in contract["fixtures"]:
                raise ContractError(f"Content case {case_id} references unknown fixture {fixture_id}")
        fixture_values = _fixture_namespace(contract, case.get("fixtures", []), f"content case {case_id}")
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
        if not _view_state_renderers(state):
            raise ContractError(f"Audit case {case_id} references view state {state_machine_id}.{state_name} with no visual renderer")
        for fixture_id in case.get("fixtures", []):
            if fixture_id not in contract["fixtures"]:
                raise ContractError(f"Audit case {case_id} references unknown fixture {fixture_id}")
        fixture_values = _fixture_namespace(contract, case.get("fixtures", []), f"audit case {case_id}")
        _validate_fixture_templates(case, fixture_values, f"audit case {case_id}")
        for fact_use in case.get("facts", []):
            fact_id = fact_use["ref"]
            _validate_fixture_templates(contract["facts"][fact_id], fixture_values, f"audit case {case_id} fact {fact_id}")
        if state.get("fields") and not _setup_has_model(contract, case.get("fixtures", []), case.get("facts", []), state_machine["model"]):
            raise ContractError(f"Audit case {case_id} renders fields for {state_machine_id}.{state_name} but does not include a {state_machine['model']} fixture or fact")
        if state.get("child_state_machines"):
            mounted_instances = {mount["id"]: mount for mount in state["child_state_machines"]}
            expected_instances = case.get("instances")
            if not expected_instances:
                raise ContractError(f"Audit case {case_id} for composed state machine state {state_machine_id}.{state_name} must declare instances")
            if set(expected_instances) != set(mounted_instances):
                raise ContractError(f"Audit case {case_id} instance state vector must exactly cover mounted state machine instances")
            for instance_id, expected in expected_instances.items():
                child_state_machine_id = mounted_instances[instance_id]["state_machine"]
                if expected["view_state"] not in contract["state_machines"][child_state_machine_id]["view_states"]:
                    raise ContractError(f"Audit case {case_id} references unknown state machine view state {child_state_machine_id}.{expected['view_state']}")
                selected_state = contract["state_machines"][child_state_machine_id]["view_states"][expected["view_state"]]
                if selected_state.get("fields") and not _setup_has_model(contract, case.get("fixtures", []), case.get("facts", []), contract["state_machines"][child_state_machine_id]["model"]):
                    raise ContractError(f"Audit case {case_id} renders fields for {child_state_machine_id}.{expected['view_state']} but does not include a {contract['state_machines'][child_state_machine_id]['model']} fixture or fact")
            covered_composable_states.add((state_machine_id, state_name))
    missing_composed = sorted(f"{state_machine_id}.{state_name}" for state_machine_id, state_name in composable_states - covered_composable_states)
    if missing_composed:
        raise ContractError("Missing audit coverage for composed state machine states: " + ", ".join(missing_composed))
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
        for state_name, state in state_machine.get("view_states", {}).items():
            if state.get("fields") and not _setup_has_model(contract, list(contract.get("fixtures", {})), _all_fact_uses(contract), state_machine["model"]):
                raise ContractError(f"Rendered fields for {state_machine_id}.{state_name} require at least one {state_machine['model']} fixture or fact")


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
            if transition["triggered_by"] not in contract["operations"]:
                raise ContractError(
                    f"Model {rid} lifecycle transition references unknown operation {transition['triggered_by']}"
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
    for operation_id, operation in contract.get("operations", {}).items():
        for field_name, type_expr in operation.get("input", {}).items():
            _validate_type_reference(contract, f"Operation {operation_id} input {field_name}", type_expr)
        for outcome_id, outcome in operation.get("outcomes", {}).items():
            _validate_type_reference(contract, f"Operation {operation_id} outcome {outcome_id}", outcome["result"])
    for event_id, event in contract.get("events", {}).items():
        _validate_type_reference(contract, f"Event {event_id} payload_schema", event["payload_schema"])


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
    if kind in {"array", "map", "nullable", "optional"}:
        _validate_type_reference(contract, label, value)
        return
    if kind == "object":
        for field_name, field in normalize_field_map(value.get("fields", value)).items():
            _validate_type_reference(contract, f"{label}.{field_name}", field["type"])


def _validate_operations(contract: dict[str, Any]) -> None:
    models = contract["models"]
    operations = contract["operations"]
    for cid, cap in operations.items():
        _validate_operation_relationships(cid, cap, models)
        transition = cap.get("transition")
        if transition:
            model_id = transition["model"]
            lifecycle = models[model_id].get("lifecycle")
            if not lifecycle:
                raise ContractError(f"Operation {cid} declares transition but {model_id} has no lifecycle")
            if transition["field"] != lifecycle["field"]:
                raise ContractError(f"Operation {cid} transition field does not match model lifecycle")
            if transition["from"] not in lifecycle["states"] or transition["to"] not in lifecycle["states"]:
                raise ContractError(f"Operation {cid} transition references unknown lifecycle state")
    for rid, model in models.items():
        lifecycle = model.get("lifecycle")
        if not lifecycle:
            continue
        for transition in lifecycle.get("transitions", []):
            triggered_by = transition["triggered_by"]
            operation = operations[triggered_by]
            if operation["operation_kind"] != "transition":
                raise ContractError(
                    f"Model {rid} lifecycle transition {triggered_by} must reference a transition operation"
                )
            cap_transition = operation.get("transition")
            if (
                not cap_transition
                or cap_transition["model"] != rid
                or cap_transition["from"] != transition["from"]
                or cap_transition["to"] != transition["to"]
            ):
                raise ContractError(f"Model {rid} lifecycle and operation {triggered_by} disagree")
    for event_id, event in contract["events"].items():
        for cap_id in event["emitted_by"]:
            if cap_id not in operations:
                raise ContractError(f"Event {event_id} emitted by unknown operation {cap_id}")


def _validate_operation_relationships(cid: str, cap: dict[str, Any], models: dict[str, Any]) -> None:
    _validate_operation_outcomes(cid, cap)
    for field in ["creates", "reads", "updates", "deletes"]:
        for model_id in cap.get(field, []):
            if model_id not in models:
                raise ContractError(f"Operation {cid} {field} unknown model {model_id}")

    if "transition" in cap:
        model_id = cap["transition"]["model"]
        if model_id not in models:
            raise ContractError(f"Operation {cid} transition references unknown model {model_id}")

    operation_kind = cap["operation_kind"]
    if operation_kind == "query":
        _require_relationship(cid, cap, "reads")
        _reject_non_empty_relationships(cid, cap, {"creates", "updates", "deletes"})
        if "transition" in cap:
            raise ContractError(f"Query operation {cid} must not declare transition")
        _validate_query_success_result(cid, cap)
    elif operation_kind == "command":
        if "transition" in cap:
            raise ContractError(f"Only transition operations may declare transition: {cid}")
    elif operation_kind == "transition":
        if "transition" not in cap:
            raise ContractError(f"Transition operation {cid} must declare transition")
        _reject_non_empty_relationships(cid, cap, {"creates", "reads", "updates", "deletes"})
        _require_output_model(cid, cap, cap["transition"]["model"])
    else:  # pragma: no cover - schema prevents this.
        raise ContractError(f"Unsupported operation_kind {operation_kind}: {cid}")


def _require_relationship(cid: str, cap: dict[str, Any], field: str) -> None:
    if not cap.get(field):
        raise ContractError(f"Operation {cid} operation_kind {cap['operation_kind']} must declare {field}")


def _require_exact_relationship(cid: str, cap: dict[str, Any], field: str, count: int) -> None:
    _require_relationship(cid, cap, field)
    actual = len(cap[field])
    if actual != count:
        raise ContractError(f"Operation {cid} operation_kind {cap['operation_kind']} must declare exactly {count} {field}")


def _reject_non_empty_relationships(cid: str, cap: dict[str, Any], fields: set[str]) -> None:
    extras = sorted(field for field in fields if cap.get(field))
    if extras:
        raise ContractError(f"Operation {cid} operation_kind {cap['operation_kind']} does not support effects: {extras}")


def _require_output_model(cid: str, cap: dict[str, Any], model_id: str) -> None:
    if model_name(_success_result_type(cap)) != model_id:
        raise ContractError(f"Operation {cid} success outcome result must be {model_id}")


def _validate_query_success_result(cid: str, cap: dict[str, Any]) -> None:
    reads = cap.get("reads", [])
    if len(reads) != 1:
        return
    expected_model = reads[0]
    result_type = _success_result_type(cap)
    if model_name(result_type) == expected_model or is_array_of_model(result_type, expected_model):
        return
    raise ContractError(
        f"Operation {cid} query success outcome result must be {expected_model} "
        f"or {type_display(array_of({'model': expected_model}))}"
    )


def _validate_operation_outcomes(cid: str, cap: dict[str, Any]) -> None:
    outcomes = cap["outcomes"]
    successes = _success_outcomes(cap)
    failures = _failure_outcomes(cap)
    if len(successes) != 1:
        raise ContractError(f"Operation {cid} must declare exactly one success outcome")
    if not failures:
        raise ContractError(f"Operation {cid} must declare at least one failure outcome")
    unknown_kinds = sorted(
        f"{name}:{outcome['kind']}" for name, outcome in outcomes.items() if outcome["kind"] not in {"success", "failure"}
    )
    if unknown_kinds:
        raise ContractError(f"Operation {cid} has unsupported outcome kinds: {unknown_kinds}")
    for outcome_id, outcome in outcomes.items():
        emits = outcome.get("emits", [])
        emit_ids = [_emit_event_id(emit) for emit in emits]
        if len(emit_ids) != len(set(emit_ids)):
            raise ContractError(f"Operation {cid} outcome {outcome_id} emits duplicate events")
        if outcome["kind"] == "failure":
            if emits:
                raise ContractError(f"Operation {cid} failure outcome {outcome_id} must not emit events")
            if not is_problem_type(outcome["result"]):
                raise ContractError(f"Operation {cid} failure outcome {outcome_id} result must be Problem or a *Problem type")


def _validate_policies(contract: dict[str, Any]) -> None:
    policies = contract["policies"]
    operations = contract["operations"]
    entry_points = contract["entry_points"]
    for operation_id, operation in operations.items():
        policy_id = operation["authorization_policy"]["policy"]
        if policy_id not in policies:
            raise ContractError(f"Operation {operation_id} references unknown policy {policy_id}")
        if not _policy_covers_target(policies[policy_id], "operation", operation_id):
            raise ContractError(f"Operation {operation_id} authorization_policy {policy_id} must cover operation target")
    for entry_id, entry in entry_points.items():
        authorization_policy = entry.get("authorization_policy")
        if not authorization_policy:
            continue
        policy_id = authorization_policy["policy"]
        if policy_id not in policies:
            raise ContractError(f"Entry point {entry_id} references unknown policy {policy_id}")
        target_kind, target_ref = entry_target_pair(entry)
        if not _policy_covers_target(policies[policy_id], "entry_point", entry_id) and not _policy_covers_target(policies[policy_id], target_kind, target_ref):
            raise ContractError(f"Entry point {entry_id} authorization_policy {policy_id} must cover entry point or invoked target")
    for policy_id, policy in policies.items():
        for target in policy["targets"]:
            kind, ref = _one(target, f"Policy {policy_id} target")
            if kind == "model" and ref not in contract["models"]:
                raise ContractError(f"Policy {policy_id} target references unknown model {ref}")
            if kind == "operation" and ref not in operations:
                raise ContractError(f"Policy {policy_id} target references unknown operation {ref}")
            if kind == "entry_point" and ref not in entry_points:
                raise ContractError(f"Policy {policy_id} target references unknown entry point {ref}")
        for condition in policy.get("conditions", []):
            kind, body = _one(condition, f"Policy {policy_id} condition")
            if kind in {"always", "input_present", "subject_role"}:
                continue
            if kind in {"resource_exists", "resource_state"}:
                model_id = body["model"]
                if model_id not in contract["models"]:
                    raise ContractError(f"Policy {policy_id} condition references unknown model {model_id}")
                if kind == "resource_state" and body["field"] not in contract["models"][model_id]["fields"]:
                    raise ContractError(f"Policy {policy_id} condition references unknown {model_id} field {body['field']}")
                continue
            raise ContractError(f"Policy {policy_id} condition is unsupported: {kind}")


def _policy_covers_target(policy: dict[str, Any], kind: str, ref: str) -> bool:
    return any(target == {kind: ref} for target in policy.get("targets", []))


def _policy_assertion_target(assertion: dict[str, Any], label: str) -> tuple[str, str]:
    items = [(key, assertion[key]) for key in ("operation", "entry_point") if key in assertion]
    if len(items) != 1:
        raise ContractError(f"{label} must contain exactly one policy target")
    return items[0]


def _validate_emit_payload_mapping(
    contract: dict[str, Any],
    operation_id: str,
    operation: dict[str, Any],
    outcome_id: str,
    outcome: dict[str, Any],
    event_id: str,
    event_payload: Any,
    emit: Any,
) -> None:
    label = f"Operation {operation_id} outcome {outcome_id} emit {event_id}"
    source_scopes: TypeScopes = {
        "input": _type_scope(operation["input"]),
        "outcome": _typed_source_paths(contract, ("result",), outcome["result"]),
    }

    if isinstance(emit, str):
        if not type_equals(event_payload, outcome["result"]):
            raise ContractError(
                f"{label} must declare payload mapping because event payload is "
                f"{type_display(event_payload)}, not {type_display(outcome['result'])}"
            )
        return

    has_payload = "payload" in emit
    has_payload_bindings = "payload_bindings" in emit
    if has_payload == has_payload_bindings:
        raise ContractError(f"{label} must declare exactly one of payload or payload_bindings")
    if has_payload:
        source = emit["payload"]
        actual = _reference_expression_type(contract, f"{label} payload source", source, source_scopes)
        if not type_equals(actual, event_payload):
            raise ContractError(f"{label} payload source {source} type must be {type_display(event_payload)}, got {type_display(actual)}")
        return

    _validate_mapping_to_type(contract, label, emit["payload_bindings"], event_payload, source_scopes)


def _validate_state_machines(contract: dict[str, Any]) -> None:
    for state_machine_id, state_machine in contract["state_machines"].items():
        if not state_machine_id.startswith("state_machine."):
            raise ContractError(f"state machine id must start with state_machine.: {state_machine_id}")
        if state_machine["model"] not in contract["models"]:
            raise ContractError(f"state machine {state_machine_id} references unknown model {state_machine['model']}")
        _validate_data_bindings(
            contract, f"state machine {state_machine_id}", state_machine.get("data_dependencies", []), state_machine.get("context", {}), model=state_machine["model"]
        )
        if state_machine["initial_view_state"] not in state_machine["view_states"]:
            raise ContractError(f"state machine {state_machine_id} initial view state is not declared: {state_machine['initial_view_state']}")
        model_fields = set(contract["models"][state_machine["model"]]["fields"])
        for state_name, state in state_machine["view_states"].items():
            _validate_state_machine_view_state(
                contract,
                f"state machine {state_machine_id}",
                state_name,
                state,
                field_names=model_fields,
                data_context=state_machine.get("context", {}),
                model=state_machine["model"],
            )
            if state.get("child_state_machines") or state.get("renderers") or state.get("message_sync_rules"):
                _validate_state_composition(contract, state_machine_id, state_machine, state_name, state)
        _validate_field_state_data_sources(f"state machine {state_machine_id}", state_machine["view_states"], state_machine.get("data_dependencies", []), state_machine.get("transitions", []))
        _validate_state_machine_transitions(contract, state_machine_id, state_machine)
        _validate_messages(state_machine_id, state_machine)


def _validate_state_machine_view_state(
    contract: dict[str, Any],
    owner_label: str,
    state_name: str,
    state: dict[str, Any],
    field_names: set[str],
    data_context: dict[str, Any] | None = None,
    model: str | None = None,
) -> None:
    _validate_data_bindings(contract, f"{owner_label}.{state_name}", state.get("data_dependencies", []), data_context, model=model)
    for field in state.get("fields", []):
        if field not in field_names:
            raise ContractError(f"{owner_label}.{state_name} field slot is not declared on the model/context: {field}")
    for operation in state["available_operations"]:
        if operation not in contract["operations"]:
            raise ContractError(f"{owner_label}.{state_name} available operation references unknown operation {operation}")
    _validate_presentation(contract, owner_label, field_names, state_name, state)


def _validate_data_bindings(
    contract: dict[str, Any],
    owner_label: str,
    data: list[dict[str, Any]],
    context: dict[str, Any] | None,
    *,
    model: str | None = None,
) -> None:
    context_keys = set((context or {}).keys())
    for datum in data:
        operation_id = datum["operation"]
        if operation_id not in contract["operations"]:
            raise ContractError(f"{owner_label} data references unknown operation {operation_id}")
        operation = contract["operations"][operation_id]
        if operation["operation_kind"] != "query":
            raise ContractError(f"{owner_label} data operation must be query: {operation_id}")
        if model and model not in operation.get("reads", []):
            raise ContractError(f"{owner_label} data operation {operation_id} must read model {model}")
        input_keys = set((operation.get("input") or {}).keys())
        missing = sorted(input_keys - context_keys)
        if missing:
            raise ContractError(
                f"{owner_label} data operation {operation_id} input not provided by context: {missing}"
            )


def _validate_field_state_data_sources(
    owner_label: str,
    states: dict[str, Any],
    owner_data: list[dict[str, Any]],
    transitions: list[dict[str, Any]],
) -> None:
    for state_name, state in states.items():
        if not state.get("fields") or _state_has_data_source(state_name, states, owner_data, transitions):
            continue
        raise ContractError(f"{owner_label}.{state_name} declares field slots without data source")


def _state_has_data_source(
    state_name: str,
    states: dict[str, Any],
    owner_data: list[dict[str, Any]],
    transitions: list[dict[str, Any]],
) -> bool:
    if owner_data or states[state_name].get("data_dependencies"):
        return True
    for transition in transitions:
        if transition["to"] != state_name or not _is_data_event(transition["on"]):
            continue
        source_state = states.get(transition["from"], {})
        if owner_data or source_state.get("data_dependencies"):
            return True
    return False


def _validate_state_machine_transitions(contract: dict[str, Any], state_machine_id: str, state_machine: dict[str, Any]) -> None:
    states = set(state_machine["view_states"])
    for transition in state_machine.get("transitions", []):
        if transition["from"] not in states or transition["to"] not in states:
            raise ContractError(f"state machine {state_machine_id} transition uses unknown state: {transition}")
        if _is_data_event(transition["on"]) and not _transition_data_bindings(state_machine, transition):
            raise ContractError(
                f"state machine {state_machine_id} transition uses data signal without state machine or source-state data: {transition['on']}"
            )
        message_payload = _state_machine_message_payload(state_machine, "accepts", transition["on"], f"state machine {state_machine_id} transition message")
        for effect in transition.get("effects", []):
            kind, body = _one(effect, f"state machine {state_machine_id} transition effect")
            if kind == "set":
                if body["context"] not in state_machine.get("context", {}):
                    raise ContractError(f"state machine {state_machine_id} transition sets undeclared context: {body['context']}")
            elif kind == "emit":
                emitted_payload = _state_machine_message_payload(state_machine, "emits", body["message"], f"state machine {state_machine_id} transition emit")
                _validate_payload_bindings(
                    contract=contract,
                    label=f"state machine {state_machine_id} transition emit {body['message']} payload_bindings",
                    bindings=body["payload_bindings"],
                    payload=emitted_payload,
                    scopes={"message": _type_scope(message_payload), "context": _type_scope(state_machine.get("context", {}))},
                )
            else:  # pragma: no cover - schema prevents this.
                raise ContractError(f"state machine {state_machine_id} unsupported transition effect: {kind}")
    for transition in state_machine.get("transitions", []):
        if not _transition_has_audit_content(state_machine, transition):
            raise ContractError(
                f"state machine {state_machine_id} transition {transition['on']} from {transition['from']} "
                f"to {transition['to']} must declare rationale, data, or effects"
            )


def _validate_messages(state_machine_id: str, state_machine: dict[str, Any]) -> None:
    messages = state_machine.get("messages", _empty_messages())
    declared_accepts = set(messages.get("accepts", {}))
    declared_emits = set(messages.get("emits", {}))
    ambiguous = sorted(declared_accepts & declared_emits)
    if ambiguous:
        raise ContractError(f"state machine {state_machine_id} declares state-machine message as both accepted and emitted: {ambiguous}")
    accepted = _state_machine_accepts(state_machine)
    emitted = _state_machine_emits(state_machine)
    orphan_accepts = sorted(declared_accepts - accepted)
    if orphan_accepts:
        raise ContractError(f"state machine {state_machine_id} declares accepted state-machine message without transition: {orphan_accepts}")
    orphan_emits = sorted(declared_emits - emitted)
    if orphan_emits:
        raise ContractError(f"state machine {state_machine_id} declares emitted state-machine message without emit effect: {orphan_emits}")
    undeclared_accepts = sorted(accepted - declared_accepts)
    if undeclared_accepts:
        raise ContractError(f"state machine {state_machine_id} accepts state-machine message without declaring it: {undeclared_accepts}")
    undeclared_emits = sorted(emitted - declared_emits)
    if undeclared_emits:
        raise ContractError(f"state machine {state_machine_id} emits state-machine message without declaring it: {undeclared_emits}")


def _validate_state_machine_message_payload_consistency(contract: dict[str, Any]) -> None:
    declared: dict[str, tuple[str, str, dict[str, Any]]] = {}
    domain_events = set(contract.get("events", {}))
    for state_machine_id, state_machine in contract.get("state_machines", {}).items():
        messages = state_machine.get("messages", _empty_messages())
        for direction in ("accepts", "emits"):
            for message_id, message in messages.get(direction, {}).items():
                if message_id in domain_events:
                    raise ContractError(f"state-machine message {message_id} conflicts with domain event {message_id}")
                payload = message["payload_schema"]
                existing = declared.get(message_id)
                if existing and (
                    set(existing[2]) != set(payload)
                    or any(not type_equals(existing[2][key], payload[key]) for key in payload)
                ):
                    first_fsm, first_direction, first_payload = existing
                    raise ContractError(
                        f"state-machine message {message_id} payload_schema differs between {first_fsm}.{first_direction} "
                        f"and {state_machine_id}.{direction}: "
                        f"{ {key: type_display(value) for key, value in first_payload.items()} } vs "
                        f"{ {key: type_display(value) for key, value in payload.items()} }"
                    )
                declared[message_id] = (state_machine_id, direction, payload)


def _validate_state_composition(contract: dict[str, Any], state_machine_id: str, state_machine: dict[str, Any], state_name: str, state: dict[str, Any]) -> None:
    label = f"{state_machine_id}.{state_name}"
    parent_state_machine_id = state_machine_id
    parent_state_machine = state_machine
    if not any(renderer.get("layout") for renderer in (state.get("renderers") or {}).values()):
        raise ContractError(f"composed state machine state {label} must declare renderer layout")
    if not state.get("child_state_machines"):
        raise ContractError(f"composed state machine state {label} must mount at least one state machine")
    regions = set(renderer_regions(state))
    if not regions:
        raise ContractError(f"composed state machine state {label} must declare layout regions")
    mounts: dict[str, dict[str, Any]] = {}
    for mount in state["child_state_machines"]:
        if mount["id"] in mounts:
            raise ContractError(f"composed state machine state {label} has duplicate state machine mount: {mount['id']}")
        mounts[mount["id"]] = mount
        if mount["region"] not in regions:
            raise ContractError(f"composed state machine state {label} mounts state machine in undeclared region: {mount['region']}")
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
            _validate_condition_context(label, parent_state_machine.get("context", {}), selected["when"])
        mount_context = mount.get("context_bindings", {})
        expected_context = set(child_state_machine.get("context", {}))
        if set(mount_context) != expected_context:
            raise ContractError(
                f"composed state machine state {label}.{mount['id']} context keys {sorted(mount_context)} "
                f"must exactly match state machine context {sorted(expected_context)}"
            )
        _validate_state_machine_context_refs(
            contract,
            label,
            parent_state_machine.get("context", {}),
            child_state_machine.get("context", {}),
            mount_context,
        )
    used_regions = {mount["region"] for mount in state["child_state_machines"]}
    missing_must_render = [region for region, spec in renderer_regions(state).items() if spec.get("must_render") and region not in used_regions]
    if missing_must_render:
        raise ContractError(f"composed state machine state {label} missing must_render layout regions: {missing_must_render}")
    _validate_renderer_layouts(label, state)
    _validate_sync_rules(contract, parent_state_machine_id, state_name, parent_state_machine, state, mounts)


def _validate_renderer_layouts(state_machine_id: str, state: dict[str, Any]) -> None:
    html_regions = set(renderer_html_regions(state))
    textual_regions = set(renderer_textual_containers(state))
    if html_regions and textual_regions and html_regions != textual_regions:
        raise ContractError(f"composed state machine {state_machine_id} layout regions differ between html and textual")


def _validate_condition_context(state_machine_id: str, context: dict[str, Any], condition: Any) -> None:
    if isinstance(condition, dict):
        if "context_present" in condition:
            keys = [condition["context_present"]]
        elif "context_equals" in condition:
            keys = [condition["context_equals"]["field"]]
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


def _validate_state_machine_context_refs(
    contract: dict[str, Any],
    state_machine_id: str,
    parent_context: dict[str, Any],
    child_context: dict[str, Any],
    mapping: dict[str, Any],
) -> None:
    scopes = {"state_machine": _type_scope(parent_context)}
    for key, value in mapping.items():
        _validate_expression_type(
            contract,
            f"composed state machine {state_machine_id} context {key}",
            value,
            child_context[key],
            scopes,
        )


def _state_machine_emits(state_machine: dict[str, Any]) -> set[str]:
    emits: set[str] = set()
    for transition in state_machine.get("transitions", []):
        for effect in transition.get("effects", []):
            kind, body = _one(effect, "state_machine transition effect")
            if kind == "emit":
                emits.add(body["message"])
    return emits


def _state_machine_accepts(state_machine: dict[str, Any]) -> set[str]:
    return {transition["on"] for transition in state_machine.get("transitions", [])}


def _state_machine_message_payload(state_machine: dict[str, Any], direction: str, message_id: str, label: str) -> dict[str, Any]:
    message = state_machine.get("messages", {}).get(direction, {}).get(message_id)
    if not message:
        raise ContractError(f"{label} references undeclared state-machine message: {message_id}")
    return message.get("payload_schema", {})


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


def _validate_expression_type(
    contract: dict[str, Any] | None,
    label: str,
    expression: Any,
    expected_type: Any,
    scopes: TypeScopes,
) -> None:
    actual_type = _expression_type(contract, expression, scopes, label)
    if actual_type and not type_equals(actual_type, expected_type):
        raise ContractError(f"{label} type mismatch: expected {type_display(expected_type)}, got {type_display(actual_type)}")


def _expression_type(contract: dict[str, Any] | None, expression: Any, scopes: TypeScopes, label: str) -> Any | None:
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


def _is_data_event(message: str) -> bool:
    return message.startswith("data.")


def _transition_data_bindings(state_machine: dict[str, Any], transition: dict[str, Any]) -> list[dict[str, Any]]:
    source_state = state_machine.get("view_states", {}).get(transition["from"], {})
    return source_state.get("data_dependencies", []) or state_machine.get("data_dependencies", [])


def _transition_target_data_bindings(state_machine: dict[str, Any], transition: dict[str, Any]) -> list[dict[str, Any]]:
    target_state = state_machine.get("view_states", {}).get(transition["to"], {})
    return target_state.get("data_dependencies", [])


def _transition_has_audit_content(state_machine: dict[str, Any], transition: dict[str, Any]) -> bool:
    if transition.get("rationale") or transition.get("effects"):
        return True
    if _is_data_event(transition["on"]):
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
    for rule in state.get("message_sync_rules", []):
        if rule["id"] in seen:
            raise ContractError(f"composed state machine state {label} has duplicate sync rule: {rule['id']}")
        seen.add(rule["id"])
        source_id = rule["when"]["instance"]
        if source_id not in mounts:
            raise ContractError(f"composed state machine state {label} sync source instance is unknown: {source_id}")
        source_fsm = contract["state_machines"][mounts[source_id]["state_machine"]]
        message_id = rule["when"]["message"]
        if message_id not in _state_machine_emits(source_fsm):
            raise ContractError(f"composed state machine state {label} sync listens for message the source does not emit: {message_id}")
        source_payload = _state_machine_message_payload(source_fsm, "emits", message_id, f"composed state machine state {label} sync trigger")
        for effect in rule["effects"]:
            kind, body = _one(effect, f"composed state machine state {label} sync effect")
            if kind == "set":
                if body["context"] not in context:
                    raise ContractError(f"composed state machine state {label} sync sets undeclared context: {body['context']}")
                if "from" in body:
                    _validate_expression_type(
                        contract,
                        f"composed state machine state {label} sync set {body['context']}",
                        body["from"],
                        context[body["context"]],
                        {"message": _type_scope(source_payload), "state_machine": _type_scope(context)},
                    )
            elif kind == "send":
                target_id = body["instance"]
                if target_id not in mounts:
                    raise ContractError(f"composed state machine state {label} sync sends to unknown instance: {target_id}")
                target_fsm = contract["state_machines"][mounts[target_id]["state_machine"]]
                if body["message"] not in _state_machine_accepts(target_fsm):
                    raise ContractError(f"composed state machine state {label} sync sends message the target does not accept: {body['message']}")
                target_payload = _state_machine_message_payload(target_fsm, "accepts", body["message"], f"composed state machine state {label} sync send")
                _validate_payload_bindings(
                    contract=contract,
                    label=f"composed state machine state {label} sync send {body['message']} to {target_id} payload_bindings",
                    bindings=body["payload_bindings"],
                    payload=target_payload,
                    scopes={"message": _type_scope(source_payload), "state_machine": _type_scope(context)},
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
    operations = set(state["available_operations"])
    regions = set(renderer_regions(state))
    mounts = {mount["id"] for mount in state.get("child_state_machines", [])}

    html_contract = renderer_html_presentation(state)
    for slot in html_contract.get("slots", []):
        bind_kind, bind_value = _one(slot["binding"], f"{owner_label}.{state_name} html slot binding")
        _validate_slot_binding(owner_label, state_name, "HTML slot", bind_kind, bind_value, text_slots, asset_slots, field_slots, operations)

    for rule in renderer_html_style(state).get("rules", []):
        _validate_renderer_style_selector(
            owner_label,
            state_name,
            rule["selector"],
            text_slots,
            asset_slots,
            field_slots,
            operations,
            regions,
            mounts,
            "html style",
        )

    textual = renderer_textual_presentation(state)
    widgets = textual.get("widgets", [])
    widget_ids = [widget["id"] for widget in widgets]
    if len(widget_ids) != len(set(widget_ids)):
        raise ContractError(f"{owner_label}.{state_name} Textual widgets contain duplicate ids")
    widget_targets = {"text": set(), "asset": set(), "field": set(), "action": set()}
    for widget in widgets:
        bind_kind, bind_value = _one(widget["binding"], f"{owner_label}.{state_name} textual widget binding")
        _validate_slot_binding(owner_label, state_name, "Textual widget", bind_kind, bind_value, text_slots, asset_slots, field_slots, operations)
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
            operations,
            regions,
            mounts,
            "textual style",
        )
        if widgets and selector.startswith("slot."):
            name = selector[len("slot."):]
            if name not in widget_targets["text"] and name not in widget_targets["asset"] and name not in widget_targets["field"]:
                raise ContractError(f"{owner_label}.{state_name} textual style selector has no matching Textual widget: {selector}")
        if widgets and selector.startswith("action."):
            action = selector[len("action."):]
            if action not in widget_targets["action"]:
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
    operations: set[str],
) -> None:
    if bind_kind == "text" and bind_value not in text_slots:
        raise ContractError(f"{owner_label}.{state_name} {label} text binding is not declared: {bind_value}")
    if bind_kind == "asset" and bind_value not in asset_slots:
        raise ContractError(f"{owner_label}.{state_name} {label} asset binding is not declared: {bind_value}")
    if bind_kind == "operation" and bind_value not in operations:
        raise ContractError(f"{owner_label}.{state_name} {label} operation binding is not declared: {bind_value}")
    if bind_kind == "field" and bind_value not in field_slots:
        raise ContractError(f"{owner_label}.{state_name} {label} field binding is not declared: {bind_value}")


def _validate_renderer_style_selector(
    owner_label: str,
    state_name: str,
    selector: str,
    text_slots: set[str],
    asset_slots: set[str],
    field_slots: set[str],
    operations: set[str],
    regions: set[str],
    mounts: set[str],
    label: str,
) -> None:
    if selector.startswith("region.") or selector.startswith("mount."):
        _validate_composition_selector(f"{owner_label}.{state_name}", selector, regions, mounts, label)
        return
    _validate_style_selector(owner_label, state_name, selector, text_slots, asset_slots, field_slots, operations, label)


def _validate_style_selector(
    owner_label: str,
    state_name: str,
    selector: str,
    text_slots: set[str],
    asset_slots: set[str],
    field_slots: set[str],
    operations: set[str],
    label: str,
) -> None:
    if selector in {"root", "screen"}:
        return
    if selector.startswith("slot."):
        name = selector[len("slot."):]
        if name not in text_slots and name not in asset_slots and name not in field_slots:
            raise ContractError(f"{owner_label}.{state_name} {label} selector references undeclared slot: {selector}")
        return
    if selector.startswith("operation."):
        ref = selector[len("operation."):]
        if ref not in operations:
            raise ContractError(f"{owner_label}.{state_name} {label} selector references undeclared operation: {ref}")
        return
    raise ContractError(f"{owner_label}.{state_name} {label} selector is not supported: {selector}")


def _validate_composition_selector(state_machine_id: str, selector: str, regions: set[str], mounts: set[str], label: str) -> None:
    if selector in {"root", "screen"}:
        return
    if selector.startswith("region."):
        region = selector[len("region."):]
        if region not in regions:
            raise ContractError(f"composed state machine {state_machine_id} {label} selector references undeclared layout region: {selector}")
        return
    if selector.startswith("child_state_machine."):
        mount = selector[len("child_state_machine."):]
        if mount not in mounts:
            raise ContractError(f"composed state machine {state_machine_id} {label} selector references undeclared child state machine: {selector}")
        return
    raise ContractError(f"composed state machine {state_machine_id} {label} selector is not supported: {selector}")


def _validate_entries(contract: dict[str, Any]) -> None:
    for eid, entry in contract["entry_points"].items():
        adapter_kind, adapter = entry_point_adapter_pair(entry)
        target_kind, target = entry_point_target_pair(entry)
        kind = "state_machine" if target_kind == "state_machine" else target_kind
        value = target["ref"]
        _validate_entry_point_fields(eid, entry, adapter_kind)
        _validate_entry_input_shape(eid, entry, adapter_kind)
        if adapter_kind == "ui":
            if kind != "state_machine" or value not in contract["state_machines"]:
                raise ContractError(f"UI entry point {eid} must target a known state machine")
            renderer = adapter.get("renderer")
            if renderer and "renderer" not in target:
                target["renderer"] = renderer
            _validate_state_machine_target_renderer(contract, eid, entry, value, allowed_renderers={"html"})
            _require_adapter(adapter, eid, "path")
            _validate_path_params(entry, eid)
            declared = _entry_input_map(entry, "params")
            _validate_state_machine_entry_inputs(contract, eid, value, declared=declared, input_label="input.params")
            _validate_target_bindings(contract, eid, entry, declared)
        elif adapter_kind == "http":
            if kind != "operation" or value not in contract["operations"]:
                raise ContractError(f"HTTP entry point {eid} must target a known operation")
            _require_adapter(adapter, eid, "method")
            _require_adapter(adapter, eid, "path")
            _validate_path_params(entry, eid)
            operation = contract["operations"][value]
            params = _entry_input_map(entry, "params")
            body = _entry_input_map(entry, "body")
            _validate_api_entry_input(eid, entry, operation, params, body)
            _validate_target_bindings(contract, eid, entry, {**params, **body})
            _validate_api_entry_responses(eid, entry, operation)
        elif adapter_kind == "cli":
            _require_adapter(adapter, eid, "cli_command")
            args = _entry_input_map(entry, "args")
            if kind == "operation":
                if value not in contract["operations"]:
                    raise ContractError(f"CLI entry point {eid} must target a known operation")
                operation = contract["operations"][value]
                _validate_exact_entry_inputs(eid, "input.args", args, operation["input"])
                _validate_target_bindings(contract, eid, entry, args)
                _validate_cli_operation_responses(eid, entry, operation)
            elif kind == "state_machine":
                if value not in contract["state_machines"]:
                    raise ContractError(f"CLI entry point {eid} must target a known state machine")
                _validate_state_machine_target_renderer(contract, eid, entry, value, allowed_renderers=set(STATE_MACHINE_RENDERERS))
                _validate_state_machine_entry_inputs(contract, eid, value, declared=args, input_label="input.args")
                _validate_target_bindings(contract, eid, entry, args)
                target_renderer = entry_state_machine_renderer(entry)
                assert target_renderer is not None
                if entry_point_responses(entry):
                    raise ContractError(f"CLI entry point {eid} targeting a state machine must not declare responses")
            elif kind == "workflow":
                if value not in contract["workflows"]:
                    raise ContractError(f"CLI entry point {eid} must target a known workflow")
                _validate_workflow_entry_target_source(contract, eid, entry, value)
                if args:
                    raise ContractError(f"CLI entry point {eid} targeting a workflow must not declare input.args")
                _validate_async_entry_responses(eid, entry, require_failure_disposition=False)
            else:
                raise ContractError(f"CLI entry point {eid} cannot target raw {kind}")
        elif adapter_kind in {"worker", "scheduled"}:
            if kind != "workflow" or value not in contract["workflows"]:
                raise ContractError(f"{adapter_kind} entry point {eid} must target a known workflow")
            _validate_workflow_entry_target_source(contract, eid, entry, value)
            if adapter_kind == "scheduled":
                _require_adapter(adapter, eid, "schedule_expression")
                if entry_point_input(entry):
                    raise ContractError(f"Scheduled entry point {eid} must not declare input")
            else:
                _validate_event_payload_entry_input(contract, eid, entry, value)
            _validate_async_entry_responses(eid, entry, require_failure_disposition=adapter_kind == "worker")
        elif adapter_kind == "webhook":
            if kind != "workflow" or value not in contract["workflows"]:
                raise ContractError(f"Webhook entry point {eid} must target a known workflow")
            _validate_workflow_entry_target_source(contract, eid, entry, value)
            _require_adapter(adapter, eid, "path")
            _validate_path_params(entry, eid)
            _validate_event_payload_entry_input(contract, eid, entry, value)
            _validate_webhook_entry_responses(eid, entry)


def _validate_entry_point_fields(entry_id: str, entry: dict[str, Any], adapter_kind: str) -> None:
    allowed = {"adapter", "target", "rationale", "authorization_policy"}
    generated = {
        "ui": {"route"},
        "http": {"endpoint"},
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
        "ui": {"params"},
        "http": {"params", "body"},
        "cli": {"args"},
        "worker": {"payload"},
        "scheduled": set(),
        "webhook": {"params", "payload"},
    }[adapter_kind]
    input_spec = entry_point_input(entry)
    extra = sorted(set(input_spec) - allowed)
    if extra:
        raise ContractError(f"Entry point {entry_id} adapter {adapter_kind} has unsupported input sections: {extra}")
    seen: dict[str, Any] = {}
    for section in ("params", "body", "args"):
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
    source = entry_workflow_target_source(entry)
    if source is None:
        raise ContractError(f"Entry {entry_id} workflow target must declare when")
    workflow_trigger = contract["workflows"][workflow_id]["trigger"]
    if source != workflow_trigger:
        raise ContractError(f"Entry {entry_id} workflow target source must match workflow {workflow_id} trigger")


def _validate_api_entry_input(
    entry_id: str,
    entry: dict[str, Any],
    operation: dict[str, Any],
    params: dict[str, Any],
    body: dict[str, Any],
) -> None:
    cap_input = operation["input"]
    all_input = {**params, **body}
    if set(params) - set(cap_input):
        raise ContractError(f"API entry {entry_id} input.params must be operation input fields")
    if set(body) - set(cap_input):
        raise ContractError(f"API entry {entry_id} input.body must be operation input fields")
    if set(params) & set(body):
        raise ContractError(f"API entry {entry_id} input fields cannot appear in both params and body")
    _validate_entry_input_types(entry_id, "input.params", params, cap_input)
    _validate_entry_input_types(entry_id, "input.body", body, cap_input)
    method = (entry_point_method(entry) or "").lower()
    if method in {"get", "delete"}:
        if body:
            raise ContractError(f"API entry {entry_id} {entry_point_method(entry)} must not declare input.body")
        if set(params) != set(cap_input):
            missing_params = sorted(set(cap_input) - set(params))
            raise ContractError(f"API entry {entry_id} {entry_point_method(entry)} must declare all operation inputs as input.params: {missing_params}")
    missing = sorted(set(cap_input) - set(all_input))
    if missing:
        raise ContractError(f"API entry {entry_id} input must include every operation input: {missing}")


def _validate_event_payload_entry_input(contract: dict[str, Any], entry_id: str, entry: dict[str, Any], workflow_id: str) -> None:
    source = entry_workflow_target_source(entry)
    if not source or "event" not in source:
        return
    event_id = source["event"]
    event = contract["events"].get(event_id)
    if not event:
        raise ContractError(f"Entry {entry_id} workflow target source references unknown event {event_id}")
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
    if kind == "operation":
        expected = contract["operations"][value]["input"]
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
        actual_type = _reference_expression_type(
            contract,
            f"Entry {entry_id} target.input_bindings.{target_name}",
            source,
            source_scopes,
        )
        expected_type = expected[target_name]
        if not type_equals(actual_type, expected_type):
            raise ContractError(
                f"Entry {entry_id} target.input_bindings.{target_name} type mismatch: "
                f"expected {type_display(expected_type)}, got {type_display(actual_type)} from {source}"
            )


def _validate_api_entry_responses(entry_id: str, entry: dict[str, Any], operation: dict[str, Any]) -> None:
    responses = _operation_entry_responses(entry_id, entry, operation)
    statuses: dict[int, str] = {}
    for outcome_id, response in responses.items():
        outcome = operation["outcomes"][outcome_id]
        if set(response) != {"status", "body"}:
            raise ContractError(f"API entry {entry_id} response {outcome_id} must declare exactly status and body")
        status = response["status"]
        if status in statuses:
            raise ContractError(
                f"API entry {entry_id} responses {statuses[status]} and {outcome_id} cannot share HTTP status {status}"
            )
        statuses[status] = outcome_id
        if outcome["kind"] == "success":
            expected = 201 if operation.get("creates") else 200
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


def _validate_cli_operation_responses(entry_id: str, entry: dict[str, Any], operation: dict[str, Any]) -> None:
    responses = _operation_entry_responses(entry_id, entry, operation)
    exit_codes: dict[int, str] = {}
    for outcome_id, response in responses.items():
        outcome = operation["outcomes"][outcome_id]
        if "exit_code" not in response:
            raise ContractError(f"CLI entry {entry_id} response {outcome_id} must declare exit_code")
        exit_code = response["exit_code"]
        if outcome["kind"] == "success":
            if set(response) != {"exit_code", "stdout"}:
                raise ContractError(f"CLI entry {entry_id} success response {outcome_id} must declare exactly exit_code and stdout")
            if exit_code != 0:
                raise ContractError(f"CLI entry {entry_id} success response {outcome_id} exit_code must be 0")
            _validate_response_value(
                f"CLI entry {entry_id} response {outcome_id}.stdout",
                response["stdout"],
                outcome["result"],
            )
        else:
            if set(response) != {"exit_code", "stderr"}:
                raise ContractError(f"CLI entry {entry_id} failure response {outcome_id} must declare exactly exit_code and stderr")
            if exit_code == 0:
                raise ContractError(f"CLI entry {entry_id} failure response {outcome_id} exit_code must be nonzero")
            _validate_response_value(
                f"CLI entry {entry_id} response {outcome_id}.stderr",
                response["stderr"],
                outcome["result"],
            )
        if exit_code in exit_codes:
            raise ContractError(
                f"CLI entry {entry_id} responses {exit_codes[exit_code]} and {outcome_id} cannot share exit_code {exit_code}"
            )
        exit_codes[exit_code] = outcome_id


def _operation_entry_responses(entry_id: str, entry: dict[str, Any], operation: dict[str, Any]) -> dict[str, Any]:
    responses = entry_point_responses(entry)
    if set(responses) != set(operation["outcomes"]):
        missing = sorted(set(operation["outcomes"]) - set(responses))
        extra = sorted(set(responses) - set(operation["outcomes"]))
        parts = []
        if missing:
            parts.append("missing: " + ", ".join(missing))
        if extra:
            parts.append("extra: " + ", ".join(extra))
        raise ContractError(f"Entry {entry_id} responses must exactly map operation outcomes" + (": " + "; ".join(parts) if parts else ""))
    return responses


def _validate_response_value(label: str, value: dict[str, Any], expected_type: Any) -> None:
    if set(value) != {"type", "from"} or value["from"] != "$outcome.result" or not type_equals(value["type"], expected_type):
        raise ContractError(f"{label} must expose $outcome.result as {type_display(expected_type)}")


def _validate_async_entry_responses(entry_id: str, entry: dict[str, Any], *, require_failure_disposition: bool) -> None:
    responses = entry_point_responses(entry)
    accepted = responses.get("accepted")
    if accepted != {"disposition": "acknowledge"}:
        raise ContractError(f"Entry {entry_id} responses.accepted must declare disposition: acknowledge")
    failure_responses = {name: response for name, response in responses.items() if name != "accepted"}
    if require_failure_disposition and not failure_responses:
        raise ContractError(f"Entry {entry_id} must declare at least one non-acknowledge disposition such as retry, reject, or dead_letter")
    for response_id, response in failure_responses.items():
        if set(response) != {"disposition", "problem"}:
            raise ContractError(f"Entry {entry_id} disposition {response_id} must declare exactly disposition and problem")
        if response["disposition"] not in {"retry", "reject", "dead_letter"}:
            raise ContractError(f"Entry {entry_id} disposition {response_id} must be retry, reject, or dead_letter")
        _validate_problem_type(f"Entry {entry_id} disposition {response_id} problem", response["problem"])
    if require_failure_disposition and not any(response["disposition"] in {"reject", "dead_letter"} for response in failure_responses.values()):
        raise ContractError(f"Entry {entry_id} must declare a reject or dead_letter disposition for malformed or poison messages")


def _validate_webhook_entry_responses(entry_id: str, entry: dict[str, Any]) -> None:
    if entry_point_responses(entry) != {"accepted": {"status": 202}}:
        raise ContractError(f"Webhook entry {entry_id} responses.accepted.status must be 202")


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
    required: dict[str, Any] = {}
    _add_data_context_requirements(contract, f"state machine {state_machine_id}", state_machine.get("data_dependencies", []), state_machine.get("context", {}), required)
    for state_name, state in state_machine.get("view_states", {}).items():
        _add_data_context_requirements(contract, f"state machine {state_machine_id}.{state_name}", state.get("data_dependencies", []), state_machine.get("context", {}), required)
        for mount in state.get("child_state_machines", []):
            state_machine = contract["state_machines"][mount["state_machine"]]
            initial_state = state_machine["view_states"][mount["initial_view_state"]]
            _add_mount_context_requirements(contract, state_machine_id, mount, state_machine, state_machine.get("data_dependencies", []), required)
            _add_mount_context_requirements(contract, state_machine_id, mount, state_machine, initial_state.get("data_dependencies", []), required)
    return required


def _add_data_context_requirements(
    contract: dict[str, Any],
    label: str,
    data: list[dict[str, Any]],
    context: dict[str, Any],
    required: dict[str, Any],
) -> None:
    for datum in data:
        operation = contract["operations"][datum["operation"]]
        for key, expected_type in operation["input"].items():
            actual_type = context.get(key)
            if not type_equals(actual_type, expected_type):
                raise ContractError(f"{label} context {key} type must be {type_display(expected_type)}, got {type_display(actual_type)}")
            _add_required_entry_context(required, key, expected_type, label)


def _add_mount_context_requirements(
    contract: dict[str, Any],
    state_machine_id: str,
    mount: dict[str, Any],
    state_machine: dict[str, Any],
    data: list[dict[str, Any]],
    required: dict[str, Any],
) -> None:
    mount_context = mount.get("context", {})
    child_state_machine_context = state_machine.get("context", {})
    parent_state_machine_context = contract["state_machines"][state_machine_id].get("context", {})
    for datum in data:
        operation = contract["operations"][datum["operation"]]
        for child_key, expected_type in operation["input"].items():
            if not type_equals(child_state_machine_context.get(child_key), expected_type):
                raise ContractError(f"composed state machine {state_machine_id}.{mount['id']} state machine context {child_key} type must be {type_display(expected_type)}")
            value = mount_context.get(child_key)
            if not is_reference_expression(value):
                continue
            try:
                ref = parse_reference_expression(value)
            except ReferenceExpressionError as exc:
                raise ContractError(f"composed state machine {state_machine_id}.{mount['id']} has malformed runtime reference: {value}") from exc
            if ref.root != "state_machine":
                continue
            parent_key = ref.path[0]
            actual_type = _reference_expression_type(
                contract,
                f"composed state machine {state_machine_id}.{mount['id']} parent context {parent_key}",
                value,
                {"state_machine": _type_scope(parent_state_machine_context)},
            )
            if not type_equals(actual_type, expected_type):
                raise ContractError(
                    f"composed state machine {state_machine_id}.{mount['id']} parent context {parent_key} type must be "
                    f"{type_display(expected_type)}, got {type_display(actual_type)}"
                )
            _add_required_entry_context(
                required,
                parent_key,
                parent_state_machine_context[parent_key],
                f"composed state machine {state_machine_id}.{mount['id']}",
            )


def _add_required_entry_context(required: dict[str, Any], key: str, type_name: Any, label: str) -> None:
    existing = required.get(key)
    if existing and not type_equals(existing, type_name):
        raise ContractError(
            f"{label} requires conflicting entry input type for {key}: "
            f"{type_display(existing)} vs {type_display(type_name)}"
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
        if not type_equals(expected_type, type_name):
            raise ContractError(
                f"Entry {entry_id} {field}.{name} type mismatch: "
                f"expected {type_display(expected_type)}, got {type_display(type_name)}"
            )


def _entry_input_map(entry: dict[str, Any], section: str) -> dict[str, Any]:
    value = entry_point_input(entry).get(section, {})
    return value if isinstance(value, dict) else {}


def _entry_input_source_types(contract: dict[str, Any], entry: dict[str, Any]) -> TypeScope:
    source_types: TypeScope = {}
    for section in ("params", "body", "args"):
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
    return {(name,): type_name for name, type_name in types.items()}


def _typed_source_paths(contract: dict[str, Any], prefix: tuple[str, ...], type_name: Any) -> TypeScope:
    return {prefix: type_name}


def _merge_type_scopes(target: TypeScopes, source: TypeScopes) -> None:
    for root, entries in source.items():
        target.setdefault(root, {}).update(entries)


def _validate_mapping_to_type(
    contract: dict[str, Any],
    label: str,
    mapping: dict[str, str],
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
        actual_type = _reference_expression_type(contract, f"{label} mapping {field}", source, source_scopes)
        expected_type = expected[field]
        if not type_equals(actual_type, expected_type):
            raise ContractError(
                f"{label} mapping {field} source {source} type must be "
                f"{type_display(expected_type)}, got {type_display(actual_type)}"
            )


def _success_outcomes(cap: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {name: outcome for name, outcome in cap["outcomes"].items() if outcome["kind"] == "success"}


def _failure_outcomes(cap: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {name: outcome for name, outcome in cap["outcomes"].items() if outcome["kind"] == "failure"}


def _primary_success_outcome(cap: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    successes = _success_outcomes(cap)
    if len(successes) != 1:
        raise ContractError("Operation must declare exactly one success outcome")
    return next(iter(successes.items()))


def _success_result_type(cap: dict[str, Any]) -> Any:
    return _primary_success_outcome(cap)[1]["result"]


def _validate_workflows(contract: dict[str, Any]) -> None:
    for wid, workflow in contract["workflows"].items():
        kind, value = _one(workflow["trigger"], f"workflow {wid} trigger")
        if kind == "event" and value not in contract["events"]:
            raise ContractError(f"Workflow {wid} trigger references unknown event {value}")
        if kind == "operation" and value not in contract["operations"]:
            raise ContractError(f"Workflow {wid} trigger references unknown operation {value}")
        _validate_workflow_outcomes(wid, workflow)
        step_ids = [step["id"] for step in workflow["steps"]]
        if len(step_ids) != len(set(step_ids)):
            raise ContractError(f"Workflow {wid} step ids must be unique")
        step_id_set = set(step_ids)
        source_types = _workflow_trigger_source_types(contract, wid, workflow)
        routed_outcomes: set[str] = set()
        for step in workflow["steps"]:
            if step["operation"] not in contract["operations"]:
                raise ContractError(f"Workflow {wid} step references unknown operation {step['operation']}")
            operation = contract["operations"][step["operation"]]
            _validate_workflow_step_bindings(contract, wid, step, operation, source_types)
            routed_outcomes.update(_validate_workflow_step_routes(wid, workflow, step, operation, step_id_set))
            _merge_type_scopes(source_types, _workflow_step_source_types(contract, step, operation))
        if routed_outcomes != set(workflow["outcomes"]):
            missing = sorted(set(workflow["outcomes"]) - routed_outcomes)
            extra = sorted(routed_outcomes - set(workflow["outcomes"]))
            parts = []
            if missing:
                parts.append("missing outcome routes: " + ", ".join(missing))
            if extra:
                parts.append("unknown outcome routes: " + ", ".join(extra))
            raise ContractError(f"Workflow {wid} outcomes must be reachable from step routes" + (": " + "; ".join(parts) if parts else ""))


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
    kind, value = _one(workflow["trigger"], f"workflow {workflow_id} trigger")
    if kind == "event":
        payload_type = contract["events"][value]["payload_schema"]
    else:
        payload_type = _success_result_type(contract["operations"][value])
    return {"trigger": _typed_source_paths(contract, ("payload",), payload_type)}


def _workflow_step_source_types(contract: dict[str, Any], step: dict[str, Any], operation: dict[str, Any]) -> TypeScopes:
    sources: TypeScope = {}
    for outcome_id, outcome in operation["outcomes"].items():
        sources.update(_typed_source_paths(contract, (step["id"], "outcomes", outcome_id, "result"), outcome["result"]))
    return {"steps": sources}


WORKFLOW_ROUTE_ACTIONS = ("next_step", "complete_as", "fail_as", "retry_policy", "dead_letter_as")


def _workflow_route_action(route: dict[str, Any]) -> tuple[str, Any]:
    actions = [action for action in WORKFLOW_ROUTE_ACTIONS if action in route]
    if len(actions) != 1:
        raise ContractError(
            "workflow route must declare exactly one of "
            + ", ".join(WORKFLOW_ROUTE_ACTIONS)
        )
    action = actions[0]
    return action, route[action]


def _workflow_route_outcome(action: str, value: Any) -> str | None:
    if action in {"complete_as", "fail_as", "dead_letter_as"}:
        return value
    if action == "retry_policy":
        return value["fail_as"]
    return None


def _validate_workflow_step_bindings(
    contract: dict[str, Any],
    workflow_id: str,
    step: dict[str, Any],
    operation: dict[str, Any],
    source_types: TypeScopes,
) -> None:
    bindings = step["input_bindings"]
    expected = operation["input"]
    if set(bindings) != set(expected):
        missing = sorted(set(expected) - set(bindings))
        extra = sorted(set(bindings) - set(expected))
        parts = []
        if missing:
            parts.append("missing: " + ", ".join(missing))
        if extra:
            parts.append("extra: " + ", ".join(extra))
        raise ContractError(f"Workflow {workflow_id} step {step['id']} input_bindings must exactly map operation input" + (": " + "; ".join(parts) if parts else ""))
    for name, source in bindings.items():
        actual_type = _reference_expression_type(
            contract,
            f"Workflow {workflow_id} step {step['id']} input {name}",
            source,
            source_types,
        )
        expected_type = expected[name]
        if not type_equals(actual_type, expected_type):
            raise ContractError(
                f"Workflow {workflow_id} step {step['id']} input {name} source {source} type must be "
                f"{type_display(expected_type)}, got {type_display(actual_type)}"
            )


def _validate_workflow_step_routes(
    workflow_id: str,
    workflow: dict[str, Any],
    step: dict[str, Any],
    operation: dict[str, Any],
    step_ids: set[str],
) -> set[str]:
    routes = step["outcome_routes"]
    if set(routes) != set(operation["outcomes"]):
        missing = sorted(set(operation["outcomes"]) - set(routes))
        extra = sorted(set(routes) - set(operation["outcomes"]))
        parts = []
        if missing:
            parts.append("missing: " + ", ".join(missing))
        if extra:
            parts.append("extra: " + ", ".join(extra))
        raise ContractError(f"Workflow {workflow_id} step {step['id']} outcome_routes must exactly map operation outcomes" + (": " + "; ".join(parts) if parts else ""))

    routed_outcomes: set[str] = set()
    for outcome_id, route in routes.items():
        try:
            action, value = _workflow_route_action(route)
        except ContractError as exc:
            raise ContractError(f"Workflow {workflow_id} step {step['id']} route {outcome_id} {exc}") from exc
        outcome = operation["outcomes"][outcome_id]
        if action == "next_step":
            next_step = value
            if next_step not in step_ids:
                raise ContractError(f"Workflow {workflow_id} step {step['id']} route {outcome_id} references unknown next step {next_step}")
            if next_step == step["id"]:
                raise ContractError(f"Workflow {workflow_id} step {step['id']} route {outcome_id} cannot loop to itself")
        else:
            routed_outcome_id = _workflow_route_outcome(action, value)
            assert routed_outcome_id is not None
            routed_outcome = workflow["outcomes"].get(routed_outcome_id)
            if not routed_outcome:
                raise ContractError(f"Workflow {workflow_id} step {step['id']} route {outcome_id} references unknown workflow outcome {routed_outcome_id}")
            expected_kind = "success" if action == "complete_as" else "failure"
            if outcome["kind"] != expected_kind or routed_outcome["kind"] != expected_kind:
                raise ContractError(f"Workflow {workflow_id} step {step['id']} route {outcome_id} must preserve {outcome['kind']} outcome semantics")
            if not type_equals(routed_outcome["result"], outcome["result"]):
                raise ContractError(
                    f"Workflow {workflow_id} outcome {routed_outcome_id} result must be "
                    f"{type_display(outcome['result'])} to receive step outcome {outcome_id}"
                )
            routed_outcomes.add(routed_outcome_id)
        if action == "retry_policy":
            if outcome["kind"] != "failure":
                raise ContractError(f"Workflow {workflow_id} step {step['id']} route {outcome_id} retry_policy is only valid for failure outcomes")
            retry = value
            if retry["attempts"] < 1 or retry["attempts"] > 10:
                raise ContractError(f"Workflow {workflow_id} step {step['id']} route {outcome_id} retry_policy attempts must be between 1 and 10")
        if action == "dead_letter_as" and outcome["kind"] != "failure":
            raise ContractError(f"Workflow {workflow_id} step {step['id']} route {outcome_id} dead_letter_as is only valid for failure outcomes")
    return routed_outcomes


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
        for fact in test_case["then"].get("assertion_facts", []):
            _validate_fact_body(contract, fact, f"Test case {test_case_id} then.assertion_facts")
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
    if isinstance(node, str):
        if is_reference_expression(node):
            refs.append(node)
    elif isinstance(node, dict):
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
    if kind in {"open_entry", "call_entry"}:
        if ref not in contract["entry_points"]:
            raise ContractError(f"Test case {test_case_id} references unknown entry point {ref}")
        entry = contract["entry_points"][ref]
        adapter_kind, _ = entry_point_adapter_pair(entry)
        entry_target_kind, _ = entry_target_pair(entry)
        if kind == "open_entry" and not (adapter_kind in {"ui", "cli"} and entry_target_kind == "state_machine"):
            raise ContractError(f"Test case {test_case_id} open_entry must reference a UI or CLI state machine entry point")
        if kind == "call_entry" and not (adapter_kind in {"http", "cli"} and entry_target_kind == "operation"):
            raise ContractError(f"Test case {test_case_id} call_entry must reference an HTTP or CLI operation entry point")
        _validate_test_case_entry_input(test_case_id, kind, body, entry)
    elif kind == "invoke_operation":
        if ref not in contract["operations"]:
            raise ContractError(f"Test case {test_case_id} references unknown operation {ref}")
    elif kind == "emit_event":
        if ref not in contract["events"]:
            raise ContractError(f"Test case {test_case_id} references unknown event {ref}")
        _validate_test_case_event_payload(contract, test_case_id, ref, body.get("payload", {}))
    _validate_test_case_outcome(contract, test_case_id, test_case)


def _validate_test_case_event_payload(contract: dict[str, Any], test_case_id: str, event_id: str, payload: dict[str, Any]) -> None:
    event = contract["events"][event_id]
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
            f"Test case {test_case_id} emit_event.payload must exactly match event {event_id} payload "
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
    for section in ("params", "body", "args"):
        fields.update(_entry_input_map(entry, section))
    return fields


def _subject_ref(subject_ref: dict[str, str]) -> tuple[str, str]:
    return next(iter(subject_ref.items()))


def _validate_test_case_subject(contract: dict[str, Any], test_case_id: str, test_case: dict[str, Any]) -> None:
    subject_kind, subject_value = _subject_ref(test_case["subject_ref"])
    collections = {
        "entry_point": "entry_points",
        "event": "events",
        "operation": "operations",
        "state_machine": "state_machines",
        "workflow": "workflows",
    }
    if subject_value not in contract[collections[subject_kind]]:
        raise ContractError(f"Test case {test_case_id} subject_ref references unknown {subject_kind} {subject_value}")

    when_kind, when_body = _one(test_case["when"], f"test case {test_case_id} when")
    then = test_case["then"]
    operation_ref = _test_case_operation_ref(contract, when_kind, when_body)
    entry_ref = when_body["ref"] if when_kind in {"open_entry", "call_entry"} else None
    event_ref = when_body["ref"] if when_kind == "emit_event" else None
    state_machine_ref = _test_case_state_machine_ref(contract, when_kind, when_body)

    if subject_kind == "entry_point" and entry_ref != subject_value:
        raise ContractError(f"Test case {test_case_id} subject_ref.entry_point must match the entry point under test")
    if subject_kind == "operation" and operation_ref != subject_value:
        raise ContractError(f"Test case {test_case_id} subject_ref.operation must match the operation under test")
    if subject_kind == "event" and event_ref != subject_value and subject_value not in (then.get("events") or {}).get("emitted", []):
        raise ContractError(f"Test case {test_case_id} subject_ref.event must match the emitted event under test")
    if subject_kind == "state_machine":
        asserted = (then.get("state_machine") or {}).get("ref")
        if subject_value not in {state_machine_ref, asserted}:
            raise ContractError(f"Test case {test_case_id} subject_ref.state_machine must match the state machine under test")
    if subject_kind == "workflow":
        workflow = then.get("workflow") or {}
        if workflow.get("ref") != subject_value:
            raise ContractError(f"Test case {test_case_id} subject_ref.workflow must match then.workflow.ref")


def _test_case_operation_ref(contract: dict[str, Any], when_kind: str, when_body: dict[str, Any]) -> str | None:
    if when_kind == "invoke_operation":
        return when_body["ref"]
    if when_kind == "call_entry":
        target_kind, target_ref = entry_target_pair(contract["entry_points"][when_body["ref"]])
        if target_kind == "operation":
            return target_ref
    return None


def _test_case_state_machine_ref(contract: dict[str, Any], when_kind: str, when_body: dict[str, Any]) -> str | None:
    if when_kind != "open_entry":
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
        for sync_id in (expected_state_machine.get("message_sync_rules") or {}).get("observed_rules", []):
            state_name = expected_state_machine.get("view_state")
            selected_state = state_machine.get("view_states", {}).get(state_name, {}) if state_name else {}
            if sync_id not in {rule["id"] for rule in selected_state.get("message_sync_rules", [])}:
                raise ContractError(f"Test case {test_case_id} references unknown sync rule {state_machine_id}.{sync_id}")
        for key in (expected_state_machine.get("context") or {}):
            if key not in state_machine.get("context", {}):
                raise ContractError(f"Test case {test_case_id} asserts undeclared state machine context {state_machine_id}.{key}")
    for field in ["enables", "forbids", "invoked"]:
        for cap_id in then.get(field, []):
            if cap_id not in contract["operations"]:
                raise ContractError(f"Test case {test_case_id} {field} unknown operation {cap_id}")
    policy_assertion = then.get("policy") or {}
    for effect in ("allowed", "denied"):
        for assertion in policy_assertion.get(effect, []):
            kind, ref = _policy_assertion_target(assertion, f"Test case {test_case_id} policy.{effect}")
            if kind == "operation" and ref not in contract["operations"]:
                raise ContractError(f"Test case {test_case_id} policy.{effect} unknown operation {ref}")
            if kind == "entry_point" and ref not in contract["entry_points"]:
                raise ContractError(f"Test case {test_case_id} policy.{effect} unknown entry point {ref}")
            authorization_policy = assertion.get("authorization_policy")
            if authorization_policy and authorization_policy["policy"] not in contract["policies"]:
                raise ContractError(f"Test case {test_case_id} policy.{effect} unknown authorization_policy {authorization_policy['policy']}")
    model_exists = (then.get("model") or {}).get("exists")
    if model_exists:
        model_id = model_exists["model"]
        if model_id not in contract["models"]:
            raise ContractError(f"Test case {test_case_id} asserts unknown model {model_id}")
        unknown_fields = sorted(set(model_exists["where"]) - set(contract["models"][model_id]["fields"]))
        if unknown_fields:
            raise ContractError(f"Test case {test_case_id} model.exists filters unknown {model_id} fields: {unknown_fields}")
    events = then.get("events") or {}
    emitted = set(events.get("emitted", []))
    not_emitted = set(events.get("not_emitted", []))
    overlap = sorted(emitted & not_emitted)
    if overlap:
        raise ContractError(f"Test case {test_case_id} asserts events as both emitted and not_emitted: {overlap}")
    for event_id in list(emitted) + list(not_emitted):
        if event_id not in contract["events"]:
            raise ContractError(f"Test case {test_case_id} asserts unknown event {event_id}")
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
        if when_kind != "call_entry":
            raise ContractError(f"Test case {test_case_id} response assertions require call_entry")


def _validate_test_case_event_emissions(
    contract: dict[str, Any],
    test_case_id: str,
    test_case: dict[str, Any],
    emitted: set[str],
    not_emitted: set[str],
) -> None:
    when_kind, when_body = _one(test_case["when"], f"test case {test_case_id} when")
    then = test_case["then"]
    if when_kind == "emit_event":
        if when_body["ref"] in emitted:
            return
        return
    operation_id = _test_case_operation_ref(contract, when_kind, when_body)
    outcome_id = then.get("outcome")
    if not operation_id or not outcome_id or outcome_id not in contract["operations"][operation_id]["outcomes"]:
        return
    possible = {
        _emit_event_id(emit)
        for emit in contract["operations"][operation_id]["outcomes"][outcome_id].get("emits", [])
    }
    unexpected = sorted(emitted - possible)
    if unexpected:
        raise ContractError(f"Test case {test_case_id} asserts events not emitted by {operation_id}.{outcome_id}: {unexpected}")
    contradicted = sorted(not_emitted & possible)
    if contradicted:
        raise ContractError(f"Test case {test_case_id} asserts not_emitted events emitted by {operation_id}.{outcome_id}: {contradicted}")


def _validate_test_case_invocations(contract: dict[str, Any], test_case_id: str, test_case: dict[str, Any]) -> None:
    invoked = set(test_case["then"].get("invoked", []))
    if not invoked:
        return
    when_kind, when_body = _one(test_case["when"], f"test case {test_case_id} when")
    direct = _test_case_operation_ref(contract, when_kind, when_body)
    expected = {direct} if direct else set()
    if when_kind == "emit_event":
        event_id = when_body["ref"]
        for workflow in contract["workflows"].values():
            if workflow["trigger"] == {"event": event_id}:
                expected.update(step["operation"] for step in workflow["steps"])
    unexpected = sorted(invoked - expected)
    if unexpected:
        raise ContractError(f"Test case {test_case_id} asserts operation invocations unrelated to when: {unexpected}")


def _workflow_can_run_from_test_case(contract: dict[str, Any], test_case: dict[str, Any]) -> bool:
    workflow_assertion = test_case["then"].get("workflow") or {}
    workflow_id = workflow_assertion.get("ref")
    if not workflow_id or workflow_id not in contract["workflows"]:
        return False
    workflow = contract["workflows"][workflow_id]
    when_kind, when_body = _one(test_case["when"], "test case when")
    trigger_kind, trigger_ref = _one(workflow["trigger"], f"workflow {workflow_id} trigger")
    if when_kind == "emit_event" and trigger_kind == "event":
        return when_body["ref"] == trigger_ref
    operation_id = _test_case_operation_ref(contract, when_kind, when_body)
    return trigger_kind == "operation" and operation_id == trigger_ref


def _validate_test_case_outcome(contract: dict[str, Any], test_case_id: str, test_case: dict[str, Any]) -> None:
    when_kind, when_body = _one(test_case["when"], f"test case {test_case_id} when")
    then = test_case["then"]
    outcome_id = then.get("outcome")
    cap: dict[str, Any] | None = None
    entry: dict[str, Any] | None = None
    if when_kind == "invoke_operation":
        cap = contract["operations"][when_body["ref"]]
    elif when_kind == "call_entry":
        entry = contract["entry_points"][when_body["ref"]]
        target_kind, target_ref = entry_target_pair(entry)
        if target_kind == "operation":
            cap = contract["operations"][target_ref]
    if cap is None:
        if outcome_id:
            raise ContractError(f"Test case {test_case_id} asserts outcome but does not execute an operation")
        return
    if not outcome_id:
        raise ContractError(f"Test case {test_case_id} must assert an operation outcome")
    if outcome_id not in cap["outcomes"]:
        raise ContractError(f"Test case {test_case_id} asserts unknown outcome {outcome_id}")
    if entry is None:
        return
    if outcome_id not in entry_point_responses(entry):
        raise ContractError(f"Test case {test_case_id} outcome {outcome_id} is not mapped by entry point {when_body['ref']}")
    response_assertion = then.get("response")
    if response_assertion:
        response = entry_point_responses(entry)[outcome_id]
        for key in ("status", "exit_code"):
            if key in response_assertion and response.get(key) != response_assertion[key]:
                raise ContractError(f"Test case {test_case_id} response.{key} does not match entry point response for outcome {outcome_id}")


def _validate_test_case_archetype(test_case_id: str, test_case: dict[str, Any]) -> None:
    archetype = test_case["archetype"]
    when_kind, _ = _one(test_case["when"], f"test case {test_case_id} when")
    then = test_case["then"]
    if archetype == "empty_collection_state_machine":
        if when_kind != "open_entry" or then.get("state_machine", {}).get("view_state") != "empty":
            raise ContractError(f"Test case {test_case_id} empty_collection_state_machine requires open_entry and state_machine.view_state=empty")
    elif archetype == "ready_collection_state_machine":
        if when_kind != "open_entry" or then.get("state_machine", {}).get("view_state") != "ready":
            raise ContractError(f"Test case {test_case_id} ready_collection_state_machine requires open_entry and state_machine.view_state=ready")
    elif archetype == "state_machine_composition_sync":
        state_machine_assert = then.get("state_machine", {})
        if when_kind != "open_entry" or not state_machine_assert.get("instances"):
            raise ContractError(f"Test case {test_case_id} state_machine_composition_sync requires open_entry and state_machine.instances")
    elif archetype == "state_machine_composition":
        state_machine_assert = then.get("state_machine", {})
        if when_kind != "open_entry" or not state_machine_assert.get("instances"):
            raise ContractError(f"Test case {test_case_id} state_machine_composition requires open_entry and state_machine.instances")
    elif archetype == "operation_outcome":
        if when_kind != "invoke_operation" or "outcome" not in then:
            raise ContractError(f"Test case {test_case_id} operation_outcome requires invoke_operation and outcome")
    elif archetype == "entry_response":
        if when_kind != "call_entry" or "outcome" not in then or "response" not in then:
            raise ContractError(f"Test case {test_case_id} entry_response requires call_entry, outcome, and response")
    elif archetype == "workflow_event_success":
        workflow = then.get("workflow", {})
        if when_kind != "emit_event" or not workflow.get("executed") or "outcome" not in workflow:
            raise ContractError(f"Test case {test_case_id} workflow_event_success requires emit_event, workflow.executed=true, and workflow.outcome")
    elif archetype == "forbidden_action":
        if not (then.get("policy") or {}).get("denied"):
            raise ContractError(f"Test case {test_case_id} forbidden_action requires policy.denied")


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
            "assertion_facts",
            f"Test case {test_case_id}",
        ))
    for case_id, case in audit_cases(contract).items():
        case_uses: set[str] = set()
        for fact_use in case.get("facts", []):
            fact_id = fact_use["ref"]
            if fact_id not in contract["facts"]:
                raise ContractError(f"Audit case {case_id} references unknown fact {fact_id}")
            if fact_id in case_uses:
                raise ContractError(f"Audit case {case_id} uses fact {fact_id} more than once")
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
                required = {"queries": [datum["query"] for datum in parent_state_machine.get("data_dependencies", [])], "surfaces": [], "text": [], "assets": [], "available_operations": []}
                state_machine_assertion["surface"] = parent_state["surface"]
                required["surfaces"].append(parent_state["surface"])
                required["queries"].extend(datum["query"] for datum in parent_state.get("data_dependencies", []))
                required["text"].extend(parent_state["text"])
                required["assets"].extend(parent_state["assets"])
                required["available_operations"].extend(parent_state["available_operations"])
                for instance_id, expected in state_machine_assertion["instances"].items():
                    mount = mounts[instance_id]
                    mounted_state_machine = contract["state_machines"][mount["state_machine"]]
                    mounted_state = mounted_state_machine["view_states"][expected["view_state"]]
                    expected["surface"] = mounted_state["surface"]
                    expected["source"] = mount["state_machine"]
                    required["queries"].extend(datum["query"] for datum in mounted_state_machine.get("data_dependencies", []))
                    required["queries"].extend(datum["query"] for datum in mounted_state.get("data_dependencies", []))
                    required["surfaces"].append(mounted_state["surface"])
                    required["text"].extend(mounted_state["text"])
                    required["assets"].extend(mounted_state["assets"])
                    required["available_operations"].extend(mounted_state["available_operations"])
                state_machine_assertion["composition"] = {
                    "renderers": parent_state.get("renderers", {}),
                    "child_state_machines": parent_state.get("child_state_machines", []),
                    "message_sync_rules": parent_state.get("message_sync_rules", []),
                }
                assertions["requires"] = {key: list(dict.fromkeys(values)) for key, values in required.items()}
            elif "view_state" in state_machine_assertion:
                state_name = state_machine_assertion["view_state"]
                state = state_machine["view_states"][state_name]
                state_machine_assertion["surface"] = state["surface"]
                assertions["requires"] = {
                    "queries": [datum["query"] for datum in state_machine.get("data_dependencies", [])] + [datum["query"] for datum in state.get("data_dependencies", [])],
                    "surfaces": [state["surface"]],
                    "text": list(state["text"]),
                    "assets": list(state["assets"]),
                    "available_operations": list(state["available_operations"]),
                }
        when_kind, when_body = _one(test_case["when"], "test case when")
        cap_id = None
        if when_kind == "invoke_operation":
            cap_id = when_body["ref"]
        elif when_kind == "call_entry":
            entry = contract["entry_points"][when_body["ref"]]
            target_kind, target_ref = entry_target_pair(entry)
            if target_kind == "operation":
                cap_id = target_ref
        if cap_id:
            assertions.setdefault("policy", {"allowed": [{"operation": cap_id}]})
        _expand_policy_assertions(contract, assertions)


def _expand_policy_assertions(contract: dict[str, Any], assertions: dict[str, Any]) -> None:
    policy = assertions.get("policy")
    if not policy:
        return
    for effect in ("allowed", "denied"):
        for assertion in policy.get(effect, []):
            if "authorization_policy" in assertion:
                continue
            kind, ref = _policy_assertion_target(assertion, f"policy.{effect}")
            if kind == "operation":
                assertion["authorization_policy"] = {"policy": contract["operations"][ref]["authorization_policy"]["policy"]}
            elif kind == "entry_point":
                authorization_policy = contract["entry_points"][ref].get("authorization_policy")
                if authorization_policy:
                    assertion["authorization_policy"] = {"policy": authorization_policy["policy"]}


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
    declared = set(_entry_input_map(entry, "params"))
    if placeholders != declared:
        raise ContractError(
            f"Entry {entry_id} path params {sorted(placeholders)} must exactly match input.params {sorted(declared)}"
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
