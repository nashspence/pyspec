from __future__ import annotations

import asyncio
import base64
import hashlib
import html
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Literal

from .compile import ContractError, render_examples
from .content import AssetResult, ContentContext, ContentError, call_asset, call_text
from .io import write_yaml
from .layout import renderer_textual_presentation, renderer_html_layout, renderer_html_presentation, renderer_html_regions
from .paths import GENERATED_SPEC_DIR, generated_relative as g
from .project import default_html_slots, format_attrs, humanize, state_machines_projection, state_machine_styles_projection, safe_id
from .runtime import fixture_namespace, resolve
from .targets import (
    entry_state_machine_renderer,
    entry_point_adapter_pair,
    entry_point_cli_command,
    entry_point_input,
    entry_point_method,
    entry_point_path,
    entry_point_response_handlers,
    entry_point_responses,
    entry_point_schedule_expression,
    entry_target_pair,
)
from .json_schema import effective_property_schema, schema_properties, type_display

ROOT = Path(__file__).resolve().parent

_EventCardMode = Literal["reference", "emitted"]

_DOT_FONT = "Arial"
_DOT_ARROW_FORWARD = "→"
_DOT_ARROW_ASSIGN = "←"

_DOT_SIZE_TITLE = 13
_DOT_SIZE_BODY = 10
_DOT_SIZE_META = 8
_DOT_SIZE_NODE = 9
_DOT_SIZE_DEFAULT_NODE = 11

_DOT_COLOR_EDGE = "#3f3f46"
_DOT_COLOR_MUTED = "#64748b"
_DOT_COLOR_TYPE = "#94a3b8"
_DOT_COLOR_AUDIT_TEXT = "#3f3f46"

_DOT_COLOR_ENTRY = "#0891b2"
_DOT_COLOR_ENTRY_TEXT = "#155e75"
_DOT_COLOR_ENTRY_HEADER = "#ecfeff"

_DOT_COLOR_NEUTRAL_BORDER = "#71717a"
_DOT_COLOR_NEUTRAL_HEADER = "#f8fafc"
_DOT_COLOR_BOUNDARY_BORDER = "#64748b"
_DOT_COLOR_TARGET_BORDER = "#9333ea"
_DOT_COLOR_TARGET_HEADER = "#faf5ff"
_DOT_COLOR_SUCCESS_BORDER = "#16a34a"
_DOT_COLOR_SUCCESS_HEADER = "#f0fdf4"
_DOT_COLOR_FAILURE_BORDER = "#dc2626"
_DOT_COLOR_FAILURE_HEADER = "#fef2f2"

_DOT_COLOR_CAPABILITY_BORDER = "#2563eb"
_DOT_COLOR_CAPABILITY_HEADER = "#eff6ff"
_DOT_COLOR_EVENT_BORDER = "#4f46e5"
_DOT_COLOR_EVENT_TEXT = "#312e81"
_DOT_COLOR_EVENT_HEADER = "#eef2ff"

_DOT_COLOR_STATE_MACHINE_BORDER = "#047857"
_DOT_COLOR_STATE_MACHINE_HEADER = "#ecfdf5"
_DOT_COLOR_WORKFLOW_BORDER = "#a16207"
_DOT_COLOR_WORKFLOW_HEADER = "#fefce8"
_DOT_COLOR_MESSAGE_BORDER = "#be185d"
_DOT_COLOR_MESSAGE_HEADER = "#fdf2f8"
_DOT_COLOR_CONTEXT_BORDER = "#15803d"
_DOT_COLOR_CONTEXT_HEADER = "#f0fdf4"
_DOT_COLOR_ENTITY_TYPE_BORDER = "#15803d"
_DOT_COLOR_ENTITY_TYPE_HEADER = "#f0fdfa"
_DOT_COLOR_SCHEMA_BORDER = "#7c3aed"
_DOT_COLOR_SCHEMA_HEADER = "#f5f3ff"
_DOT_COLOR_POLICY_BORDER = "#c2410c"
_DOT_COLOR_POLICY_HEADER = "#fff7ed"

_GRAPHVIZ_INPUT_HASH_PREFIX = "pyspec-contract-input-sha256:"
_TEXTUAL_INPUT_HASH_PREFIX = "pyspec-contract-textual-input-sha256:"


@dataclass(frozen=True)
class _DotCardStyle:
    header_bg: str
    border: str


_DOT_STYLE_ENTRY = _DotCardStyle(header_bg=_DOT_COLOR_ENTRY_HEADER, border=_DOT_COLOR_ENTRY)
_DOT_STYLE_EXTERNAL = _DotCardStyle(header_bg=_DOT_COLOR_NEUTRAL_HEADER, border=_DOT_COLOR_BOUNDARY_BORDER)
_DOT_STYLE_TARGET = _DotCardStyle(header_bg=_DOT_COLOR_TARGET_HEADER, border=_DOT_COLOR_TARGET_BORDER)
_DOT_STYLE_SUCCESS_EXIT = _DotCardStyle(header_bg=_DOT_COLOR_SUCCESS_HEADER, border=_DOT_COLOR_SUCCESS_BORDER)
_DOT_STYLE_FAILURE_EXIT = _DotCardStyle(header_bg=_DOT_COLOR_FAILURE_HEADER, border=_DOT_COLOR_FAILURE_BORDER)
_DOT_STYLE_NEUTRAL = _DotCardStyle(header_bg=_DOT_COLOR_NEUTRAL_HEADER, border=_DOT_COLOR_NEUTRAL_BORDER)
_DOT_STYLE_CAPABILITY = _DotCardStyle(header_bg=_DOT_COLOR_CAPABILITY_HEADER, border=_DOT_COLOR_CAPABILITY_BORDER)
_DOT_STYLE_EVENT = _DotCardStyle(header_bg=_DOT_COLOR_EVENT_HEADER, border=_DOT_COLOR_EVENT_BORDER)
_DOT_STYLE_STATE_MACHINE = _DotCardStyle(header_bg=_DOT_COLOR_STATE_MACHINE_HEADER, border=_DOT_COLOR_STATE_MACHINE_BORDER)
_DOT_STYLE_WORKFLOW = _DotCardStyle(header_bg=_DOT_COLOR_WORKFLOW_HEADER, border=_DOT_COLOR_WORKFLOW_BORDER)
_DOT_STYLE_MESSAGE = _DotCardStyle(header_bg=_DOT_COLOR_MESSAGE_HEADER, border=_DOT_COLOR_MESSAGE_BORDER)
_DOT_STYLE_CONTEXT = _DotCardStyle(header_bg=_DOT_COLOR_CONTEXT_HEADER, border=_DOT_COLOR_CONTEXT_BORDER)
_DOT_STYLE_ENTITY_TYPE = _DotCardStyle(header_bg=_DOT_COLOR_ENTITY_TYPE_HEADER, border=_DOT_COLOR_ENTITY_TYPE_BORDER)
_DOT_STYLE_SCHEMA = _DotCardStyle(header_bg=_DOT_COLOR_SCHEMA_HEADER, border=_DOT_COLOR_SCHEMA_BORDER)
_DOT_STYLE_POLICY = _DotCardStyle(header_bg=_DOT_COLOR_POLICY_HEADER, border=_DOT_COLOR_POLICY_BORDER)


def _under(relative: str, *parts: str) -> str:
    return "/".join([relative, *parts])


def state_machine_graph_file(state_machine_id: str) -> str:
    return g("audit_evidence", "state_machines", safe_id(state_machine_id), "state_machine.svg")


def view_state_root(state_machine_id: str, state_name: str) -> str:
    return g("audit_evidence", "state_machines", safe_id(state_machine_id), "view_states", safe_id(state_name))


def composition_file(state_machine_id: str, state_name: str = "ready") -> str:
    return g("audit_evidence", "state_machines", safe_id(state_machine_id), "view_states", safe_id(state_name), "composition.svg")


def entrypoint_flow_file(entry_id: str, adapter_kind: str) -> str:
    return g("audit_evidence", "entrypoints", safe_id(adapter_kind), safe_id(entry_id), "flow.svg")


def workflow_flow_file(workflow_id: str) -> str:
    return g("audit_evidence", "workflows", safe_id(workflow_id), "flow.svg")


def application_action_flow_file(application_action_id: str) -> str:
    return g("audit_evidence", "application_actions", safe_id(application_action_id), "flow.svg")


def audit_coverage_file() -> str:
    return g("audit_evidence", "coverage.yaml")


def render_example_root(state_machine_id: str, case_id: str, state_name: str = "ready") -> str:
    return g("audit_evidence", "state_machines", safe_id(state_machine_id), "view_states", safe_id(state_name), "render_examples", safe_id(case_id))


def _render_filename(profile_id: str, viewport_id: str, extension: str) -> str:
    stem = f"{safe_id(profile_id)}.{safe_id(viewport_id)}"
    if extension == "html":
        return f"html.{stem}.source.html"
    if extension == "png":
        return f"html.{stem}.screenshot.png"
    if extension == "py":
        return f"textual.{stem}.source.py"
    if extension == "svg":
        return f"textual.{stem}.capture.svg"
    raise ContractError(f"Unknown audit render extension: {extension}")


def view_state_render_file(state_machine_id: str, state_name: str, profile_id: str, viewport_id: str, extension: str) -> str:
    return _under(view_state_root(state_machine_id, state_name), "renders", _render_filename(profile_id, viewport_id, extension))


def render_example_render_file(state_machine_id: str, case_id: str, profile_id: str, viewport_id: str, extension: str, state_name: str = "ready") -> str:
    return _under(render_example_root(state_machine_id, case_id, state_name), "renders", _render_filename(profile_id, viewport_id, extension))


def _projection_surface_root(state_machine: dict[str, Any]) -> str:
    return view_state_root(state_machine["owner"], state_machine["view_state"])


def _projection_surface_file(state_machine: dict[str, Any], profile_id: str, viewport_id: str, extension: str) -> str:
    return view_state_render_file(state_machine["owner"], state_machine["view_state"], profile_id, viewport_id, extension)


def _render_example_root(contract: dict[str, Any], case_id: str, case: dict[str, Any]) -> str:
    return render_example_root(case["state_machine"], case_id, case["view_state"])


def _render_example_file(contract: dict[str, Any], case_id: str, case: dict[str, Any], profile_id: str, viewport_id: str, extension: str) -> str:
    return render_example_render_file(case["state_machine"], case_id, profile_id, viewport_id, extension, case["view_state"])


def _projection_render_surfaces(state_machine: dict[str, Any]) -> set[str]:
    renderers = state_machine.get("renderers") or {}
    surfaces: set[str] = set()
    if renderers.get("html"):
        surfaces.add("html")
    if renderers.get("textual"):
        surfaces.add("textual")
    return surfaces


def _render_example_surfaces(contract: dict[str, Any], case: dict[str, Any]) -> set[str]:
    state = contract["state_machines"][case["state_machine"]]["view_states"][case["view_state"]]
    renderers = state.get("renderers") or {}
    surfaces: set[str] = set()
    if renderers.get("html"):
        surfaces.add("html")
    if renderers.get("textual"):
        surfaces.add("textual")
    return surfaces


def _profile_viewports(contract: dict[str, Any], surface: str) -> list[tuple[str, str, dict[str, int]]]:
    field = "html_viewports" if surface == "html" else "textual_viewports"
    return [
        (profile_id, name, viewport)
        for profile_id, profile in sorted(contract.get("render_profiles", {}).items())
        for name, viewport in sorted(profile.get(field, {}).items())
    ]


def _scope_text_file(scope_root: str) -> str:
    return _under(scope_root, "text.yaml")


def _scope_fixtures_file(scope_root: str) -> str:
    return _under(scope_root, "fixtures.yaml")


def _scope_asset_file(scope_root: str, asset_id: str) -> str:
    return _under(scope_root, "assets", f"{safe_id(asset_id)}.svg")


def _text_doc(contract: dict[str, Any], text_refs: Iterable[str]) -> dict[str, Any]:
    return {"project": contract["project"], "text_resources": {ref: contract["text_resources"][ref] for ref in sorted(text_refs)}}


def _fixtures_doc(
    contract: dict[str, Any],
    fixture_ids: Iterable[str],
    precondition_ids: Iterable[str],
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "project": contract["project"],
        "fixtures": {fixture_id: contract["fixtures"][fixture_id] for fixture_id in sorted(fixture_ids)},
        "preconditions": {precondition_id: contract["preconditions"][precondition_id] for precondition_id in sorted(precondition_ids)},
        "context": context or {},
    }


def _state_needs_data(contract: dict[str, Any], state_machine: dict[str, Any]) -> bool:
    if state_machine.get("data_loaders") or state_machine["slots"].get("fields"):
        return True
    text_refs = state_machine["slots"].get("text", [])
    asset_refs = state_machine["slots"].get("assets", [])
    return any(contract["text_resources"][ref].get("args") for ref in text_refs) or any(contract["assets"][ref].get("args") for ref in asset_refs)


def _fixture_ids_for_model(contract: dict[str, Any], entity_type_id: str) -> set[str]:
    return {
        fixture_id
        for fixture_id, fixture in contract.get("fixtures", {}).items()
        if _find_model_records(fixture.get("values", {}), entity_type_id)
    }


def _precondition_ids_for_model(contract: dict[str, Any], entity_type_id: str) -> set[str]:
    precondition_ids = set()
    for precondition_id, precondition in contract.get("preconditions", {}).items():
        _, body = _precondition_selector(precondition, precondition_id)
        if body["entity_type"] == entity_type_id:
            precondition_ids.add(precondition_id)
    return precondition_ids


def _fixture_ids_for_preconditions(contract: dict[str, Any], precondition_ids: Iterable[str], entity_type_id: str) -> set[str]:
    fixture_ids: set[str] = set()
    for precondition_id in sorted(precondition_ids):
        precondition_uses = [{"ref": precondition_id}]
        try:
            _apply_precondition_uses(contract, precondition_uses, {}, entity_type_id, [])
            continue
        except (AssertionError, KeyError, TypeError):
            pass
        for fixture_id in contract.get("fixtures", {}):
            try:
                namespace = fixture_namespace(contract, [fixture_id])
                _apply_precondition_uses(contract, precondition_uses, namespace, entity_type_id, [])
            except (AssertionError, KeyError, TypeError):
                continue
            fixture_ids.add(fixture_id)
            break
    return fixture_ids


def _surface_scope_inputs(contract: dict[str, Any], state_machine: dict[str, Any]) -> tuple[set[str], set[str], set[str], set[str], dict[str, Any]]:
    text_refs = set(state_machine["slots"].get("text", []))
    asset_refs = set(state_machine["slots"].get("assets", []))
    fixture_ids: set[str] = set()
    precondition_ids: set[str] = set()
    if _state_needs_data(contract, state_machine):
        entity_type_id = state_machine_model(contract, state_machine)
        fixture_ids = _fixture_ids_for_model(contract, entity_type_id)
        precondition_ids = _precondition_ids_for_model(contract, entity_type_id)
        fixture_ids.update(_fixture_ids_for_preconditions(contract, precondition_ids, entity_type_id))
    return text_refs, asset_refs, fixture_ids, precondition_ids, {}


def _render_example_scope_inputs(contract: dict[str, Any], case: dict[str, Any]) -> tuple[set[str], set[str], set[str], set[str], dict[str, Any]]:
    state_machines = render_example_state_machines(contract, case)
    text_refs = {text_ref for state_machine in state_machines for text_ref in state_machine["slots"].get("text", [])}
    asset_refs = {asset_ref for state_machine in state_machines for asset_ref in state_machine["slots"].get("assets", [])}
    fixture_ids = set(case.get("seed_fixtures", []))
    precondition_ids = {precondition_use["ref"] for precondition_use in case.get("precondition_refs", [])}
    return text_refs, asset_refs, fixture_ids, precondition_ids, case.get("context") or {}


def _audit_scope_expected_files(scope_root: str, asset_refs: Iterable[str]) -> set[str]:
    files = {_scope_text_file(scope_root), _scope_fixtures_file(scope_root)}
    files.update(_scope_asset_file(scope_root, asset_id) for asset_id in asset_refs)
    return files


def _write_audit_scope_inputs(
    root: Path,
    contract: dict[str, Any],
    scope_root: str,
    text_refs: Iterable[str],
    asset_refs: Iterable[str],
    fixture_ids: Iterable[str],
    precondition_ids: Iterable[str],
    context: dict[str, Any] | None = None,
) -> None:
    text_path = root / _scope_text_file(scope_root)
    text_path.parent.mkdir(parents=True, exist_ok=True)
    write_yaml(text_path, _text_doc(contract, text_refs))
    fixtures_path = root / _scope_fixtures_file(scope_root)
    fixtures_path.parent.mkdir(parents=True, exist_ok=True)
    write_yaml(fixtures_path, _fixtures_doc(contract, fixture_ids, precondition_ids, context))
    for asset_id in sorted(asset_refs):
        asset_path = root / _scope_asset_file(scope_root, asset_id)
        asset_path.parent.mkdir(parents=True, exist_ok=True)
        asset_path.write_text(asset_placeholder_svg(contract["assets"][asset_id]), encoding="utf-8")


def _write_audit_inputs(root: Path, contract: dict[str, Any], projection: dict[str, Any]) -> None:
    for state_machine in _audit_projection_surfaces(contract, projection):
        if not _projection_render_surfaces(state_machine):
            continue
        _write_audit_scope_inputs(root, contract, _projection_surface_root(state_machine), *_surface_scope_inputs(contract, state_machine))
    for case_id, case in sorted(render_examples(contract).items()):
        _write_audit_scope_inputs(root, contract, _render_example_root(contract, case_id, case), *_render_example_scope_inputs(contract, case))


def _audit_projection_surfaces(contract: dict[str, Any], projection: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        state_machine
        for state_machine in projection["state_machines"]
        if not contract["state_machines"][state_machine["owner"]]["view_states"][state_machine["view_state"]].get("child_state_machines")
    ]


def _audit_visual_expected_files(contract: dict[str, Any]) -> set[str]:
    files: set[str] = set()
    for state_machine_id in contract.get("state_machines", {}):
        files.add(state_machine_graph_file(state_machine_id))
    for state_machine_id, state_machine in contract.get("state_machines", {}).items():
        for state_name, state in state_machine.get("view_states", {}).items():
            if state.get("child_state_machines"):
                files.add(composition_file(state_machine_id, state_name))
    for entry_id, entry in contract.get("entry_points", {}).items():
        adapter_kind, _ = entry_point_adapter_pair(entry)
        files.add(entrypoint_flow_file(entry_id, adapter_kind))
    for workflow_id in contract.get("workflows", {}):
        files.add(workflow_flow_file(workflow_id))
    for application_action_id in contract.get("application_actions", {}):
        files.add(application_action_flow_file(application_action_id))

    projection = state_machines_projection(contract)
    for state_machine in _audit_projection_surfaces(contract, projection):
        render_surfaces = _projection_render_surfaces(state_machine)
        if not render_surfaces:
            continue
        scope_root = _projection_surface_root(state_machine)
        _, asset_refs, _, _, _ = _surface_scope_inputs(contract, state_machine)
        files.update(_audit_scope_expected_files(scope_root, asset_refs))
        if "html" in render_surfaces:
            for profile_id, breakpoint, _ in _profile_viewports(contract, "html"):
                files.add(_projection_surface_file(state_machine, profile_id, breakpoint, "html"))
                files.add(_projection_surface_file(state_machine, profile_id, breakpoint, "png"))
        if "textual" in render_surfaces:
            for profile_id, breakpoint, _ in _profile_viewports(contract, "textual"):
                files.add(_projection_surface_file(state_machine, profile_id, breakpoint, "py"))
                files.add(_projection_surface_file(state_machine, profile_id, breakpoint, "svg"))

    for case_id, case in render_examples(contract).items():
        scope_root = _render_example_root(contract, case_id, case)
        _, asset_refs, _, _, _ = _render_example_scope_inputs(contract, case)
        files.update(_audit_scope_expected_files(scope_root, asset_refs))
        render_surfaces = _render_example_surfaces(contract, case)
        if "html" in render_surfaces:
            for profile_id, breakpoint, _ in _profile_viewports(contract, "html"):
                files.add(_render_example_file(contract, case_id, case, profile_id, breakpoint, "html"))
                files.add(_render_example_file(contract, case_id, case, profile_id, breakpoint, "png"))
        if "textual" in render_surfaces:
            for profile_id, breakpoint, _ in _profile_viewports(contract, "textual"):
                files.add(_render_example_file(contract, case_id, case, profile_id, breakpoint, "py"))
                files.add(_render_example_file(contract, case_id, case, profile_id, breakpoint, "svg"))
    return files


