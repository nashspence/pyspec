from __future__ import annotations

import argparse
import copy
import os
from functools import lru_cache
import re
import shutil
import sys
from pathlib import Path
from typing import Any

import fastjsonschema

from . import rules
from .layers import LayerError, parse_layers, validate_patch_layers
from .io import read_json, read_yaml, write_json, write_yaml
from .project import projection_files

ROOT = Path(__file__).resolve().parents[1]


class ContractError(ValueError):
    pass


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


TARGET_ORDER = ("copy", "asset", "content_case", "audit_profile", "fixture", "resource", "capability", "panel", "view", "entry", "workflow", "scenario", "render_case")



ENTITY_SECTIONS: dict[str, str] = {
    "copy": "copies",
    "asset": "assets",
    "content_case": "content_cases",
    "audit_profile": "audit_profiles",
    "render_case": "render_cases",
    "fixture": "fixtures",
    "resource": "resources",
    "capability": "capabilities",
    "panel": "panels",
    "view": "views",
    "entry": "entries",
    "workflow": "workflows",
    "scenario": "scenarios",
}


REF_KINDS = ["asset", "command", "copy", "endpoint", "panel", "policy", "query", "route", "screen", "workflow"]


def compile_patch(patch: dict[str, Any], layers: set[str] | None = None) -> dict[str, Any]:
    validate_against_schema(patch, "pm_patch.schema.json")
    try:
        validate_patch_layers(patch, layers)
    except LayerError as exc:
        raise ContractError(str(exc)) from exc

    contract: dict[str, Any] = {
        "version": 1,
        "project": patch["project"],
        "status": patch["status"],
        "review_flags": patch.get("review_flags", []),
        "copies": {},
        "assets": {},
        "content_cases": {},
        "audit_profiles": {},
        "render_cases": {},
        "fixtures": {},
        "resources": {},
        "capabilities": {},
        "events": {},
        "panels": {},
        "views": {},
        "entries": {},
        "workflows": {},
        "scenarios": {},
        "refs": {},
    }

    for index, change in enumerate(patch["changes"], start=1):
        verb, entity, entity_id, spec = _normalize_patch_change(change)
        section_name = ENTITY_SECTIONS[entity]
        section = contract[section_name]

        if verb == "add":
            _unique(section, entity_id, entity)
            section[entity_id] = _compile_entity(entity, spec, contract)
        elif verb == "replace":
            if entity_id not in section:
                raise ContractError(f"Cannot replace missing {entity}: {entity_id}")
            section[entity_id] = _compile_entity(entity, spec, contract)
        elif verb == "delete":
            if entity_id not in section:
                raise ContractError(f"Cannot delete missing {entity}: {entity_id}")
            del section[entity_id]
        else:  # pragma: no cover - schema should prevent this.
            raise ContractError(f"Unsupported patch verb at change {index}: {verb}")

    contract["events"] = _derive_events(contract)
    contract["refs"] = _derive_refs(contract)
    _semantic_validate(contract)
    _expand_scenarios(contract)
    validate_against_schema(contract, "contract.schema.json")
    return contract


def _normalize_patch_change(change: dict[str, Any]) -> tuple[str, str, str, dict[str, Any] | None]:
    op = change["op"]
    if op in {"add", "replace"}:
        entity = change["target"]
        spec = copy.deepcopy(change["spec"])
        spec["id"] = change["id"]
        spec["basis"] = copy.deepcopy(change["basis"])
        return op, entity, change["id"], spec

    if op == "delete":
        return op, change["target"], change["id"], None

    raise ContractError(f"Unknown operation: {op}")

def _one_entity_payload(change: dict[str, Any], label: str) -> tuple[str, Any]:
    present = [(entity, change[entity]) for entity in ENTITY_SECTIONS if entity in change]
    if len(present) != 1:
        raise ContractError(f"{label} must contain exactly one subject: {sorted(ENTITY_SECTIONS)}")
    return present[0]


