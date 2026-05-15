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
from .layout import layout_html, layout_html_regions, layout_regions, layout_textual, layout_textual_containers
from .paths import COMPILED_SPEC_PATH, GENERATED_SPEC_DIR, SOURCE_SPEC_PATH
from .project import projection_files
from .runtime_refs import ReferenceExpressionError, is_reference_expression, parse_reference_expression
from .targets import FSM_RENDER_SURFACES, entry_fsm_surface, entry_target_pair, entry_workflow_trigger
from .type_expr import (
    TypeExpressionError,
    array_of,
    base_model_name,
    dereference_type,
    is_array_of_model,
    is_problem_type,
    literal_type_expr,
    normalize_field_map,
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


TARGET_ORDER = ("copy", "asset", "content_case", "audit_profile", "fixture", "fact", "model", "capability", "event", "fsm", "entry", "workflow", "scenario")



ENTITY_SECTIONS: dict[str, str] = {
    "copy": "copies",
    "asset": "assets",
    "content_case": "content_cases",
    "audit_profile": "audit_profiles",
    "fixture": "fixtures",
    "fact": "facts",
    "model": "models",
    "capability": "capabilities",
    "event": "events",
    "fsm": "fsms",
    "entry": "entries",
    "workflow": "workflows",
    "scenario": "scenarios",
}


REF_KINDS = ["asset", "command", "endpoint", "policy", "query", "route", "screen", "state_machine", "surface", "text", "workflow"]


def empty_compiled_contract(project: str) -> dict[str, Any]:
    return {
        "project": project,
        "copies": {},
        "assets": {},
        "content_cases": {},
        "audit_profiles": {},
        "fixtures": {},
        "facts": {},
        "models": {},
        "capabilities": {},
        "events": {},
        "fsms": {},
        "entries": {},
        "workflows": {},
        "scenarios": {},
        "refs": {},
    }


AUTHOR_SECTION_ORDER = ("fixtures", "facts", "models", "capabilities", "events", "fsms", "entries", "workflows", "scenarios", "copies", "assets", "content_cases", "audit_profiles")


def _prune_empty_author_sections(author: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {"project": author["project"]}
    for section_name in AUTHOR_SECTION_ORDER:
        value = author.get(section_name)
        if value:
            result[section_name] = value
    return result


def _default_basis(entity: str, entity_id: str) -> str:
    return f"Declared {entity} {entity_id}."[:280]


def _empty_fsm_messages() -> dict[str, dict[str, Any]]:
    return {"accepts": {}, "emits": {}}


def _normalize_fsm_messages(messages: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    messages = messages or {}
    normalized: dict[str, dict[str, Any]] = {}
    for direction in ("accepts", "emits"):
        normalized[direction] = {}
        for message_id, message in (messages.get(direction) or {}).items():
            message_spec = copy.deepcopy(message)
            message_spec.setdefault("payload", {})
            normalized[direction][message_id] = message_spec
    return {
        "accepts": normalized["accepts"],
        "emits": normalized["emits"],
    }


def _prune_redundant_author_transitions(author: dict[str, Any]) -> None:
    """Let model lifecycles be the source of truth for simple transitions."""
    capabilities = author.get("capabilities") or {}
    for model_id, model in (author.get("models") or {}).items():
        lifecycle = model.get("lifecycle") if isinstance(model, dict) else None
        if not lifecycle:
            continue
        field = lifecycle["field"]
        for transition in lifecycle.get("transitions", []):
            capability = capabilities.get(transition["triggered_by"])
            if not isinstance(capability, dict):
                continue
            declared = capability.get("transition")
            if declared == {"model": model_id, "field": field, "from": transition["from"], "to": transition["to"]}:
                capability.pop("transition", None)


def _prune_empty_author_fsm_message_directions(author: dict[str, Any]) -> None:
    for fsm in (author.get("fsms") or {}).values():
        messages = fsm.get("messages")
        if not isinstance(messages, dict):
            continue
        for direction in ("accepts", "emits"):
            for message in (messages.get(direction) or {}).values():
                if isinstance(message, dict) and message.get("payload") == {}:
                    message.pop("payload")
            if messages.get(direction) == {}:
                messages.pop(direction)
        if not messages:
            fsm.pop("messages", None)


def author_from_source(source: dict[str, Any], layers: set[str] | None = None) -> dict[str, Any]:
    validate_against_schema(source, "author.schema.json")
    try:
        validate_author_layers(source, layers)
    except LayerError as exc:
        raise ContractError(str(exc)) from exc
    author = _prune_empty_author_sections(copy.deepcopy(source))
    _prune_redundant_author_transitions(author)
    _prune_empty_author_fsm_message_directions(author)
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

    _derive_capability_transitions(contract)
    contract["events"] = _derive_events(contract)
    contract["refs"] = _derive_refs(contract)
    used_facts = _expand_scenario_fact_uses(contract)
    _semantic_validate(contract, used_facts)
    _expand_scenarios(contract)
    validate_against_schema(contract, "spec.schema.json")
    return contract


def _apply_author_defaults(entity: str, spec: dict[str, Any]) -> None:
    why = spec.pop("why", None)
    if why and "basis" in spec:
        raise ContractError(f"Authored {entity} {spec['id']} must use either basis or why, not both")
    spec.setdefault("basis", why or _default_basis(entity, spec["id"]))
    if entity == "fsm":
        spec.setdefault("context", {})
        spec.setdefault("data", [])
        spec["messages"] = _normalize_fsm_messages(spec.get("messages"))
        spec.setdefault("transitions", [])
    elif entity == "capability":
        for outcome in spec.get("outcomes", {}).values():
            outcome.setdefault("emits", [])


def _compile_entity(entity: str, spec: dict[str, Any] | None, contract: dict[str, Any]) -> dict[str, Any]:
    if spec is None:  # pragma: no cover - delete never compiles an entity.
        raise ContractError(f"Cannot compile missing {entity} spec")

    if entity == "copy":
        item = {"placeholder": spec["placeholder"], "basis": spec["basis"]}
        for field in ["max_chars", "tone", "args", "resolver"]:
            if field in spec:
                item[field] = spec[field]
        return item

    if entity == "asset":
        item = {"kind": spec["kind"], "placeholder": spec["placeholder"], "basis": spec["basis"]}
        for field in ["alt_copy", "args", "resolver"]:
            if field in spec:
                item[field] = spec[field]
        return item

    if entity == "content_case":
        item = {"ref": spec["ref"], "args": spec["args"], "basis": spec["basis"]}
        if "fixtures" in spec:
            item["fixtures"] = spec["fixtures"]
        return item

    if entity == "audit_profile":
        item = {"basis": spec["basis"]}
        for field in ["html", "textual"]:
            if field in spec:
                item[field] = spec[field]
        return item

    if entity == "fixture":
        return {"values": spec["values"], "basis": spec["basis"]}

    if entity == "fact":
        kind, body = _one_fact(spec, f"Fact {spec['id']}")
        return {kind: body, "basis": spec["basis"]}

    if entity == "model":
        item = {
            "fields": normalize_field_map(spec["fields"]),
            "lifecycle": spec.get("lifecycle"),
            "basis": spec["basis"],
        }
        return item

    if entity == "capability":
        capability: dict[str, Any] = {
            "archetype": spec["archetype"],
            "input": spec["input"],
            "outcomes": spec["outcomes"],
            "policy": rules.policy_ref(spec["id"]),
            "basis": spec["basis"],
        }
        for field in ["creates", "reads", "updates", "deletes", "transition"]:
            if field in spec:
                capability[field] = spec[field]
        return capability

    if entity == "event":
        return {
            "payload": spec["payload"],
            "emitted_by": [],
            "basis": spec["basis"],
        }

    if entity == "fsm":
        fsm_id = spec["id"]
        fsm: dict[str, Any] = {
            "model": spec["model"],
            "context": spec["context"],
            "data": _compile_data(fsm_id, spec.get("data", [])),
            "messages": _normalize_fsm_messages(spec.get("messages")),
            "initial": spec["initial"],
            "states": _compile_states(fsm_id, spec.get("states", {})),
            "transitions": spec.get("transitions", []),
            "basis": spec["basis"],
        }
        if "archetype" in spec:
            fsm["archetype"] = spec["archetype"]
        return fsm

    if entity == "entry":
        entry_id = spec["id"]
        entry: dict[str, Any] = {
            "surface": spec["surface"],
            "input": spec.get("input", {}),
            "target": spec["target"],
            "basis": spec["basis"],
        }
        if "responses" in spec:
            entry["responses"] = spec["responses"]
        for field in ["method", "path", "command", "schedule"]:
            if field in spec:
                entry[field] = spec[field]
        kind, value = entry_target_pair(spec["target"])
        if spec["surface"] == "web" and kind == "fsm":
            entry["route"] = rules.route_ref(value)
        elif spec["surface"] == "api" and kind == "capability":
            entry["endpoint"] = rules.endpoint_ref(value)
        elif spec["surface"] == "cli":
            entry["command_ref"] = rules.command_ref(value)
        elif spec["surface"] in {"worker", "schedule"} and kind == "workflow":
            entry["workflow_ref"] = rules.workflow_ref(value)
        return entry

    if entity == "workflow":
        return {
            "trigger": spec["trigger"],
            "outcomes": spec["outcomes"],
            "steps": spec["steps"],
            "ref": rules.workflow_ref(spec["id"]),
            "basis": spec["basis"],
        }

    if entity == "scenario":
        return {
            "feature": spec["feature"],
            "title": spec["title"],
            "archetype": spec["archetype"],
            "arrange": spec["given"],
            "execute": spec["when"],
            "assert": dict(spec["then"]),
            "basis": spec["basis"],
        }

    raise ContractError(f"Unknown contract entity kind: {entity}")


def _ref_subject(owner_id: str) -> str:
    return rules.resource_tail(owner_id)


def _state_surface_ref(owner_id: str, state_name: str) -> str:
    if owner_id.startswith("state_machine."):
        return f"{owner_id}.{state_name}"
    return rules.fsm_ref(owner_id, state_name)


def _compile_data(owner_id: str, capability_ids: list[str]) -> list[dict[str, str]]:
    subject = _ref_subject(owner_id)
    data = []
    for cap_id in capability_ids:
        qref = rules.query_ref(subject, cap_id, many=len(capability_ids) > 1)
        data.append({"query": qref, "capability": cap_id})
    return data


def _compile_states(owner_id: str, states: dict[str, Any]) -> dict[str, Any]:
    subject = _ref_subject(owner_id)
    compiled = {}
    for state_name, state in states.items():
        item = {
            "surface": _state_surface_ref(owner_id, state_name),
            "data": _compile_data(owner_id, state.get("data", [])),
            "copy": [rules.copy_ref(subject, state_name, slot) for slot in state.get("copy_slots", [])],
            "assets": [rules.asset_ref(subject, state_name, slot) for slot in state.get("asset_slots", [])],
            "fields": state.get("field_slots", []),
            "actions": state.get("actions", []),
        }
        if "presentation" in state:
            item["presentation"] = state["presentation"]
        for field in ["layout", "mounts", "sync"]:
            if field in state:
                item[field] = state[field]
        if state.get("audit"):
            item["audit"] = {
                case_name: _compile_audit_case(owner_id, state_name, case_name, case)
                for case_name, case in state["audit"].items()
            }
        compiled[state_name] = item
    return compiled


def _compile_audit_case(fsm_id: str, state_name: str, case_name: str, case: dict[str, Any]) -> dict[str, Any]:
    item = {
        "profile": case["profile"],
        "surfaces": case["surfaces"],
        "fixtures": case["fixtures"],
        "basis": case.get("basis", _default_basis("audit_case", f"{fsm_id}.{state_name}.{case_name}")),
    }
    for field in ["context", "facts", "instances"]:
        if field in case:
            item[field] = case[field]
    return item


def audit_cases(contract: dict[str, Any]) -> dict[str, dict[str, Any]]:
    cases: dict[str, dict[str, Any]] = {}
    for fsm_id, fsm in sorted(contract.get("fsms", {}).items()):
        for state_name, state in sorted(fsm.get("states", {}).items()):
            for case_name, case in sorted((state.get("audit") or {}).items()):
                case_id = f"{fsm_id}.{state_name}.{case_name}.audit"
                cases[case_id] = {"fsm": fsm_id, "state": state_name, "name": case_name, **case}
    return cases


def _derive_capability_transitions(contract: dict[str, Any]) -> None:
    """Derive transition capability details from model lifecycle declarations.

    Authored sources should not have to repeat the same state transition in both
    the model lifecycle and the capability. The compiled contract remains
    explicit for downstream projections and validators.
    """
    by_capability: dict[str, dict[str, Any]] = {}
    for model_id, model in contract.get("models", {}).items():
        lifecycle = model.get("lifecycle")
        if not lifecycle:
            continue
        field = lifecycle["field"]
        for transition in lifecycle.get("transitions", []):
            capability_id = transition["triggered_by"]
            if capability_id in by_capability:
                raise ContractError(f"Capability {capability_id} is used by multiple lifecycle transitions")
            by_capability[capability_id] = {
                "model": model_id,
                "field": field,
                "from": transition["from"],
                "to": transition["to"],
            }

    for capability_id, capability in contract.get("capabilities", {}).items():
        if capability.get("archetype") != "transition" or "transition" in capability:
            continue
        derived = by_capability.get(capability_id)
        if not derived:
            continue
        capability["transition"] = derived


def _derive_events(contract: dict[str, Any]) -> dict[str, Any]:
    events: dict[str, Any] = copy.deepcopy(contract.get("events", {}))
    for capability_id, capability in sorted(contract["capabilities"].items()):
        for outcome_id, outcome in sorted(capability["outcomes"].items()):
            for emit in outcome.get("emits", []):
                event_id = _emit_event_id(emit)
                if outcome["kind"] != "success":
                    raise ContractError(f"Capability {capability_id} failure outcome {outcome_id} must not emit events")
                payload_type = events.get(event_id, {}).get("payload", outcome["result"])
                event = events.setdefault(event_id, {
                    "emitted_by": [],
                    "payload": payload_type,
                    "basis": capability["basis"],
                })
                _validate_emit_payload_mapping(contract, capability_id, capability, outcome_id, outcome, event_id, event["payload"], emit)
                event["emitted_by"].append(capability_id)
    return events


def _emit_event_id(emit: Any) -> str:
    if isinstance(emit, str):
        return emit
    return emit["event"]


def _derive_refs(contract: dict[str, Any]) -> dict[str, list[str]]:
    refs: dict[str, set[str]] = {kind: set() for kind in REF_KINDS}
    for capability_id, capability in contract["capabilities"].items():
        refs["policy"].add(capability["policy"])
    refs["text"].update(contract.get("copies", {}))
    refs["asset"].update(contract.get("assets", {}))
    for fsm_id in contract["fsms"]:
        refs["state_machine"].add(fsm_id)
    for owner in contract["fsms"].values():
        for datum in owner.get("data", []):
            refs["query"].add(datum["query"])
        for state in owner.get("states", {}).values():
            for datum in state.get("data", []):
                refs["query"].add(datum["query"])
            refs["surface"].add(state["surface"])
            refs["text"].update(state["copy"])
            refs["asset"].update(state["assets"])
    for entry in contract["entries"].values():
        for ref_kind, field in [
            ("route", "route"),
            ("endpoint", "endpoint"),
            ("command", "command_ref"),
            ("workflow", "workflow_ref"),
        ]:
            if field in entry:
                refs[ref_kind].add(entry[field])
    for fsm_id, fsm in contract["fsms"].items():
        if _fsm_has_textual_screen(fsm):
            refs["screen"].add(rules.screen_ref(fsm_id))
    for workflow in contract["workflows"].values():
        refs["workflow"].add(workflow["ref"])
    return {kind: sorted(values) for kind, values in sorted(refs.items()) if values}


def _fsm_has_textual_screen(fsm: dict[str, Any]) -> bool:
    return any(
        "textual" in (state.get("layout") or {}) or "textual" in (state.get("presentation") or {})
        for state in fsm.get("states", {}).values()
    )


def _semantic_validate(contract: dict[str, Any], used_facts: set[str]) -> None:
    _validate_copy_assets(contract)
    _validate_content_cases(contract)
    _validate_audit_profiles(contract)
    _validate_models(contract)
    _validate_capabilities(contract)
    _validate_fsms(contract)
    _validate_fsm_message_payload_consistency(contract)
    _validate_entries(contract)
    _validate_workflows(contract)
    _validate_fixtures(contract)
    _validate_facts(contract)
    _validate_scenarios(contract)
    _validate_audit_cases(contract)
    _validate_facts_are_used(contract, used_facts)



def _validate_copy_assets(contract: dict[str, Any]) -> None:
    used_copy: set[str] = set()
    used_assets: set[str] = set()
    for owner in contract.get("fsms", {}).values():
        for state in owner.get("states", {}).values():
            used_copy.update(state.get("copy", []))
            used_assets.update(state.get("assets", []))
    declared_copy = set(contract.get("copies", {}))
    declared_assets = set(contract.get("assets", {}))
    if declared_copy != used_copy:
        raise ContractError(_diff_message("copy placeholders", used_copy, declared_copy))
    if declared_assets != used_assets:
        raise ContractError(_diff_message("asset placeholders", used_assets, declared_assets))
    for copy_id, item in contract.get("copies", {}).items():
        max_chars = item.get("max_chars")
        if max_chars is not None and len(item["placeholder"]) > max_chars:
            raise ContractError(f"Copy {copy_id} placeholder exceeds max_chars")
    for asset_id, item in contract.get("assets", {}).items():
        alt_copy = item.get("alt_copy")
        if alt_copy and alt_copy not in declared_copy:
            raise ContractError(f"Asset {asset_id} alt_copy references unknown copy {alt_copy}")




def _validate_content_cases(contract: dict[str, Any]) -> None:
    final_refs = {
        ref
        for section in ["copies", "assets"]
        for ref, item in contract.get(section, {}).items()
        if item.get("resolver")
    }
    declared_case_refs: set[str] = set()
    for ref, item in list(contract.get("copies", {}).items()) + list(contract.get("assets", {}).items()):
        resolver = item.get("resolver")
        if resolver:
            if resolver != ref:
                raise ContractError(f"Content resolver for {ref} must equal the content id")
            if not item.get("args"):
                # Arg-less resolvers are allowed, but declaring args is preferred for dynamic content.
                pass
    for case_id, case in contract.get("content_cases", {}).items():
        ref = case["ref"]
        section = "copies" if ref.startswith("text.") else "assets"
        if ref not in contract.get(section, {}):
            raise ContractError(f"Content case {case_id} references unknown {section[:-1]} {ref}")
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


def _validate_audit_profiles(contract: dict[str, Any]) -> None:
    if contract.get("fsms") and not contract.get("audit_profiles"):
        raise ContractError("At least one audit_profile is required when fsms are declared")


def _validate_audit_cases(contract: dict[str, Any]) -> None:
    cases = audit_cases(contract)
    composable_states = {
        (fsm_id, state_name)
        for fsm_id, fsm in contract.get("fsms", {}).items()
        for state_name, state in fsm.get("states", {}).items()
        if state.get("layout") or state.get("mounts")
    }
    covered_composable_states: set[tuple[str, str]] = set()
    for case_id, case in cases.items():
        fsm_id = case["fsm"]
        state_name = case["state"]
        fsm = contract["fsms"][fsm_id]
        state = fsm["states"][state_name]
        if case["profile"] not in contract.get("audit_profiles", {}):
            raise ContractError(f"Audit case {case_id} references unknown audit_profile {case['profile']}")
        profile = contract["audit_profiles"][case["profile"]]
        for surface in case.get("surfaces", []):
            if surface not in profile:
                raise ContractError(f"Audit case {case_id} uses {surface} but audit_profile {case['profile']} does not declare {surface}")
        for fixture_id in case.get("fixtures", []):
            if fixture_id not in contract["fixtures"]:
                raise ContractError(f"Audit case {case_id} references unknown fixture {fixture_id}")
        fixture_values = _fixture_namespace(contract, case.get("fixtures", []), f"audit case {case_id}")
        _validate_fixture_templates(case, fixture_values, f"audit case {case_id}")
        for fact_use in case.get("facts", []):
            fact_id = fact_use["use"]
            _validate_fixture_templates(contract["facts"][fact_id], fixture_values, f"audit case {case_id} fact {fact_id}")
        if state.get("fields") and not _setup_has_model(contract, case.get("fixtures", []), case.get("facts", []), fsm["model"]):
            raise ContractError(f"Audit case {case_id} renders fields for {fsm_id}.{state_name} but does not include a {fsm['model']} fixture or fact")
        if state.get("mounts"):
            mounted_instances = {mount["id"]: mount for mount in state["mounts"]}
            expected_instances = case.get("instances")
            if not expected_instances:
                raise ContractError(f"Audit case {case_id} for composed FSM state {fsm_id}.{state_name} must declare instances")
            if set(expected_instances) != set(mounted_instances):
                raise ContractError(f"Audit case {case_id} instance state vector must exactly cover mounted FSM instances")
            for instance_id, expected in expected_instances.items():
                child_fsm_id = mounted_instances[instance_id]["fsm"]
                if expected["state"] not in contract["fsms"][child_fsm_id]["states"]:
                    raise ContractError(f"Audit case {case_id} references unknown FSM state {child_fsm_id}.{expected['state']}")
                selected_state = contract["fsms"][child_fsm_id]["states"][expected["state"]]
                if selected_state.get("fields") and not _setup_has_model(contract, case.get("fixtures", []), case.get("facts", []), contract["fsms"][child_fsm_id]["model"]):
                    raise ContractError(f"Audit case {case_id} renders fields for {child_fsm_id}.{expected['state']} but does not include a {contract['fsms'][child_fsm_id]['model']} fixture or fact")
            covered_composable_states.add((fsm_id, state_name))
    missing_composed = sorted(f"{fsm_id}.{state_name}" for fsm_id, state_name in composable_states - covered_composable_states)
    if missing_composed:
        raise ContractError("Missing audit coverage for composed FSM states: " + ", ".join(missing_composed))
    _validate_fsm_state_fixture_coverage(contract)


def _validate_fsm_state_fixture_coverage(contract: dict[str, Any]) -> None:
    for fsm_id, fsm in contract.get("fsms", {}).items():
        for state_name, state in fsm.get("states", {}).items():
            if state.get("fields") and not _setup_has_model(contract, list(contract.get("fixtures", {})), _all_fact_uses(contract), fsm["model"]):
                raise ContractError(f"Rendered fields for {fsm_id}.{state_name} require at least one {fsm['model']} fixture or fact")


def _setup_has_model(contract: dict[str, Any], fixture_ids: list[str], fact_uses: list[dict[str, str]], model_id: str) -> bool:
    return _fixtures_include_model(contract, fixture_ids, model_id) or _fact_uses_include_model(contract, fact_uses, model_id)


def _fixtures_include_model(contract: dict[str, Any], fixture_ids: list[str], model_id: str) -> bool:
    for fixture_id in fixture_ids:
        if fixture_id in contract.get("fixtures", {}) and _value_contains_model(contract["fixtures"][fixture_id]["values"], model_id):
            return True
    return False


def _fact_uses_include_model(contract: dict[str, Any], fact_uses: list[dict[str, str]], model_id: str) -> bool:
    for fact_use in fact_uses:
        fact_id = fact_use["use"]
        fact = contract["facts"].get(fact_id)
        if not fact:
            continue
        kind, body = _one_fact(fact, f"Fact {fact_id}")
        if kind == "present" and body["model"] == model_id:
            return True
    return False


def _all_fact_uses(contract: dict[str, Any]) -> list[dict[str, str]]:
    return [{"use": fact_id} for fact_id in contract.get("facts", {})]


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
            if transition["triggered_by"] not in contract["capabilities"]:
                raise ContractError(
                    f"Model {rid} lifecycle transition references unknown operation {transition['triggered_by']}"
                )


def _validate_capabilities(contract: dict[str, Any]) -> None:
    models = contract["models"]
    capabilities = contract["capabilities"]
    for cid, cap in capabilities.items():
        _validate_capability_relationships(cid, cap, models)
        transition = cap.get("transition")
        if transition:
            model_id = transition["model"]
            lifecycle = models[model_id].get("lifecycle")
            if not lifecycle:
                raise ContractError(f"Capability {cid} declares transition but {model_id} has no lifecycle")
            if transition["field"] != lifecycle["field"]:
                raise ContractError(f"Capability {cid} transition field does not match model lifecycle")
            if transition["from"] not in lifecycle["states"] or transition["to"] not in lifecycle["states"]:
                raise ContractError(f"Capability {cid} transition references unknown lifecycle state")
    for rid, model in models.items():
        lifecycle = model.get("lifecycle")
        if not lifecycle:
            continue
        for transition in lifecycle.get("transitions", []):
            triggered_by = transition["triggered_by"]
            capability = capabilities[triggered_by]
            if capability["archetype"] != "transition":
                raise ContractError(
                    f"Model {rid} lifecycle transition {triggered_by} must reference a transition operation"
                )
            cap_transition = capability.get("transition")
            if (
                not cap_transition
                or cap_transition["model"] != rid
                or cap_transition["from"] != transition["from"]
                or cap_transition["to"] != transition["to"]
            ):
                raise ContractError(f"Model {rid} lifecycle and operation {triggered_by} disagree")
    for event_id, event in contract["events"].items():
        for cap_id in event["emitted_by"]:
            if cap_id not in capabilities:
                raise ContractError(f"Event {event_id} emitted by unknown capability {cap_id}")


def _validate_capability_relationships(cid: str, cap: dict[str, Any], models: dict[str, Any]) -> None:
    _validate_capability_outcomes(cid, cap)
    for field in ["creates", "reads", "updates", "deletes"]:
        for model_id in cap.get(field, []):
            if model_id not in models:
                raise ContractError(f"Capability {cid} {field} unknown model {model_id}")

    if "transition" in cap:
        model_id = cap["transition"]["model"]
        if model_id not in models:
            raise ContractError(f"Capability {cid} transition references unknown model {model_id}")

    archetype = cap["archetype"]
    if archetype == "create":
        _require_exact_relationship(cid, cap, "creates", 1)
        _reject_relationships(cid, cap, {"reads", "updates", "deletes", "transition"})
        _require_output_model(cid, cap, cap["creates"][0])
    elif archetype == "read":
        _require_exact_relationship(cid, cap, "reads", 1)
        _reject_relationships(cid, cap, {"creates", "updates", "deletes", "transition"})
        _require_output_model(cid, cap, cap["reads"][0])
    elif archetype == "list":
        _require_exact_relationship(cid, cap, "reads", 1)
        _reject_relationships(cid, cap, {"creates", "updates", "deletes", "transition"})
        expected_model = cap["reads"][0]
        if not is_array_of_model(_success_result_type(cap), expected_model):
            raise ContractError(f"Capability {cid} list success outcome result must be {type_display(array_of({'model': expected_model}))}")
    elif archetype == "query":
        _require_relationship(cid, cap, "reads")
        _reject_relationships(cid, cap, {"creates", "updates", "deletes", "transition"})
    elif archetype == "update":
        _require_exact_relationship(cid, cap, "updates", 1)
        _reject_relationships(cid, cap, {"creates", "deletes", "transition"})
        _require_output_model(cid, cap, cap["updates"][0])
    elif archetype == "delete":
        _require_exact_relationship(cid, cap, "deletes", 1)
        _reject_relationships(cid, cap, {"creates", "updates", "transition"})
    elif archetype == "transition":
        if "transition" not in cap:
            raise ContractError(f"Transition capability {cid} must declare transition")
        _reject_relationships(cid, cap, {"creates", "reads", "updates", "deletes"})
        _require_output_model(cid, cap, cap["transition"]["model"])
    elif archetype == "command":
        if "transition" in cap:
            raise ContractError(f"Only transition capabilities may declare transition: {cid}")
    else:  # pragma: no cover - schema prevents this.
        raise ContractError(f"Unsupported capability archetype {archetype}: {cid}")


def _require_relationship(cid: str, cap: dict[str, Any], field: str) -> None:
    if not cap.get(field):
        raise ContractError(f"Capability {cid} archetype {cap['archetype']} must declare {field}")


def _require_exact_relationship(cid: str, cap: dict[str, Any], field: str, count: int) -> None:
    _require_relationship(cid, cap, field)
    actual = len(cap[field])
    if actual != count:
        raise ContractError(f"Capability {cid} archetype {cap['archetype']} must declare exactly {count} {field}")


def _reject_relationships(cid: str, cap: dict[str, Any], fields: set[str]) -> None:
    extras = sorted(field for field in fields if field in cap)
    if extras:
        raise ContractError(f"Capability {cid} archetype {cap['archetype']} does not support fields: {extras}")


def _require_output_model(cid: str, cap: dict[str, Any], model_id: str) -> None:
    if model_name(_success_result_type(cap)) != model_id:
        raise ContractError(f"Capability {cid} success outcome result must be {model_id}")


def _validate_capability_outcomes(cid: str, cap: dict[str, Any]) -> None:
    outcomes = cap["outcomes"]
    successes = _success_outcomes(cap)
    failures = _failure_outcomes(cap)
    if len(successes) != 1:
        raise ContractError(f"Capability {cid} must declare exactly one success outcome")
    if not failures:
        raise ContractError(f"Capability {cid} must declare at least one failure outcome")
    unknown_kinds = sorted(
        f"{name}:{outcome['kind']}" for name, outcome in outcomes.items() if outcome["kind"] not in {"success", "failure"}
    )
    if unknown_kinds:
        raise ContractError(f"Capability {cid} has unsupported outcome kinds: {unknown_kinds}")
    for outcome_id, outcome in outcomes.items():
        emits = outcome.get("emits", [])
        emit_ids = [_emit_event_id(emit) for emit in emits]
        if len(emit_ids) != len(set(emit_ids)):
            raise ContractError(f"Capability {cid} outcome {outcome_id} emits duplicate events")
        if outcome["kind"] == "failure":
            if emits:
                raise ContractError(f"Capability {cid} failure outcome {outcome_id} must not emit events")
            if not is_problem_type(outcome["result"]):
                raise ContractError(f"Capability {cid} failure outcome {outcome_id} result must be Problem or a *Problem type")


def _validate_emit_payload_mapping(
    contract: dict[str, Any],
    capability_id: str,
    capability: dict[str, Any],
    outcome_id: str,
    outcome: dict[str, Any],
    event_id: str,
    event_payload: Any,
    emit: Any,
) -> None:
    label = f"Capability {capability_id} outcome {outcome_id} emit {event_id}"
    source_scopes: TypeScopes = {
        "input": _type_scope(capability["input"]),
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
    has_with = "with" in emit
    if has_payload == has_with:
        raise ContractError(f"{label} must declare exactly one of payload or with")
    if has_payload:
        source = emit["payload"]
        actual = _reference_expression_type(contract, f"{label} payload source", source, source_scopes)
        if not type_equals(actual, event_payload):
            raise ContractError(f"{label} payload source {source} type must be {type_display(event_payload)}, got {type_display(actual)}")
        return

    _validate_mapping_to_type(contract, label, emit["with"], event_payload, source_scopes)


def _validate_fsms(contract: dict[str, Any]) -> None:
    for fsm_id, fsm in contract["fsms"].items():
        if not fsm_id.startswith("state_machine."):
            raise ContractError(f"FSM id must start with state_machine.: {fsm_id}")
        if fsm["model"] not in contract["models"]:
            raise ContractError(f"FSM {fsm_id} references unknown model {fsm['model']}")
        _validate_data_bindings(
            contract, f"FSM {fsm_id}", fsm.get("data", []), fsm.get("context", {}), model=fsm["model"]
        )
        if fsm["initial"] not in fsm["states"]:
            raise ContractError(f"FSM {fsm_id} initial state is not declared: {fsm['initial']}")
        model_fields = set(contract["models"][fsm["model"]]["fields"])
        for state_name, state in fsm["states"].items():
            _validate_fsm_state(
                contract,
                f"FSM {fsm_id}",
                state_name,
                state,
                field_names=model_fields,
                data_context=fsm.get("context", {}),
                model=fsm["model"],
            )
            if state.get("mounts") or state.get("layout") or state.get("sync"):
                _validate_state_composition(contract, fsm_id, fsm, state_name, state)
        _validate_field_state_data_sources(f"FSM {fsm_id}", fsm["states"], fsm.get("data", []), fsm.get("transitions", []))
        _validate_fsm_transitions(contract, fsm_id, fsm)
        _validate_fsm_messages(fsm_id, fsm)


def _validate_fsm_state(
    contract: dict[str, Any],
    owner_label: str,
    state_name: str,
    state: dict[str, Any],
    field_names: set[str],
    data_context: dict[str, Any] | None = None,
    model: str | None = None,
) -> None:
    _validate_data_bindings(contract, f"{owner_label}.{state_name}", state.get("data", []), data_context, model=model)
    for field in state.get("fields", []):
        if field not in field_names:
            raise ContractError(f"{owner_label}.{state_name} field slot is not declared on the model/context: {field}")
    for action in state["actions"]:
        if action not in contract["capabilities"]:
            raise ContractError(f"{owner_label}.{state_name} action references unknown capability {action}")
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
        capability_id = datum["capability"]
        if capability_id not in contract["capabilities"]:
            raise ContractError(f"{owner_label} data references unknown capability {capability_id}")
        capability = contract["capabilities"][capability_id]
        if capability["archetype"] not in {"read", "list", "query"}:
            raise ContractError(f"{owner_label} data capability must be read, list, or query: {capability_id}")
        if model and model not in capability.get("reads", []):
            raise ContractError(f"{owner_label} data capability {capability_id} must read model {model}")
        input_keys = set((capability.get("input") or {}).keys())
        missing = sorted(input_keys - context_keys)
        if missing:
            raise ContractError(
                f"{owner_label} data capability {capability_id} input not provided by context: {missing}"
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
    if owner_data or states[state_name].get("data"):
        return True
    for transition in transitions:
        if transition["to"] != state_name or not _is_data_event(transition["on"]):
            continue
        source_state = states.get(transition["from"], {})
        if owner_data or source_state.get("data"):
            return True
    return False


def _validate_fsm_transitions(contract: dict[str, Any], fsm_id: str, fsm: dict[str, Any]) -> None:
    states = set(fsm["states"])
    for transition in fsm.get("transitions", []):
        if transition["from"] not in states or transition["to"] not in states:
            raise ContractError(f"FSM {fsm_id} transition uses unknown state: {transition}")
        if _is_data_event(transition["on"]) and not _transition_data_bindings(fsm, transition):
            raise ContractError(
                f"FSM {fsm_id} transition uses data message without FSM or source-state data: {transition['on']}"
            )
        message_payload = _fsm_message_payload(fsm, "accepts", transition["on"], f"FSM {fsm_id} transition message")
        for effect in transition.get("effects", []):
            kind, body = _one(effect, f"FSM {fsm_id} transition effect")
            if kind == "set":
                if body["context"] not in fsm.get("context", {}):
                    raise ContractError(f"FSM {fsm_id} transition sets undeclared context: {body['context']}")
            elif kind == "emit":
                emitted_payload = _fsm_message_payload(fsm, "emits", body["message"], f"FSM {fsm_id} transition emit")
                _validate_data_map(
                    contract=contract,
                    label=f"FSM {fsm_id} transition emit {body['message']} data",
                    data=body["data"],
                    payload=emitted_payload,
                    scopes={"message": _type_scope(message_payload), "context": _type_scope(fsm.get("context", {}))},
                )
            else:  # pragma: no cover - schema prevents this.
                raise ContractError(f"FSM {fsm_id} unsupported transition effect: {kind}")
    for transition in fsm.get("transitions", []):
        if not _transition_has_audit_content(fsm, transition):
            raise ContractError(
                f"FSM {fsm_id} transition {transition['on']} from {transition['from']} "
                f"to {transition['to']} must declare basis, data, or effects"
            )


def _validate_fsm_messages(fsm_id: str, fsm: dict[str, Any]) -> None:
    messages = fsm.get("messages", _empty_fsm_messages())
    declared_accepts = set(messages.get("accepts", {}))
    declared_emits = set(messages.get("emits", {}))
    ambiguous = sorted(declared_accepts & declared_emits)
    if ambiguous:
        raise ContractError(f"FSM {fsm_id} declares message as both accepted and emitted: {ambiguous}")
    accepted = _fsm_accepts(fsm)
    emitted = _fsm_emits(fsm)
    orphan_accepts = sorted(declared_accepts - accepted)
    if orphan_accepts:
        raise ContractError(f"FSM {fsm_id} declares accepted message without transition: {orphan_accepts}")
    orphan_emits = sorted(declared_emits - emitted)
    if orphan_emits:
        raise ContractError(f"FSM {fsm_id} declares emitted message without emit effect: {orphan_emits}")
    undeclared_accepts = sorted(accepted - declared_accepts)
    if undeclared_accepts:
        raise ContractError(f"FSM {fsm_id} accepts message without declaring it: {undeclared_accepts}")
    undeclared_emits = sorted(emitted - declared_emits)
    if undeclared_emits:
        raise ContractError(f"FSM {fsm_id} emits message without declaring it: {undeclared_emits}")


def _validate_fsm_message_payload_consistency(contract: dict[str, Any]) -> None:
    declared: dict[str, tuple[str, str, dict[str, Any]]] = {}
    domain_events = set(contract.get("events", {}))
    for fsm_id, fsm in contract.get("fsms", {}).items():
        messages = fsm.get("messages", _empty_fsm_messages())
        for direction in ("accepts", "emits"):
            for message_id, message in messages.get(direction, {}).items():
                if message_id in domain_events:
                    raise ContractError(f"FSM message {message_id} conflicts with domain event {message_id}")
                payload = message["payload"]
                existing = declared.get(message_id)
                if existing and (
                    set(existing[2]) != set(payload)
                    or any(not type_equals(existing[2][key], payload[key]) for key in payload)
                ):
                    first_fsm, first_direction, first_payload = existing
                    raise ContractError(
                        f"FSM message {message_id} payload differs between {first_fsm}.{first_direction} "
                        f"and {fsm_id}.{direction}: "
                        f"{ {key: type_display(value) for key, value in first_payload.items()} } vs "
                        f"{ {key: type_display(value) for key, value in payload.items()} }"
                    )
                declared[message_id] = (fsm_id, direction, payload)


def _validate_state_composition(contract: dict[str, Any], fsm_id: str, fsm: dict[str, Any], state_name: str, state: dict[str, Any]) -> None:
    label = f"{fsm_id}.{state_name}"
    parent_fsm_id = fsm_id
    parent_fsm = fsm
    if not state.get("layout"):
        raise ContractError(f"Composed FSM state {label} must declare layout")
    if not state.get("mounts"):
        raise ContractError(f"Composed FSM state {label} must mount at least one FSM")
    regions = set(layout_regions(state["layout"]))
    if not regions:
        raise ContractError(f"Composed FSM state {label} must declare layout regions")
    mounts: dict[str, dict[str, Any]] = {}
    for mount in state["mounts"]:
        if mount["id"] in mounts:
            raise ContractError(f"Composed FSM state {label} has duplicate FSM mount: {mount['id']}")
        mounts[mount["id"]] = mount
        if mount["region"] not in regions:
            raise ContractError(f"Composed FSM state {label} mounts FSM in undeclared region: {mount['region']}")
        child_fsm_id = mount["fsm"]
        if child_fsm_id not in contract["fsms"]:
            raise ContractError(f"Composed FSM state {label} mounts unknown FSM: {child_fsm_id}")
        child_fsm = contract["fsms"][child_fsm_id]
        if mount["initial"] not in child_fsm["states"]:
            raise ContractError(f"Composed FSM state {label}.{mount['id']} initial state is unknown: {mount['initial']}")
        selected = mount.get("selected")
        if selected and selected["state"] not in child_fsm["states"]:
            raise ContractError(f"Composed FSM state {label}.{mount['id']} selected state is unknown: {selected['state']}")
        if selected:
            _validate_condition_context(label, parent_fsm.get("context", {}), selected["when"])
        mount_context = mount.get("context", {})
        expected_context = set(child_fsm.get("context", {}))
        if set(mount_context) != expected_context:
            raise ContractError(
                f"Composed FSM state {label}.{mount['id']} context keys {sorted(mount_context)} "
                f"must exactly match FSM context {sorted(expected_context)}"
            )
        _validate_fsm_context_refs(
            contract,
            label,
            parent_fsm.get("context", {}),
            child_fsm.get("context", {}),
            mount_context,
        )
    used_regions = {mount["region"] for mount in state["mounts"]}
    missing_required = [region for region, spec in layout_regions(state["layout"]).items() if spec.get("required") and region not in used_regions]
    if missing_required:
        raise ContractError(f"Composed FSM state {label} missing required layout regions: {missing_required}")
    _validate_layout_contract(label, state["layout"], regions, set(mounts))
    _validate_sync_rules(contract, parent_fsm_id, state_name, parent_fsm, state, mounts)


def _validate_layout_contract(fsm_id: str, layout: dict[str, Any], regions: set[str], mounts: set[str]) -> None:
    html_regions = set(layout_html_regions(layout))
    textual_regions = set(layout_textual_containers(layout))
    if html_regions and textual_regions and html_regions != textual_regions:
        raise ContractError(f"Composed FSM {fsm_id} layout regions differ between html and textual")
    for rule in ((layout_html(layout).get("css") or {}).get("rules", [])):
        _validate_composition_selector(fsm_id, rule["selector"], regions, mounts, "CSS")
    textual = layout_textual(layout)
    for rule in ((textual.get("tcss") or {}).get("rules", [])):
        _validate_composition_selector(fsm_id, rule["selector"], regions, mounts, "TCSS")


def _validate_condition_context(fsm_id: str, context: dict[str, Any], condition: Any) -> None:
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
            raise ContractError(f"Composed FSM {fsm_id} condition has malformed runtime reference: {condition}") from exc
        if ref.root != "state_machine":
            raise ContractError(f"Composed FSM {fsm_id} condition references unavailable runtime root: ${ref.root}")
        keys = [ref.path[0]]
    else:
        keys = []
    for key in keys:
        if key not in context:
            raise ContractError(f"Composed FSM {fsm_id} condition references undeclared context: {key}")


def _validate_fsm_context_refs(
    contract: dict[str, Any],
    fsm_id: str,
    parent_context: dict[str, Any],
    child_context: dict[str, Any],
    mapping: dict[str, Any],
) -> None:
    scopes = {"state_machine": _type_scope(parent_context)}
    for key, value in mapping.items():
        _validate_expression_type(
            contract,
            f"Composed FSM {fsm_id} context {key}",
            value,
            child_context[key],
            scopes,
        )


def _fsm_emits(fsm: dict[str, Any]) -> set[str]:
    emits: set[str] = set()
    for transition in fsm.get("transitions", []):
        for effect in transition.get("effects", []):
            kind, body = _one(effect, "fsm transition effect")
            if kind == "emit":
                emits.add(body["message"])
    return emits


def _fsm_accepts(fsm: dict[str, Any]) -> set[str]:
    return {transition["on"] for transition in fsm.get("transitions", [])}


def _fsm_message_payload(fsm: dict[str, Any], direction: str, message_id: str, label: str) -> dict[str, Any]:
    message = fsm.get("messages", {}).get(direction, {}).get(message_id)
    if not message:
        raise ContractError(f"{label} references undeclared FSM message: {message_id}")
    return message.get("payload", {})


def _validate_data_map(
    contract: dict[str, Any] | None,
    label: str,
    data: dict[str, Any],
    payload: dict[str, Any],
    scopes: TypeScopes,
) -> None:
    actual = set(data)
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
        _validate_expression_type(contract, f"{label}.{field}", data[field], expected_type, scopes)


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


def _transition_data_bindings(fsm: dict[str, Any], transition: dict[str, Any]) -> list[dict[str, Any]]:
    source_state = fsm.get("states", {}).get(transition["from"], {})
    return source_state.get("data", []) or fsm.get("data", [])


def _transition_target_data_bindings(fsm: dict[str, Any], transition: dict[str, Any]) -> list[dict[str, Any]]:
    target_state = fsm.get("states", {}).get(transition["to"], {})
    return target_state.get("data", [])


def _transition_has_audit_content(fsm: dict[str, Any], transition: dict[str, Any]) -> bool:
    if transition.get("basis") or transition.get("effects"):
        return True
    if _is_data_event(transition["on"]):
        return bool(_transition_data_bindings(fsm, transition))
    return bool(_transition_target_data_bindings(fsm, transition))


def _validate_sync_rules(
    contract: dict[str, Any],
    fsm_id: str,
    state_name: str,
    fsm: dict[str, Any],
    state: dict[str, Any],
    mounts: dict[str, dict[str, Any]],
) -> None:
    label = f"{fsm_id}.{state_name}"
    seen: set[str] = set()
    context = fsm.get("context", {})
    for rule in state.get("sync", []):
        if rule["id"] in seen:
            raise ContractError(f"Composed FSM state {label} has duplicate sync rule: {rule['id']}")
        seen.add(rule["id"])
        source_id = rule["when"]["instance"]
        if source_id not in mounts:
            raise ContractError(f"Composed FSM state {label} sync source instance is unknown: {source_id}")
        source_fsm = contract["fsms"][mounts[source_id]["fsm"]]
        message_id = rule["when"]["message"]
        if message_id not in _fsm_emits(source_fsm):
            raise ContractError(f"Composed FSM state {label} sync listens for message the source does not emit: {message_id}")
        source_payload = _fsm_message_payload(source_fsm, "emits", message_id, f"Composed FSM state {label} sync trigger")
        for effect in rule["do"]:
            kind, body = _one(effect, f"composed FSM state {label} sync effect")
            if kind == "set":
                if body["context"] not in context:
                    raise ContractError(f"Composed FSM state {label} sync sets undeclared context: {body['context']}")
                if "from" in body:
                    _validate_expression_type(
                        contract,
                        f"Composed FSM state {label} sync set {body['context']}",
                        body["from"],
                        context[body["context"]],
                        {"message": _type_scope(source_payload), "state_machine": _type_scope(context)},
                    )
            elif kind == "send":
                target_id = body["instance"]
                if target_id not in mounts:
                    raise ContractError(f"Composed FSM state {label} sync sends to unknown instance: {target_id}")
                target_fsm = contract["fsms"][mounts[target_id]["fsm"]]
                if body["message"] not in _fsm_accepts(target_fsm):
                    raise ContractError(f"Composed FSM state {label} sync sends message the target does not accept: {body['message']}")
                target_payload = _fsm_message_payload(target_fsm, "accepts", body["message"], f"Composed FSM state {label} sync send")
                _validate_data_map(
                    contract=contract,
                    label=f"Composed FSM state {label} sync send {body['message']} to {target_id} data",
                    data=body["data"],
                    payload=target_payload,
                    scopes={"message": _type_scope(source_payload), "state_machine": _type_scope(context)},
                )
            else:  # pragma: no cover - schema prevents this.
                raise ContractError(f"Composed FSM state {label} unsupported sync effect: {kind}")


def _validate_presentation(contract: dict[str, Any], owner_label: str, field_names: set[str], state_name: str, state: dict[str, Any]) -> None:
    presentation = state.get("presentation") or {}
    if not presentation:
        return
    copy_slots = {ref.rsplit(".", 1)[-1] for ref in state["copy"]}
    asset_slots = {ref.rsplit(".", 1)[-1] for ref in state["assets"]}
    field_slots = set(state.get("fields", []))
    actions = set(state["actions"])

    html_contract = presentation.get("html") or {}
    for slot in html_contract.get("slots", []):
        kind = slot["kind"]
        if kind == "copy" and slot["slot"] not in copy_slots:
            raise ContractError(f"{owner_label}.{state_name} HTML copy slot is not declared: {slot['slot']}")
        if kind == "asset" and slot["slot"] not in asset_slots:
            raise ContractError(f"{owner_label}.{state_name} HTML asset slot is not declared: {slot['slot']}")
        if kind == "asset" and slot.get("alt_copy_slot") and slot["alt_copy_slot"] not in copy_slots:
            raise ContractError(f"{owner_label}.{state_name} HTML asset alt_copy_slot is not declared: {slot['alt_copy_slot']}")
        if kind == "field" and slot["slot"] not in field_slots:
            raise ContractError(f"{owner_label}.{state_name} HTML field slot is not declared: {slot['slot']}")
        if kind == "action" and slot["ref"] not in actions:
            raise ContractError(f"{owner_label}.{state_name} HTML action slot is not declared: {slot['ref']}")

    for rule in (presentation.get("css") or {}).get("rules", []):
        _validate_style_selector(owner_label, state_name, rule["selector"], copy_slots, asset_slots, field_slots, actions, "CSS")

    textual = presentation.get("textual") or {}
    widgets = textual.get("widgets", [])
    widget_ids = [widget["id"] for widget in widgets]
    if len(widget_ids) != len(set(widget_ids)):
        raise ContractError(f"{owner_label}.{state_name} Textual widgets contain duplicate ids")
    widget_targets = {"copy": set(), "asset": set(), "field": set(), "action": set()}
    for widget in widgets:
        bind_kind, bind_value = _one(widget["bind"], f"{owner_label}.{state_name} textual widget bind")
        if bind_kind == "copy" and bind_value not in copy_slots:
            raise ContractError(f"{owner_label}.{state_name} Textual widget copy bind is not declared: {bind_value}")
        if bind_kind == "asset" and bind_value not in asset_slots:
            raise ContractError(f"{owner_label}.{state_name} Textual widget asset bind is not declared: {bind_value}")
        if bind_kind == "action" and bind_value not in actions:
            raise ContractError(f"{owner_label}.{state_name} Textual widget action bind is not declared: {bind_value}")
        if bind_kind == "field" and bind_value not in field_slots:
            raise ContractError(f"{owner_label}.{state_name} Textual widget field bind is not declared: {bind_value}")
        if bind_kind in widget_targets:
            widget_targets[bind_kind].add(bind_value)
    for rule in textual.get("tcss", {}).get("rules", []):
        selector = rule["selector"]
        _validate_style_selector(owner_label, state_name, selector, copy_slots, asset_slots, field_slots, actions, "TCSS")
        if widgets and selector.startswith("slot."):
            name = selector[len("slot."):]
            if name not in widget_targets["copy"] and name not in widget_targets["asset"] and name not in widget_targets["field"]:
                raise ContractError(f"{owner_label}.{state_name} TCSS selector has no matching Textual widget: {selector}")
        if widgets and selector.startswith("action."):
            action = selector[len("action."):]
            if action not in widget_targets["action"]:
                raise ContractError(f"{owner_label}.{state_name} TCSS selector has no matching Textual widget: {selector}")


def _validate_style_selector(
    owner_label: str,
    state_name: str,
    selector: str,
    copy_slots: set[str],
    asset_slots: set[str],
    field_slots: set[str],
    actions: set[str],
    label: str,
) -> None:
    if selector in {"root", "screen"}:
        return
    if selector.startswith("slot."):
        name = selector[len("slot."):]
        if name not in copy_slots and name not in asset_slots and name not in field_slots:
            raise ContractError(f"{owner_label}.{state_name} {label} selector references undeclared slot: {selector}")
        return
    if selector.startswith("action."):
        ref = selector[len("action."):]
        if ref not in actions:
            raise ContractError(f"{owner_label}.{state_name} {label} selector references undeclared action: {ref}")
        return
    raise ContractError(f"{owner_label}.{state_name} {label} selector is not supported: {selector}")


def _validate_composition_selector(fsm_id: str, selector: str, regions: set[str], mounts: set[str], label: str) -> None:
    if selector in {"root", "screen"}:
        return
    if selector.startswith("region."):
        region = selector[len("region."):]
        if region not in regions:
            raise ContractError(f"Composed FSM {fsm_id} {label} selector references undeclared layout region: {selector}")
        return
    if selector.startswith("mount."):
        mount = selector[len("mount."):]
        if mount not in mounts:
            raise ContractError(f"Composed FSM {fsm_id} {label} selector references undeclared FSM mount: {selector}")
        return
    raise ContractError(f"Composed FSM {fsm_id} {label} selector is not supported: {selector}")


def _validate_entries(contract: dict[str, Any]) -> None:
    for eid, entry in contract["entries"].items():
        surface = entry["surface"]
        _validate_entry_surface_fields(eid, entry)
        _validate_entry_input_shape(eid, entry)
        kind, value = entry_target_pair(entry["target"])
        if surface == "web":
            if kind != "fsm" or value not in contract["fsms"]:
                raise ContractError(f"Web entry {eid} must target a known FSM")
            _validate_fsm_target_surface(contract, eid, entry, value, allowed_surfaces={"html"})
            _require(entry, eid, "path")
            _validate_path_params(entry, eid)
            declared = _entry_input_map(entry, "params")
            _validate_fsm_entry_inputs(contract, eid, value, declared=declared, input_label="input.params")
            _validate_target_bindings(contract, eid, entry, declared)
        elif surface == "api":
            if kind != "capability" or value not in contract["capabilities"]:
                raise ContractError(f"API entry {eid} must target a known capability")
            _require(entry, eid, "method")
            _require(entry, eid, "path")
            _validate_path_params(entry, eid)
            capability = contract["capabilities"][value]
            params = _entry_input_map(entry, "params")
            body = _entry_input_map(entry, "body")
            _validate_api_entry_input(eid, entry, capability, params, body)
            _validate_target_bindings(contract, eid, entry, {**params, **body})
            _validate_api_entry_responses(eid, entry, capability)
        elif surface == "cli":
            _require(entry, eid, "command")
            args = _entry_input_map(entry, "args")
            if kind == "capability":
                if value not in contract["capabilities"]:
                    raise ContractError(f"CLI entry {eid} must target a known capability")
                capability = contract["capabilities"][value]
                _validate_exact_entry_inputs(eid, "input.args", args, capability["input"])
                _validate_target_bindings(contract, eid, entry, args)
                _validate_cli_capability_responses(eid, entry, capability)
            elif kind == "fsm":
                if value not in contract["fsms"]:
                    raise ContractError(f"CLI entry {eid} must target a known FSM")
                _validate_fsm_target_surface(contract, eid, entry, value, allowed_surfaces=set(FSM_RENDER_SURFACES))
                _validate_fsm_entry_inputs(contract, eid, value, declared=args, input_label="input.args")
                _validate_target_bindings(contract, eid, entry, args)
                target_surface = entry_fsm_surface(entry)
                assert target_surface is not None
                if "responses" in entry:
                    raise ContractError(f"CLI entry {eid} targeting an FSM must not declare responses")
            elif kind == "workflow":
                if value not in contract["workflows"]:
                    raise ContractError(f"CLI entry {eid} must target a known workflow")
                _validate_workflow_entry_trigger(contract, eid, entry, value)
                if args:
                    raise ContractError(f"CLI entry {eid} targeting a workflow must not declare input.args")
                _validate_async_entry_responses(eid, entry, require_failure_disposition=False)
            else:
                raise ContractError(f"CLI entry {eid} cannot target raw {kind}")
        elif surface in {"worker", "schedule"}:
            if kind != "workflow" or value not in contract["workflows"]:
                raise ContractError(f"{surface} entry {eid} must target a known workflow")
            _validate_workflow_entry_trigger(contract, eid, entry, value)
            if surface == "schedule":
                _require(entry, eid, "schedule")
                if entry.get("input"):
                    raise ContractError(f"Schedule entry {eid} must not declare input")
            else:
                _validate_event_payload_entry_input(contract, eid, entry, value)
            _validate_async_entry_responses(eid, entry, require_failure_disposition=surface == "worker")
        elif surface == "webhook":
            if kind != "workflow" or value not in contract["workflows"]:
                raise ContractError(f"Webhook entry {eid} must target a known workflow")
            _validate_workflow_entry_trigger(contract, eid, entry, value)
            _require(entry, eid, "path")
            _validate_path_params(entry, eid)
            _validate_event_payload_entry_input(contract, eid, entry, value)
            _validate_webhook_entry_responses(eid, entry)


def _validate_entry_surface_fields(entry_id: str, entry: dict[str, Any]) -> None:
    allowed = {
        "web": {"surface", "input", "target", "basis", "path", "route"},
        "api": {"surface", "input", "target", "responses", "basis", "method", "path", "endpoint"},
        "cli": {"surface", "input", "target", "responses", "basis", "command", "command_ref"},
        "worker": {"surface", "input", "target", "responses", "basis", "workflow_ref"},
        "schedule": {"surface", "input", "target", "responses", "basis", "schedule", "workflow_ref"},
        "webhook": {"surface", "input", "target", "responses", "basis", "path"},
    }[entry["surface"]]
    extra = sorted(set(entry) - allowed)
    if extra:
        raise ContractError(f"Entry {entry_id} surface {entry['surface']} has unsupported fields: {extra}")


def _validate_entry_input_shape(entry_id: str, entry: dict[str, Any]) -> None:
    allowed = {
        "web": {"params"},
        "api": {"params", "body"},
        "cli": {"args"},
        "worker": {"payload"},
        "schedule": set(),
        "webhook": {"params", "payload"},
    }[entry["surface"]]
    input_spec = entry.get("input", {})
    extra = sorted(set(input_spec) - allowed)
    if extra:
        raise ContractError(f"Entry {entry_id} surface {entry['surface']} has unsupported input sections: {extra}")
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


def _validate_fsm_target_surface(
    contract: dict[str, Any],
    entry_id: str,
    entry: dict[str, Any],
    fsm_id: str,
    *,
    allowed_surfaces: set[str],
) -> None:
    surface = entry_fsm_surface(entry)
    if surface is None:
        raise ContractError(f"Entry {entry_id} FSM target must declare surface")
    if surface not in allowed_surfaces:
        raise ContractError(f"Entry {entry_id} cannot target FSM surface {surface!r}")
    if not _fsm_supports_render_surface(contract["fsms"][fsm_id], surface):
        raise ContractError(f"Entry {entry_id} targets FSM {fsm_id} surface {surface} but that FSM does not declare it")


def _fsm_supports_render_surface(fsm: dict[str, Any], surface: str) -> bool:
    return any(
        surface in (state.get("layout") or {}) or surface in (state.get("presentation") or {})
        for state in fsm.get("states", {}).values()
    )


def _validate_workflow_entry_trigger(contract: dict[str, Any], entry_id: str, entry: dict[str, Any], workflow_id: str) -> None:
    trigger = entry_workflow_trigger(entry)
    if trigger is None:
        raise ContractError(f"Entry {entry_id} workflow target must declare trigger")
    workflow_trigger = contract["workflows"][workflow_id]["trigger"]
    if trigger != workflow_trigger:
        raise ContractError(f"Entry {entry_id} workflow trigger must match workflow {workflow_id} trigger")


def _validate_api_entry_input(
    entry_id: str,
    entry: dict[str, Any],
    capability: dict[str, Any],
    params: dict[str, Any],
    body: dict[str, Any],
) -> None:
    cap_input = capability["input"]
    all_input = {**params, **body}
    if set(params) - set(cap_input):
        raise ContractError(f"API entry {entry_id} input.params must be capability input fields")
    if set(body) - set(cap_input):
        raise ContractError(f"API entry {entry_id} input.body must be capability input fields")
    if set(params) & set(body):
        raise ContractError(f"API entry {entry_id} input fields cannot appear in both params and body")
    _validate_entry_input_types(entry_id, "input.params", params, cap_input)
    _validate_entry_input_types(entry_id, "input.body", body, cap_input)
    if entry["method"].lower() in {"get", "delete"}:
        if body:
            raise ContractError(f"API entry {entry_id} {entry['method']} must not declare input.body")
        if set(params) != set(cap_input):
            missing_params = sorted(set(cap_input) - set(params))
            raise ContractError(f"API entry {entry_id} {entry['method']} must declare all capability inputs as input.params: {missing_params}")
    missing = sorted(set(cap_input) - set(all_input))
    if missing:
        raise ContractError(f"API entry {entry_id} input must include every capability input: {missing}")


def _validate_event_payload_entry_input(contract: dict[str, Any], entry_id: str, entry: dict[str, Any], workflow_id: str) -> None:
    trigger = entry_workflow_trigger(entry)
    if not trigger or "event" not in trigger:
        return
    event_id = trigger["event"]
    event = contract["events"].get(event_id)
    if not event:
        raise ContractError(f"Entry {entry_id} workflow trigger references unknown event {event_id}")
    payload_type = (entry.get("input") or {}).get("payload")
    if not type_equals(payload_type, event["payload"]):
        raise ContractError(f"Entry {entry_id} input.payload must be {type_display(event['payload'])}, got {type_display(payload_type)}")


def _validate_target_bindings(
    contract: dict[str, Any],
    entry_id: str,
    entry: dict[str, Any],
    target_input_types: dict[str, Any],
) -> None:
    kind, value = entry_target_pair(entry["target"])
    bindings = entry["target"].get("with", {})
    if kind == "capability":
        expected = contract["capabilities"][value]["input"]
    elif kind == "fsm":
        expected = {name: contract["fsms"][value].get("context", {})[name] for name in target_input_types}
    else:
        if bindings:
            raise ContractError(f"Entry {entry_id} target.with is not supported for workflow targets")
        return
    if set(bindings) != set(expected):
        missing = sorted(set(expected) - set(bindings))
        extra = sorted(set(bindings) - set(expected))
        parts = []
        if missing:
            parts.append("missing: " + ", ".join(missing))
        if extra:
            parts.append("extra: " + ", ".join(extra))
        raise ContractError(f"Entry {entry_id} target.with must exactly bind target input" + (": " + "; ".join(parts) if parts else ""))
    source_scopes: TypeScopes = {"input": _entry_input_source_types(contract, entry)}
    for target_name, source in bindings.items():
        actual_type = _reference_expression_type(
            contract,
            f"Entry {entry_id} target.with.{target_name}",
            source,
            source_scopes,
        )
        expected_type = expected[target_name]
        if not type_equals(actual_type, expected_type):
            raise ContractError(
                f"Entry {entry_id} target.with.{target_name} type mismatch: "
                f"expected {type_display(expected_type)}, got {type_display(actual_type)} from {source}"
            )


def _validate_api_entry_responses(entry_id: str, entry: dict[str, Any], capability: dict[str, Any]) -> None:
    responses = _capability_entry_responses(entry_id, entry, capability)
    statuses: dict[int, str] = {}
    for outcome_id, response in responses.items():
        outcome = capability["outcomes"][outcome_id]
        if set(response) != {"status", "body"}:
            raise ContractError(f"API entry {entry_id} response {outcome_id} must declare exactly status and body")
        status = response["status"]
        if status in statuses:
            raise ContractError(
                f"API entry {entry_id} responses {statuses[status]} and {outcome_id} cannot share HTTP status {status}"
            )
        statuses[status] = outcome_id
        if outcome["kind"] == "success":
            expected = 201 if capability["archetype"] == "create" else 200
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


def _validate_cli_capability_responses(entry_id: str, entry: dict[str, Any], capability: dict[str, Any]) -> None:
    responses = _capability_entry_responses(entry_id, entry, capability)
    exit_codes: dict[int, str] = {}
    for outcome_id, response in responses.items():
        outcome = capability["outcomes"][outcome_id]
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


def _capability_entry_responses(entry_id: str, entry: dict[str, Any], capability: dict[str, Any]) -> dict[str, Any]:
    responses = entry.get("responses", {})
    if set(responses) != set(capability["outcomes"]):
        missing = sorted(set(capability["outcomes"]) - set(responses))
        extra = sorted(set(responses) - set(capability["outcomes"]))
        parts = []
        if missing:
            parts.append("missing: " + ", ".join(missing))
        if extra:
            parts.append("extra: " + ", ".join(extra))
        raise ContractError(f"Entry {entry_id} responses must exactly map capability outcomes" + (": " + "; ".join(parts) if parts else ""))
    return responses


def _validate_response_value(label: str, value: dict[str, Any], expected_type: Any) -> None:
    if set(value) != {"type", "from"} or value["from"] != "$outcome.result" or not type_equals(value["type"], expected_type):
        raise ContractError(f"{label} must expose $outcome.result as {type_display(expected_type)}")


def _validate_async_entry_responses(entry_id: str, entry: dict[str, Any], *, require_failure_disposition: bool) -> None:
    responses = entry.get("responses", {})
    accepted = responses.get("accepted")
    if accepted != {"disposition": "ack"}:
        raise ContractError(f"Entry {entry_id} responses.accepted must declare disposition: ack")
    failure_responses = {name: response for name, response in responses.items() if name != "accepted"}
    if require_failure_disposition and not failure_responses:
        raise ContractError(f"Entry {entry_id} must declare at least one non-ack disposition such as retry, reject, or dead_letter")
    for response_id, response in failure_responses.items():
        if set(response) != {"disposition", "problem"}:
            raise ContractError(f"Entry {entry_id} disposition {response_id} must declare exactly disposition and problem")
        if response["disposition"] not in {"retry", "reject", "dead_letter"}:
            raise ContractError(f"Entry {entry_id} disposition {response_id} must be retry, reject, or dead_letter")
        _validate_problem_type(f"Entry {entry_id} disposition {response_id} problem", response["problem"])
    if require_failure_disposition and not any(response["disposition"] in {"reject", "dead_letter"} for response in failure_responses.values()):
        raise ContractError(f"Entry {entry_id} must declare a reject or dead_letter disposition for malformed or poison messages")


def _validate_webhook_entry_responses(entry_id: str, entry: dict[str, Any]) -> None:
    if entry.get("responses") != {"accepted": {"status": 202}}:
        raise ContractError(f"Webhook entry {entry_id} responses.accepted.status must be 202")


def _validate_fsm_entry_inputs(
    contract: dict[str, Any],
    entry_id: str,
    fsm_id: str,
    *,
    declared: dict[str, Any],
    input_label: str,
) -> None:
    fsm = contract["fsms"][fsm_id]
    fsm_context = fsm.get("context", {})
    extra = sorted(set(declared) - set(fsm_context))
    if extra:
        raise ContractError(f"Entry {entry_id} {input_label} must be declared FSM context fields: {extra}")
    _validate_entry_input_types(entry_id, input_label, declared, fsm_context)
    required = _required_entry_fsm_context(contract, fsm_id)
    missing = sorted(set(required) - set(declared))
    if missing:
        raise ContractError(f"Entry {entry_id} {input_label} must include required FSM context inputs: {missing}")


def _required_entry_fsm_context(contract: dict[str, Any], fsm_id: str) -> dict[str, Any]:
    fsm = contract["fsms"][fsm_id]
    required: dict[str, Any] = {}
    _add_data_context_requirements(contract, f"FSM {fsm_id}", fsm.get("data", []), fsm.get("context", {}), required)
    for state_name, state in fsm.get("states", {}).items():
        _add_data_context_requirements(contract, f"FSM {fsm_id}.{state_name}", state.get("data", []), fsm.get("context", {}), required)
        for mount in state.get("mounts", []):
            fsm = contract["fsms"][mount["fsm"]]
            initial_state = fsm["states"][mount["initial"]]
            _add_mount_context_requirements(contract, fsm_id, mount, fsm, fsm.get("data", []), required)
            _add_mount_context_requirements(contract, fsm_id, mount, fsm, initial_state.get("data", []), required)
    return required


def _add_data_context_requirements(
    contract: dict[str, Any],
    label: str,
    data: list[dict[str, Any]],
    context: dict[str, Any],
    required: dict[str, Any],
) -> None:
    for datum in data:
        capability = contract["capabilities"][datum["capability"]]
        for key, expected_type in capability["input"].items():
            actual_type = context.get(key)
            if not type_equals(actual_type, expected_type):
                raise ContractError(f"{label} context {key} type must be {type_display(expected_type)}, got {type_display(actual_type)}")
            _add_required_entry_context(required, key, expected_type, label)


def _add_mount_context_requirements(
    contract: dict[str, Any],
    fsm_id: str,
    mount: dict[str, Any],
    fsm: dict[str, Any],
    data: list[dict[str, Any]],
    required: dict[str, Any],
) -> None:
    mount_context = mount.get("context", {})
    child_fsm_context = fsm.get("context", {})
    parent_fsm_context = contract["fsms"][fsm_id].get("context", {})
    for datum in data:
        capability = contract["capabilities"][datum["capability"]]
        for child_key, expected_type in capability["input"].items():
            if not type_equals(child_fsm_context.get(child_key), expected_type):
                raise ContractError(f"Composed FSM {fsm_id}.{mount['id']} FSM context {child_key} type must be {type_display(expected_type)}")
            value = mount_context.get(child_key)
            if not is_reference_expression(value):
                continue
            try:
                ref = parse_reference_expression(value)
            except ReferenceExpressionError as exc:
                raise ContractError(f"Composed FSM {fsm_id}.{mount['id']} has malformed runtime reference: {value}") from exc
            if ref.root != "state_machine":
                continue
            parent_key = ref.path[0]
            actual_type = _reference_expression_type(
                contract,
                f"Composed FSM {fsm_id}.{mount['id']} parent context {parent_key}",
                value,
                {"state_machine": _type_scope(parent_fsm_context)},
            )
            if not type_equals(actual_type, expected_type):
                raise ContractError(
                    f"Composed FSM {fsm_id}.{mount['id']} parent context {parent_key} type must be "
                    f"{type_display(expected_type)}, got {type_display(actual_type)}"
                )
            _add_required_entry_context(
                required,
                parent_key,
                parent_fsm_context[parent_key],
                f"Composed FSM {fsm_id}.{mount['id']}",
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
    value = (entry.get("input") or {}).get(section, {})
    return value if isinstance(value, dict) else {}


def _entry_input_source_types(contract: dict[str, Any], entry: dict[str, Any]) -> TypeScope:
    source_types: TypeScope = {}
    for section in ("params", "body", "args"):
        for name, type_name in _entry_input_map(entry, section).items():
            source_types[(section, name)] = type_name
    payload = (entry.get("input") or {}).get("payload")
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
        raise ContractError("Capability must declare exactly one success outcome")
    return next(iter(successes.items()))


def _success_result_type(cap: dict[str, Any]) -> Any:
    return _primary_success_outcome(cap)[1]["result"]


def _validate_workflows(contract: dict[str, Any]) -> None:
    for wid, workflow in contract["workflows"].items():
        kind, value = _one(workflow["trigger"], f"workflow {wid} trigger")
        if kind == "event" and value not in contract["events"]:
            raise ContractError(f"Workflow {wid} trigger references unknown event {value}")
        if kind == "capability" and value not in contract["capabilities"]:
            raise ContractError(f"Workflow {wid} trigger references unknown capability {value}")
        _validate_workflow_outcomes(wid, workflow)
        step_ids = [step["id"] for step in workflow["steps"]]
        if len(step_ids) != len(set(step_ids)):
            raise ContractError(f"Workflow {wid} step ids must be unique")
        step_id_set = set(step_ids)
        source_types = _workflow_trigger_source_types(contract, wid, workflow)
        routed_terminals: set[str] = set()
        for step in workflow["steps"]:
            if step["capability"] not in contract["capabilities"]:
                raise ContractError(f"Workflow {wid} step references unknown capability {step['capability']}")
            capability = contract["capabilities"][step["capability"]]
            _validate_workflow_step_bindings(contract, wid, step, capability, source_types)
            routed_terminals.update(_validate_workflow_step_routes(wid, workflow, step, capability, step_id_set))
            _merge_type_scopes(source_types, _workflow_step_source_types(contract, step, capability))
        if routed_terminals != set(workflow["outcomes"]):
            missing = sorted(set(workflow["outcomes"]) - routed_terminals)
            extra = sorted(routed_terminals - set(workflow["outcomes"]))
            parts = []
            if missing:
                parts.append("missing terminal routes: " + ", ".join(missing))
            if extra:
                parts.append("unknown terminal routes: " + ", ".join(extra))
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
        payload_type = contract["events"][value]["payload"]
    else:
        payload_type = _success_result_type(contract["capabilities"][value])
    return {"trigger": _typed_source_paths(contract, ("payload",), payload_type)}


def _workflow_step_source_types(contract: dict[str, Any], step: dict[str, Any], capability: dict[str, Any]) -> TypeScopes:
    sources: TypeScope = {}
    for outcome_id, outcome in capability["outcomes"].items():
        sources.update(_typed_source_paths(contract, (step["id"], "outcomes", outcome_id, "result"), outcome["result"]))
    return {"steps": sources}


def _validate_workflow_step_bindings(
    contract: dict[str, Any],
    workflow_id: str,
    step: dict[str, Any],
    capability: dict[str, Any],
    source_types: TypeScopes,
) -> None:
    bindings = step["with"]
    expected = capability["input"]
    if set(bindings) != set(expected):
        missing = sorted(set(expected) - set(bindings))
        extra = sorted(set(bindings) - set(expected))
        parts = []
        if missing:
            parts.append("missing: " + ", ".join(missing))
        if extra:
            parts.append("extra: " + ", ".join(extra))
        raise ContractError(f"Workflow {workflow_id} step {step['id']} with must exactly map capability input" + (": " + "; ".join(parts) if parts else ""))
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
    capability: dict[str, Any],
    step_ids: set[str],
) -> set[str]:
    routes = step["on"]
    if set(routes) != set(capability["outcomes"]):
        missing = sorted(set(capability["outcomes"]) - set(routes))
        extra = sorted(set(routes) - set(capability["outcomes"]))
        parts = []
        if missing:
            parts.append("missing: " + ", ".join(missing))
        if extra:
            parts.append("extra: " + ", ".join(extra))
        raise ContractError(f"Workflow {workflow_id} step {step['id']} on must exactly map capability outcomes" + (": " + "; ".join(parts) if parts else ""))

    routed_terminals: set[str] = set()
    for outcome_id, route in routes.items():
        route_targets = [key for key in ("complete", "fail", "next") if key in route]
        if len(route_targets) != 1:
            raise ContractError(f"Workflow {workflow_id} step {step['id']} route {outcome_id} must declare exactly one of complete, fail, or next")
        outcome = capability["outcomes"][outcome_id]
        target_kind = route_targets[0]
        if target_kind == "next":
            next_step = route["next"]
            if next_step not in step_ids:
                raise ContractError(f"Workflow {workflow_id} step {step['id']} route {outcome_id} references unknown next step {next_step}")
            if next_step == step["id"]:
                raise ContractError(f"Workflow {workflow_id} step {step['id']} route {outcome_id} cannot loop to itself")
        else:
            terminal_id = route[target_kind]
            terminal = workflow["outcomes"].get(terminal_id)
            if not terminal:
                raise ContractError(f"Workflow {workflow_id} step {step['id']} route {outcome_id} references unknown workflow outcome {terminal_id}")
            expected_kind = "success" if target_kind == "complete" else "failure"
            if outcome["kind"] != expected_kind or terminal["kind"] != expected_kind:
                raise ContractError(f"Workflow {workflow_id} step {step['id']} route {outcome_id} must preserve {outcome['kind']} outcome semantics")
            if not type_equals(terminal["result"], outcome["result"]):
                raise ContractError(
                    f"Workflow {workflow_id} outcome {terminal_id} result must be "
                    f"{type_display(outcome['result'])} to receive step outcome {outcome_id}"
                )
            routed_terminals.add(terminal_id)
        if "retry" in route:
            if outcome["kind"] != "failure":
                raise ContractError(f"Workflow {workflow_id} step {step['id']} route {outcome_id} retry is only valid for failure outcomes")
            retry = route["retry"]
            if retry["attempts"] < 1 or retry["attempts"] > 10:
                raise ContractError(f"Workflow {workflow_id} step {step['id']} route {outcome_id} retry attempts must be between 1 and 10")
        if route.get("dead_letter") is True and outcome["kind"] != "failure":
            raise ContractError(f"Workflow {workflow_id} step {step['id']} route {outcome_id} dead_letter is only valid for failure outcomes")
        if outcome["kind"] == "failure" and target_kind == "fail" and "retry" not in route and route.get("dead_letter") is not True:
            raise ContractError(f"Workflow {workflow_id} step {step['id']} failure route {outcome_id} must declare retry or dead_letter")
        if outcome["kind"] == "success" and ("retry" in route or route.get("dead_letter") is True):
            raise ContractError(f"Workflow {workflow_id} step {step['id']} success route {outcome_id} must not declare retry or dead_letter")
    return routed_terminals


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


def _validate_scenarios(contract: dict[str, Any]) -> None:
    for sid, scenario in contract["scenarios"].items():
        fixture_ids = scenario["arrange"].get("fixtures", [])
        for fixture_id in fixture_ids:
            if fixture_id not in contract["fixtures"]:
                raise ContractError(f"Scenario {sid} references unknown fixture {fixture_id}")
        fixture_values = _fixture_namespace(contract, fixture_ids, sid)
        _validate_fixture_templates(scenario, fixture_values, sid)
        for fact in scenario["arrange"].get("facts", []):
            _validate_fact_body(contract, fact, f"Scenario {sid}")
        _validate_scenario_when(contract, sid, scenario)
        _validate_scenario_then(contract, sid, scenario)
        _validate_scenario_archetype(sid, scenario)


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


def _fixture_namespace(contract: dict[str, Any], fixture_ids: list[str], sid: str) -> dict[str, Any]:
    namespace: dict[str, Any] = {}
    for fixture_id in fixture_ids:
        _deep_merge(namespace, copy.deepcopy(contract["fixtures"][fixture_id]["values"]), f"scenario {sid} fixture {fixture_id}")
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


def _validate_fixture_templates(node: Any, fixture_values: dict[str, Any], sid: str) -> None:
    for ref in _fixture_refs(node):
        _resolve_fixture_path(fixture_values, ref, sid)


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


def _resolve_fixture_path(fixture_values: dict[str, Any], ref: str, sid: str) -> Any:
    try:
        expression = parse_reference_expression(ref)
    except ReferenceExpressionError as exc:
        raise ContractError(f"Scenario {sid} has malformed runtime reference {ref}") from exc
    if expression.root != "fixture":
        raise ContractError(f"Scenario {sid} references unavailable runtime root: ${expression.root}")
    current: Any = fixture_values
    traversed: list[str] = []
    for part in expression.path:
        traversed.append(part)
        if not isinstance(current, dict) or part not in current:
            path = ".".join(traversed)
            raise ContractError(f"Scenario {sid} fixture ref {ref} cannot resolve at {path}")
        current = current[part]
    return current


def _validate_scenario_when(contract: dict[str, Any], sid: str, scenario: dict[str, Any]) -> None:
    kind, body = _one(scenario["execute"], f"scenario {sid} when")
    ref = body["ref"]
    if kind in {"open_entry", "call_entry"}:
        if ref not in contract["entries"]:
            raise ContractError(f"Scenario {sid} references unknown entry {ref}")
        entry = contract["entries"][ref]
        entry_target_kind, _ = entry_target_pair(entry["target"])
        if kind == "open_entry" and not (entry["surface"] in {"web", "cli"} and entry_target_kind == "fsm"):
            raise ContractError(f"Scenario {sid} open_entry must reference a web or cli FSM entry")
        if kind == "call_entry" and not (entry["surface"] in {"api", "cli"} and entry_target_kind == "capability"):
            raise ContractError(f"Scenario {sid} call_entry must reference an api or cli capability entry")
        _validate_scenario_entry_input(sid, kind, body, entry)
    elif kind == "invoke_capability":
        if ref not in contract["capabilities"]:
            raise ContractError(f"Scenario {sid} references unknown capability {ref}")
    elif kind == "emit_event":
        if ref not in contract["events"]:
            raise ContractError(f"Scenario {sid} references unknown event {ref}")
        _validate_scenario_event_payload(contract, sid, ref, body.get("payload", {}))
    _validate_scenario_outcome(contract, sid, scenario)


def _validate_scenario_event_payload(contract: dict[str, Any], sid: str, event_id: str, payload: dict[str, Any]) -> None:
    event = contract["events"][event_id]
    fields = object_fields_for_type(contract, event["payload"])
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
            f"Scenario {sid} emit_event.payload must exactly match event {event_id} payload "
            f"{type_display(event['payload'])}" + (": " + "; ".join(parts) if parts else "")
        )


def _validate_scenario_entry_input(sid: str, kind: str, body: dict[str, Any], entry: dict[str, Any]) -> None:
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
        raise ContractError(f"Scenario {sid} {kind}.input must exactly match entry input" + (": " + "; ".join(parts) if parts else ""))


def _entry_external_input_types(entry: dict[str, Any]) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for section in ("params", "body", "args"):
        fields.update(_entry_input_map(entry, section))
    return fields


def _validate_scenario_then(contract: dict[str, Any], sid: str, scenario: dict[str, Any]) -> None:
    then = scenario["assert"]
    if "fsm" in then:
        expected_fsm = then["fsm"]
        fsm_id = expected_fsm["ref"]
        if fsm_id not in contract["fsms"]:
            raise ContractError(f"Scenario {sid} references unknown FSM {fsm_id}")
        fsm = contract["fsms"][fsm_id]
        if "state" in expected_fsm:
            state = expected_fsm["state"]
            if state not in fsm.get("states", {}):
                raise ContractError(f"Scenario {sid} references unknown FSM state {fsm_id}.{state}")
        if "instances" in expected_fsm:
            state_name = expected_fsm.get("state")
            selected_state = fsm.get("states", {}).get(state_name, {}) if state_name else {}
            mounted_instances = {mount["id"]: mount for mount in selected_state.get("mounts", [])}
            if not mounted_instances:
                raise ContractError(f"Scenario {sid} asserts instance states for non-composed FSM state {fsm_id}.{state_name}")
            for instance_id, expectation in expected_fsm["instances"].items():
                if instance_id not in mounted_instances:
                    raise ContractError(f"Scenario {sid} references unknown FSM instance {fsm_id}.{instance_id}")
                fsm_id = mounted_instances[instance_id]["fsm"]
                if expectation["state"] not in contract["fsms"][fsm_id]["states"]:
                    raise ContractError(f"Scenario {sid} references unknown FSM state {fsm_id}.{expectation['state']}")
        for sync_id in (expected_fsm.get("sync") or {}).get("observed", []):
            state_name = expected_fsm.get("state")
            selected_state = fsm.get("states", {}).get(state_name, {}) if state_name else {}
            if sync_id not in {rule["id"] for rule in selected_state.get("sync", [])}:
                raise ContractError(f"Scenario {sid} references unknown sync rule {fsm_id}.{sync_id}")
        for key in (expected_fsm.get("context") or {}):
            if key not in fsm.get("context", {}):
                raise ContractError(f"Scenario {sid} asserts undeclared FSM context {fsm_id}.{key}")
    for field in ["enables", "forbids", "invoked"]:
        for cap_id in then.get(field, []):
            if cap_id not in contract["capabilities"]:
                raise ContractError(f"Scenario {sid} {field} unknown capability {cap_id}")
    model_exists = (then.get("model") or {}).get("exists")
    if model_exists and model_exists["model"] not in contract["models"]:
        raise ContractError(f"Scenario {sid} asserts unknown model {model_exists['model']}")
    for event_id in (then.get("events") or {}).get("emitted", []) + (then.get("events") or {}).get("not_emitted", []):
        if event_id not in contract["events"]:
            raise ContractError(f"Scenario {sid} asserts unknown event {event_id}")
    workflow = then.get("workflow")
    if workflow and workflow["ref"] not in contract["workflows"]:
        raise ContractError(f"Scenario {sid} asserts unknown workflow {workflow['ref']}")
    if workflow and workflow.get("outcome"):
        workflow_contract = contract["workflows"][workflow["ref"]]
        if workflow["outcome"] not in workflow_contract["outcomes"]:
            raise ContractError(f"Scenario {sid} asserts unknown workflow outcome {workflow['ref']}.{workflow['outcome']}")


def _validate_scenario_outcome(contract: dict[str, Any], sid: str, scenario: dict[str, Any]) -> None:
    when_kind, when_body = _one(scenario["execute"], f"scenario {sid} when")
    then = scenario["assert"]
    outcome_id = then.get("outcome")
    cap: dict[str, Any] | None = None
    entry: dict[str, Any] | None = None
    if when_kind == "invoke_capability":
        cap = contract["capabilities"][when_body["ref"]]
    elif when_kind == "call_entry":
        entry = contract["entries"][when_body["ref"]]
        if "capability" in entry["target"]:
            cap = contract["capabilities"][entry["target"]["capability"]]
    if cap is None:
        if outcome_id:
            raise ContractError(f"Scenario {sid} asserts outcome but does not execute a capability")
        return
    if not outcome_id:
        raise ContractError(f"Scenario {sid} must assert a capability outcome")
    if outcome_id not in cap["outcomes"]:
        raise ContractError(f"Scenario {sid} asserts unknown outcome {outcome_id}")
    if entry is None:
        return
    if outcome_id not in entry.get("responses", {}):
        raise ContractError(f"Scenario {sid} outcome {outcome_id} is not mapped by entry {when_body['ref']}")
    response_assertion = then.get("response")
    if response_assertion:
        response = entry["responses"][outcome_id]
        for key in ("status", "exit_code"):
            if key in response_assertion and response.get(key) != response_assertion[key]:
                raise ContractError(f"Scenario {sid} response.{key} does not match entry response for outcome {outcome_id}")


def _validate_scenario_archetype(sid: str, scenario: dict[str, Any]) -> None:
    archetype = scenario["archetype"]
    when_kind, _ = _one(scenario["execute"], f"scenario {sid} when")
    then = scenario["assert"]
    if archetype == "empty_collection_fsm":
        if when_kind != "open_entry" or then.get("fsm", {}).get("state") != "empty":
            raise ContractError(f"Scenario {sid} empty_collection_fsm requires open_entry and fsm.state=empty")
    elif archetype == "ready_collection_fsm":
        if when_kind != "open_entry" or then.get("fsm", {}).get("state") != "ready":
            raise ContractError(f"Scenario {sid} ready_collection_fsm requires open_entry and fsm.state=ready")
    elif archetype == "fsm_composition_sync":
        fsm_assert = then.get("fsm", {})
        if when_kind != "open_entry" or not fsm_assert.get("instances"):
            raise ContractError(f"Scenario {sid} fsm_composition_sync requires open_entry and fsm.instances")
    elif archetype == "fsm_composition":
        fsm_assert = then.get("fsm", {})
        if when_kind != "open_entry" or not fsm_assert.get("instances"):
            raise ContractError(f"Scenario {sid} fsm_composition requires open_entry and fsm.instances")
    elif archetype == "capability_outcome":
        if when_kind != "invoke_capability" or "outcome" not in then:
            raise ContractError(f"Scenario {sid} capability_outcome requires invoke_capability and outcome")
    elif archetype == "entry_response":
        if when_kind != "call_entry" or "outcome" not in then or "response" not in then:
            raise ContractError(f"Scenario {sid} entry_response requires call_entry, outcome, and response")
    elif archetype == "workflow_event_success":
        workflow = then.get("workflow", {})
        if when_kind != "emit_event" or not workflow.get("ran") or "outcome" not in workflow:
            raise ContractError(f"Scenario {sid} workflow_event_success requires emit_event, workflow.ran=true, and workflow.outcome")
    elif archetype == "forbidden_action":
        if "forbids" not in then:
            raise ContractError(f"Scenario {sid} forbidden_action requires forbids")


def _expand_scenario_fact_uses(contract: dict[str, Any]) -> set[str]:
    used: set[str] = set()
    for sid, scenario in contract["scenarios"].items():
        arrange = scenario["arrange"]
        expanded: list[dict[str, Any]] = []
        scenario_uses: set[str] = set()
        for fact in arrange.get("facts", []):
            if "use" not in fact:
                expanded.append(fact)
                continue
            fact_id = fact["use"]
            if fact_id not in contract["facts"]:
                raise ContractError(f"Scenario {sid} references unknown fact {fact_id}")
            if fact_id in scenario_uses:
                raise ContractError(f"Scenario {sid} uses fact {fact_id} more than once")
            scenario_uses.add(fact_id)
            used.add(fact_id)
            expanded.append(_fact_body(contract["facts"][fact_id], fact_id))
        if "facts" in arrange:
            arrange["facts"] = expanded
    for case_id, case in audit_cases(contract).items():
        case_uses: set[str] = set()
        for fact_use in case.get("facts", []):
            fact_id = fact_use["use"]
            if fact_id not in contract["facts"]:
                raise ContractError(f"Audit case {case_id} references unknown fact {fact_id}")
            if fact_id in case_uses:
                raise ContractError(f"Audit case {case_id} uses fact {fact_id} more than once")
            case_uses.add(fact_id)
            used.add(fact_id)
    return used


def _fact_body(fact: dict[str, Any], label: str) -> dict[str, Any]:
    kind, body = _one_fact(fact, f"Fact {label}")
    return {kind: copy.deepcopy(body)}


def _validate_facts_are_used(contract: dict[str, Any], used: set[str]) -> None:
    unused = sorted(set(contract["facts"]) - used)
    if unused:
        raise ContractError("Unused facts: " + ", ".join(unused))


def _expand_scenarios(contract: dict[str, Any]) -> None:
    for scenario in contract["scenarios"].values():
        assertions = scenario["assert"]
        if "fsm" in assertions:
            fsm_assert = assertions["fsm"]
            fsm_id = fsm_assert["ref"]
            fsm = contract["fsms"][fsm_id]
            if "instances" in fsm_assert:
                state_name = fsm_assert["state"]
                parent_fsm = fsm
                parent_state = parent_fsm["states"][state_name]
                mounts = {mount["id"]: mount for mount in parent_state.get("mounts", [])}
                required = {"queries": [datum["query"] for datum in parent_fsm.get("data", [])], "surfaces": [], "copy": [], "assets": [], "actions": []}
                fsm_assert["surface"] = parent_state["surface"]
                required["surfaces"].append(parent_state["surface"])
                required["queries"].extend(datum["query"] for datum in parent_state.get("data", []))
                required["copy"].extend(parent_state["copy"])
                required["assets"].extend(parent_state["assets"])
                required["actions"].extend(parent_state["actions"])
                for instance_id, expected in fsm_assert["instances"].items():
                    mount = mounts[instance_id]
                    mounted_fsm = contract["fsms"][mount["fsm"]]
                    mounted_state = mounted_fsm["states"][expected["state"]]
                    expected["surface"] = mounted_state["surface"]
                    expected["source"] = mount["fsm"]
                    required["queries"].extend(datum["query"] for datum in mounted_fsm.get("data", []))
                    required["queries"].extend(datum["query"] for datum in mounted_state.get("data", []))
                    required["surfaces"].append(mounted_state["surface"])
                    required["copy"].extend(mounted_state["copy"])
                    required["assets"].extend(mounted_state["assets"])
                    required["actions"].extend(mounted_state["actions"])
                fsm_assert["composition"] = {
                    "layout": parent_state.get("layout", {}),
                    "mounts": parent_state.get("mounts", []),
                    "sync": parent_state.get("sync", []),
                }
                assertions["requires"] = {key: list(dict.fromkeys(values)) for key, values in required.items()}
            elif "state" in fsm_assert:
                state_name = fsm_assert["state"]
                state = fsm["states"][state_name]
                fsm_assert["surface"] = state["surface"]
                assertions["requires"] = {
                    "queries": [datum["query"] for datum in fsm.get("data", [])] + [datum["query"] for datum in state.get("data", [])],
                    "surfaces": [state["surface"]],
                    "copy": list(state["copy"]),
                    "assets": list(state["assets"]),
                    "actions": list(state["actions"]),
                }
        when_kind, when_body = _one(scenario["execute"], "scenario execute")
        cap_id = None
        if when_kind == "invoke_capability":
            cap_id = when_body["ref"]
        elif when_kind == "call_entry":
            entry = contract["entries"][when_body["ref"]]
            if "capability" in entry["target"]:
                cap_id = entry["target"]["capability"]
        if cap_id:
            assertions.setdefault("policy", contract["capabilities"][cap_id]["policy"])


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


def _path_params(path: str | None) -> set[str]:
    return set(re.findall(r"{([a-z][a-z0-9_]*)}", path or ""))


def _validate_path_params(entry: dict[str, Any], entry_id: str) -> None:
    placeholders = _path_params(entry.get("path"))
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