def audit_expected_files(contract: dict[str, Any]) -> set[str]:
    return {audit_coverage_file()} | _audit_visual_expected_files(contract)


def _audit_visual_evidence_files(contract: dict[str, Any]) -> set[str]:
    files: set[str] = set()
    for state_machine_id in contract.get("state_machines", {}):
        files.add(state_machine_graph_file(state_machine_id))
    for state_machine_id, state_machine in contract.get("state_machines", {}).items():
        for state_name, state in state_machine.get("view_states", {}).items():
            if state.get("child_state_machines"):
                files.add(composition_file(state_machine_id, state_name))
    for entry_id, entry in contract.get("entry_points", {}).items():
        adapter_kind, _ = entry_point_adapter_pair(entry)
        files.add(entrypoint_flow_file(entry_id, adapter_kind))
    for workflow_id in contract.get("workflows", {}):
        files.add(workflow_flow_file(workflow_id))
    for application_action_id in contract.get("application_actions", {}):
        files.add(application_action_flow_file(application_action_id))

    projection = state_machines_projection(contract)
    for surface in _audit_projection_surfaces(contract, projection):
        files.update(_projection_surface_render_capture_files(contract, surface))
    for case_id, case in render_examples(contract).items():
        files.update(_render_example_capture_files(contract, case_id, case))
    return files


def _write_audit_coverage_index(root: Path, contract: dict[str, Any]) -> None:
    path = root / audit_coverage_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    write_yaml(path, audit_coverage_index(contract), sort_keys=False)


def audit_coverage_index(contract: dict[str, Any]) -> dict[str, Any]:
    visual_evidence_sets: dict[str, list[str]] = {}
    visual_evidence_set_ids: dict[tuple[str, ...], str] = {}
    required_covered: dict[str, str] = {}
    required_missing: dict[str, dict[str, str]] = {}
    optional_covered: dict[str, str] = {}
    optional_not_shown: dict[str, dict[str, str]] = {}
    non_visual_paths: dict[str, dict[str, Any]] = {}

    def visual_evidence_set_id(files: list[str]) -> str:
        key = tuple(files)
        if key not in visual_evidence_set_ids:
            set_id = f"V{len(visual_evidence_set_ids) + 1:04d}"
            visual_evidence_set_ids[key] = set_id
            visual_evidence_sets[set_id] = files
        return visual_evidence_set_ids[key]

    for pointer in _contract_audit_pointers(contract):
        non_visual_path = _non_visual_path_classification(contract, pointer)
        if non_visual_path:
            non_visual_evidence = non_visual_path.pop("evidence", [])
            if non_visual_evidence:
                non_visual_path["visual_evidence_set"] = visual_evidence_set_id(non_visual_evidence)
            non_visual_paths[pointer] = non_visual_path
            continue
        obligation = _visual_path_obligation(contract, pointer)
        evidence = _filter_evidence_files(contract, _audit_evidence_for_pointer(contract, pointer))
        if obligation["level"] == "required":
            if evidence:
                required_covered[pointer] = visual_evidence_set_id(evidence)
            else:
                required_missing[pointer] = {"reason": obligation["reason"]}
            continue
        if evidence:
            optional_covered[pointer] = visual_evidence_set_id(evidence)
        else:
            optional_not_shown[pointer] = {"reason": obligation["reason"]}
    render_presence = _render_resource_coverage(contract, visual_evidence_set_id)
    required_text_witnesses = _visual_text_witnesses(contract, required_covered, visual_evidence_sets)
    return {
        "version": 1,
        "project": contract.get("project"),
        "summary": {
            "required_visual_paths": len(required_covered) + len(required_missing),
            "missing_required_visual_paths": len(required_missing),
            "required_visual_text_witnesses": len(required_text_witnesses),
            "optional_visual_paths": len(optional_covered) + len(optional_not_shown),
            "optional_visual_paths_not_shown": len(optional_not_shown),
            "non_visual_paths": len(non_visual_paths),
            "visual_evidence_sets": len(visual_evidence_sets),
        },
        "visual_evidence_sets": visual_evidence_sets,
        "render_presence": render_presence,
        "visual_audit": {
            "required": {
                "covered": required_covered,
                "missing": required_missing,
                "text_witnesses": required_text_witnesses,
            },
            "optional": {
                "covered": optional_covered,
                "not_shown": optional_not_shown,
            },
            "non_visual": non_visual_paths,
        },
    }


def _contract_audit_pointers(contract: dict[str, Any]) -> list[str]:
    return sorted(_iter_contract_leaf_pointers(contract, ()))


def _iter_contract_leaf_pointers(value: Any, parts: tuple[str, ...]) -> Iterable[str]:
    if isinstance(value, dict):
        if not value:
            yield _json_pointer(parts)
            return
        for key in sorted(value):
            yield from _iter_contract_leaf_pointers(value[key], (*parts, str(key)))
        return
    if isinstance(value, list):
        if not value:
            yield _json_pointer(parts)
            return
        for index, item in enumerate(value):
            yield from _iter_contract_leaf_pointers(item, (*parts, str(index)))
        return
    yield _json_pointer(parts)


def _json_pointer(parts: Iterable[str]) -> str:
    return "/" + "/".join(part.replace("~", "~0").replace("/", "~1") for part in parts)


def _json_pointer_parts(pointer: str) -> list[str]:
    if pointer == "/":
        return []
    return [part.replace("~1", "/").replace("~0", "~") for part in pointer.removeprefix("/").split("/")]


def _non_visual_path_classification(contract: dict[str, Any], pointer: str) -> dict[str, Any] | None:
    parts = _json_pointer_parts(pointer)
    if not parts:
        return None
    _ = contract
    if parts[0] == "project":
        return {
            "reason": "workspace metadata for generated artifacts; visual coverage tracks product contract paths",
        }
    if parts[0] == "refs":
        return {
            "reason": "compiled reference index metadata; owning resources are covered at their compiled spec paths",
        }
    return None


def _visual_path_obligation(contract: dict[str, Any], pointer: str) -> dict[str, str]:
    parts = _json_pointer_parts(pointer)
    if parts and parts[0] in {"assets", "assertions", "content_examples", "preconditions", "fixtures", "behavior_scenarios", "text_resources"}:
        return {"level": "optional", "reason": _optional_visual_path_reason(parts[0])}
    _ = contract
    return {"level": "required", "reason": "required product contract path has no diagram or render-capture evidence"}


def _optional_visual_path_reason(collection: str) -> str:
    return {
        "assets": "declared assets may be unused by rendered states",
        "assertions": "assertions are expected predicates and need not appear in render examples",
        "content_examples": "content examples are visual only when their referenced resource is rendered",
        "preconditions": "preconditions may support behavior setup without dedicated visual evidence",
        "fixtures": "fixtures may support behavior or content tests without appearing in render examples",
        "behavior_scenarios": "behavior scenarios may be represented by diagrams or renders, but are not required visual evidence",
        "text_resources": "text resources may be adapter or branch-specific and need not appear in rendered states",
    }[collection]


def _audit_evidence_for_pointer(contract: dict[str, Any], pointer: str) -> list[str]:
    parts = _json_pointer_parts(pointer)
    if not parts:
        return []
    if parts[0] == "project":
        return [audit_coverage_file()]
    if len(parts) < 2:
        return []
    owner = parts[1]
    if parts[0] == "assets":
        return _asset_evidence_files(contract, owner)
    if parts[0] == "authorization_policies":
        return _authorization_policy_evidence_files(contract, owner)
    if parts[0] == "content_examples":
        return _content_example_evidence_files(contract, owner)
    if parts[0] == "schemas":
        return _schema_evidence_files(contract, owner)
    if parts[0] == "entry_points":
        return _entry_point_evidence_files(contract, owner)
    if parts[0] == "domain_events":
        return _event_evidence_files(contract, owner)
    if parts[0] == "preconditions":
        return _precondition_evidence_files(contract, owner)
    if parts[0] == "fixtures":
        return _fixture_evidence_files(contract, owner)
    if parts[0] == "entity_types":
        return _model_evidence_files(contract, owner)
    if parts[0] == "application_actions":
        return _application_action_evidence_files(contract, owner)
    if parts[0] == "render_profiles":
        return _all_render_evidence_files(contract)
    if parts[0] == "state_machines":
        state_name = parts[3] if len(parts) >= 4 and parts[2] == "view_states" else None
        return _state_machine_evidence_files(contract, owner, state_name)
    if parts[0] == "behavior_scenarios":
        return _behavior_scenario_evidence_files(contract, owner)
    if parts[0] == "text_resources":
        return _text_resource_evidence_files(contract, owner)
    if parts[0] == "workflows":
        return _workflow_evidence_files(contract, owner)
    return []


def _filter_evidence_files(contract: dict[str, Any], files: Iterable[str]) -> list[str]:
    valid = _audit_visual_evidence_files(contract)
    return sorted({path for path in files if path in valid})


def _render_resource_coverage(contract: dict[str, Any], evidence_set_id: Any) -> dict[str, Any]:
    return {
        "assets": _render_resource_collection_coverage(contract, "assets", "asset", evidence_set_id),
        "text_resources": _render_resource_collection_coverage(contract, "text_resources", "text", evidence_set_id),
        "fixtures": _render_resource_collection_coverage(contract, "fixtures", "fixture", evidence_set_id),
        "preconditions": _render_resource_collection_coverage(contract, "preconditions", "precondition", evidence_set_id),
        "content_examples": _render_content_example_coverage(contract, evidence_set_id),
    }


def _render_resource_collection_coverage(contract: dict[str, Any], collection: str, kind: str, evidence_set_id: Any) -> dict[str, Any]:
    rendered: dict[str, str] = {}
    not_rendered: list[str] = []
    for resource_id in sorted(contract.get(collection, {})):
        evidence = _filter_evidence_files(contract, _scope_input_evidence_files(contract, resource_id, kind))
        if evidence:
            rendered[resource_id] = evidence_set_id(evidence)
        else:
            not_rendered.append(resource_id)
    return {"rendered": rendered, "not_rendered": not_rendered}


def _render_content_example_coverage(contract: dict[str, Any], evidence_set_id: Any) -> dict[str, Any]:
    rendered: dict[str, str] = {}
    not_rendered: list[str] = []
    for content_example_id, content_example in sorted(contract.get("content_examples", {}).items()):
        ref = content_example.get("ref")
        evidence: list[str] = []
        if ref in contract.get("text_resources", {}):
            evidence = _filter_evidence_files(contract, _scope_input_evidence_files(contract, ref, "text"))
        elif ref in contract.get("assets", {}):
            evidence = _filter_evidence_files(contract, _scope_input_evidence_files(contract, ref, "asset"))
        if evidence:
            rendered[content_example_id] = evidence_set_id(evidence)
        else:
            not_rendered.append(content_example_id)
    return {"rendered": rendered, "not_rendered": not_rendered}


_VISUAL_TEXT_REF_PREFIXES = (
    "asset.",
    "authorization_policy.",
    "cli_command.",
    "schema.",
    "data_refresh_signal.",
    "entry_point.",
    "domain_event.",
    "local_signal.",
    "application_action.",
    "query.",
    "state_machine.",
    "text.",
    "workflow.",
)


def _visual_text_witnesses(
    contract: dict[str, Any],
    required_covered: dict[str, str],
    visual_evidence_sets: dict[str, list[str]],
) -> dict[str, dict[str, Any]]:
    witnesses: dict[str, dict[str, Any]] = {}
    for pointer, evidence_set in sorted(required_covered.items()):
        evidence_files = visual_evidence_sets[evidence_set]
        if not any(path.endswith(".svg") for path in evidence_files):
            continue
        tokens = _visual_text_witness_tokens(contract, pointer, evidence_files)
        if tokens:
            witnesses[pointer] = {
                "visual_evidence_set": evidence_set,
                "tokens": tokens,
            }
    return witnesses


def _visual_text_witness_tokens(contract: dict[str, Any], pointer: str, evidence_files: Iterable[str]) -> list[str]:
    parts = _json_pointer_parts(pointer)
    if len(parts) < 2:
        return []
    try:
        value = _contract_value_at_parts(contract, parts)
    except (KeyError, IndexError, TypeError, ValueError):
        return []

    tokens: list[str] = []
    detail_evidence = _has_detail_card_evidence(evidence_files)
    if isinstance(value, str) and _generic_reference_witness_allowed(parts, detail_evidence) and _is_visual_text_reference(value):
        tokens.append(value)

    collection = parts[0]
    if collection == "authorization_policies":
        if not detail_evidence:
            return _unique_visual_text_tokens(tokens)
        tokens.extend(_authorization_policy_text_witness_tokens(contract, parts, value))
    elif collection == "entry_points":
        tokens.extend(_entry_point_text_witness_tokens(contract, parts, value))
    elif collection == "application_actions":
        tokens.extend(_application_action_text_witness_tokens(contract, parts, value, detail_evidence))
    elif collection == "domain_events":
        tokens.extend(_event_text_witness_tokens(contract, parts, value))
    elif collection == "workflows":
        tokens.extend(_workflow_text_witness_tokens(contract, parts, value))
    elif collection == "state_machines":
        tokens.extend(_state_machine_text_witness_tokens(contract, parts, value))
    elif collection == "entity_types":
        tokens.extend(_entity_type_text_witness_tokens(contract, parts, value))
    return _unique_visual_text_tokens(tokens)


def _contract_value_at_parts(value: Any, parts: Iterable[str]) -> Any:
    current = value
    for part in parts:
        if isinstance(current, list):
            current = current[int(part)]
        else:
            current = current[part]
    return current


def _is_visual_text_reference(value: str) -> bool:
    if any(value.startswith(prefix) for prefix in _VISUAL_TEXT_REF_PREFIXES):
        return True
    return False


def _generic_reference_witness_allowed(parts: list[str], detail_evidence: bool) -> bool:
    if not parts:
        return False
    if parts[0] in {"entry_points", "state_machines", "workflows"}:
        if parts[0] == "state_machines":
            return _state_machine_reference_witness_allowed(parts)
        return True
    if parts[0] == "application_actions":
        return detail_evidence or parts[-2:] == ["authorization", "policy"]
    if parts[0] == "domain_events":
        return detail_evidence
    if parts[0] == "authorization_policies":
        return detail_evidence
    return False


def _state_machine_reference_witness_allowed(parts: list[str]) -> bool:
    if "view_states" in parts:
        return any(marker in parts for marker in {"text", "assets", "action_bindings", "child_state_machines", "signal_sync_rules"})
    if "transitions" in parts:
        return parts[-1] in {"data_refresh_signal", "local_signal", "application_action", "state_machine", "workflow", "domain_event"}
    if "signals" in parts:
        return "local_signals" in parts
    return False


def _has_detail_card_evidence(evidence_files: Iterable[str]) -> bool:
    return any(
        f"/{folder}/" in path
        for path in evidence_files
        for folder in ("entrypoints", "workflows", "application_actions")
    )