def _compile_entity(entity: str, spec: dict[str, Any] | None, contract: dict[str, Any]) -> dict[str, Any]:
    if spec is None:  # pragma: no cover - delete never compiles an entity.
        raise ContractError(f"Cannot compile missing {entity} spec")

    if entity == "copy":
        item = {"placeholder": spec["placeholder"], "basis": spec["basis"]}
        for field in ["max_chars", "tone", "args", "final"]:
            if field in spec:
                item[field] = spec[field]
        return item

    if entity == "asset":
        item = {"kind": spec["kind"], "placeholder": spec["placeholder"], "basis": spec["basis"]}
        for field in ["alt_copy", "args", "final"]:
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

    if entity == "render_case":
        item = {
            "view": spec["view"],
            "profile": spec["profile"],
            "surfaces": spec["surfaces"],
            "fixtures": spec["fixtures"],
            "basis": spec["basis"],
        }
        for field in ["context", "state", "panels"]:
            if field in spec:
                item[field] = spec[field]
        return item

    if entity == "fixture":
        return {"values": spec["values"], "basis": spec["basis"]}

    if entity == "resource":
        item = {
            "kind": spec["kind"],
            "fields": spec["fields"],
            "lifecycle": spec.get("lifecycle"),
            "basis": spec["basis"],
        }
        return item

    if entity == "capability":
        capability: dict[str, Any] = {
            "archetype": spec["archetype"],
            "resource": spec["resource"],
            "input": spec["input"],
            "output": spec["output"],
            "policy": rules.policy_ref(spec["id"]),
            "emits": spec.get("emits", []),
            "errors": spec.get("errors", []),
            "basis": spec["basis"],
        }
        if "transition" in spec:
            capability["transition"] = spec["transition"]
        return capability

    if entity == "panel":
        panel_id = spec["id"]
        return {
            "kind": spec["kind"],
            "resource": spec["resource"],
            "context": spec["context"],
            "data": _compile_data(panel_id, spec.get("data", [])),
            "events": spec.get("events", []),
            "initial": spec["initial"],
            "states": _compile_states(panel_id, spec.get("states", {})),
            "transitions": spec.get("transitions", []),
            "basis": spec["basis"],
        }

    if entity == "view":
        view_id = spec["id"]
        view: dict[str, Any] = {
            "archetype": spec["archetype"],
            "resource": spec["resource"],
            "data": _compile_data(view_id, spec.get("data", [])),
            "states": _compile_states(view_id, spec.get("states", {})),
            "basis": spec["basis"],
        }
        for field in ["context", "layout", "includes", "sync"]:
            if field in spec:
                view[field] = spec[field]
        return view

    if entity == "entry":
        entry_id = spec["id"]
        entry: dict[str, Any] = {
            "surface": spec["surface"],
            "target": spec["target"],
            "basis": spec["basis"],
        }
        for field in ["method", "path", "params", "command", "args", "schedule"]:
            if field in spec:
                entry[field] = spec[field]
        kind, value = _one(spec["target"], f"entry {entry_id} target")
        if spec["surface"] == "web" and kind == "view":
            entry["route"] = rules.route_ref(value)
        elif spec["surface"] == "textual" and kind == "view":
            entry["screen"] = rules.screen_ref(value)
        elif spec["surface"] == "api" and kind == "capability":
            entry["endpoint"] = rules.endpoint_ref(value)
        elif spec["surface"] == "cli" and kind == "capability":
            entry["command_ref"] = rules.command_ref(value)
        elif spec["surface"] in {"worker", "schedule"} and kind == "workflow":
            entry["workflow_ref"] = rules.workflow_ref(value)
        return entry

    if entity == "workflow":
        return {
            "trigger": spec["trigger"],
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
    return owner_id[len("panel."):] if owner_id.startswith("panel.") else owner_id


def _state_panel_ref(owner_id: str, state_name: str) -> str:
    return f"{owner_id}.{state_name}" if owner_id.startswith("panel.") else rules.panel_ref(owner_id, state_name)


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
            "pattern": state["pattern"],
            "panel": _state_panel_ref(owner_id, state_name),
            "data": _compile_data(owner_id, state.get("data", [])),
            "copy": [rules.copy_ref(subject, state_name, slot) for slot in state.get("copy_slots", [])],
            "assets": [rules.asset_ref(subject, state_name, slot) for slot in state.get("asset_slots", [])],
            "fields": state.get("field_slots", []),
            "actions": state.get("actions", []),
        }
        if "presentation" in state:
            item["presentation"] = state["presentation"]
        compiled[state_name] = item
    return compiled


def _derive_events(contract: dict[str, Any]) -> dict[str, Any]:
    events: dict[str, Any] = {}
    for capability_id, capability in sorted(contract["capabilities"].items()):
        for event_id in capability.get("emits", []):
            event = events.setdefault(event_id, {
                "emitted_by": [],
                "payload": capability["output"],
                "basis": capability["basis"],
            })
            if event["payload"] != capability["output"]:
                raise ContractError(
                    f"Event {event_id} cannot be emitted with different payloads: "
                    f"{event['payload']} vs {capability['output']}"
                )
            event["emitted_by"].append(capability_id)
    return events


def _derive_refs(contract: dict[str, Any]) -> dict[str, list[str]]:
    refs: dict[str, set[str]] = {kind: set() for kind in REF_KINDS}
    for capability_id, capability in contract["capabilities"].items():
        refs["policy"].add(capability["policy"])
    refs["copy"].update(contract.get("copies", {}))
    refs["asset"].update(contract.get("assets", {}))
    for panel_id in contract["panels"]:
        refs["panel"].add(panel_id)
    for owner in list(contract["panels"].values()) + list(contract["views"].values()):
        for datum in owner.get("data", []):
            refs["query"].add(datum["query"])
        for state in owner.get("states", {}).values():
            for datum in state.get("data", []):
                refs["query"].add(datum["query"])
            refs["panel"].add(state["panel"])
            refs["copy"].update(state["copy"])
            refs["asset"].update(state["assets"])
    for entry in contract["entries"].values():
        for ref_kind, field in [
            ("route", "route"),
            ("screen", "screen"),
            ("endpoint", "endpoint"),
            ("command", "command_ref"),
            ("workflow", "workflow_ref"),
        ]:
            if field in entry:
                refs[ref_kind].add(entry[field])
    for workflow in contract["workflows"].values():
        refs["workflow"].add(workflow["ref"])
    return {kind: sorted(values) for kind, values in sorted(refs.items()) if values}

def _semantic_validate(contract: dict[str, Any]) -> None:
    _validate_copy_assets(contract)
    _validate_content_cases(contract)
    _validate_audit_profiles(contract)
    _validate_resources(contract)
    _validate_capabilities(contract)
    _validate_panels(contract)
    _validate_views(contract)
    _validate_entries(contract)
    _validate_workflows(contract)
    _validate_fixtures(contract)
    _validate_scenarios(contract)
    _validate_render_cases(contract)



def _validate_copy_assets(contract: dict[str, Any]) -> None:
    used_copy: set[str] = set()
    used_assets: set[str] = set()
    for owner in list(contract.get("panels", {}).values()) + list(contract.get("views", {}).values()):
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
        if (item.get("final") or {}).get("status") in {"final_draft", "approved"}
    }
    declared_case_refs: set[str] = set()
    for ref, item in list(contract.get("copies", {}).items()) + list(contract.get("assets", {}).items()):
        final = item.get("final")
        if final:
            if final["resolver"] != ref:
                raise ContractError(f"Content final resolver for {ref} must equal the content id")
            if final["status"] != "placeholder" and not item.get("args"):
                # Arg-less final resolvers are allowed, but declaring args is preferred for dynamic content.
                pass
    for case_id, case in contract.get("content_cases", {}).items():
        ref = case["ref"]
        section = "copies" if ref.startswith("copy.") else "assets"
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
    if (contract.get("views") or contract.get("panels")) and not contract.get("audit_profiles"):
        raise ContractError("At least one audit_profile is required when views or panels are declared")


def _validate_render_cases(contract: dict[str, Any]) -> None:
    cases = contract.get("render_cases", {})
    if contract.get("views") and not cases:
        raise ContractError("At least one render_case is required when views are declared")
    coverage_states: dict[str, set[str]] = {view_id: set() for view_id, view in contract.get("views", {}).items() if view.get("states")}
    coverage_composed: set[str] = set()
    for case_id, case in cases.items():
        view_id = case["view"]
        if view_id not in contract["views"]:
            raise ContractError(f"Render case {case_id} references unknown view {view_id}")
        if case["profile"] not in contract.get("audit_profiles", {}):
            raise ContractError(f"Render case {case_id} references unknown audit_profile {case['profile']}")
        profile = contract["audit_profiles"][case["profile"]]
        for surface in case.get("surfaces", []):
            if surface not in profile:
                raise ContractError(f"Render case {case_id} uses {surface} but audit_profile {case['profile']} does not declare {surface}")
        for fixture_id in case.get("fixtures", []):
            if fixture_id not in contract["fixtures"]:
                raise ContractError(f"Render case {case_id} references unknown fixture {fixture_id}")
        fixture_values = _fixture_namespace(contract, case.get("fixtures", []), f"render case {case_id}")
        _validate_fixture_templates(case, fixture_values, f"render case {case_id}")
        view = contract["views"][view_id]
        if view.get("states"):
            state = case.get("state")
            if not state:
                raise ContractError(f"Render case {case_id} for atomic view {view_id} must declare state")
            if state not in view["states"]:
                raise ContractError(f"Render case {case_id} references unknown view state {view_id}.{state}")
            selected_state = view["states"][state]
            if selected_state.get("fields") and not _fixtures_include_resource(contract, case.get("fixtures", []), view["resource"]):
                raise ContractError(f"Render case {case_id} renders fields for {view_id}.{state} but does not include a {view['resource']} fixture")
            coverage_states.setdefault(view_id, set()).add(state)
        if view.get("includes"):
            panels = case.get("panels")
            if not panels:
                raise ContractError(f"Render case {case_id} for composed view {view_id} must declare panels")
            instances = {include["id"]: include for include in view["includes"]}
            if set(panels) != set(instances):
                raise ContractError(f"Render case {case_id} panel state vector must exactly cover composed view instances")
            for instance_id, expected in panels.items():
                panel_id = instances[instance_id]["panel"]
                if expected["state"] not in contract["panels"][panel_id]["states"]:
                    raise ContractError(f"Render case {case_id} references unknown panel state {panel_id}.{expected['state']}")
                selected_state = contract["panels"][panel_id]["states"][expected["state"]]
                if selected_state.get("fields") and not _fixtures_include_resource(contract, case.get("fixtures", []), contract["panels"][panel_id]["resource"]):
                    raise ContractError(f"Render case {case_id} renders fields for {panel_id}.{expected['state']} but does not include a {contract['panels'][panel_id]['resource']} fixture")
            coverage_composed.add(view_id)
    missing_state_cases = []
    for view_id, states in coverage_states.items():
        missing = set(contract["views"][view_id].get("states", {})) - states
        missing_state_cases.extend(f"{view_id}.{state}" for state in sorted(missing))
    if missing_state_cases:
        raise ContractError("Missing render_case coverage for view states: " + ", ".join(missing_state_cases))
    missing_composed = [view_id for view_id, view in contract.get("views", {}).items() if view.get("includes") and view_id not in coverage_composed]
    if missing_composed:
        raise ContractError("Missing render_case coverage for composed views: " + ", ".join(sorted(missing_composed)))
    _validate_panel_state_fixture_coverage(contract)


def _validate_panel_state_fixture_coverage(contract: dict[str, Any]) -> None:
    for view_id, view in contract.get("views", {}).items():
        for state_name, state in view.get("states", {}).items():
            if state.get("fields") and not _fixtures_include_resource(contract, list(contract.get("fixtures", {})), view["resource"]):
                raise ContractError(f"Rendered fields for {view_id}.{state_name} require at least one {view['resource']} fixture")
    for panel_id, panel in contract.get("panels", {}).items():
        for state_name, state in panel.get("states", {}).items():
            if state.get("fields") and not _fixtures_include_resource(contract, list(contract.get("fixtures", {})), panel["resource"]):
                raise ContractError(f"Rendered fields for {panel_id}.{state_name} require at least one {panel['resource']} fixture")