def _unique_visual_text_tokens(tokens: Iterable[object]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        text = str(token).strip()
        if not text or text in seen:
            continue
        unique.append(text)
        seen.add(text)
    return unique


def _authorization_policy_text_witness_tokens(contract: dict[str, Any], parts: list[str], value: Any) -> list[str]:
    if len(parts) < 3:
        return []
    policy_id = parts[1]
    policy = contract.get("authorization_policies", {}).get(policy_id, {})
    if parts[2] == "effect" and isinstance(value, str):
        return ["effect", value]
    if parts[2] == "subjects" and len(parts) >= 5:
        if parts[-1] == "kind" and isinstance(value, str):
            return ["subjects", value]
        if parts[-1] == "source" and isinstance(value, str):
            return ["subjects", _format_flow_source(value)]
    if parts[2] == "resources" and isinstance(value, str):
        return [value]
    if parts[2] == "conditions" and len(parts) >= 5:
        try:
            condition = policy.get("conditions", [])[int(parts[3])]
        except (IndexError, TypeError, ValueError):
            return []
        if "entity_state_condition" in condition:
            body = condition["entity_state_condition"]
            tokens = [f"{type_display({'$ref': body['entity_type']})}.{body['field']}"]
            if parts[-1] == "equals":
                tokens.append(_format_scalar(value))
            return tokens
        if "entity_exists" in condition and isinstance(value, str):
            return [f"{type_display({'$ref': value})} exists"]
        if "input_present" in condition and isinstance(value, str):
            return ["input_present", value]
        if "subject_has_role" in condition and isinstance(value, str):
            return ["subject_has_role", value]
    return []


def _entry_point_text_witness_tokens(contract: dict[str, Any], parts: list[str], value: Any) -> list[str]:
    _ = contract
    tokens: list[str] = []
    if isinstance(value, str):
        if parts[-1] == "cli_command":
            tokens.append(value)
        elif parts[-1] == "method":
            tokens.append(value.upper())
        elif parts[-1] in {"path", "route", "endpoint", "screen"}:
            tokens.append(value)
        elif parts[-1] == "disposition":
            tokens.extend(["disposition", value])
        elif parts[-1] == "backoff":
            tokens.extend(["retry", value])
        elif parts[-1] == "from" and "bindings" in parts:
            tokens.append(_format_flow_source(value))
    elif isinstance(value, int):
        if parts[-1] == "status":
            tokens.extend(["status", str(value)])
        elif parts[-1] == "exit_code":
            tokens.extend(["exit_code", str(value)])
        elif parts[-1] == "attempts":
            tokens.extend(["retry", str(value)])
    tokens.extend(_type_leaf_text_witness_tokens(contract, parts))
    return tokens


def _application_action_text_witness_tokens(contract: dict[str, Any], parts: list[str], value: Any, detail_evidence: bool) -> list[str]:
    if not detail_evidence:
        return []
    tokens: list[str] = []
    if len(parts) >= 4 and parts[2] == "authorization":
        if parts[-1] == "policy" and isinstance(value, str):
            return [value]
        if parts[-1] in {"authentication_required_as", "access_denied_as"} and isinstance(value, str):
            return [parts[-1], value]
    if len(parts) >= 5 and parts[2] == "lifecycle_transition":
        lifecycle_transition = contract["application_actions"][parts[1]]["lifecycle_transition"]
        field_token = f"{type_display({'$ref': lifecycle_transition['entity_type']})}.{lifecycle_transition['field']}"
        tokens.append(field_token)
        if parts[-1] in {"from", "to"}:
            tokens.append(_format_scalar(value))
        return tokens
    if len(parts) >= 5 and parts[2] == "outcomes":
        outcome_id = parts[3]
        outcome = contract["application_actions"][parts[1]]["outcomes"][outcome_id]
        if parts[-1] == "kind" and isinstance(value, str):
            return [outcome_id, value]
        if parts[-2:] == ["result", "$ref"] and isinstance(value, str):
            return [outcome_id, type_display({"$ref": value})]
    tokens.extend(_type_leaf_text_witness_tokens(contract, parts))
    return tokens


def _event_text_witness_tokens(contract: dict[str, Any], parts: list[str], value: Any) -> list[str]:
    _ = contract
    if len(parts) >= 3 and parts[2] == "emitted_by" and isinstance(value, str):
        return [value]
    return []


def _workflow_text_witness_tokens(contract: dict[str, Any], parts: list[str], value: Any) -> list[str]:
    _ = contract
    tokens: list[str] = []
    if isinstance(value, str):
        if parts[-1] == "id" and "steps" in parts:
            tokens.append(value)
        elif len(parts) >= 5 and parts[2] == "outcomes":
            outcome_id = parts[3]
            if parts[-1] == "kind":
                tokens.extend([outcome_id, value])
            elif parts[-2:] == ["result", "schema"]:
                tokens.extend([outcome_id, value])
        elif parts[-1] in {"complete_as", "fail_as", "dead_letter_as", "next_step"}:
            tokens.append(value)
        elif parts[-1] == "backoff":
            tokens.extend(["retry_policy", value])
    elif isinstance(value, int) and parts[-1] == "attempts":
        tokens.extend(["retry_policy", str(value)])
    return tokens


def _state_machine_text_witness_tokens(contract: dict[str, Any], parts: list[str], value: Any) -> list[str]:
    _ = contract
    tokens: list[str] = []
    if isinstance(value, str) and "child_state_machines" in parts and parts[-1] in {"html_region", "textual_container", "initial_view_state"}:
        tokens.append(value)
    tokens.extend(_type_leaf_text_witness_tokens(contract, parts))
    return tokens


def _entity_type_text_witness_tokens(contract: dict[str, Any], parts: list[str], value: Any) -> list[str]:
    tokens = _type_leaf_text_witness_tokens(contract, parts)
    if len(parts) >= 4 and parts[2] == "entity_lifecycle" and isinstance(value, str):
        if parts[-1] in {"field", "initial_state"}:
            tokens.append(value)
        elif "lifecycle_states" in parts or parts[-1] in {"from", "to"}:
            tokens.append(value)
    return tokens


def _type_leaf_text_witness_tokens(contract: dict[str, Any], parts: list[str]) -> list[str]:
    if not parts or parts[-1] not in {"$ref", "type", "items", "enum", "const", "format"}:
        return []
    if parts[0] not in {"entry_points", "entity_types", "schemas", "application_actions", "state_machines", "workflows"}:
        return []
    parent_parts = parts[:-1]
    try:
        schema = _contract_value_at_parts(contract, parent_parts)
    except (KeyError, IndexError, TypeError, ValueError):
        return []
    field = _type_field_name(parts)
    if not field:
        return []
    return [field, type_display(schema)]


def _type_field_name(parts: list[str]) -> str | None:
    if len(parts) >= 6 and parts[0] == "entity_types" and parts[2] == "schema" and "properties" in parts:
        return _part_after(parts, "properties")
    if len(parts) >= 6 and parts[0] == "application_actions" and parts[2] == "input" and "properties" in parts:
        return _part_after(parts, "properties")
    if len(parts) >= 6 and parts[0] == "schemas" and parts[2] == "schema" and "properties" in parts:
        return _part_after(parts, "properties")
    if parts[0] == "entry_points":
        if "path_params" in parts:
            return _part_after(parts, "path_params")
        if "query_params" in parts:
            return _part_after(parts, "query_params")
        if "body" in parts:
            field = _part_after(parts, "body")
            return "body" if field == "type" else field
        if "args" in parts:
            return _part_after(parts, "args")
        if "payload" in parts:
            return "payload"
        if "stdout" in parts:
            return "stdout"
        if "stderr" in parts:
            return "stderr"
        if "problem" in parts:
            return "problem"
        if "result" in parts:
            return parts[parts.index("result") - 1] if parts.index("result") > 0 else None
    if len(parts) >= 5 and parts[0] == "workflows" and parts[2] == "outcomes" and parts[4] == "result":
        return parts[3]
    if parts[0] == "state_machines" and "payload_schema" in parts:
        return _part_after(parts, "properties")
    return None


def _part_after(parts: list[str], marker: str) -> str | None:
    try:
        index = parts.index(marker) + 1
    except ValueError:
        return None
    return parts[index] if index < len(parts) else None


def _entry_point_evidence_files(contract: dict[str, Any], entry_id: str) -> list[str]:
    entry = contract.get("entry_points", {}).get(entry_id)
    if not entry:
        return []
    adapter_kind, _ = entry_point_adapter_pair(entry)
    return [entrypoint_flow_file(entry_id, adapter_kind)]


def _workflow_evidence_files(contract: dict[str, Any], workflow_id: str) -> list[str]:
    if workflow_id not in contract.get("workflows", {}):
        return []
    return [workflow_flow_file(workflow_id)]


def _state_machine_evidence_files(contract: dict[str, Any], state_machine_id: str, state_name: str | None = None) -> list[str]:
    state_machine = contract.get("state_machines", {}).get(state_machine_id)
    if not state_machine:
        return []
    files = [state_machine_graph_file(state_machine_id)]
    states = {state_name: state_machine["view_states"][state_name]} if state_name else state_machine.get("view_states", {})
    projection = state_machines_projection(contract)
    for current_state_name, state in states.items():
        if state.get("child_state_machines"):
            files.append(composition_file(state_machine_id, current_state_name))
        files.extend(_view_state_render_evidence_files(contract, state_machine_id, current_state_name))
        for surface in _audit_projection_surfaces(contract, projection):
            if surface["owner"] == state_machine_id and surface["view_state"] == current_state_name:
                files.extend(_projection_surface_render_capture_files(contract, surface))
    return files


def _application_action_evidence_files(contract: dict[str, Any], application_action_id: str) -> list[str]:
    if application_action_id not in contract.get("application_actions", {}):
        return []
    files: list[str] = [application_action_flow_file(application_action_id)]
    for entry_id, entry in sorted(contract.get("entry_points", {}).items()):
        target_kind, target_value = entry_target_pair(entry)
        if target_kind == "application_action" and target_value == application_action_id:
            files.extend(_entry_point_evidence_files(contract, entry_id))
        elif target_kind == "entry_point":
            delegated = contract.get("entry_points", {}).get(target_value)
            if delegated:
                delegated_target_kind, delegated_target_value = entry_target_pair(delegated)
                if delegated_target_kind == "application_action" and delegated_target_value == application_action_id:
                    files.extend(_entry_point_evidence_files(contract, entry_id))
    for workflow_id, workflow in sorted(contract.get("workflows", {}).items()):
        if any(step.get("application_action") == application_action_id for step in workflow.get("steps", [])):
            files.extend(_workflow_evidence_files(contract, workflow_id))
    for state_machine_id, state_machine in sorted(contract.get("state_machines", {}).items()):
        if _value_contains_string(state_machine, application_action_id):
            files.extend(_state_machine_evidence_files(contract, state_machine_id))
    return files


def _authorization_policy_evidence_files(contract: dict[str, Any], policy_id: str) -> list[str]:
    if policy_id not in contract.get("authorization_policies", {}):
        return []
    files: list[str] = []
    for entry_id, entry in sorted(contract.get("entry_points", {}).items()):
        if entry.get("authorization_policy") == policy_id:
            files.extend(_entry_point_evidence_files(contract, entry_id))
    for application_action_id, application_action in sorted(contract.get("application_actions", {}).items()):
        if (application_action.get("authorization") or {}).get("policy") == policy_id:
            files.extend(_application_action_evidence_files(contract, application_action_id))
    return files


def _event_evidence_files(contract: dict[str, Any], event_id: str) -> list[str]:
    if event_id not in contract.get("domain_events", {}):
        return []
    files: list[str] = []
    event = contract["domain_events"][event_id]
    for application_action_id in event.get("emitted_by", []):
        files.extend(_application_action_evidence_files(contract, application_action_id))
    for workflow_id, workflow in sorted(contract.get("workflows", {}).items()):
        if _value_contains_string(workflow.get("trigger", {}), event_id):
            files.extend(_workflow_evidence_files(contract, workflow_id))
    for entry_id, entry in sorted(contract.get("entry_points", {}).items()):
        if _value_contains_string(entry, event_id):
            files.extend(_entry_point_evidence_files(contract, entry_id))
    return files


def _schema_evidence_files(contract: dict[str, Any], schema_id: str) -> list[str]:
    if schema_id not in contract.get("schemas", {}):
        return []
    files: list[str] = []
    for event_id, event in sorted(contract.get("domain_events", {}).items()):
        if _value_contains_string(event.get("payload_schema", {}), schema_id):
            files.extend(_event_evidence_files(contract, event_id))
    for application_action_id, operation in sorted(contract.get("application_actions", {}).items()):
        if _value_contains_string(operation, schema_id):
            files.extend(_application_action_evidence_files(contract, application_action_id))
    for workflow_id, workflow in sorted(contract.get("workflows", {}).items()):
        if _value_contains_string(workflow, schema_id):
            files.extend(_workflow_evidence_files(contract, workflow_id))
    for entry_id, entry in sorted(contract.get("entry_points", {}).items()):
        if _value_contains_string(entry, schema_id):
            files.extend(_entry_point_evidence_files(contract, entry_id))
    return files


def _model_evidence_files(contract: dict[str, Any], entity_type_id: str) -> list[str]:
    if entity_type_id not in contract.get("entity_types", {}):
        return []
    files: list[str] = []
    for application_action_id, operation in sorted(contract.get("application_actions", {}).items()):
        if _value_contains_string(operation, entity_type_id):
            files.extend(_application_action_evidence_files(contract, application_action_id))
    for event_id, event in sorted(contract.get("domain_events", {}).items()):
        if _value_contains_string(event, entity_type_id):
            files.extend(_event_evidence_files(contract, event_id))
    for entry_id, entry in sorted(contract.get("entry_points", {}).items()):
        if _value_contains_string(entry, entity_type_id):
            files.extend(_entry_point_evidence_files(contract, entry_id))
    for state_machine_id, state_machine in sorted(contract.get("state_machines", {}).items()):
        if state_machine.get("entity_type") == entity_type_id or _value_contains_string(state_machine.get("view_states", {}), entity_type_id):
            files.extend(_state_machine_evidence_files(contract, state_machine_id))
    return files


def _text_resource_evidence_files(contract: dict[str, Any], text_id: str) -> list[str]:
    if text_id not in contract.get("text_resources", {}):
        return []
    files = _scope_input_evidence_files(contract, text_id, "text")
    for entry_id, entry in sorted(contract.get("entry_points", {}).items()):
        if _value_contains_string(entry, text_id):
            files.extend(_entry_point_evidence_files(contract, entry_id))
    for state_machine_id, state_machine in sorted(contract.get("state_machines", {}).items()):
        if _value_contains_string(state_machine, text_id):
            files.extend(_state_machine_evidence_files(contract, state_machine_id))
    return files


def _asset_evidence_files(contract: dict[str, Any], asset_id: str) -> list[str]:
    if asset_id not in contract.get("assets", {}):
        return []
    files = _scope_input_evidence_files(contract, asset_id, "asset")
    for state_machine_id, state_machine in sorted(contract.get("state_machines", {}).items()):
        if _value_contains_string(state_machine, asset_id):
            files.extend(_state_machine_evidence_files(contract, state_machine_id))
    return files


def _fixture_evidence_files(contract: dict[str, Any], fixture_id: str) -> list[str]:
    if fixture_id not in contract.get("fixtures", {}):
        return []
    return _scope_input_evidence_files(contract, fixture_id, "fixture")


def _precondition_evidence_files(contract: dict[str, Any], precondition_id: str) -> list[str]:
    if precondition_id not in contract.get("preconditions", {}):
        return []
    return _scope_input_evidence_files(contract, precondition_id, "precondition")


def _behavior_scenario_evidence_files(contract: dict[str, Any], behavior_scenario_id: str) -> list[str]:
    behavior_scenario = contract.get("behavior_scenarios", {}).get(behavior_scenario_id)
    if not behavior_scenario:
        return []
    files: list[str] = []
    when = behavior_scenario.get("when", {})
    for action in ("open_entry_point", "call_entry_point"):
        if action in when:
            files.extend(_entry_point_evidence_files(contract, when[action]["ref"]))
    if "invoke_application_action" in when:
        files.extend(_application_action_evidence_files(contract, when["invoke_application_action"]["ref"]))
    if "emit_domain_event" in when:
        files.extend(_event_evidence_files(contract, when["emit_domain_event"]["ref"]))
    if "run_workflow" in when:
        files.extend(_workflow_evidence_files(contract, when["run_workflow"]["ref"]))
    for case_id, case in sorted(render_examples(contract).items()):
        if case_id == behavior_scenario_id or case.get("behavior_scenario") == behavior_scenario_id:
            files.extend(_render_example_capture_files(contract, case_id, case))
    return files


def _content_example_evidence_files(contract: dict[str, Any], content_example_id: str) -> list[str]:
    content_example = contract.get("content_examples", {}).get(content_example_id)
    if not content_example:
        return []
    files: list[str] = []
    ref = content_example.get("ref")
    if ref in contract.get("text_resources", {}):
        files.extend(_text_resource_evidence_files(contract, ref))
    if ref in contract.get("assets", {}):
        files.extend(_asset_evidence_files(contract, ref))
    return files


def _scope_input_evidence_files(contract: dict[str, Any], ref: str, kind: str) -> list[str]:
    files: list[str] = []
    projection = state_machines_projection(contract)
    for surface in _audit_projection_surfaces(contract, projection):
        text_refs, asset_refs, fixture_ids, precondition_ids, _ = _surface_scope_inputs(contract, surface)
        if kind == "text" and ref in text_refs:
            files.extend(_projection_surface_render_capture_files(contract, surface))
        elif kind == "asset" and ref in asset_refs:
            files.extend(_projection_surface_render_capture_files(contract, surface))
        elif kind == "fixture" and ref in fixture_ids:
            files.extend(_projection_surface_render_capture_files(contract, surface))
        elif kind == "precondition" and ref in precondition_ids:
            files.extend(_projection_surface_render_capture_files(contract, surface))
    for case_id, case in sorted(render_examples(contract).items()):
        text_refs, asset_refs, fixture_ids, precondition_ids, _ = _render_example_scope_inputs(contract, case)
        if kind == "text" and ref in text_refs:
            files.extend(_render_example_capture_files(contract, case_id, case))
        elif kind == "asset" and ref in asset_refs:
            files.extend(_render_example_capture_files(contract, case_id, case))
        elif kind == "fixture" and ref in fixture_ids:
            files.extend(_render_example_capture_files(contract, case_id, case))
        elif kind == "precondition" and ref in precondition_ids:
            files.extend(_render_example_capture_files(contract, case_id, case))
    return files


def _projection_surface_render_capture_files(contract: dict[str, Any], surface: dict[str, Any]) -> list[str]:
    files: list[str] = []
    for render_surface in _projection_render_surfaces(surface):
        for profile_id, breakpoint, _ in _profile_viewports(contract, render_surface):
            extension = "png" if render_surface == "html" else "svg"
            files.append(_projection_surface_file(surface, profile_id, breakpoint, extension))
    return files


def _render_example_capture_files(contract: dict[str, Any], case_id: str, case: dict[str, Any]) -> list[str]:
    files: list[str] = []
    for render_surface in _render_example_surfaces(contract, case):
        for profile_id, breakpoint, _ in _profile_viewports(contract, render_surface):
            extension = "png" if render_surface == "html" else "svg"
            files.append(_render_example_file(contract, case_id, case, profile_id, breakpoint, extension))
    return files


def _all_render_evidence_files(contract: dict[str, Any]) -> list[str]:
    files: list[str] = []
    projection = state_machines_projection(contract)
    for surface in _audit_projection_surfaces(contract, projection):
        files.extend(_view_state_render_evidence_files(contract, surface["owner"], surface["view_state"]))
    for case_id, case in sorted(render_examples(contract).items()):
        files.extend(_render_example_capture_files(contract, case_id, case))
    return _filter_evidence_files(contract, files)


def _view_state_render_evidence_files(contract: dict[str, Any], state_machine_id: str, state_name: str) -> list[str]:
    files: list[str] = []
    projection = state_machines_projection(contract)
    for surface in _audit_projection_surfaces(contract, projection):
        if surface["owner"] != state_machine_id or surface["view_state"] != state_name:
            continue
        files.extend(_projection_surface_render_capture_files(contract, surface))
    for case_id, case in sorted(render_examples(contract).items()):
        if case.get("state_machine") != state_machine_id or case.get("view_state") != state_name:
            continue
        files.extend(_render_example_capture_files(contract, case_id, case))
    return _filter_evidence_files(contract, files)


def _value_contains_string(value: Any, needle: str) -> bool:
    if isinstance(value, str):
        return value == needle
    if isinstance(value, dict):
        return any(key == needle or _value_contains_string(item, needle) for key, item in value.items())
    if isinstance(value, list):
        return any(_value_contains_string(item, needle) for item in value)
    return False


def generate_audit(
    root: Path,
    contract: dict[str, Any],
    tools_root: Path | None = None,
    previous_audit_root: Path | None = None,
) -> None:
    root = root.resolve()
    audit_root = root / GENERATED_SPEC_DIR / "audit_evidence"
    backup_parent: Path | None = None
    restore_audit_root: Path | None = None
    if audit_root.exists():
        backup_container = root / GENERATED_SPEC_DIR.parent
        backup_container.mkdir(parents=True, exist_ok=True)
        backup_parent = Path(tempfile.mkdtemp(prefix=".pyspec-audit-backup-", dir=str(backup_container)))
        restore_audit_root = backup_parent / "audit_evidence"
        shutil.move(str(audit_root), str(restore_audit_root))
        previous_audit_root = restore_audit_root
    audit_root.mkdir(parents=True, exist_ok=True)

    try:
        projection = state_machines_projection(contract)
        _write_audit_inputs(root, contract, projection)
        _write_audit_coverage_index(root, contract)

        if _audit_visual_expected_files(contract):
            _render_visual_audit_subprocess(root, tools_root or root, previous_audit_root)
    except BaseException:
        if audit_root.exists():
            shutil.rmtree(audit_root)
        if restore_audit_root and restore_audit_root.exists():
            shutil.move(str(restore_audit_root), str(audit_root))
        raise
    finally:
        if backup_parent and backup_parent.exists():
            shutil.rmtree(backup_parent, ignore_errors=True)


def _render_visual_audit_subprocess(root: Path, tools_root: Path, previous_audit_root: Path | None = None) -> None:
    env = os.environ.copy()
    env["PM_CONTRACT_AUDIT_WORKER"] = "1"
    src_root = str(ROOT.parent)
    env["PYTHONPATH"] = src_root if not env.get("PYTHONPATH") else src_root + os.pathsep + env["PYTHONPATH"]
    cmd = [sys.executable, "-m", "pyspec_contract.audit", str(root), str(tools_root)]
    if previous_audit_root:
        cmd.append(str(previous_audit_root))
    result = subprocess.run(
        cmd,
        cwd=str(root),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=900,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        suffix = f":\n{detail}" if detail else ""
        raise ContractError(f"Visual audit renderer failed with exit code {result.returncode}{suffix}")


def _render_visual_audit(
    root: Path,
    contract: dict[str, Any],
    _tools_root: Path,
    projection: dict[str, Any] | None = None,
    previous_audit_root: Path | None = None,
) -> None:
    projection = projection or state_machines_projection(contract)
    for state_machine_id, state_machine in sorted(contract.get("state_machines", {}).items()):
        path = root / state_machine_graph_file(state_machine_id)
        _write_graphviz_svg(path, state_machine_dot(state_machine_id, state_machine, contract), _previous_audit_path(root, previous_audit_root, path))
    for state_machine_id, state_machine in sorted(contract.get("state_machines", {}).items()):
        for state_name, state in sorted(state_machine.get("view_states", {}).items()):
            if not state.get("child_state_machines"):
                continue
            path = root / composition_file(state_machine_id, state_name)
            _write_graphviz_svg(
                path,
                composition_dot(f"{state_machine_id}.{state_name}", {"context": state_machine.get("context", {}), **state}, contract),
                _previous_audit_path(root, previous_audit_root, path),
            )
    for entry_id, entry in sorted(contract.get("entry_points", {}).items()):
        adapter_kind, _ = entry_point_adapter_pair(entry)
        path = root / entrypoint_flow_file(entry_id, adapter_kind)
        _write_graphviz_svg(path, entrypoint_flow_dot(entry_id, entry, contract), _previous_audit_path(root, previous_audit_root, path))
    for workflow_id, workflow in sorted(contract.get("workflows", {}).items()):
        path = root / workflow_flow_file(workflow_id)
        _write_graphviz_svg(path, workflow_flow_dot(workflow_id, workflow, contract), _previous_audit_path(root, previous_audit_root, path))
    for application_action_id, operation in sorted(contract.get("application_actions", {}).items()):
        path = root / application_action_flow_file(application_action_id)
        _write_graphviz_svg(path, application_action_flow_dot(application_action_id, operation, contract), _previous_audit_path(root, previous_audit_root, path))

    has_html_audit = bool(_profile_viewports(contract, "html")) and (
        any("html" in _projection_render_surfaces(state_machine) for state_machine in _audit_projection_surfaces(contract, projection))
        or any("html" in _render_example_surfaces(contract, case) for case in render_examples(contract).values())
    )
    if has_html_audit:
        _render_html_audit(root, contract, projection, previous_audit_root)

    audit_state_machines = _audit_projection_surfaces(contract, projection)
    has_textual_audit = bool(_profile_viewports(contract, "textual")) and (
        any("textual" in _projection_render_surfaces(state_machine) for state_machine in audit_state_machines)
        or any("textual" in _render_example_surfaces(contract, case) for case in render_examples(contract).values())
    )
    if has_textual_audit:
        try:
            import textual  # noqa: F401
        except Exception as exc:  # pragma: no cover - dependency absence is environment-specific.
            raise ContractError("Missing Textual dependency; install requirements.txt") from exc
        textual_jobs: list[tuple[Path, list[tuple[str, str]], dict[str, int], Path | None, Path | None]] = []
        for state_machine in sorted(audit_state_machines, key=lambda p: p["id"]):
            if "textual" not in _projection_render_surfaces(state_machine):
                continue
            lines = state_machine_textual_lines(root, contract, state_machine, None)
            for profile_id, name, viewport in _profile_viewports(contract, "textual"):
                py_path = root / _projection_surface_file(state_machine, profile_id, name, "py")
                svg_path = root / _projection_surface_file(state_machine, profile_id, name, "svg")
                _write_textual_source(py_path, lines)
                textual_jobs.append((
                    svg_path,
                    lines,
                    viewport,
                    _previous_audit_path(root, previous_audit_root, py_path),
                    _previous_audit_path(root, previous_audit_root, svg_path),
                ))
        for case_id, case in sorted(render_examples(contract).items()):
            if "textual" not in _render_example_surfaces(contract, case):
                continue
            lines = textual_audit_lines(root, contract, case_id, case)
            for profile_id, name, viewport in _profile_viewports(contract, "textual"):
                py_path = root / _render_example_file(contract, case_id, case, profile_id, name, "py")
                svg_path = root / _render_example_file(contract, case_id, case, profile_id, name, "svg")
                previous_py_path = _previous_audit_path(root, previous_audit_root, py_path)
                previous_svg_path = _previous_audit_path(root, previous_audit_root, svg_path)
                _write_textual_source(py_path, lines)
                textual_jobs.append((
                    svg_path,
                    lines,
                    viewport,
                    previous_py_path,
                    previous_svg_path,
                ))
        asyncio.run(_render_textual_batch(textual_jobs))


def _render_html_audit(root: Path, contract: dict[str, Any], projection: dict[str, Any], previous_audit_root: Path | None = None) -> None:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover - dependency absence is environment-specific.
        raise ContractError("Missing Playwright dependency; install requirements.txt and run python -m playwright install chromium, or provide system Chromium") from exc

    with sync_playwright() as pw:
        try:
            browser = _launch_chromium(pw)
        except Exception as exc:  # pragma: no cover - browser launch depends on the host image.
            raise ContractError(f"HTML audit renderer could not launch Chromium: {exc}") from exc
        try:
            page = browser.new_page()
            try:
                for state_machine in sorted(_audit_projection_surfaces(contract, projection), key=lambda p: p["id"]):
                    if "html" not in _projection_render_surfaces(state_machine):
                        continue
                    html_doc = audit_html_document(contract, render_state_machine_audit_html(root, contract, state_machine, None), state_machine_surface_ids={state_machine["id"]})
                    for profile_id, name, viewport in _profile_viewports(contract, "html"):
                        html_path = root / _projection_surface_file(state_machine, profile_id, name, "html")
                        png_path = root / _projection_surface_file(state_machine, profile_id, name, "png")
                        _write_html_and_png_page(
                            page,
                            html_doc,
                            html_path,
                            png_path,
                            viewport,
                            _previous_audit_path(root, previous_audit_root, html_path),
                            _previous_audit_path(root, previous_audit_root, png_path),
                        )
                for case_id, case in sorted(render_examples(contract).items()):
                    if "html" in _render_example_surfaces(contract, case):
                        html_doc = audit_html_document(
                            contract,
                            render_example_html(root, contract, case_id, case),
                            state_machine_surface_ids={state_machine["id"] for state_machine in render_example_state_machines(contract, case)},
                            composition_ids=_render_example_composition_ids(contract, case),
                        )
                        for profile_id, name, viewport in _profile_viewports(contract, "html"):
                            html_path = root / _render_example_file(contract, case_id, case, profile_id, name, "html")
                            png_path = root / _render_example_file(contract, case_id, case, profile_id, name, "png")
                            _write_html_and_png_page(
                                page,
                                html_doc,
                                html_path,
                                png_path,
                                viewport,
                                _previous_audit_path(root, previous_audit_root, html_path),
                                _previous_audit_path(root, previous_audit_root, png_path),
                            )
            finally:
                page.close()
        finally:
            browser.close()


def _write_html_source(html_path: Path, html_doc: str, previous_html_path: Path | None = None) -> None:
    html_path.parent.mkdir(parents=True, exist_ok=True)
    if previous_html_path and _text_file_equals(previous_html_path, html_doc):
        shutil.copy2(previous_html_path, html_path)
        return
    html_path.write_text(html_doc, encoding="utf-8")


def _write_png_page(
    page: Any,
    html_doc: str,
    png_path: Path,
    viewport: dict[str, int],
    previous_png_path: Path | None = None,
) -> None:
    png_path.parent.mkdir(parents=True, exist_ok=True)
    _ = previous_png_path
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            page.set_viewport_size({"width": viewport["width"], "height": viewport["height"]})
            page.set_content(html_doc, wait_until="load")
            page.screenshot(path=str(png_path), full_page=False, type="png", timeout=10000)
            last_error = None
            break
        except Exception as exc:  # pragma: no cover - renderer failure details come from Playwright.
            last_error = exc
            if attempt < 2:
                page.wait_for_timeout(100)
    if last_error is not None:
        raise ContractError(f"HTML renderer failed for {png_path}: {last_error}") from last_error
    if png_path.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
        raise ContractError(f"HTML renderer did not produce a PNG: {png_path}")


def _write_html_and_png_page(
    page: Any,
    html_doc: str,
    html_path: Path,
    png_path: Path,
    viewport: dict[str, int],
    previous_html_path: Path | None = None,
    previous_png_path: Path | None = None,
) -> None:
    html_path.parent.mkdir(parents=True, exist_ok=True)
    png_path.parent.mkdir(parents=True, exist_ok=True)
    if (
        previous_html_path
        and previous_png_path
        and _text_file_equals(previous_html_path, html_doc)
        and _png_matches_viewport(previous_png_path, viewport)
    ):
        shutil.copy2(previous_html_path, html_path)
        shutil.copy2(previous_png_path, png_path)
        return
    _write_html_source(html_path, html_doc)
    _write_png_page(page, html_doc, png_path, viewport)


def _chromium_executable() -> str | None:
    return os.environ.get("CONTRACT_AUDIT_CHROMIUM") or shutil.which("chromium") or shutil.which("chromium-browser") or shutil.which("google-chrome") or shutil.which("google-chrome-stable")


def _launch_chromium(pw: Any) -> Any:
    executable = _chromium_executable()
    args = ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
    if executable:
        return pw.chromium.launch(executable_path=executable, args=args)
    return pw.chromium.launch(args=args)


def _graphviz_dot_executable() -> str:
    executable = os.environ.get("CONTRACT_AUDIT_GRAPHVIZ_DOT") or shutil.which("dot")
    if not executable:
        raise ContractError("Missing Graphviz dependency; install graphviz so the dot executable is available")
    return executable


def _write_graphviz_svg(path: Path, dot_source: str, previous_path: Path | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    input_hash = _input_hash(dot_source)
    if previous_path and _svg_has_input_hash(previous_path, input_hash):
        shutil.copy2(previous_path, path)
        return
    path.write_text(_svg_with_input_hash(_render_graphviz_svg(dot_source, path.stem), input_hash), encoding="utf-8")


def _render_graphviz_svg(dot_source: str, graph_id: str) -> str:
    try:
        result = subprocess.run(
            [_graphviz_dot_executable(), "-Tsvg"],
            input=dot_source,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ContractError(f"Graphviz renderer timed out for {graph_id}") from exc
    if result.returncode != 0:
        detail = result.stderr.strip() or f"exit code {result.returncode}"
        raise ContractError(f"Graphviz renderer failed for {graph_id}: {detail}")
    svg = _strip_svg_preamble(result.stdout)
    if not svg.lstrip().startswith("<svg") or "</svg>" not in svg:
        raise ContractError("Graphviz renderer did not produce SVG")
    return svg


def _strip_svg_preamble(svg: str) -> str:
    start = svg.find("<svg")
    end = svg.rfind("</svg>")
    if start == -1 or end == -1:
        return svg
    return svg[start : end + len("</svg>")] + "\n"


def _input_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _svg_has_input_hash(path: Path, input_hash: str, prefix: str = _GRAPHVIZ_INPUT_HASH_PREFIX) -> bool:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    marker = f"<!-- {prefix} {input_hash} -->"
    return text.lstrip().startswith("<svg") and marker in text and "</svg>" in text


def _svg_with_input_hash(svg: str, input_hash: str, prefix: str = _GRAPHVIZ_INPUT_HASH_PREFIX) -> str:
    marker = f"\n<!-- {prefix} {input_hash} -->"
    insert_at = svg.find(">")
    if insert_at == -1:
        return svg
    return svg[: insert_at + 1] + marker + svg[insert_at + 1:]


def _previous_audit_path(root: Path, previous_audit_root: Path | None, path: Path) -> Path | None:
    if previous_audit_root is None:
        return None
    try:
        relative = path.relative_to(root / GENERATED_SPEC_DIR / "audit_evidence")
    except ValueError:
        return None
    previous = previous_audit_root / relative
    return previous if previous.exists() else None


def _text_file_equals(path: Path, text: str) -> bool:
    try:
        return path.read_text(encoding="utf-8") == text
    except OSError:
        return False


def _png_matches_viewport(path: Path, viewport: dict[str, int]) -> bool:
    try:
        from PIL import Image

        if path.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
            return False
        with Image.open(path) as image:
            return image.size == (viewport["width"], viewport["height"])
    except Exception:
        return False


def _write_textual_source(path: Path, lines: list[tuple[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textual_source(lines), encoding="utf-8")


def textual_source(lines: list[tuple[str, str]]) -> str:
    return f'''from __future__ import annotations

from textual.app import App, ComposeResult
from textual.containers import Container
from textual.widgets import Button, Static

LINES = {lines!r}


class AuditApp(App[None]):
    CSS = """
    Screen {{ layout: vertical; }}
    #root {{ padding: 1; }}
    Static {{ margin: 0 0 1 0; }}
    Button {{ margin: 0 0 1 0; width: auto; }}
    """

    def compose(self) -> ComposeResult:
        with Container(id="root"):
            for index, (kind, value) in enumerate(LINES):
                if kind == "button":
                    yield Button(value, id=f"button_{{index}}")
                else:
                    yield Static(value, id=f"line_{{index}}")


if __name__ == "__main__":
    AuditApp().run()
'''


async def _render_textual_batch(
    jobs: list[tuple[Path, list[tuple[str, str]], dict[str, int], Path | None, Path | None]],
) -> None:
    for path, lines, viewport, previous_source_path, previous_svg_path in jobs:
        await _render_textual_svg(path, lines, viewport, previous_source_path, previous_svg_path)


async def _render_textual_svg(
    path: Path,
    lines: list[tuple[str, str]],
    viewport: dict[str, int],
    previous_source_path: Path | None = None,
    previous_svg_path: Path | None = None,
) -> None:
    from textual.app import App, ComposeResult
    from textual.containers import Container
    from textual.widgets import Button, Static

    source = textual_source(lines)
    input_hash = _input_hash(json.dumps({"source": source, "viewport": viewport}, sort_keys=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    if (
        previous_source_path
        and previous_svg_path
        and _text_file_equals(previous_source_path, source)
        and _svg_has_input_hash(previous_svg_path, input_hash, _TEXTUAL_INPUT_HASH_PREFIX)
    ):
        shutil.copy2(previous_svg_path, path)
        return

    class AuditApp(App[None]):
        CSS = """
        Screen { layout: vertical; }
        #root { padding: 1; }
        Static { margin: 0 0 1 0; }
        Button { margin: 0 0 1 0; width: auto; }
        """

        def compose(self) -> ComposeResult:
            with Container(id="root"):
                for index, (kind, value) in enumerate(lines):
                    if kind == "button":
                        yield Button(value, id=f"button_{index}")
                    else:
                        yield Static(value, id=f"line_{index}")

    app = AuditApp()
    async with app.run_test(size=(viewport["columns"], viewport["rows"])) as pilot:
        await pilot.pause()
        svg = app.export_screenshot()
    if not isinstance(svg, str) or "<svg" not in svg:
        raise ContractError("Textual renderer did not produce SVG")
    path.write_text(_svg_with_input_hash(svg, input_hash, _TEXTUAL_INPUT_HASH_PREFIX), encoding="utf-8")


def state_machine_dot(state_machine_id: str, state_machine: dict[str, Any], contract: dict[str, Any]) -> str:
    lines = _dot_graph_preamble("state_machine_" + safe_id(state_machine_id))
    for state_name in sorted(state_machine["view_states"]):
        state = state_machine["view_states"][state_name]
        sections = _state_machine_view_state_sections(state_machine, state_name, state, contract)
        lines.append(
            _dot_html_node(
                _dot_node_id("view_state", state_name),
                _dot_card(
                    state_name,
                    "initial view state" if state_name == state_machine["initial_view_state"] else "view state",
                    sections,
                    style=_DOT_STYLE_ENTRY if state_name == state_machine["initial_view_state"] else _DOT_STYLE_NEUTRAL,
                ),
            )
        )
    for index, transition in enumerate(state_machine.get("transitions", [])):
        source = _dot_node_id("view_state", transition["from"])
        target = _dot_node_id("view_state", transition["to"])
        transition_label = _signal_label(transition["on"])
        transition_id = _dot_node_id("transition", f"{index}_{transition['from']}_{transition['to']}_{transition_label}")
        lines.append(
            _dot_html_node(
                transition_id,
                _dot_card(
                    transition_label,
                    "transition signal",
                    _format_transition_sections(state_machine, transition, contract),
                    rationale=transition.get("rationale", ""),
                    style=_DOT_STYLE_CAPABILITY,
                ),
            )
        )
        lines.append(_dot_edge(source, transition_id))
        lines.append(_dot_edge(transition_id, target))
    lines.append("}")
    return "\n".join(lines) + "\n"


def composition_dot(state_machine_id: str, state_machine: dict[str, Any], contract: dict[str, Any]) -> str:
    sync_state_machine_order: list[str] = []
    for rule in state_machine.get("signal_sync_rules", []):
        sync_state_machine_order.append(rule["when"]["instance"])
        sync_state_machine_order.extend(effect["send"]["instance"] for effect in rule.get("effects", []) if "send" in effect)
    sync_state_machine_index = {state_machine_id: index for index, state_machine_id in enumerate(dict.fromkeys(sync_state_machine_order))}
    mounts = sorted(
        state_machine.get("child_state_machines", []),
        key=lambda mount: (sync_state_machine_index.get(mount["id"], len(sync_state_machine_index)), mount["id"]),
    )
    mount_by_id = {mount["id"]: mount for mount in mounts}
    mount_node_by_id = {mount["id"]: _dot_node_id("child_state_machine", mount["id"]) for mount in mounts}
    mount_node_ids = [mount_node_by_id[mount["id"]] for mount in mounts]
    has_sync = bool(state_machine.get("signal_sync_rules"))
    lines = _dot_graph_preamble("composition_" + safe_id(state_machine_id))
    for mount in mounts:
        lines.append(_dot_html_node(mount_node_by_id[mount["id"]], _dot_mount_card(mount)))
    if mount_node_ids and not has_sync:
        lines.extend(_dot_invisible_order(mount_node_ids, indent="  "))
    if not has_sync:
        lines.append(_dot_html_node("local_signal_sync_none", _dot_card("No local signal sync", "local signal sync", [], style=_DOT_STYLE_NEUTRAL)))
    for rule in state_machine.get("signal_sync_rules", []):
        signal_id = rule["when"]["local_signal"]
        emit_id = _dot_node_id("local_signal_emit", f"{rule['id']}_{rule['when']['instance']}_{signal_id}")
        sync_id = _dot_node_id("local_signal_sync", rule["id"])
        send_effects = [(index, effect) for index, effect in enumerate(rule.get("effects", [])) if "send" in effect]
        effect_ids = [_dot_node_id("local_signal_effect", f"{rule['id']}_{index}") for index, _ in send_effects]
        lines.append(
            _dot_html_node(
                emit_id,
                _dot_card(
                    _local_signal_label(signal_id),
                    "emitted local signal",
                    [
                        ("source", _emitting_transition_refs(rule["when"]["instance"], signal_id, mount_by_id, contract)),
                        ("payload", _emitted_local_signal_data_lines(rule["when"]["instance"], signal_id, mount_by_id, contract)),
                    ],
                    style=_DOT_STYLE_EVENT,
                ),
            )
        )
        lines.append(
            _dot_html_node(
                sync_id,
                _dot_card(
                    rule["id"],
                    "local signal sync",
                    [("set", _sync_set_lines(rule, state_machine))],
                    style=_DOT_STYLE_WORKFLOW,
                ),
            )
        )
        for index, effect in send_effects:
            effect_id = _dot_node_id("local_signal_effect", f"{rule['id']}_{index}")
            lines.append(_dot_html_node(effect_id, _dot_sync_effect_card(effect, mount_by_id, contract)))
        if effect_ids:
            lines.append("  { rank=same; " + " ".join(_dot_quote(effect_id) for effect_id in effect_ids) + " }")
            lines.extend(_dot_invisible_order(effect_ids, indent="  "))
    for rule in state_machine.get("signal_sync_rules", []):
        emit_id = _dot_node_id("local_signal_emit", f"{rule['id']}_{rule['when']['instance']}_{rule['when']['local_signal']}")
        sync_id = _dot_node_id("local_signal_sync", rule["id"])
        source = mount_node_by_id.get(rule["when"]["instance"])
        if source:
            lines.append(_dot_edge(source, emit_id, {"color": _DOT_COLOR_EVENT_BORDER, "penwidth": "1.4"}))
        lines.append(_dot_edge(emit_id, sync_id, {"color": _DOT_COLOR_EVENT_BORDER, "penwidth": "1.2"}))
        for index, effect in enumerate(rule.get("effects", [])):
            if "send" not in effect:
                continue
            effect_id = _dot_node_id("local_signal_effect", f"{rule['id']}_{index}")
            lines.append(_dot_edge(sync_id, effect_id, {"color": _DOT_COLOR_MESSAGE_BORDER, "penwidth": "1.3"}))
            target = mount_node_by_id.get(effect["send"]["instance"])
            if not target:
                continue
            lines.append(_dot_edge(effect_id, target, {"color": _DOT_COLOR_MESSAGE_BORDER, "penwidth": "1.4"}))
    lines.append("}")
    return "\n".join(lines) + "\n"


def entrypoint_flow_dot(entry_id: str, entry: dict[str, Any], contract: dict[str, Any]) -> str:
    adapter_kind, _ = entry_point_adapter_pair(entry)
    target_kind, target_value = entry_target_pair(entry)
    target_renderer = entry_state_machine_renderer(entry) if target_kind == "state_machine" else None
    entry_node = _dot_node_id("entrypoint", entry_id)
    target_node = _dot_node_id("entrypoint_target", target_value)
    response_nodes = _entry_point_response_nodes(entry_id, entry, contract)
    target_tail = [] if target_kind == "state_machine" else _entry_target_tail_nodes(target_kind, target_value, contract)
    entry_sections = _entry_binding_sections(entry, contract)
    entry_sections.extend(_entry_input_sections(entry, contract))
    _, output_title = _entry_io_card_titles(adapter_kind)
    lines = _dot_graph_preamble("entrypoint_" + safe_id(entry_id))
    lines.extend(
        [
            _dot_html_node(
                entry_node,
                _dot_card(
                    _entry_surface_title(entry),
                    f"{adapter_kind} entry point",
                    entry_sections,
                    rationale=entry.get("rationale", ""),
                    style=_DOT_STYLE_ENTRY,
                ),
            ),
        ]
    )
    lines.append(_dot_html_node(target_node, _entry_target_card(target_kind, target_value, contract, renderer=target_renderer)))
    if response_nodes:
        lines.extend(
            _dot_html_node(
                node_id,
                _dot_card(outcome_id if subtitle else output_title, subtitle or outcome_id, sections, style=_exit_card_style(outcome_kind)),
            )
            for node_id, outcome_id, subtitle, outcome_kind, sections in response_nodes
        )
    lines.extend(_dot_html_node(node_id, label) for node_id, label in target_tail)
    lines.append(_dot_edge(entry_node, target_node))
    for node_id, _ in target_tail:
        lines.append(_dot_edge(target_node, node_id))
    if response_nodes:
        for node_id, _, _, _, _ in response_nodes:
            lines.append(_dot_edge(target_node, node_id))
        if len(response_nodes) > 1:
            lines.append("  { rank=same; " + " ".join(_dot_quote(node_id) for node_id, _, _, _, _ in response_nodes) + " }")
            lines.extend(_dot_invisible_order([node_id for node_id, _, _, _, _ in response_nodes], indent="  "))
    if len(target_tail) > 1:
        lines.append("  { rank=same; " + " ".join(_dot_quote(node_id) for node_id, _ in target_tail) + " }")
        lines.extend(_dot_invisible_order([node_id for node_id, _ in target_tail], indent="  "))
    lines.append("}")
    return "\n".join(lines) + "\n"


def _entry_io_card_titles(adapter_kind: str) -> tuple[str, str]:
    if adapter_kind in {"http_api", "html_route", "webhook"}:
        return "request", "response"
    if adapter_kind == "cli":
        return "command input", "command output"
    if adapter_kind == "worker":
        return "domain event payload", "integration message disposition"
    if adapter_kind == "scheduled":
        return "schedule trigger", "trigger disposition"
    return "input", "output"


def workflow_flow_dot(workflow_id: str, workflow: dict[str, Any], contract: dict[str, Any]) -> str:
    trigger_kind, trigger_value = _target_pair(workflow["trigger"])
    trigger_node = _dot_node_id("workflow_trigger", f"{trigger_kind}_{trigger_value}")
    workflow_node = _dot_node_id("workflow", workflow_id)
    step_nodes = [(_dot_node_id("workflow_step", f"{workflow_id}_{step['id']}"), step) for step in workflow["steps"]]
    outcome_nodes = [
        (_dot_node_id("workflow_outcome", f"{workflow_id}_{outcome_id}"), outcome_id, outcome)
        for outcome_id, outcome in sorted(workflow["outcomes"].items())
    ]
    step_node_by_id = {step["id"]: node_id for node_id, step in step_nodes}
    outcome_node_by_id = {outcome_id: node_id for node_id, outcome_id, _ in outcome_nodes}
    lines = _dot_graph_preamble("workflow_" + safe_id(workflow_id))
    lines.extend(
        [
            _dot_html_node(trigger_node, _workflow_trigger_card(trigger_kind, trigger_value, contract)),
            _dot_html_node(
                workflow_node,
                _dot_card(
                    workflow_id,
                    "workflow",
                    [
                        ("ref", [workflow.get("ref", "")]),
                        ("steps", [f"{step['id']} {_DOT_ARROW_FORWARD} {step['application_action']}" for step in workflow["steps"]]),
                        ("outcomes", [_DotTypedField(outcome_id, outcome["result"], outcome["kind"]) for outcome_id, outcome in sorted(workflow["outcomes"].items())]),
                    ],
                    rationale=workflow.get("rationale", ""),
                    style=_DOT_STYLE_WORKFLOW,
                ),
            ),
        ]
    )
    for node_id, step in step_nodes:
        lines.append(_dot_html_node(node_id, _workflow_step_card(step, contract)))
    for node_id, outcome_id, outcome in outcome_nodes:
        lines.append(_dot_html_node(node_id, _workflow_outcome_card(outcome_id, outcome)))
    lines.append(_dot_edge(trigger_node, workflow_node))
    if step_nodes:
        lines.append(_dot_edge(workflow_node, step_nodes[0][0]))
    for node_id, step in step_nodes:
        for outcome_id, transition in sorted(step["outcome_transitions"].items()):
            attrs = {"label": outcome_id}
            transition_key, value = _workflow_transition_action(transition)
            if transition_key == "next_step":
                lines.append(_dot_edge(node_id, step_node_by_id[value], attrs))
            else:
                outcome = _workflow_transition_outcome(transition_key, value)
                assert outcome is not None
                lines.append(_dot_edge(node_id, outcome_node_by_id[outcome], attrs))
    if outcome_nodes:
        lines.append("  { rank=same; " + " ".join(_dot_quote(node_id) for node_id, _, _ in outcome_nodes) + " }")
        lines.extend(_dot_invisible_order([node_id for node_id, _, _ in outcome_nodes], indent="  "))
    lines.append("}")
    return "\n".join(lines) + "\n"


def application_action_flow_dot(application_action_id: str, application_action: dict[str, Any], contract: dict[str, Any]) -> str:
    input_node = _dot_node_id("application_action_input", application_action_id)
    authorization = application_action.get("authorization") or {}
    policy_id = authorization.get("policy")
    policy_node = _dot_node_id("application_action_policy", policy_id) if policy_id else None
    authorization_failure_labels = {
        authorization.get("authentication_required_as"): "authentication_required_as",
        authorization.get("access_denied_as"): "access_denied_as",
    }
    resource_nodes = _application_action_resource_nodes(application_action_id, application_action, contract)
    outcome_nodes = [
        (_dot_node_id("action_outcome", f"{application_action_id}_{outcome_id}"), outcome_id, outcome)
        for outcome_id, outcome in sorted(application_action.get("outcomes", {}).items())
    ]
    event_nodes: dict[str, str] = {}
    for _, outcome in sorted(application_action.get("outcomes", {}).items()):
        for emit in outcome.get("emits", []):
            event_id = emit["domain_event"] if isinstance(emit, dict) else emit
            event_nodes.setdefault(event_id, _dot_node_id("application_action_event", f"{application_action_id}_{event_id}"))

    lines = _dot_graph_preamble("application_action_" + safe_id(application_action_id))
    if application_action.get("input"):
        lines.append(_dot_html_node(input_node, _dot_card("input", "action input", [("fields", _typed_fields(application_action["input"]))], style=_DOT_STYLE_EXTERNAL)))
    if policy_id:
        lines.append(_dot_html_node(policy_node or "", _policy_reference_card(policy_id, contract, subtitle="authorization gate", include_resources=False)))
    for node_id, _, target_id, target_kind, sections in resource_nodes:
        style = _DOT_STYLE_ENTITY_TYPE if target_kind == "entity_type" else _DOT_STYLE_SCHEMA
        lines.append(_dot_html_node(node_id, _dot_card(target_id, f"{target_kind} resource", sections, style=style)))
    for node_id, outcome_id, outcome in outcome_nodes:
        lines.append(_dot_html_node(node_id, _action_outcome_card(outcome_id, outcome)))
    for event_id, node_id in event_nodes.items():
        lines.append(_dot_html_node(node_id, _event_card(event_id, contract, subtitle="emitted event", mode="emitted")))

    entry_node = input_node if application_action.get("input") else None
    if entry_node and policy_node:
        lines.append(_dot_edge(entry_node, policy_node, {"label": "authorize", "color": _DOT_COLOR_POLICY_BORDER, "penwidth": "1.2"}))
        entry_node = policy_node
    elif policy_node:
        entry_node = policy_node

    flow_tail = entry_node
    for node_id, action, _, target_kind, _ in resource_nodes:
        if flow_tail:
            resource_color = _DOT_COLOR_ENTITY_TYPE_BORDER if target_kind == "entity_type" else _DOT_COLOR_SCHEMA_BORDER
            lines.append(_dot_edge(flow_tail, node_id, {"label": action, "color": resource_color}))
        flow_tail = node_id

    for node_id, outcome_id, outcome in outcome_nodes:
        authorization_failure_label = authorization_failure_labels.get(outcome_id)
        if authorization_failure_label and policy_node:
            lines.append(_dot_edge(policy_node, node_id, {"label": authorization_failure_label, "color": _DOT_COLOR_POLICY_BORDER}))
        elif flow_tail:
            lines.append(_dot_edge(flow_tail, node_id, {"label": outcome["kind"], "color": _outcome_edge_color(outcome["kind"])}))
        for emit in outcome.get("emits", []):
            event_id = emit["domain_event"] if isinstance(emit, dict) else emit
            lines.append(_dot_edge(node_id, event_nodes[event_id], {"label": "emit", "color": _DOT_COLOR_EVENT_BORDER, "penwidth": "1.2"}))
    if outcome_nodes:
        lines.append("  { rank=same; " + " ".join(_dot_quote(node_id) for node_id, _, _ in outcome_nodes) + " }")
        lines.extend(_dot_invisible_order([node_id for node_id, _, _ in outcome_nodes], indent="  "))
    lines.append("}")
    return "\n".join(lines) + "\n"


def _application_action_reference_sections(application_action_id: str, application_action: dict[str, Any]) -> list[tuple[str, list[object]]]:
    sections: list[tuple[str, list[object]]] = []
    if application_action.get("action_kind"):
        sections.append(("kind", [application_action["action_kind"]]))
    authorization = application_action.get("authorization")
    if authorization:
        sections.append((
            "authorization",
            [
                f"policy: {authorization['policy']}",
                f"authentication_required_as: {authorization['authentication_required_as']}",
                f"access_denied_as: {authorization['access_denied_as']}",
            ],
        ))
    return sections


def _application_action_resource_nodes(
    application_action_id: str,
    application_action: dict[str, Any],
    contract: dict[str, Any],
) -> list[tuple[str, str, str, str, list[tuple[str, list[object]]]]]:
    nodes: list[tuple[str, str, str, str, list[tuple[str, list[object]]]]] = []
    seen: set[tuple[str, str, str]] = set()
    for action in ["creates", "reads", "updates", "deletes"]:
        for target_id in application_action.get(action, []):
            target_kind = "entity_type" if target_id in contract.get("entity_types", {}) else "schema"
            key = (action, target_kind, target_id)
            if key in seen:
                continue
            seen.add(key)
            resource = contract.get("entity_types", {}).get(target_id, contract.get("schemas", {}).get(target_id, {}))
            fields = schema_properties(resource.get("schema", {}))
            nodes.append((
                _dot_node_id("application_action_resource", f"{application_action_id}_{action}_{target_id}"),
                action,
                target_id,
                target_kind,
                [("fields", _schema_fields(fields))],
            ))
    if application_action.get("lifecycle_transition"):
        lifecycle_transition = application_action["lifecycle_transition"]
        field = schema_properties(contract["entity_types"][lifecycle_transition["entity_type"]]["schema"])[lifecycle_transition["field"]]
        nodes.append((
            _dot_node_id("application_action_resource", f"{application_action_id}_lifecycle_transition_{lifecycle_transition['entity_type']}_{lifecycle_transition['field']}"),
            "lifecycle_transition",
            lifecycle_transition["entity_type"],
            "entity_type",
            [("change", [_DotTransitionField(f"{type_display({'$ref': lifecycle_transition['entity_type']})}.{lifecycle_transition['field']}", effective_property_schema(field), f"{lifecycle_transition['from']} {_DOT_ARROW_FORWARD} {lifecycle_transition['to']}")])],
        ))
    return nodes


def _action_outcome_card(outcome_id: str, outcome: dict[str, Any]) -> str:
    sections: list[tuple[str, list[object]]] = [("result", [_DotTypedField("result", outcome["result"])])]
    return _dot_card(outcome_id, f"{outcome['kind']} outcome", sections, style=_exit_card_style(outcome["kind"]))


def _outcome_edge_color(kind: str) -> str:
    if kind == "success":
        return _DOT_COLOR_SUCCESS_BORDER
    if kind == "failure":
        return _DOT_COLOR_FAILURE_BORDER
    return _DOT_COLOR_TARGET_BORDER


def _policy_reference_card(
    policy_id: str,
    contract: dict[str, Any],
    *,
    subtitle: str = "authorization policy",
    include_resources: bool = True,
) -> str:
    policy = contract.get("authorization_policies", {}).get(policy_id, {})
    sections = [("effect", [policy.get("effect", "")])]
    if policy.get("subjects"):
        sections.append(("subjects", _format_subjects(policy["subjects"])))
    if include_resources and policy.get("resources"):
        sections.append(("resources", _format_authorization_resources(policy["resources"])))
    if policy.get("conditions"):
        sections.append(("conditions", _format_conditions(policy["conditions"])))
    return _dot_card(policy_id, subtitle, sections, rationale=policy.get("rationale", ""), style=_DOT_STYLE_POLICY)


def _schema_fields(fields: dict[str, Any]) -> list[_DotTypedField]:
    return [_DotTypedField(name, effective_property_schema(field)) for name, field in sorted(schema_properties(fields).items())]


def _entry_surface_title(entry: dict[str, Any]) -> str:
    adapter_kind, _ = entry_point_adapter_pair(entry)
    if adapter_kind == "http_api":
        return f"{(entry_point_method(entry) or '').upper()} {entry_point_path(entry) or ''}".strip()
    if adapter_kind in {"html_route", "webhook"}:
        return entry_point_path(entry) or adapter_kind
    if adapter_kind == "cli":
        return entry_point_cli_command(entry) or adapter_kind
    if adapter_kind == "scheduled":
        return entry_point_schedule_expression(entry) or adapter_kind
    if adapter_kind == "worker":
        return entry.get("workflow_ref", adapter_kind)
    return adapter_kind


def _entry_binding_sections(entry: dict[str, Any], contract: dict[str, Any]) -> list[tuple[str, list[object]]]:
    labels = {
        "route": "route",
        "screen": "screen",
        "endpoint": "endpoint",
        "cli_command_ref": "cli command",
        "workflow_ref": "workflow",
    }
    sections = [(label, [entry[key]]) for key, label in labels.items() if entry.get(key)]
    schedule = entry_point_schedule_expression(entry)
    if schedule:
        sections.append(("schedule", [schedule]))
    sections.extend(_authorization_policy_sections(entry.get("authorization_policy"), contract, include_details=False))
    return sections


def _entry_input_sections(entry: dict[str, Any], contract: dict[str, Any]) -> list[tuple[str, list[object]]]:
    sections: list[tuple[str, list[object]]] = []
    entry_input = entry_point_input(entry)
    if entry_input.get("path_params"):
        sections.append(("path params", _typed_fields(entry_input["path_params"])))
    if entry_input.get("query_params"):
        sections.append(("query params", _typed_fields(entry_input["query_params"])))
    if entry_input.get("body"):
        sections.append(("body", _typed_fields(entry_input["body"])))
    if entry_input.get("args"):
        sections.append(("args", _typed_fields(entry_input["args"])))
    if entry_input.get("payload"):
        sections.append(("payload", [_DotTypedField("payload", entry_input["payload"])]))
    return sections


def _entry_point_response_nodes(entry_id: str, entry: dict[str, Any], contract: dict[str, Any]) -> list[tuple[str, str, str | None, str | None, list[tuple[str, list[object]]]]]:
    responses = entry_point_responses(entry)
    handlers = entry_point_response_handlers(entry)
    if not responses and not handlers:
        return []
    target_kind, target_value = entry_target_pair(entry)
    outcomes = _entry_point_response_outcomes(contract, target_kind, target_value)
    nodes = []
    for outcome_id, response in sorted(responses.items()):
        outcome = outcomes.get(outcome_id)
        outcome_kind = outcome["kind"] if outcome else _entry_response_style_kind(response)
        subtitle = f"{outcome['kind']} response" if outcome else _entry_disposition_subtitle(response, outcome_kind)
        node_id = _dot_node_id("entrypoint_response", f"{entry_id}_{outcome_id}")
        nodes.append((node_id, outcome_id, subtitle, outcome_kind, _entry_point_response_sections(response)))
    for outcome_id, handler in sorted(handlers.items()):
        outcome = outcomes.get(outcome_id)
        outcome_kind = outcome["kind"] if outcome else _entry_response_style_kind(handler)
        subtitle = f"{outcome['kind']} response handler" if outcome else _entry_disposition_subtitle(handler, outcome_kind) or "response handler"
        node_id = _dot_node_id("entrypoint_response", f"{entry_id}_{outcome_id}")
        nodes.append((node_id, outcome_id, subtitle, outcome_kind, _entry_point_response_sections(handler)))
    return nodes


def _entry_disposition_subtitle(response: dict[str, Any], outcome_kind: str | None) -> str | None:
    if "disposition" not in response:
        return None
    if outcome_kind in {"success", "failure"}:
        return f"{outcome_kind} disposition"
    return "disposition"


def _entry_response_style_kind(response: dict[str, Any]) -> str | None:
    disposition = response.get("disposition")
    if disposition == "acknowledge":
        return "success"
    if disposition in {"retry", "reject", "dead_letter"} or "problem" in response:
        return "failure"
    return None


def _exit_card_style(outcome_kind: str | None) -> _DotCardStyle:
    if outcome_kind == "success":
        return _DOT_STYLE_SUCCESS_EXIT
    if outcome_kind == "failure":
        return _DOT_STYLE_FAILURE_EXIT
    return _DOT_STYLE_TARGET


def _entry_point_response_outcomes(contract: dict[str, Any], target_kind: str, target_value: str) -> dict[str, Any]:
    if target_kind == "application_action":
        return contract["application_actions"][target_value]["outcomes"]
    if target_kind == "entry_point":
        delegated_kind, delegated_value = entry_target_pair(contract["entry_points"][target_value])
        return _entry_point_response_outcomes(contract, delegated_kind, delegated_value)
    return {}


def _entry_point_response_sections(response: dict[str, Any]) -> list[tuple[str, list[object]]]:
    sections: list[tuple[str, list[object]]] = []
    if "status" in response:
        sections.append(("status", [str(response["status"])]))
    if "body" in response:
        body = response["body"]
        sections.append(("body", [_DotTypedField("body", body["type"], body.get("from"))]))
    if "stdout" in response:
        stdout = response["stdout"]
        if "type" in stdout:
            sections.append(("stdout", [_DotTypedField("stdout", stdout["type"], stdout.get("from"))]))
        else:
            sections.append(("stdout", [stdout["text"]]))
            if stdout.get("bindings"):
                sections.append(("stdout bindings", _format_binding_lines(stdout["bindings"])))
    if "stderr" in response:
        stderr = response["stderr"]
        if "type" in stderr:
            sections.append(("stderr", [_DotTypedField("stderr", stderr["type"], stderr.get("from"))]))
        else:
            sections.append(("stderr", [stderr["text"]]))
            if stderr.get("bindings"):
                sections.append(("stderr bindings", _format_binding_lines(stderr["bindings"])))
    if "exit_code" in response:
        sections.append(("exit_code", [str(response["exit_code"])]))
    if "disposition" in response:
        sections.append(("disposition", [response["disposition"]]))
    if "problem" in response:
        sections.append(("problem", [_DotTypedField("problem", response["problem"])]))
    if "retry_policy" in response:
        retry = response["retry_policy"]
        sections.append(("retry", [f"{retry['attempts']} {retry['backoff']}"]))
    return sections


def _format_binding_lines(bindings: dict[str, Any]) -> list[str]:
    lines = []
    for name, binding in sorted(bindings.items()):
        if isinstance(binding, dict) and "from" in binding:
            lines.append(f"{name} {_DOT_ARROW_ASSIGN} {_format_flow_source(binding)}")
        elif isinstance(binding, dict) and "value" in binding:
            lines.append(f"{name} = {_format_flow_source(binding)}")
        else:
            lines.append(f"{name} = {_format_flow_source(binding)}")
    return lines


def _entry_target_card(
    target_kind: str,
    target_value: str,
    contract: dict[str, Any],
    *,
    renderer: str | None = None,
) -> str:
    if target_kind == "state_machine":
        state_machine = contract["state_machines"][target_value]
        return _dot_card(
            target_value,
            f"target state machine ({renderer})" if renderer else "target state machine",
            _state_machine_summary_sections(state_machine, contract),
            rationale=state_machine.get("rationale", ""),
            style=_DOT_STYLE_TARGET,
        )
    if target_kind == "application_action":
        application_action = contract["application_actions"][target_value]
        return _dot_card(
            target_value,
            "target application action",
            _application_action_reference_sections(target_value, application_action),
            rationale=application_action.get("rationale", ""),
            style=_DOT_STYLE_CAPABILITY,
        )
    if target_kind == "workflow":
        workflow = contract["workflows"][target_value]
        return _dot_card(
            target_value,
            "target workflow",
            [
                ("trigger", [_target_label(*_target_pair(workflow["trigger"]))]),
                ("steps", [f"{step['id']} {_DOT_ARROW_FORWARD} {step['application_action']}" for step in workflow["steps"]]),
                ("outcomes", [_DotTypedField(outcome_id, outcome["result"], outcome["kind"]) for outcome_id, outcome in sorted(workflow["outcomes"].items())]),
            ],
            rationale=workflow.get("rationale", ""),
            style=_DOT_STYLE_WORKFLOW,
        )
    if target_kind == "entry_point":
        delegated = contract["entry_points"][target_value]
        adapter_kind, _ = entry_point_adapter_pair(delegated)
        delegated_target_kind, delegated_target_value = entry_target_pair(delegated)
        sections: list[tuple[str, list[object]]] = [
            ("adapter", [adapter_kind]),
            ("target", [_target_label(delegated_target_kind, delegated_target_value)]),
        ]
        if delegated_target_kind == "application_action":
            sections.extend(_application_action_reference_sections(delegated_target_value, contract["application_actions"][delegated_target_value]))
        else:
            sections.extend(_authorization_policy_sections(delegated.get("authorization_policy"), contract, include_details=False))
        return _dot_card(
            target_value,
            "delegated entry point",
            sections,
            rationale=delegated.get("rationale", ""),
            style=_DOT_STYLE_ENTRY,
        )
    if target_kind == "domain_event":
        return _event_card(target_value, contract)
    return _dot_card(target_value, f"target {target_kind}", [], style=_DOT_STYLE_NEUTRAL)


def _entry_target_tail_nodes(target_kind: str, target_value: str, contract: dict[str, Any]) -> list[tuple[str, str]]:
    if target_kind != "state_machine":
        return []
    state_machine = contract["state_machines"][target_value]
    nodes: list[tuple[str, str]] = []
    for state_name, state in sorted(state_machine.get("view_states", {}).items()):
        if state.get("child_state_machines"):
            nodes.extend(
                (_dot_node_id("entrypoint_mount", f"{target_value}_{state_name}_{mount['id']}"), _dot_mount_card(mount))
                for mount in state["child_state_machines"]
            )
        else:
            nodes.append((_dot_node_id("entrypoint_state_machine_view_state", f"{target_value}_{state_name}"), _state_machine_view_state_card(state_machine, state_name, state, contract)))
    return nodes


def _state_machine_summary_sections(state_machine: dict[str, Any], contract: dict[str, Any]) -> list[tuple[str, list[object]]]:
    sections: list[tuple[str, list[object]]] = []
    bindings = _data_loader_bindings(state_machine.get("data_loaders", {}))
    application_action_ids = [binding["application_action"] for binding in bindings]
    inputs = _format_data_inputs(state_machine, bindings, contract)
    queries = [binding["data_loader"] for binding in bindings]
    loads = _format_application_action_outputs(application_action_ids, contract)
    guards = _format_action_authorization_policies(application_action_ids, contract)
    if inputs:
        sections.append(("input", inputs))
    if queries:
        sections.append(("data_loaders", queries))
    if loads:
        sections.append(("load", loads))
    if guards:
        sections.append(("authorization_policies", guards))
    sections.append(("entity_type", [state_machine["entity_type"]]))
    sync_ids = [rule["id"] for state in state_machine.get("view_states", {}).values() for rule in state.get("signal_sync_rules", [])]
    if sync_ids:
        sections.append(("signal_sync_rules", sync_ids))
    return sections


def _state_machine_view_state_card(state_machine: dict[str, Any], state_name: str, state: dict[str, Any], contract: dict[str, Any]) -> str:
    return _dot_card(
        state_name,
        "view state",
        _state_machine_view_state_sections(state_machine, state_name, state, contract),
        style=_DOT_STYLE_NEUTRAL,
    )


def _state_machine_view_state_sections(
    state_machine: dict[str, Any],
    state_name: str,
    state: dict[str, Any],
    contract: dict[str, Any],
) -> list[tuple[str, Iterable[object]]]:
    data_loaders = state.get("data_loaders", {})
    action_bindings = state.get("action_bindings", {})
    query_application_action_ids = [invocation["application_action"] for invocation in data_loaders.values()]
    application_action_ids = [invocation["application_action"] for invocation in action_bindings.values()]
    return [
        ("text", state.get("text", [])),
        ("assets", state.get("assets", [])),
        (_state_field_section_title(state_machine, state_name, state), _format_state_fields(state_machine, state, contract)),
        ("data_loaders", _format_action_binding_outputs(data_loaders, contract)),
        ("action_bindings", _format_action_binding_outputs(action_bindings, contract)),
        ("authorization_policies", _format_action_authorization_policies([*query_application_action_ids, *application_action_ids], contract)),
        ("child_state_machines", _format_mounts(state.get("child_state_machines", []))),
        ("signal_sync_rules", [rule["id"] for rule in state.get("signal_sync_rules", [])]),
    ]


def _workflow_trigger_card(trigger_kind: str, trigger_value: str, contract: dict[str, Any]) -> str:
    if trigger_kind == "domain_event":
        return _event_card(trigger_value, contract, subtitle="domain event trigger")
    if trigger_kind == "application_action":
        application_action = contract["application_actions"][trigger_value]
        return _dot_card(
            trigger_value,
            "application action trigger",
            _application_action_reference_sections(trigger_value, application_action),
            rationale=application_action.get("rationale", ""),
            style=_DOT_STYLE_EVENT,
        )
    return _dot_card(trigger_value, f"{trigger_kind} trigger", [], style=_DOT_STYLE_EVENT)


def _workflow_step_card(step: dict[str, Any], contract: dict[str, Any]) -> str:
    application_action = contract["application_actions"][step["application_action"]]
    sections: list[tuple[str, list[object]]] = [
        ("application_action", [step["application_action"]]),
        ("input bindings", _format_binding_lines(step["input_bindings"])),
        ("transitions", _workflow_transition_lines(step)),
    ]
    sections.extend(_application_action_reference_sections(step["application_action"], application_action))
    return _dot_card(
        step["id"],
        "workflow step",
        sections,
        rationale=application_action.get("rationale", ""),
        style=_DOT_STYLE_NEUTRAL,
    )


def _workflow_transition_lines(step: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for outcome_id, transition in sorted(step["outcome_transitions"].items()):
        transition_key, value = _workflow_transition_action(transition)
        if transition_key == "retry_policy":
            target = f"retry_policy {_DOT_ARROW_FORWARD} {value['fail_as']}"
            suffix = f" ({value['attempts']} {value['backoff']})"
        else:
            target = f"{transition_key} {_DOT_ARROW_FORWARD} {value}"
            suffix = ""
        lines.append(f"{outcome_id}: {target}{suffix}")
    return lines


def _workflow_transition_action(transition: dict[str, Any]) -> tuple[str, Any]:
    for transition_key in ("next_step", "complete_as", "fail_as", "retry_policy", "dead_letter_as"):
        if transition_key in transition:
            return transition_key, transition[transition_key]
    raise KeyError("workflow transition has no target")


def _workflow_transition_outcome(transition_key: str, value: Any) -> str | None:
    if transition_key in {"complete_as", "fail_as", "dead_letter_as"}:
        return value
    if transition_key == "retry_policy":
        return value["fail_as"]
    return None


def _workflow_outcome_card(outcome_id: str, outcome: dict[str, Any]) -> str:
    return _dot_card(
        outcome_id,
        f"{outcome['kind']} workflow outcome",
        [("result", [_DotTypedField("result", outcome["result"])])],
        style=_exit_card_style(outcome["kind"]),
    )


def _event_card(
    event_id: str,
    contract: dict[str, Any],
    *,
    subtitle: str = "target domain event",
    mode: _EventCardMode = "reference",
) -> str:
    event = contract.get("domain_events", {}).get(event_id, {})
    sections: list[tuple[str, list[object]]] = []
    if event.get("payload_schema"):
        payload_field = _DotExpandedTypedField("payload", event["payload_schema"]) if mode == "emitted" else _DotTypedField("payload", event["payload_schema"])
        sections.append(("payload", [payload_field]))
    if mode == "reference" and event.get("emitted_by"):
        sections.append(("emitted by", event["emitted_by"]))
    return _dot_card(
        event_id,
        subtitle,
        sections,
        rationale=event.get("rationale", ""),
        style=_DOT_STYLE_EVENT,
    )


def _authorization_policy_sections(
    policy_id: str | None,
    contract: dict[str, Any],
    *,
    include_details: bool = True,
) -> list[tuple[str, list[object]]]:
    if not policy_id:
        return []
    sections: list[tuple[str, list[object]]] = [("authorization_policy", [policy_id])]
    if not include_details:
        return sections
    policy = contract.get("authorization_policies", {}).get(policy_id)
    if not policy:
        return sections
    sections.append(("effect", [policy["effect"]]))
    sections.append(("subjects", _format_subjects(policy.get("subjects", []))))
    sections.append(("resources", _format_authorization_resources(policy.get("resources", []))))
    sections.append(("conditions", _format_conditions(policy.get("conditions", []))))
    return sections


def _format_subjects(subjects: Iterable[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for subject in subjects:
        line = subject["kind"]
        if subject.get("source"):
            line = f"{line} {_DOT_ARROW_ASSIGN} {_format_flow_source(subject['source'])}"
        lines.append(line)
    return lines


def _format_authorization_resources(resources: Iterable[dict[str, str]]) -> list[str]:
    return [f"{kind}: {value}" for kind, value in (_target_pair(resource) for resource in resources)]


def _format_conditions(conditions: Iterable[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for condition in conditions:
        kind, body = _target_pair(condition)
        if kind == "unconditional":
            lines.append(f"unconditional {_format_scalar(body)}")
        elif kind == "input_present":
            lines.append(f"input_present {body}")
        elif kind == "entity_exists":
            lines.append(f"{body['entity_type']} exists")
        elif kind == "entity_state_condition":
            lines.append(f"{body['entity_type']}.{body['field']} = {_format_scalar(body['equals'])}")
        elif kind == "subject_has_role":
            lines.append(f"subject_has_role {body}")
        else:
            lines.append(f"{kind}: {_format_scalar(body)}")
    return lines


def _typed_fields(fields: dict[str, Any]) -> list[_DotTypedField]:
    return [_DotTypedField(name, type_name) for name, type_name in sorted(schema_properties(fields).items())]


def _target_pair(target: dict[str, str]) -> tuple[str, str]:
    return next(iter(target.items()))


def _target_label(kind: str, value: str) -> str:
    return f"{kind} {value}"


def _format_mounts(mounts: Iterable[dict[str, Any]]) -> list[_DotTypedField]:
    lines: list[_DotTypedField] = []
    for mount in sorted(mounts, key=lambda item: (item.get("html_region") or item.get("textual_container") or "", item["id"])):
        placement = mount.get("html_region") or mount.get("textual_container")
        lines.append(_DotReferenceField(placement or "", mount["state_machine"]))
    return lines


def _dot_mount_card(mount: dict[str, Any]) -> str:
    placement = mount.get("html_region") or mount.get("textual_container")
    return _dot_card(
        mount["id"],
        f"{placement} mount",
        [
            ("state_machine", [mount["state_machine"]]),
            ("initial_view_state", [mount["initial_view_state"]]),
        ],
        style=_DOT_STYLE_STATE_MACHINE,
    )


def _dot_sync_effect_card(
    effect: dict[str, Any],
    mount_by_id: dict[str, dict[str, Any]],
    contract: dict[str, Any],
) -> str:
    if "send" in effect:
        send = effect["send"]
        return _dot_card(
            _local_signal_label(send["local_signal"]),
            "sent local signal",
            [
                ("causes", _receiving_transition_refs(send["instance"], send["local_signal"], mount_by_id, contract)),
                ("payload", _sent_local_signal_data_lines(send, mount_by_id, contract)),
            ],
            style=_DOT_STYLE_MESSAGE,
        )
    assignment = effect["set"]
    return _dot_card(
        f"set {assignment['context']}",
        "state machine context update",
        [
            ("set", [_format_flow_assignment(assignment["context"], _assignment_value(assignment), identity_scope=None)]),
        ],
        style=_DOT_STYLE_CONTEXT,
    )


def _emitted_local_signal_data_lines(
    instance_id: str,
    emitted: str,
    mount_by_id: dict[str, dict[str, Any]],
    contract: dict[str, Any],
) -> list[_DotTypedField]:
    payload = _local_signal_payload_for_instance(instance_id, "emits", emitted, mount_by_id, contract)
    lines: list[_DotTypedField] = []
    seen: set[str] = set()
    for emit in _emitting_transition_emits(instance_id, emitted, mount_by_id, contract):
        for line in _format_typed_data_flow(emit.get("payload_bindings", {}), payload):
            signature = str(line)
            if signature not in seen:
                lines.append(line)
                seen.add(signature)
    return lines


def _sync_set_lines(rule: dict[str, Any], state_machine: dict[str, Any]) -> list[_DotTypedField]:
    lines = []
    context = schema_properties(state_machine["context"])
    for effect in rule.get("effects", []):
        assignment = effect.get("set")
        if not assignment:
            continue
        target = assignment["context"]
        lines.append(_format_typed_flow_assignment(target, context[target], _assignment_value(assignment), identity_scope=None))
    return lines


def _sent_local_signal_data_lines(
    send: dict[str, Any],
    mount_by_id: dict[str, dict[str, Any]],
    contract: dict[str, Any],
) -> list[_DotTypedField]:
    payload = _local_signal_payload_for_instance(send["instance"], "accepts", send["local_signal"], mount_by_id, contract)
    return _format_typed_data_flow(send.get("payload_bindings", {}), payload)


def _assignment_value(assignment: dict[str, Any]) -> Any:
    return assignment.get("from", assignment.get("value", ""))


def _local_signal_payload_for_instance(
    instance_id: str,
    direction: str,
    local_signal: str,
    mount_by_id: dict[str, dict[str, Any]],
    contract: dict[str, Any],
) -> dict[str, str]:
    mount = mount_by_id[instance_id]
    state_machine = contract["state_machines"][mount["state_machine"]]
    return schema_properties(state_machine["signals"][direction]["local_signals"][local_signal]["payload_schema"])


def _emitting_transition_emits(
    instance_id: str,
    emitted: str,
    mount_by_id: dict[str, dict[str, Any]],
    contract: dict[str, Any],
) -> list[dict[str, Any]]:
    mount = mount_by_id[instance_id]
    state_machine = contract["state_machines"][mount["state_machine"]]
    emits = []
    for transition in state_machine.get("transitions", []):
        for effect in transition.get("effects", []):
            emit = effect.get("emit")
            if emit and emit["local_signal"] == emitted:
                emits.append(emit)
    return emits


def _emitting_transition_refs(
    instance_id: str,
    emitted: str,
    mount_by_id: dict[str, dict[str, Any]],
    contract: dict[str, Any] | None,
) -> list[str]:
    refs = []
    if not contract:
        return refs
    mount = mount_by_id.get(instance_id)
    if not mount:
        return refs
    state_machine = contract.get("state_machines", {}).get(mount["state_machine"])
    if not state_machine:
        return refs
    for transition in state_machine.get("transitions", []):
        if any(effect.get("emit", {}).get("local_signal") == emitted for effect in transition.get("effects", [])):
            refs.append(_signal_label(transition["on"]))
    return refs


def _receiving_transition_refs(
    instance_id: str,
    local_signal: str,
    mount_by_id: dict[str, dict[str, Any]],
    contract: dict[str, Any] | None,
) -> list[str]:
    if not contract:
        return []
    mount = mount_by_id.get(instance_id)
    if not mount:
        return []
    state_machine = contract.get("state_machines", {}).get(mount["state_machine"])
    if not state_machine:
        return []
    target_sources: dict[str, list[str]] = {}
    for transition in state_machine.get("transitions", []):
        if transition["on"] == {"local_signal": local_signal}:
            target_sources.setdefault(transition["to"], []).append(transition["from"])
    if len(target_sources) == 1:
        target = next(iter(target_sources))
        return [f"to {target}"]
    return [f"to {target} (from {', '.join(sorted(sources))})" for target, sources in sorted(target_sources.items())]


def _dot_node_id(prefix: str, value: str) -> str:
    return f"{prefix}_{safe_id(value)}"


def _dot_graph_preamble(graph_id: str) -> list[str]:
    return [
        f"digraph {_dot_quote(graph_id)} {{",
        '  graph [rankdir="LR", bgcolor="transparent", pad="0.25", nodesep="0.38", ranksep="0.85", splines="spline"];',
        f'  node [fontname="{_DOT_FONT}", fontsize="{_DOT_SIZE_DEFAULT_NODE}"];',
        f'  edge [color="{_DOT_COLOR_EDGE}", fontname="{_DOT_FONT}", fontsize="{_DOT_SIZE_BODY}", arrowsize="0.8"];',
    ]


def _dot_circle_node(
    node_id: str,
    label: str,
    *,
    width: str,
    color: str,
    fontcolor: str,
    shape: str = "circle",
) -> str:
    return _dot_plain_node(
        node_id,
        {
            "shape": shape,
            "label": label,
            "width": width,
            "fixedsize": "true",
            "color": color,
            "fontcolor": fontcolor,
            "fontsize": str(_DOT_SIZE_NODE),
        },
    )


def _dot_plain_node(node_id: str, attrs: dict[str, object], indent: str = "  ") -> str:
    return f"{indent}{_dot_quote(node_id)}{_dot_attrs(attrs)};"


def _dot_edge(source: str, target: str, attrs: dict[str, object] | None = None, indent: str = "  ") -> str:
    edge_attrs = {name: value for name, value in (attrs or {}).items() if name != "color"}
    return f"{indent}{_dot_quote(source)} -> {_dot_quote(target)}{_dot_attrs(edge_attrs)};"


def _dot_invisible_order(node_ids: list[str], indent: str) -> list[str]:
    return [
        _dot_edge(source, target, {"style": "invis", "weight": "100"}, indent=indent)
        for source, target in zip(node_ids, node_ids[1:])
    ]


class _DotHtml(str):
    pass


class _DotTypedField:
    def __init__(self, field: str, type_name: Any, source: str | None = None) -> None:
        self.field = field
        self.type_name = type_display(_display_type(type_name))
        self.source = source

    def __str__(self) -> str:
        suffix = f" {_DOT_ARROW_ASSIGN} {self.source}" if self.source is not None else ""
        return f"{self.field} {self.type_name}{suffix}"


class _DotExpandedTypedField(_DotTypedField):
    pass


class _DotReferenceField(_DotTypedField):
    def __init__(self, field: str, ref: str, source: str | None = None) -> None:
        self.field = field
        self.type_name = ref
        self.source = source


class _DotTransitionField:
    def __init__(self, field: str, type_name: Any, change: str) -> None:
        self.field = field
        self.type_name = type_display(_display_type(type_name))
        self.change = change

    def __str__(self) -> str:
        return f"{self.field} {self.type_name} {self.change}"


def _display_type(type_name: Any) -> Any:
    return type_name


def _dot_html_node(node_id: str, label: str, attrs: dict[str, object] | None = None, indent: str = "  ") -> str:
    node_attrs: dict[str, object] = {"shape": "plain", "label": _DotHtml(label)}
    node_attrs.update(attrs or {})
    return _dot_plain_node(node_id, node_attrs, indent=indent)


def _dot_card(
    title: str,
    subtitle: str | None,
    sections: Iterable[tuple[str, Iterable[object]]],
    *,
    rationale: str | None = None,
    style: _DotCardStyle = _DOT_STYLE_NEUTRAL,
) -> str:
    header_bg = style.header_bg
    border = style.border
    rows = [
        f'<TR><TD BGCOLOR="{border}" HEIGHT="3" FIXEDSIZE="false"></TD></TR>',
        _dot_header_row(title, subtitle, header_bg=header_bg),
    ]
    if rationale:
        rows.extend(_dot_text_rows(_wrap_dot_text(rationale, width=50), point_size=_DOT_SIZE_BODY, italic=True, color=_DOT_COLOR_AUDIT_TEXT))
    rows.extend(_dot_section_rows(sections))
    return (
        f'<TABLE BORDER="1" CELLBORDER="0" CELLSPACING="0" CELLPADDING="4" COLOR="{border}" BGCOLOR="#ffffff">'
        + "".join(rows)
        + "</TABLE>"
    )


def _dot_header_row(title: str, subtitle: str | None, *, header_bg: str) -> str:
    header_rows = [
        f'<TR><TD ALIGN="LEFT"><FONT POINT-SIZE="{_DOT_SIZE_TITLE}"><B>{_dot_html_text(title)}</B></FONT></TD></TR>',
    ]
    if subtitle:
        header_rows.extend(
            f'<TR><TD ALIGN="LEFT"><FONT POINT-SIZE="{_DOT_SIZE_META}" COLOR="{_DOT_COLOR_MUTED}">{_dot_html_text(line)}</FONT></TD></TR>'
            for line in _wrap_dot_text(subtitle)
        )
    header = (
        '<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="0" CELLPADDING="0">'
        + "".join(header_rows)
        + "</TABLE>"
    )
    return (
        f'<TR><TD BGCOLOR="{header_bg}" ALIGN="LEFT">'
        f"{header}</TD></TR>"
    )


def _dot_text_rows(lines: Iterable[str], *, point_size: int, italic: bool = False, color: str | None = None) -> list[str]:
    inner_rows = []
    font_attrs = [f'POINT-SIZE="{point_size}"']
    if color:
        font_attrs.append(f'COLOR="{color}"')
    open_font = "<FONT " + " ".join(font_attrs) + ">"
    for line in lines:
        text = _dot_html_text(line)
        if italic:
            text = f"<I>{text}</I>"
        inner_rows.append(f'<TR><TD ALIGN="LEFT">{open_font}{text}</FONT></TD></TR>')
    if not inner_rows:
        return []
    return [_dot_nested_rows(inner_rows)]


def _dot_section_rows(sections: Iterable[tuple[str, Iterable[object]]]) -> list[str]:
    rows: list[str] = []
    compact_rows: list[str] = []
    for title, values in sections:
        section = _dot_section_inner_rows(title, values)
        if not section:
            continue
        is_compact, inner_rows = section
        if is_compact:
            compact_rows.extend(inner_rows)
            continue
        if compact_rows:
            rows.append(_dot_nested_rows(compact_rows, cell_spacing=1))
            compact_rows = []
        rows.append(_dot_nested_rows(inner_rows))
    if compact_rows:
        rows.append(_dot_nested_rows(compact_rows, cell_spacing=1))
    return rows


def _dot_section_inner_rows(title: str, values: Iterable[object]) -> tuple[bool, list[str]] | None:
    values = list(values)
    if values and all(isinstance(value, _DotTransitionField) for value in values):
        return _dot_transition_field_section_inner_rows(title, values)
    if values and all(isinstance(value, _DotTypedField) for value in values):
        return _dot_typed_field_section_inner_rows(title, values)
    wrapped_values = [wrapped for value in values if (wrapped := _wrap_dot_text(value))]
    if not wrapped_values:
        return None
    inner_rows: list[str] = []
    is_compact = len(wrapped_values) == 1 and len(wrapped_values[0]) == 1
    if len(wrapped_values) == 1:
        wrapped = wrapped_values[0]
        inner_rows.append(_dot_key_value_row(title, wrapped[0]))
        for line in wrapped[1:]:
            inner_rows.append(_dot_key_value_row("", line))
        return is_compact, inner_rows
    for wrapped in wrapped_values:
        if not inner_rows:
            inner_rows.append(f'<TR><TD ALIGN="LEFT"><FONT POINT-SIZE="{_DOT_SIZE_BODY}"><B>{_dot_html_text(title)}</B></FONT></TD></TR>')
        inner_rows.append(f'<TR><TD ALIGN="LEFT"><FONT POINT-SIZE="{_DOT_SIZE_BODY}">{_dot_html_text(wrapped[0])}</FONT></TD></TR>')
        for line in wrapped[1:]:
            inner_rows.append(f'<TR><TD ALIGN="LEFT"><FONT POINT-SIZE="{_DOT_SIZE_BODY}">{_dot_html_text(line)}</FONT></TD></TR>')
    return False, inner_rows


def _dot_typed_field_section_inner_rows(title: str, values: list[object]) -> tuple[bool, list[str]]:
    compactable = all(not isinstance(value, _DotExpandedTypedField) for value in values)
    if compactable and (title in {"input", "output", "payload", "payload_schema", "data_loaders", "set", "load", "action_bindings"}) and len(values) == 1:
        rows = []
        for index, value in enumerate(values):
            if isinstance(value, _DotTypedField):
                rows.append(_dot_typed_field_key_value_row(title if index == 0 else "", value))
        return True, rows
    inner_rows = [f'<TR><TD ALIGN="LEFT"><FONT POINT-SIZE="{_DOT_SIZE_BODY}"><B>{_dot_html_text(title)}</B></FONT></TD></TR>']
    inner_rows.extend(_dot_typed_field_row(value) for value in values if isinstance(value, _DotTypedField))
    return False, inner_rows


def _dot_transition_field_section_inner_rows(title: str, values: list[object]) -> tuple[bool, list[str]]:
    inner_rows = [f'<TR><TD ALIGN="LEFT"><FONT POINT-SIZE="{_DOT_SIZE_BODY}"><B>{_dot_html_text(title)}</B></FONT></TD></TR>']
    inner_rows.extend(_dot_transition_field_row(value) for value in values if isinstance(value, _DotTransitionField))
    return False, inner_rows


def _dot_transition_field_row(value: _DotTransitionField) -> str:
    return (
        '<TR><TD ALIGN="LEFT" VALIGN="MIDDLE" HEIGHT="11">'
        f'<FONT POINT-SIZE="{_DOT_SIZE_BODY}">{_dot_html_text(value.field)}</FONT>'
        f'<FONT POINT-SIZE="{_DOT_SIZE_META}" COLOR="{_DOT_COLOR_TYPE}">&#160;&#160;{_dot_html_text(value.type_name)}</FONT>'
        f'<FONT POINT-SIZE="{_DOT_SIZE_META}">&#160;&#160;{_dot_html_text(value.change)}</FONT>'
        "</TD></TR>"
    )


def _dot_typed_field_row(value: _DotTypedField) -> str:
    source = _dot_typed_field_source(value)
    return (
        '<TR><TD ALIGN="LEFT" VALIGN="MIDDLE" HEIGHT="11">'
        f'<FONT POINT-SIZE="{_DOT_SIZE_BODY}">{_dot_html_text(value.field)}</FONT>'
        f'<FONT POINT-SIZE="{_DOT_SIZE_META}" COLOR="{_DOT_COLOR_TYPE}">&#160;&#160;{_dot_html_text(value.type_name)}</FONT>'
        f"{source}"
        "</TD></TR>"
    )


def _dot_typed_field_key_value_row(title: str, value: _DotTypedField) -> str:
    key = f"<B>{_dot_html_text(title)}:</B>&#160;&#160;" if title else "&#160;&#160;"
    source = _dot_typed_field_source(value)
    return (
        '<TR><TD ALIGN="LEFT" VALIGN="MIDDLE" HEIGHT="11">'
        f'<FONT POINT-SIZE="{_DOT_SIZE_BODY}">{key}{_dot_html_text(value.field)}</FONT>'
        f'<FONT POINT-SIZE="{_DOT_SIZE_META}" COLOR="{_DOT_COLOR_TYPE}">&#160;&#160;{_dot_html_text(value.type_name)}</FONT>'
        f"{source}"
        "</TD></TR>"
    )


def _dot_typed_field_source(value: _DotTypedField) -> str:
    if value.source is None:
        return ""
    return f'<FONT POINT-SIZE="{_DOT_SIZE_META}">&#160;{_DOT_ARROW_ASSIGN}&#160;{_dot_html_text(value.source)}</FONT>'


def _dot_key_value_text(title: str, value: str) -> str:
    key = f"<B>{_dot_html_text(title)}:</B>&#160;&#160;" if title else "&#160;&#160;"
    return f"{key}{_dot_html_text(value)}"


def _dot_key_value_row(title: str, value: str) -> str:
    return (
        f'<TR><TD ALIGN="LEFT" VALIGN="MIDDLE" HEIGHT="11"><FONT POINT-SIZE="{_DOT_SIZE_BODY}">'
        f"{_dot_key_value_text(title, value)}</FONT></TD></TR>"
    )


def _dot_nested_rows(inner_rows: list[str], *, cell_spacing: int = 0) -> str:
    inner = (
        f'<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="{cell_spacing}" CELLPADDING="0">'
        + "".join(inner_rows)
        + "</TABLE>"
    )
    return f'<TR><TD ALIGN="LEFT">{inner}</TD></TR>'


def _wrap_dot_text(value: object, width: int = 58) -> list[str]:
    text = str(value)
    if not text:
        return []
    chunks: list[str] = []
    for chunk in textwrap.wrap(text, width=width, break_long_words=False, break_on_hyphens=False):
        if len(chunk) <= width:
            chunks.append(chunk)
        else:
            chunks.extend(_wrap_dot_token(chunk, width))
    if chunks:
        return chunks
    return _wrap_dot_token(text, width)


def _wrap_dot_token(text: str, width: int) -> list[str]:
    if len(text) <= width:
        return [text]
    parts = text.split(".")
    lines: list[str] = []
    current = ""
    for part in parts:
        candidate = part if not current else f"{current}.{part}"
        if len(candidate) <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = part
    if current:
        lines.append(current)
    return lines or [text]


def _format_data_flow(mapping: dict[str, Any], *, identity_scope: str | None = "signal.payload") -> list[str]:
    return [_format_flow_assignment(key, value, identity_scope=identity_scope) for key, value in sorted(mapping.items())]


def _format_typed_data_flow(
    mapping: dict[str, Any],
    field_types: dict[str, str],
    *,
    identity_scope: str | None = "signal.payload",
) -> list[_DotTypedField]:
    return [
        _format_typed_flow_assignment(key, field_types[key], value, identity_scope=identity_scope)
        for key, value in sorted(mapping.items())
    ]


def _format_typed_flow_assignment(
    target: str,
    type_name: Any,
    value: Any,
    *,
    identity_scope: str | None = "signal.payload",
) -> _DotTypedField:
    source = _format_flow_source(value)
    if identity_scope and source == f"{identity_scope}.{target}":
        return _DotTypedField(target, type_name)
    if source.startswith("signal.payload."):
        source = source[len("signal.payload.") :]
    return _DotTypedField(target, type_name, source)


def _format_flow_assignment(target: str, value: Any, *, identity_scope: str | None = "signal.payload") -> str:
    source = _format_flow_source(value)
    if identity_scope and source == f"{identity_scope}.{target}":
        return target
    if source.startswith("signal.payload."):
        source = source[len("signal.payload.") :]
    return f"{target} {_DOT_ARROW_ASSIGN} {source}"


def _format_flow_source(value: Any) -> str:
    if isinstance(value, dict) and set(value) == {"from"}:
        return value["from"][1:] if isinstance(value["from"], str) and value["from"].startswith("$") else str(value["from"])
    if isinstance(value, dict) and set(value) == {"value"}:
        return _format_scalar(value["value"])
    if isinstance(value, str) and value.startswith("$"):
        return value[1:]
    return _format_scalar(value)


def _format_transition_sections(
    state_machine: dict[str, Any], transition: dict[str, Any], contract: dict[str, Any]
) -> list[tuple[str, list[object]]]:
    sections: list[tuple[str, list[object]]] = []
    if _is_data_refresh_signal(transition["on"]):
        bindings = _transition_data_bindings(state_machine, transition)
        application_action_ids = [binding["application_action"] for binding in bindings]
        data_sources = _format_application_action_outputs(application_action_ids, contract)
        guards = _format_action_authorization_policies(application_action_ids, contract)
        queries = [binding["data_loader"] for binding in bindings]
        inputs = _format_data_inputs(state_machine, bindings, contract)
        if inputs:
            sections.append(("input", inputs))
        if queries:
            sections.append(("data_loaders", queries))
        if data_sources:
            sections.append(("load", data_sources))
        if guards:
            sections.append(("authorization_policies", guards))
    else:
        target_bindings = _transition_target_data_bindings(state_machine, transition)
        application_action_ids = [binding["application_action"] for binding in target_bindings]
        data_sources = _format_application_action_outputs(application_action_ids, contract)
        guards = _format_action_authorization_policies(application_action_ids, contract)
        queries = [binding["data_loader"] for binding in target_bindings]
        required_context = _format_data_inputs(state_machine, target_bindings, contract)
        if required_context:
            sections.append(("input", required_context))
        if queries:
            sections.append(("data_loaders", queries))
        if data_sources:
            sections.append(("load", data_sources))
        if guards:
            sections.append(("authorization_policies", guards))
    sections.extend(_format_transition_effect_sections(state_machine, transition))
    return sections


def _transition_target_data_bindings(state_machine: dict[str, Any], transition: dict[str, Any]) -> list[dict[str, Any]]:
    target_state = state_machine.get("view_states", {}).get(transition["to"], {})
    return _data_loader_bindings(target_state.get("data_loaders", {}))


def _state_field_section_title(state_machine: dict[str, Any], state_name: str, state: dict[str, Any]) -> str:
    application_actions = [binding["application_action"] for binding in _state_field_data_bindings(state_machine, state_name, state) if binding.get("application_action")]
    unique = sorted(dict.fromkeys(application_actions))
    if len(unique) == 1:
        return f"{unique[0]} fields"
    if unique:
        return "data fields"
    if state_machine.get("entity_type"):
        return f"{state_machine['entity_type']} fields"
    return "state machine context fields"


def _state_field_data_bindings(state_machine: dict[str, Any], state_name: str, state: dict[str, Any]) -> list[dict[str, Any]]:
    bindings = _data_loader_bindings(state.get("data_loaders", {}))
    if bindings:
        return bindings
    incoming_data_bindings: list[dict[str, Any]] = []
    for transition in state_machine.get("transitions", []):
        if transition["to"] == state_name and _is_data_refresh_signal(transition["on"]):
            incoming_data_bindings.extend(_transition_data_bindings(state_machine, transition))
    if incoming_data_bindings:
        return _unique_data_bindings(incoming_data_bindings)
    return _data_loader_bindings(state_machine.get("data_loaders", {}))


def _format_state_fields(state_machine: dict[str, Any], state: dict[str, Any], contract: dict[str, Any]) -> list[_DotTypedField]:
    entity_type_fields = schema_properties(contract["entity_types"][state_machine["entity_type"]]["schema"]) if state_machine.get("entity_type") else {}
    context_fields = schema_properties(state_machine.get("context", {}))
    fields: list[_DotTypedField] = []
    for field in state["fields"]:
        if field in entity_type_fields:
            fields.append(_DotTypedField(field, effective_property_schema(entity_type_fields[field])))
        elif field in context_fields:
            fields.append(_DotTypedField(field, context_fields[field]))
    return fields


def _format_application_action_outputs(application_action_ids: Iterable[str], contract: dict[str, Any]) -> list[_DotTypedField]:
    application_actions = contract["application_actions"]
    fields: list[_DotTypedField] = []
    for application_action_id in application_action_ids:
        for _, outcome in sorted(application_actions[application_action_id]["outcomes"].items()):
            if outcome["kind"] == "success":
                fields.append(_DotTypedField(application_action_id, outcome["result"]))
    return fields


def _format_action_binding_outputs(invocations: dict[str, Any], contract: dict[str, Any]) -> list[_DotTypedField]:
    application_actions = contract["application_actions"]
    fields: list[_DotTypedField] = []
    for invocation_id, invocation in sorted(invocations.items()):
        application_action_id = invocation["application_action"]
        for _, outcome in sorted(application_actions[application_action_id]["outcomes"].items()):
            if outcome["kind"] == "success":
                fields.append(_DotTypedField(f"{invocation_id}: {application_action_id}", outcome["result"]))
    return fields


def _format_action_authorization_policies(application_action_ids: Iterable[str], contract: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    seen: set[str] = set()
    for application_action_id in application_action_ids:
        if application_action_id in seen:
            continue
        seen.add(application_action_id)
        application_action = contract["application_actions"].get(application_action_id)
        authorization_policy = (application_action.get("authorization") or {}).get("policy") if application_action else None
        if authorization_policy:
            lines.append(f"{application_action_id}: {authorization_policy}")
    return lines


def _format_data_inputs(
    state_machine: dict[str, Any], bindings: Iterable[dict[str, Any]], contract: dict[str, Any]
) -> list[_DotTypedField]:
    application_actions = contract["application_actions"]
    inputs: list[_DotTypedField] = []
    seen: set[str] = set()
    for binding in bindings:
        operation = application_actions[binding["application_action"]]
        for key, input_type in sorted(schema_properties(operation["input"]).items()):
            input_label = f"{binding.get('data_loader', binding['application_action'])}.{key}"
            signature = f"{input_label} {input_type}"
            if signature not in seen:
                inputs.append(_DotTypedField(input_label, input_type))
                seen.add(signature)
    return inputs


def _is_data_refresh_signal(signal: dict[str, str]) -> bool:
    return "data_refresh_signal" in signal


def _signal_label(signal: dict[str, str]) -> str:
    if "local_signal" in signal:
        return _local_signal_label(signal["local_signal"])
    if "data_refresh_signal" in signal:
        return f"data_refresh_signal.{signal['data_refresh_signal']}"
    return str(signal)


def _local_signal_label(local_signal: str) -> str:
    return f"local_signal.{local_signal}"


def _transition_data_bindings(state_machine: dict[str, Any], transition: dict[str, Any]) -> list[dict[str, Any]]:
    source_state = state_machine.get("view_states", {}).get(transition["from"], {})
    bindings = source_state.get("data_loaders", {}) or state_machine.get("data_loaders", {})
    return _data_loader_bindings(bindings)


def _data_loader_bindings(invocations: dict[str, Any]) -> list[dict[str, Any]]:
    return _unique_data_bindings(
        {"data_loader": invocation_id, "application_action": invocation["application_action"]}
        for invocation_id, invocation in sorted((invocations or {}).items())
    )


def _unique_data_bindings(bindings: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    seen: set[tuple[Any, Any]] = set()
    for binding in bindings:
        key = (binding.get("application_action"), binding.get("data_loader"))
        if key not in seen:
            unique.append(binding)
            seen.add(key)
    return unique


def _format_transition_effect_sections(state_machine: dict[str, Any], transition: dict[str, Any]) -> list[tuple[str, list[object]]]:
    sections: list[tuple[str, list[object]]] = []
    for effect in transition.get("effects", []):
        if "emit" in effect:
            emit = effect["emit"]
            sections.append(("emit", [_local_signal_label(emit["local_signal"])]))
            payload_types = schema_properties(state_machine["signals"]["emits"]["local_signals"][emit["local_signal"]]["payload_schema"])
            payload = _format_typed_data_flow(emit.get("payload_bindings", {}), payload_types)
            if payload:
                sections.append(("payload", payload))
        elif "set" in effect:
            assignment = effect["set"]
            target = assignment["context"]
            context = schema_properties(state_machine["context"])
            sections.append((
                "set",
                [_format_typed_flow_assignment(target, context[target], _assignment_value(assignment), identity_scope=None)],
            ))
    return sections


def _format_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def _dot_attrs(attrs: dict[str, object]) -> str:
    return " [" + ", ".join(f"{name}={_dot_attr_value(value)}" for name, value in attrs.items()) + "]"


def _dot_attr_value(value: object) -> str:
    if isinstance(value, _DotHtml):
        return f"<{value}>"
    return _dot_quote(value)


def _dot_html_text(value: object) -> str:
    return html.escape(str(value), quote=False)


def _dot_quote(value: object) -> str:
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def audit_html_document(
    contract: dict[str, Any],
    body: str,
    *,
    state_machine_surface_ids: Iterable[str] | None = None,
    composition_ids: Iterable[str] | None = None,
) -> str:
    css = state_machine_styles_projection(contract, surface_ids=state_machine_surface_ids, composition_ids=composition_ids)
    extra_css = """
    body { margin: 0; font-family: ui-sans-serif, system-ui, sans-serif; background: #f7f7f8; color: #171717; }
    main { padding: 24px; }
    .contract-state-machine-surface, .contract-state-machine-composition { background: white; border: 1px solid #d0d0d0; border-radius: 12px; padding: 16px; box-sizing: border-box; }
    .contract-state-machine-composition { display: grid; grid-template-columns: minmax(180px, 1fr) minmax(280px, 2fr) minmax(180px, 1fr); gap: 16px; max-width: none; }
    .contract-layout-region { min-height: 120px; display: grid; gap: 12px; align-content: start; }
    .audit-records { display: grid; gap: 0.75rem; }
    .audit-record { border: 1px solid #e4e4e7; border-radius: 10px; padding: 0.75rem; display: grid; gap: 0.35rem; }
    .audit-field { display: grid; gap: 0.15rem; }
    .audit-field-label { color: #52525b; font-size: 0.75rem; }
    .audit-field-value { font-weight: 600; }
    img.audit-asset { max-width: 100%; height: auto; border-radius: 8px; }
    button { padding: 0.5rem 0.75rem; border: 1px solid #222; border-radius: 6px; background: #fff; justify-self: start; }
    @media (max-width: 700px) { .contract-state-machine-composition { grid-template-columns: 1fr; } }
    """
    return "\n".join([
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        "<title>spec audit render</title>",
        "<style>", css, extra_css, "</style>",
        "</head>",
        "<body>",
        "<main>",
        body,
        "</main>",
        "</body>",
        "</html>",
    ])


def render_example_html(root: Path, contract: dict[str, Any], case_id: str, case: dict[str, Any]) -> str:
    state_machine = contract["state_machines"][case["state_machine"]]
    state = state_machine["view_states"][case["view_state"]]
    if state.get("child_state_machines"):
        return render_composed_example_html(root, contract, case)
    projection = state_machines_projection(contract)
    state_machine = next(item for item in projection["state_machines"] if item["owner_kind"] == "state_machine" and item["owner"] == case["state_machine"] and item["view_state"] == case["view_state"])
    return render_state_machine_audit_html(root, contract, state_machine, case)


def render_example_state_machines(contract: dict[str, Any], case: dict[str, Any]) -> list[dict[str, Any]]:
    projection = state_machines_projection(contract)
    state_machine = contract["state_machines"][case["state_machine"]]
    state = state_machine["view_states"][case["view_state"]]
    if state.get("child_state_machines"):
        state_machines = []
        for mount in state["child_state_machines"]:
            state_name = case["instances"][mount["id"]]["view_state"]
            state_machines.append(next(item for item in projection["state_machines"] if item["owner_kind"] == "state_machine" and item["owner"] == mount["state_machine"] and item["view_state"] == state_name))
        return state_machines
    return [next(item for item in projection["state_machines"] if item["owner_kind"] == "state_machine" and item["owner"] == case["state_machine"] and item["view_state"] == case["view_state"])]


def _render_example_composition_ids(contract: dict[str, Any], case: dict[str, Any]) -> set[str]:
    state = contract["state_machines"][case["state_machine"]]["view_states"][case["view_state"]]
    if state.get("child_state_machines"):
        return {f"{case['state_machine']}.{case['view_state']}"}
    return set()


def render_composed_example_html(root: Path, contract: dict[str, Any], case: dict[str, Any]) -> str:
    state_machine = contract["state_machines"][case["state_machine"]]
    state = state_machine["view_states"][case["view_state"]]
    projection = state_machines_projection(contract)
    composition = next(item for item in projection["compositions"] if item["state_machine"] == case["state_machine"] and item["view_state"] == case["view_state"])
    html_layout = renderer_html_layout(composition)
    root_spec = html_layout.get("root") or {"element": "section"}
    tag = root_spec.get("element", "section")
    classes = " ".join(["contract-state-machine-composition"] + root_spec.get("classes", []))
    attrs = {"class": classes, "data-contract-composition": composition["id"]}
    if root_spec.get("role") and root_spec["role"] != "none":
        attrs["role"] = root_spec["role"]
    parts = [f"<{tag}{format_attrs(attrs)}>"]
    for region_name, region in sorted(renderer_html_regions(state).items(), key=lambda item: item[1].get("order", 0)):
        region_tag = region.get("element", "div")
        region_classes = " ".join(["contract-layout-region", f"contract-layout-region--{region_name}"] + region.get("classes", []))
        region_attrs = {"class": region_classes, "data-layout-region": region_name, "data-must-render": str(region["must_render"]).lower()}
        if region.get("role") and region["role"] != "none":
            region_attrs["role"] = region["role"]
        parts.append(f"<{region_tag}{format_attrs(region_attrs)}>")
        for mount in [item for item in state["child_state_machines"] if item.get("html_region") == region_name]:
            state_name = case["instances"][mount["id"]]["view_state"]
            state_machine = next(item for item in projection["state_machines"] if item["owner_kind"] == "state_machine" and item["owner"] == mount["state_machine"] and item["view_state"] == state_name)
            parts.append(render_state_machine_audit_html(root, contract, state_machine, case))
        parts.append(f"</{region_tag}>")
    parts.append(f"</{tag}>")
    return "\n".join(parts)


def render_state_machine_audit_html(root: Path, contract: dict[str, Any], state_machine: dict[str, Any], case: dict[str, Any] | None) -> str:
    html_contract = renderer_html_presentation(state_machine)
    root_spec = html_contract.get("root") or {"element": "section"}
    tag = root_spec.get("element", "section")
    classes = " ".join(["contract-state-machine-surface"] + root_spec.get("classes", []))
    attrs = {
        "class": classes,
        "data-contract-state-machine-surface": state_machine["id"],
        "data-contract-view-state": state_machine["view_state"],
    }
    if root_spec.get("role") and root_spec["role"] != "none":
        attrs["role"] = root_spec["role"]
    lines = [f"<{tag}{format_attrs(attrs)}>"]
    slots = html_contract.get("slots") or default_html_slots(state_machine)
    field_slots = [slot for slot in slots if "field_slot" in slot["binding"]]
    for slot in slots:
        if "field_slot" in slot["binding"]:
            continue
        records = records_for_state_machine(contract, state_machine, case)
        record = records[0] if records else {}
        context = render_context(contract, case)
        namespace = render_namespace(contract, case)
        lines.extend(render_html_slot_runtime(root, contract, state_machine, slot, record, context, namespace))
    if field_slots:
        records = records_for_state_machine(contract, state_machine, case)
        lines.append('<div class="audit-records">')
        for record in records[:4] or [{}]:
            lines.append('<article class="audit-record">')
            for slot in field_slots:
                lines.extend(render_html_field_slot(record, slot))
            lines.append('</article>')
        lines.append('</div>')
    lines.append(f"</{tag}>")
    return "\n".join(lines)


def render_html_slot_runtime(root: Path, contract: dict[str, Any], state_machine: dict[str, Any], slot: dict[str, Any], record: dict[str, Any], context: dict[str, Any], namespace: dict[str, Any]) -> list[str]:
    kind, bind_value = next(iter(slot["binding"].items()))
    tag = slot["element"]
    classes = slot.get("classes", [])
    attrs: dict[str, str] = {"data-contract-slot": slot.get("id", bind_value)}
    if classes:
        attrs["class"] = " ".join(classes)
    if slot.get("role") and slot["role"] != "none":
        attrs["role"] = slot["role"]
    if kind == "text_slot":
        text_ref = slot_ref(state_machine, "text", bind_value)
        attrs["data-text"] = text_ref
        if slot.get("level"):
            attrs["aria-level"] = str(slot["level"])
        text = resolve_text_resource(root, contract, text_ref, record, context, namespace)
        return [f"<{tag}{format_attrs(attrs)}>{html.escape(text)}</{tag}>"]
    if kind == "asset_slot":
        asset_ref = slot_ref(state_machine, "asset", bind_value)
        attrs["data-asset"] = asset_ref
        asset_result = resolve_asset_result(root, contract, asset_ref, record, context, namespace)
        label = asset_result.alt or contract["assets"][asset_ref]["placeholder"]["label"]
        if tag == "img":
            attrs.setdefault("alt", label)
            svg = asset_result.body
            attrs.setdefault("src", "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii"))
            attrs.setdefault("class", (attrs.get("class", "") + " audit-asset").strip())
            return [f"<img{format_attrs(attrs)}>"]
        return [f"<{tag}{format_attrs(attrs)} aria-label={html.escape(label, quote=True)!r}></{tag}>"]
    if kind == "literal":
        return [f"<{tag}{format_attrs(attrs)}>{html.escape(str(bind_value))}</{tag}>"]
    action_binding = bind_value
    attrs["data-action-binding"] = action_binding
    if tag == "a":
        attrs.setdefault("href", "#")
    if tag == "button":
        attrs.setdefault("type", "button")
    return [f"<{tag}{format_attrs(attrs)}>{html.escape(humanize(action_binding))}</{tag}>"]


def render_html_field_slot(record: dict[str, Any], slot: dict[str, Any]) -> list[str]:
    tag = slot["element"]
    field = slot["binding"]["field_slot"]
    attrs: dict[str, str] = {"class": "audit-field", "data-contract-slot": field, "data-field": field}
    if slot.get("classes"):
        attrs["class"] += " " + " ".join(slot["classes"])
    if slot.get("role") and slot["role"] != "none":
        attrs["role"] = slot["role"]
    label = slot.get("label") or humanize(field)
    value = record.get(field, "—")
    return [
        f"<{tag}{format_attrs(attrs)}>",
        f'<span class="audit-field-label">{html.escape(label)}</span>',
        f'<span class="audit-field-value">{html.escape(str(value))}</span>',
        f"</{tag}>",
    ]


def slot_ref(state_machine: dict[str, Any], kind: str, slot: str) -> str:
    key = "text" if kind == "text" else "assets"
    for ref in state_machine["slots"][key]:
        if ref.rsplit(".", 1)[-1] == slot:
            return ref
    raise KeyError(f"{state_machine['id']} has no {kind} slot {slot}")


def textual_audit_lines(root: Path, contract: dict[str, Any], case_id: str, case: dict[str, Any]) -> list[tuple[str, str]]:
    projection = state_machines_projection(contract)
    state_machine = contract["state_machines"][case["state_machine"]]
    state = state_machine["view_states"][case["view_state"]]
    lines: list[tuple[str, str]] = []
    if state.get("child_state_machines"):
        for mount in state["child_state_machines"]:
            state_name = case["instances"][mount["id"]]["view_state"]
            state_machine = next(item for item in projection["state_machines"] if item["owner_kind"] == "state_machine" and item["owner"] == mount["state_machine"] and item["view_state"] == state_name)
            lines.extend(state_machine_textual_lines(root, contract, state_machine, case))
    else:
        state_machine = next(item for item in projection["state_machines"] if item["owner_kind"] == "state_machine" and item["owner"] == case["state_machine"] and item["view_state"] == case["view_state"])
        lines.extend(state_machine_textual_lines(root, contract, state_machine, case))
    return lines or [("static", " ")]


def state_machine_textual_lines(root: Path, contract: dict[str, Any], state_machine: dict[str, Any], case: dict[str, Any] | None) -> list[tuple[str, str]]:
    lines: list[tuple[str, str]] = []
    textual = renderer_textual_presentation(state_machine)
    widgets = textual.get("widgets") or []
    if widgets:
        records = records_for_state_machine(contract, state_machine, case)
        record = records[0] if records else {}
        context = render_context(contract, case)
        namespace = render_namespace(contract, case)
        for widget in widgets:
            bind_kind, bind_value = next(iter(widget["binding"].items()))
            if bind_kind == "text_slot":
                ref = slot_ref(state_machine, "text", bind_value)
                lines.append(("static", resolve_text_resource(root, contract, ref, record, context, namespace)))
            elif bind_kind == "asset_slot":
                ref = slot_ref(state_machine, "asset", bind_value)
                lines.append(("static", resolve_asset_result(root, contract, ref, record, context, namespace).alt or contract["assets"][ref]["placeholder"]["label"]))
            elif bind_kind == "field_slot":
                lines.append(("static", str(record.get(bind_value, "—"))))
            elif bind_kind == "action_binding":
                lines.append(("button", humanize(bind_value)))
            elif bind_kind == "literal":
                lines.append(("static", str(bind_value)))
        return lines
    records = records_for_state_machine(contract, state_machine, case)
    record = records[0] if records else {}
    context = render_context(contract, case)
    namespace = render_namespace(contract, case)
    for text_ref in state_machine["slots"]["text"]:
        lines.append(("static", resolve_text_resource(root, contract, text_ref, record, context, namespace)))
    for asset_ref in state_machine["slots"]["assets"]:
        lines.append(("static", resolve_asset_result(root, contract, asset_ref, record, context, namespace).alt or contract["assets"][asset_ref]["placeholder"]["label"]))
    fields = state_machine["slots"].get("fields", [])
    if fields:
        for record in (records_for_state_machine(contract, state_machine, case)[:4] or [{}]):
            for field in fields:
                lines.append(("static", f"{humanize(field)}: {record.get(field, '—')}"))
    for invocation_id in state_machine["slots"]["action_bindings"]:
        lines.append(("button", humanize(invocation_id)))
    return lines or [("static", " ")]


def records_for_state_machine(contract: dict[str, Any], state_machine: dict[str, Any], case: dict[str, Any] | None) -> list[dict[str, Any]]:
    entity_type_id = state_machine_model(contract, state_machine)
    model_key = f"{entity_type_id.lower()}_id"
    owner_context = state_machine_owner_context(contract, state_machine)
    fixtures = case.get("seed_fixtures", []) if case else sorted(contract.get("fixtures", {}))
    records: list[dict[str, Any]] = []
    if case:
        namespace = fixture_namespace(contract, fixtures)
        records.extend(_find_model_records(namespace, entity_type_id))
        records = _apply_precondition_uses(contract, case.get("precondition_refs", []), namespace, entity_type_id, records)
        context = _resolved_render_example_context(contract, case, namespace)
    else:
        context = {}
        for fixture_id in fixtures:
            records.extend(_find_model_records(contract["fixtures"][fixture_id]["values"], entity_type_id))
        records = _apply_facts_with_available_fixtures(contract, entity_type_id, records)
    selected_id = context.get(model_key)
    if not selected_id and model_key in owner_context:
        selected_id = context.get(f"selected_{model_key}")
    if selected_id and model_key in owner_context:
        selected = [record for record in records if record.get("id") == selected_id]
        if selected:
            return selected
    if model_key in owner_context and records:
        return records[:1]
    return records


def state_machine_model(contract: dict[str, Any], state_machine: dict[str, Any]) -> str:
    return contract["state_machines"][state_machine["owner"]]["entity_type"]


def state_machine_owner_context(contract: dict[str, Any], state_machine: dict[str, Any]) -> dict[str, Any]:
    return schema_properties(contract["state_machines"][state_machine["owner"]].get("context", {}))


def _resolved_render_example_context(contract: dict[str, Any], case: dict[str, Any], namespace: dict[str, Any]) -> dict[str, Any]:
    context = {}
    for key, value in (case.get("context") or {}).items():
        context[key] = resolve(value, namespace)
    return context


def _find_model_records(value: Any, entity_type_id: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if value.get("entity_type") == entity_type_id:
            record = dict(value)
            record.pop("entity_type", None)
            records.append(record)
        for child in value.values():
            records.extend(_find_model_records(child, entity_type_id))
    elif isinstance(value, list):
        for item in value:
            records.extend(_find_model_records(item, entity_type_id))
    return records


def _apply_facts_with_available_fixtures(contract: dict[str, Any], entity_type_id: str, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    current = list(records)
    namespaces = [{}]
    for fixture_id in sorted(contract.get("fixtures", {})):
        try:
            namespaces.append(fixture_namespace(contract, [fixture_id]))
        except (AssertionError, KeyError, TypeError):
            continue
    for precondition_id in sorted(contract.get("preconditions", {})):
        precondition_uses = [{"ref": precondition_id}]
        for namespace in namespaces:
            try:
                next_records = _apply_precondition_uses(contract, precondition_uses, namespace, entity_type_id, current)
            except (AssertionError, KeyError, TypeError):
                continue
            current = _dedupe_records(next_records)
            break
    return current


def _apply_precondition_uses(contract: dict[str, Any], precondition_uses: list[dict[str, str]], namespace: dict[str, Any], entity_type_id: str, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    current = list(records)
    for precondition_use in precondition_uses:
        precondition_id = precondition_use["ref"]
        kind, body = _precondition_selector(contract["preconditions"][precondition_id], precondition_id)
        if body["entity_type"] != entity_type_id:
            continue
        if kind == "present":
            current.append(resolve(body["values"], namespace))
        elif kind == "absent":
            where = resolve(body["where"], namespace)
            current = [record for record in current if not _record_matches(record, where)]
    return _dedupe_records(current)


def _precondition_selector(precondition: dict[str, Any], precondition_id: str) -> tuple[str, dict[str, Any]]:
    items = [(key, precondition[key]) for key in ("absent", "present") if key in precondition]
    if len(items) != 1:
        raise ContractError(f"Precondition {precondition_id} must contain exactly one precondition selector")
    return items[0]


def _record_matches(record: dict[str, Any], where: dict[str, Any]) -> bool:
    return all(record.get(key) == value for key, value in where.items())


def _dedupe_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in records:
        key = json.dumps(record, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(record)
    return deduped


def render_namespace(contract: dict[str, Any], case: dict[str, Any] | None) -> dict[str, Any]:
    if case:
        return fixture_namespace(contract, case.get("seed_fixtures", []))
    return {}


def render_context(contract: dict[str, Any], case: dict[str, Any] | None) -> dict[str, Any]:
    if not case:
        return {}
    namespace = render_namespace(contract, case)
    return _resolved_render_example_context(contract, case, namespace)


def content_args(contract: dict[str, Any], ref: str, item: dict[str, Any], record: dict[str, Any], context: dict[str, Any], namespace: dict[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for name in item.get("args", {}):
        if name in record:
            values[name] = record[name]
        elif name in context:
            values[name] = context[name]
        elif name in namespace:
            values[name] = namespace[name]
        else:
            raise ContractError(f"Cannot bind content arg {ref}.{name} from record, render context, or fixtures")
    return values


def resolve_text_resource(root: Path, contract: dict[str, Any], ref: str, record: dict[str, Any], context: dict[str, Any], namespace: dict[str, Any]) -> str:
    item = contract["text_resources"][ref]
    source_ref = item.get("source_ref")
    if not source_ref:
        text = item["placeholder"]
    else:
        try:
            text = call_text(root, ref, content_args(contract, ref, item, record, context, namespace), ContentContext(surface="audit"))
        except ContentError as exc:
            raise ContractError(str(exc)) from exc
    max_chars = item.get("max_chars")
    if max_chars is not None and len(text) > max_chars:
        raise ContractError(f"Text source {ref} exceeds max_chars")
    if not text.strip():
        raise ContractError(f"Text source {ref} returned empty text")
    return text


def resolve_asset_result(root: Path, contract: dict[str, Any], ref: str, record: dict[str, Any], context: dict[str, Any], namespace: dict[str, Any]) -> AssetResult:
    item = contract["assets"][ref]
    source_ref = item.get("source_ref")
    if not source_ref:
        return AssetResult(mime_type="image/svg+xml", body=asset_placeholder_svg(item), alt=item["placeholder"]["label"])
    try:
        result = call_asset(root, ref, content_args(contract, ref, item, record, context, namespace), ContentContext(surface="audit"))
    except ContentError as exc:
        raise ContractError(str(exc)) from exc
    if result.mime_type != "image/svg+xml":
        raise ContractError(f"Asset source {ref} must return image/svg+xml")
    if not result.body.lstrip().startswith("<svg") or "</svg>" not in result.body:
        raise ContractError(f"Asset source {ref} did not return SVG")
    return result


def asset_placeholder_svg(asset: dict[str, Any]) -> str:
    placeholder = asset["placeholder"]
    label = placeholder["label"]
    ratio = placeholder.get("aspect_ratio", "4:3")
    w_raw, h_raw = ratio.split(":")
    width = 320
    height = max(120, int(width * int(h_raw) / int(w_raw)))
    cx, cy = width / 2, height / 2
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(label, quote=True)}">
  <title>{html.escape(label)}</title>
  <defs>
    <linearGradient id="g" x1="0" x2="1" y1="0" y2="1">
      <stop offset="0" stop-color="#fafafa"/>
      <stop offset="1" stop-color="#e4e4e7"/>
    </linearGradient>
  </defs>
  <rect width="100%" height="100%" rx="18" fill="url(#g)" stroke="#a1a1aa" stroke-width="2"/>
  <circle cx="{cx-54:.0f}" cy="{cy-18:.0f}" r="38" fill="#d4d4d8"/>
  <rect x="{cx-18:.0f}" y="{cy-58:.0f}" width="92" height="92" rx="16" fill="#f4f4f5" stroke="#a1a1aa" stroke-width="2"/>
  <path d="M{cx-72:.0f} {cy+54:.0f} C{cx-28:.0f} {cy+6:.0f}, {cx+32:.0f} {cy+88:.0f}, {cx+92:.0f} {cy+18:.0f}" fill="none" stroke="#71717a" stroke-width="8" stroke-linecap="round"/>
</svg>
'''


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) not in {2, 3}:
        print("usage: pyspec audit <root> <tools_root> [previous_audit_root]", file=sys.stderr)
        return 2
    root = Path(argv[0]).resolve()
    tools_root = Path(argv[1]).resolve()
    previous_audit_root = Path(argv[2]).resolve() if len(argv) == 3 else None
    from .io import read_yaml
    from .paths import COMPILED_SPEC_PATH
    contract = read_yaml(root / COMPILED_SPEC_PATH)
    try:
        _render_visual_audit(root, contract, tools_root, previous_audit_root=previous_audit_root)
    except (ContractError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    # Playwright/Textual can leave cleanup state that blocks interpreter shutdown in
    # constrained containers. This worker has completed all file outputs; exit
    # immediately so the compiler process stays deterministic.
    os._exit(0)


if __name__ == "__main__":
    raise SystemExit(main())