def _fixtures_include_resource(contract: dict[str, Any], fixture_ids: list[str], resource_id: str) -> bool:
    for fixture_id in fixture_ids:
        if fixture_id in contract.get("fixtures", {}) and _value_contains_resource(contract["fixtures"][fixture_id]["values"], resource_id):
            return True
    return False


def _value_contains_resource(value: Any, resource_id: str) -> bool:
    if isinstance(value, dict):
        if value.get("resource") == resource_id:
            return True
        return any(_value_contains_resource(child, resource_id) for child in value.values())
    if isinstance(value, list):
        return any(_value_contains_resource(item, resource_id) for item in value)
    return False


def _validate_resources(contract: dict[str, Any]) -> None:
    for rid, resource in contract["resources"].items():
        lifecycle = resource.get("lifecycle")
        if not lifecycle:
            continue
        if lifecycle["field"] not in resource["fields"]:
            raise ContractError(f"Resource {rid} lifecycle field is not a field: {lifecycle['field']}")
        states = set(lifecycle["states"])
        if lifecycle["initial"] not in states:
            raise ContractError(f"Resource {rid} lifecycle initial state is not declared: {lifecycle['initial']}")
        for transition in lifecycle.get("transitions", []):
            if transition["from"] not in states or transition["to"] not in states:
                raise ContractError(f"Resource {rid} lifecycle transition uses unknown state: {transition}")


def _validate_capabilities(contract: dict[str, Any]) -> None:
    resources = contract["resources"]
    capabilities = contract["capabilities"]
    for cid, cap in capabilities.items():
        if cap["resource"] not in resources:
            raise ContractError(f"Capability {cid} references unknown resource {cap['resource']}")
        if cap["archetype"] == "transition" and "transition" not in cap:
            raise ContractError(f"Transition capability {cid} must declare transition")
        if cap["archetype"] != "transition" and "transition" in cap:
            raise ContractError(f"Only transition capabilities may declare transition: {cid}")
        if "transition" in cap:
            lifecycle = resources[cap["resource"]].get("lifecycle")
            if not lifecycle:
                raise ContractError(f"Capability {cid} declares transition but {cap['resource']} has no lifecycle")
            transition = cap["transition"]
            if transition["field"] != lifecycle["field"]:
                raise ContractError(f"Capability {cid} transition field does not match resource lifecycle")
            if transition["from"] not in lifecycle["states"] or transition["to"] not in lifecycle["states"]:
                raise ContractError(f"Capability {cid} transition references unknown lifecycle state")
    for rid, resource in resources.items():
        lifecycle = resource.get("lifecycle")
        if not lifecycle:
            continue
        for transition in lifecycle.get("transitions", []):
            by = transition["by"]
            if by not in capabilities:
                raise ContractError(f"Resource {rid} lifecycle transition references unknown capability {by}")
            cap_transition = capabilities[by].get("transition")
            if not cap_transition or cap_transition["from"] != transition["from"] or cap_transition["to"] != transition["to"]:
                raise ContractError(f"Resource {rid} lifecycle and capability {by} disagree")
    for event_id, event in contract["events"].items():
        for cap_id in event["emitted_by"]:
            if cap_id not in capabilities:
                raise ContractError(f"Event {event_id} emitted by unknown capability {cap_id}")


def _validate_panels(contract: dict[str, Any]) -> None:
    for panel_id, panel in contract["panels"].items():
        if not panel_id.startswith("panel."):
            raise ContractError(f"Panel id must start with panel.: {panel_id}")
        if panel["resource"] not in contract["resources"]:
            raise ContractError(f"Panel {panel_id} references unknown resource {panel['resource']}")
        for datum in panel.get("data", []):
            if datum["capability"] not in contract["capabilities"]:
                raise ContractError(f"Panel {panel_id} data references unknown capability {datum['capability']}")
        if panel["initial"] not in panel["states"]:
            raise ContractError(f"Panel {panel_id} initial state is not declared: {panel['initial']}")
        resource_fields = set(contract["resources"][panel["resource"]]["fields"])
        for state_name, state in panel["states"].items():
            _validate_panelish_state(contract, f"Panel {panel_id}", state_name, state, field_names=resource_fields)
        _validate_panel_transitions(panel_id, panel)


def _validate_panelish_state(
    contract: dict[str, Any],
    owner_label: str,
    state_name: str,
    state: dict[str, Any],
    field_names: set[str],
) -> None:
    for datum in state.get("data", []):
        if datum["capability"] not in contract["capabilities"]:
            raise ContractError(f"{owner_label}.{state_name} data references unknown capability {datum['capability']}")
    for field in state.get("fields", []):
        if field not in field_names:
            raise ContractError(f"{owner_label}.{state_name} field slot is not declared on the resource/context: {field}")
    for action in state["actions"]:
        if action not in contract["capabilities"]:
            raise ContractError(f"{owner_label}.{state_name} action references unknown capability {action}")
    _validate_presentation(contract, owner_label, field_names, state_name, state)


def _validate_panel_transitions(panel_id: str, panel: dict[str, Any]) -> None:
    states = set(panel["states"])
    for transition in panel.get("transitions", []):
        if transition["from"] not in states or transition["to"] not in states:
            raise ContractError(f"Panel {panel_id} transition uses unknown state: {transition}")
        for effect in transition.get("effects", []):
            kind, body = _one(effect, f"panel {panel_id} transition effect")
            if kind == "set":
                if body["context"] not in panel.get("context", {}):
                    raise ContractError(f"Panel {panel_id} transition sets undeclared context: {body['context']}")
            elif kind == "emit":
                if not isinstance(body, str):
                    raise ContractError(f"Panel {panel_id} transition emit must name an event: {body!r}")
            else:  # pragma: no cover - schema prevents this.
                raise ContractError(f"Panel {panel_id} unsupported transition effect: {kind}")


def _validate_views(contract: dict[str, Any]) -> None:
    for vid, view in contract["views"].items():
        if view["resource"] not in contract["resources"]:
            raise ContractError(f"View {vid} references unknown resource {view['resource']}")
        if not view.get("states") and not view.get("includes"):
            raise ContractError(f"View {vid} must declare atomic states or composed panel includes")
        for datum in view.get("data", []):
            if datum["capability"] not in contract["capabilities"]:
                raise ContractError(f"View {vid} data references unknown capability {datum['capability']}")
        resource_fields = set(contract["resources"][view["resource"]]["fields"])
        for state_name, state in view.get("states", {}).items():
            _validate_panelish_state(contract, f"View {vid}", state_name, state, field_names=resource_fields)
        if view.get("includes") or view.get("layout") or view.get("sync"):
            _validate_view_composition(contract, vid, view)


def _validate_view_composition(contract: dict[str, Any], view_id: str, view: dict[str, Any]) -> None:
    if not view.get("layout"):
        raise ContractError(f"Composed view {view_id} must declare layout")
    if not view.get("includes"):
        raise ContractError(f"Composed view {view_id} must include at least one panel")
    slots = set(view["layout"]["slots"])
    instances: dict[str, dict[str, Any]] = {}
    for include in view["includes"]:
        if include["id"] in instances:
            raise ContractError(f"Composed view {view_id} has duplicate panel instance: {include['id']}")
        instances[include["id"]] = include
        if include["slot"] not in slots:
            raise ContractError(f"Composed view {view_id} includes panel in undeclared slot: {include['slot']}")
        panel_id = include["panel"]
        if panel_id not in contract["panels"]:
            raise ContractError(f"Composed view {view_id} includes unknown panel: {panel_id}")
        panel = contract["panels"][panel_id]
        if include["initial"] not in panel["states"]:
            raise ContractError(f"Composed view {view_id}.{include['id']} initial state is unknown: {include['initial']}")
        selected = include.get("selected")
        if selected and selected["state"] not in panel["states"]:
            raise ContractError(f"Composed view {view_id}.{include['id']} selected state is unknown: {selected['state']}")
        if selected:
            _validate_condition_context(view_id, view.get("context", {}), selected["when"])
        include_context = include.get("context", {})
        expected_context = set(panel.get("context", {}))
        if set(include_context) != expected_context:
            raise ContractError(
                f"Composed view {view_id}.{include['id']} context keys {sorted(include_context)} "
                f"must exactly match panel context {sorted(expected_context)}"
            )
        _validate_view_context_refs(view_id, view.get("context", {}), include_context)
    used_slots = {include["slot"] for include in view["includes"]}
    missing_required = [slot for slot, spec in view["layout"]["slots"].items() if spec["required"] and slot not in used_slots]
    if missing_required:
        raise ContractError(f"Composed view {view_id} missing required layout slots: {missing_required}")
    _validate_layout_contract(view_id, view["layout"], slots, set(instances))
    _validate_sync_rules(contract, view_id, view, instances)


def _validate_layout_contract(view_id: str, layout: dict[str, Any], slots: set[str], instances: set[str]) -> None:
    for rule in (layout.get("css") or {}).get("rules", []):
        _validate_composition_selector(view_id, rule["selector"], slots, instances, "CSS")
    textual = layout.get("textual") or {}
    seen_container_slots: set[str] = set()
    for container in textual.get("containers", []):
        slot = container["slot"]
        if slot in seen_container_slots:
            raise ContractError(f"Composed view {view_id} Textual layout has duplicate container for slot: {slot}")
        seen_container_slots.add(slot)
        if slot not in slots:
            raise ContractError(f"Composed view {view_id} Textual layout references undeclared slot: {slot}")
    for rule in ((textual.get("tcss") or {}).get("rules", [])):
        _validate_composition_selector(view_id, rule["selector"], slots, instances, "TCSS")


def _validate_condition_context(view_id: str, context: dict[str, str], condition: Any) -> None:
    if isinstance(condition, dict):
        if "context_present" in condition:
            keys = [condition["context_present"]]
        elif "context_equals" in condition:
            keys = [condition["context_equals"]["field"]]
        else:
            keys = []
    else:
        keys = re.findall(r"\$view\.([a-z][a-z0-9_]*)", str(condition))
    for key in keys:
        if key not in context:
            raise ContractError(f"Composed view {view_id} condition references undeclared context: {key}")


def _validate_view_context_refs(view_id: str, context: dict[str, str], mapping: dict[str, Any]) -> None:
    for value in mapping.values():
        if isinstance(value, str) and value.startswith("$view."):
            key = value[len("$view."):]
            if key not in context:
                raise ContractError(f"Composed view {view_id} references undeclared view context: {value}")


def _panel_emits(panel: dict[str, Any]) -> set[str]:
    emits: set[str] = set(panel.get("events", []))
    for transition in panel.get("transitions", []):
        for effect in transition.get("effects", []):
            kind, body = _one(effect, "panel transition effect")
            if kind == "emit":
                emits.add(body)
    return emits


def _panel_accepts(panel: dict[str, Any]) -> set[str]:
    accepts: set[str] = set(panel.get("events", []))
    for transition in panel.get("transitions", []):
        event = transition["event"]
        if not event.startswith("data."):
            accepts.add(event)
    return accepts


def _validate_sync_rules(contract: dict[str, Any], view_id: str, view: dict[str, Any], instances: dict[str, dict[str, Any]]) -> None:
    seen: set[str] = set()
    context = view.get("context", {})
    for rule in view.get("sync", []):
        if rule["id"] in seen:
            raise ContractError(f"Composed view {view_id} has duplicate sync rule: {rule['id']}")
        seen.add(rule["id"])
        source_id = rule["when"]["panel"]
        if source_id not in instances:
            raise ContractError(f"Composed view {view_id} sync source panel is unknown: {source_id}")
        source_panel = contract["panels"][instances[source_id]["panel"]]
        event_id = rule["when"]["emits"]
        if event_id not in _panel_emits(source_panel):
            raise ContractError(f"Composed view {view_id} sync listens for undeclared panel event: {event_id}")
        for effect in rule["do"]:
            kind, body = _one(effect, f"composed view {view_id} sync effect")
            if kind == "set":
                if body["context"] not in context:
                    raise ContractError(f"Composed view {view_id} sync sets undeclared context: {body['context']}")
            elif kind == "send":
                target_id = body["panel"]
                if target_id not in instances:
                    raise ContractError(f"Composed view {view_id} sync sends to unknown panel: {target_id}")
                target_panel = contract["panels"][instances[target_id]["panel"]]
                if body["event"] not in _panel_accepts(target_panel):
                    raise ContractError(f"Composed view {view_id} sync sends undeclared target event: {body['event']}")
            else:  # pragma: no cover - schema prevents this.
                raise ContractError(f"Composed view {view_id} unsupported sync effect: {kind}")


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


def _validate_composition_selector(view_id: str, selector: str, slots: set[str], instances: set[str], label: str) -> None:
    if selector in {"root", "screen"}:
        return
    if selector.startswith("slot."):
        slot = selector[len("slot."):]
        if slot not in slots:
            raise ContractError(f"Composed view {view_id} {label} selector references undeclared layout slot: {selector}")
        return
    if selector.startswith("instance."):
        instance = selector[len("instance."):]
        if instance not in instances:
            raise ContractError(f"Composed view {view_id} {label} selector references undeclared panel instance: {selector}")
        return
    raise ContractError(f"Composed view {view_id} {label} selector is not supported: {selector}")


def _validate_entries(contract: dict[str, Any]) -> None:
    for eid, entry in contract["entries"].items():
        surface = entry["surface"]
        kind, value = _one(entry["target"], f"entry {eid} target")
        if surface == "web":
            if kind != "view" or value not in contract["views"]:
                raise ContractError(f"Web entry {eid} must target a known view")
            _require(entry, eid, "path")
            _validate_path_params(entry, eid)
        elif surface == "textual":
            if kind != "view" or value not in contract["views"]:
                raise ContractError(f"TUI entry {eid} must target a known view")
            _require(entry, eid, "command")
        elif surface == "api":
            if kind != "capability" or value not in contract["capabilities"]:
                raise ContractError(f"API entry {eid} must target a known capability")
            _require(entry, eid, "method")
            _require(entry, eid, "path")
            _validate_path_params(entry, eid)
            cap_input = set(contract["capabilities"][value]["input"])
            if not set(entry.get("params", {})).issubset(cap_input):
                raise ContractError(f"API entry {eid} params must be capability input fields")
        elif surface == "cli":
            if kind != "capability" or value not in contract["capabilities"]:
                raise ContractError(f"CLI entry {eid} must target a known capability")
            _require(entry, eid, "command")
        elif surface in {"worker", "schedule"}:
            if kind != "workflow" or value not in contract["workflows"]:
                raise ContractError(f"{surface} entry {eid} must target a known workflow")
            if surface == "schedule":
                _require(entry, eid, "schedule")
        elif surface == "webhook":
            if kind not in {"event", "workflow"}:
                raise ContractError(f"Webhook entry {eid} must target an event or workflow")
            _require(entry, eid, "path")


def _validate_workflows(contract: dict[str, Any]) -> None:
    for wid, workflow in contract["workflows"].items():
        kind, value = _one(workflow["trigger"], f"workflow {wid} trigger")
        if kind == "event" and value not in contract["events"]:
            raise ContractError(f"Workflow {wid} trigger references unknown event {value}")
        if kind == "capability" and value not in contract["capabilities"]:
            raise ContractError(f"Workflow {wid} trigger references unknown capability {value}")
        for step in workflow["steps"]:
            if step["capability"] not in contract["capabilities"]:
                raise ContractError(f"Workflow {wid} step references unknown capability {step['capability']}")


def _validate_fixtures(contract: dict[str, Any]) -> None:
    for fixture_id, fixture in contract["fixtures"].items():
        if not fixture_id.startswith("fixture."):
            raise ContractError(f"Fixture id must start with fixture.: {fixture_id}")
        if not isinstance(fixture["values"], dict) or not fixture["values"]:
            raise ContractError(f"Fixture {fixture_id} must declare non-empty values")


def _validate_scenarios(contract: dict[str, Any]) -> None:
    for sid, scenario in contract["scenarios"].items():
        fixture_ids = scenario["arrange"].get("fixtures", [])
        for fixture_id in fixture_ids:
            if fixture_id not in contract["fixtures"]:
                raise ContractError(f"Scenario {sid} references unknown fixture {fixture_id}")
        fixture_values = _fixture_namespace(contract, fixture_ids, sid)
        _validate_fixture_templates(scenario, fixture_values, sid)
        for fact in scenario["arrange"].get("facts", []):
            body = next(iter(fact.values()))
            resource_id = body["resource"]
            if resource_id not in contract["resources"]:
                raise ContractError(f"Scenario {sid} references unknown resource {resource_id}")
            if "values" in body:
                fields = set(contract["resources"][resource_id]["fields"])
                unknown = set(body["values"]) - fields
                if unknown:
                    raise ContractError(f"Scenario {sid} seeds unknown {resource_id} fields: {sorted(unknown)}")
        _validate_scenario_when(contract, sid, scenario)
        _validate_scenario_then(contract, sid, scenario)
        _validate_scenario_archetype(sid, scenario)


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
        if node.startswith("$fixture."):
            refs.append(node)
    elif isinstance(node, dict):
        for value in node.values():
            refs.extend(_fixture_refs(value))
    elif isinstance(node, list):
        for value in node:
            refs.extend(_fixture_refs(value))
    return refs


def _resolve_fixture_path(fixture_values: dict[str, Any], ref: str, sid: str) -> Any:
    parts = ref[len("$fixture."):].split(".")
    if not parts or any(not part for part in parts):
        raise ContractError(f"Scenario {sid} has malformed fixture ref {ref}")
    current: Any = fixture_values
    traversed: list[str] = []
    for part in parts:
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
        if kind == "open_entry" and contract["entries"][ref]["surface"] not in {"web", "textual"}:
            raise ContractError(f"Scenario {sid} open_entry must reference a web or textual entry")
        if kind == "call_entry" and contract["entries"][ref]["surface"] not in {"api", "cli"}:
            raise ContractError(f"Scenario {sid} call_entry must reference an api or cli entry")
    elif kind == "invoke_capability":
        if ref not in contract["capabilities"]:
            raise ContractError(f"Scenario {sid} references unknown capability {ref}")
    elif kind == "emit_event":
        if ref not in contract["events"]:
            raise ContractError(f"Scenario {sid} references unknown event {ref}")


def _validate_scenario_then(contract: dict[str, Any], sid: str, scenario: dict[str, Any]) -> None:
    then = scenario["assert"]
    if "view" in then:
        expected_view = then["view"]
        view_id = expected_view["ref"]
        if view_id not in contract["views"]:
            raise ContractError(f"Scenario {sid} references unknown view {view_id}")
        view = contract["views"][view_id]
        if "state" in expected_view:
            state = expected_view["state"]
            if state not in view.get("states", {}):
                raise ContractError(f"Scenario {sid} references unknown view state {view_id}.{state}")
        if "panels" in expected_view:
            instances = {include["id"]: include for include in view.get("includes", [])}
            if not instances:
                raise ContractError(f"Scenario {sid} asserts panel states for non-composed view {view_id}")
            for instance_id, expectation in expected_view["panels"].items():
                if instance_id not in instances:
                    raise ContractError(f"Scenario {sid} references unknown panel instance {view_id}.{instance_id}")
                panel_id = instances[instance_id]["panel"]
                if expectation["state"] not in contract["panels"][panel_id]["states"]:
                    raise ContractError(f"Scenario {sid} references unknown panel state {panel_id}.{expectation['state']}")
        for sync_id in (expected_view.get("sync") or {}).get("observed", []):
            if sync_id not in {rule["id"] for rule in view.get("sync", [])}:
                raise ContractError(f"Scenario {sid} references unknown sync rule {view_id}.{sync_id}")
        for key in (expected_view.get("context") or {}):
            if key not in view.get("context", {}):
                raise ContractError(f"Scenario {sid} asserts undeclared view context {view_id}.{key}")
    for field in ["enables", "forbids", "invoked"]:
        for cap_id in then.get(field, []):
            if cap_id not in contract["capabilities"]:
                raise ContractError(f"Scenario {sid} {field} unknown capability {cap_id}")
    resource_exists = (then.get("resource") or {}).get("exists")
    if resource_exists and resource_exists["resource"] not in contract["resources"]:
        raise ContractError(f"Scenario {sid} asserts unknown resource {resource_exists['resource']}")
    for event_id in (then.get("events") or {}).get("emitted", []) + (then.get("events") or {}).get("not_emitted", []):
        if event_id not in contract["events"]:
            raise ContractError(f"Scenario {sid} asserts unknown event {event_id}")
    workflow = then.get("workflow")
    if workflow and workflow["ref"] not in contract["workflows"]:
        raise ContractError(f"Scenario {sid} asserts unknown workflow {workflow['ref']}")


def _validate_scenario_archetype(sid: str, scenario: dict[str, Any]) -> None:
    archetype = scenario["archetype"]
    when_kind, _ = _one(scenario["execute"], f"scenario {sid} when")
    then = scenario["assert"]
    if archetype == "empty_collection_view":
        if when_kind != "open_entry" or then.get("view", {}).get("state") != "empty":
            raise ContractError(f"Scenario {sid} empty_collection_view requires open_entry and view.state=empty")
    elif archetype == "ready_collection_view":
        if when_kind != "open_entry" or then.get("view", {}).get("state") != "ready":
            raise ContractError(f"Scenario {sid} ready_collection_view requires open_entry and view.state=ready")
    elif archetype == "composed_view_sync":
        view_assert = then.get("view", {})
        if when_kind != "open_entry" or not view_assert.get("panels"):
            raise ContractError(f"Scenario {sid} composed_view_sync requires open_entry and view.panels")
    elif archetype == "capability_success":
        if when_kind != "invoke_capability":
            raise ContractError(f"Scenario {sid} capability_success requires invoke_capability")
    elif archetype == "api_entry_success":
        if when_kind != "call_entry" or "response" not in then:
            raise ContractError(f"Scenario {sid} api_entry_success requires call_entry and response")
    elif archetype == "workflow_event_success":
        if when_kind != "emit_event" or not then.get("workflow", {}).get("ran"):
            raise ContractError(f"Scenario {sid} workflow_event_success requires emit_event and workflow.ran=true")
    elif archetype == "forbidden_action":
        if "forbids" not in then:
            raise ContractError(f"Scenario {sid} forbidden_action requires forbids")


def _expand_scenarios(contract: dict[str, Any]) -> None:
    for scenario in contract["scenarios"].values():
        assertions = scenario["assert"]
        if "view" in assertions:
            view_assert = assertions["view"]
            view_id = view_assert["ref"]
            view = contract["views"][view_id]
            if "panels" in view_assert:
                includes = {include["id"]: include for include in view.get("includes", [])}
                required = {"queries": [datum["query"] for datum in view.get("data", [])], "panel": [], "copy": [], "assets": [], "actions": []}
                if "state" in view_assert:
                    state_name = view_assert["state"]
                    state = view["states"][state_name]
                    view_assert["panel"] = state["panel"]
                    required["panel"].append(state["panel"])
                    required["queries"].extend(datum["query"] for datum in state.get("data", []))
                    required["copy"].extend(state["copy"])
                    required["assets"].extend(state["assets"])
                    required["actions"].extend(state["actions"])
                for instance_id, expected in view_assert["panels"].items():
                    include = includes[instance_id]
                    panel = contract["panels"][include["panel"]]
                    state = panel["states"][expected["state"]]
                    expected["panel"] = state["panel"]
                    expected["source"] = include["panel"]
                    required["queries"].extend(datum["query"] for datum in panel.get("data", []))
                    required["queries"].extend(datum["query"] for datum in state.get("data", []))
                    required["panel"].append(state["panel"])
                    required["copy"].extend(state["copy"])
                    required["assets"].extend(state["assets"])
                    required["actions"].extend(state["actions"])
                view_assert["composition"] = {
                    "layout": view.get("layout", {}),
                    "includes": view.get("includes", []),
                    "sync": view.get("sync", []),
                }
                assertions["requires"] = {key: list(dict.fromkeys(values)) for key, values in required.items()}
            elif "state" in view_assert:
                state_name = view_assert["state"]
                state = view["states"][state_name]
                view_assert["panel"] = state["panel"]
                assertions["requires"] = {
                    "queries": [datum["query"] for datum in view.get("data", [])] + [datum["query"] for datum in state.get("data", [])],
                    "panel": [state["panel"]],
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


def write_compiled(root: Path, patch_path: Path, tools_root: Path | None = None, render_audit: bool = True, layers: set[str] | None = None) -> dict[str, Any]:
    patch = read_yaml(patch_path)
    contract = compile_patch(patch, layers=layers)
    write_yaml(root / "contract.yaml", contract)
    generated = root / "generated"
    if generated.exists():
        shutil.rmtree(generated)
    for relative, content, kind in projection_files(contract):
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
        generate_audit(root, contract, tools_root=tools_root)
    return contract



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


def _unique(mapping: dict[str, Any], key: str, kind: str) -> None:
    if key in mapping:
        raise ContractError(f"Duplicate {kind}: {key}")


def _require(mapping: dict[str, Any], owner: str, field: str) -> None:
    if field not in mapping:
        raise ContractError(f"Entry {owner} must declare {field}")


def _path_params(path: str | None) -> set[str]:
    return set(re.findall(r"{([a-z][a-z0-9_]*)}", path or ""))


def _validate_path_params(entry: dict[str, Any], entry_id: str) -> None:
    placeholders = _path_params(entry.get("path"))
    declared = set((entry.get("params") or {}).keys())
    if placeholders != declared:
        raise ContractError(
            f"Entry {entry_id} path params {sorted(placeholders)} must exactly match params {sorted(declared)}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compile pm.patch.yaml into contract.yaml and generated projections.")
    parser.add_argument("patch", nargs="?", default="pm.patch.yaml")
    parser.add_argument("--out", default=".")
    parser.add_argument("--layers", default=None, help="Comma-separated authoring layers, e.g. core,http or core,ui,textual. Omit for full compatibility mode.")
    args = parser.parse_args(argv)
    try:
        write_compiled(Path(args.out).resolve(), Path(args.patch).resolve(), layers=parse_layers(args.layers))
        os._exit(0)
    except (ContractError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
