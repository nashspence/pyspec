from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any

from .io import read_json
from .targets import entry_state_machine_renderer, entry_point_adapter_pair, entry_point_target_pair

ROOT = Path(__file__).resolve().parent

LAYERS = {"core", "http", "domain_events", "workflow", "ui", "textual", "html"}
LAYER_ALIASES = {"full": "full", "all": "full", "api": "http", "cli": "workflow", "tui": "textual"}

# Coarse target gates. Field-level surface gates below remain stricter.
TARGET_LAYERS: dict[str, set[str]] = {
    "fixture": {"core"},
    "precondition": {"core"},
    "assertion": {"core"},
    "entity_type": {"core"},
    "authorization_policy": {"core"},
    "command": {"core"},
    "query": {"core"},
    "application_action": {"core"},
    "domain_event": {"core"},
    "behavior_scenario": {"core"},
    "workflow": {"workflow"},
    "state_machine": {"ui"},
    "text_resource": {"ui"},
    "asset": {"ui"},
    "content_example": {"ui"},
    "render_profile": {"ui"},
    "schema": {"core"},
    # entry_point is adapter-specific and handled separately.
    "entry_point": set(),
}

ENTRY_ADAPTER_LAYER = {
    "http_api": "http",
    "html_route": "ui",
    "cli": "workflow",
    "worker": "workflow",
    "scheduled": "workflow",
    "webhook": "domain_events",
}

AUTHOR_SECTIONS: dict[str, str] = {
    "text_resources": "text_resource",
    "assets": "asset",
    "content_examples": "content_example",
    "render_profiles": "render_profile",
    "fixtures": "fixture",
    "preconditions": "precondition",
    "assertions": "assertion",
    "entity_types": "entity_type",
    "authorization_policies": "authorization_policy",
    "commands": "command",
    "queries": "query",
    "application_actions": "application_action",
    "domain_events": "domain_event",
    "schemas": "schema",
    "state_machines": "state_machine",
    "entry_points": "entry_point",
    "workflows": "workflow",
    "behavior_scenarios": "behavior_scenario",
}


RENDER_SURFACE_LAYER = {"html": "html", "textual": "textual"}
RENDER_PROFILE_LAYER = {"html_viewports": "html", "textual_viewports": "textual"}

COMMON_LAYER_SETS: dict[str, set[str]] = {
    "core": {"core"},
    "core_http": {"core", "http"},
    "core_domain_events": {"core", "domain_events"},
    "core_workflow": {"core", "workflow"},
    "core_ui_textual": {"core", "ui", "textual"},
    "core_ui_html": {"core", "ui", "html"},
    "full": set(LAYERS),
}


def parse_layers(value: str | None) -> set[str] | None:
    """Parse a layer list. None means unrestricted mode."""
    if not value:
        return None
    raw = [part.strip() for part in value.split(",") if part.strip()]
    if not raw:
        return None
    expanded: set[str] = set()
    for item in raw:
        item = LAYER_ALIASES.get(item, item)
        if item == "full":
            return set(LAYERS)
        if item not in LAYERS:
            raise ValueError(f"Unknown authoring layer: {item}. Known layers: {', '.join(sorted(LAYERS | {'full'}))}")
        expanded.add(item)
    return normalize_layers(expanded)


def normalize_layers(layers: set[str] | None) -> set[str] | None:
    if layers is None:
        return None
    unknown = set(layers) - LAYERS
    if unknown:
        raise ValueError(f"Unknown authoring layers: {', '.join(sorted(unknown))}")
    result = set(layers)
    result.add("core")
    if "html" in result or "textual" in result:
        result.add("ui")
    return result


def layer_label(layers: set[str] | None) -> str:
    if layers is None or layers == LAYERS:
        return "full"
    return ",".join(sorted(layers))


def validate_author_layers(author: dict[str, Any], layers: set[str] | None) -> None:
    """Reject authored contract sections or surface details outside active layers."""
    if layers is None:
        return
    layers = normalize_layers(layers) or set(LAYERS)
    for section_name, target in AUTHOR_SECTIONS.items():
        for item_id, item in (author.get(section_name) or {}).items():
            label = f"authored {section_name}.{item_id}"
            if target not in TARGET_LAYERS:
                raise LayerError(f"{label} uses unsupported target {target!r}")
            if target != "entry_point":
                required = TARGET_LAYERS[target]
                if required and not required.issubset(layers):
                    raise LayerError(_blocked(label, target, required, layers))
            spec = copy.deepcopy(item)
            spec.pop("rationale", None)
            _validate_author_spec_layers(label, target, spec, layers)


def _validate_author_spec_layers(label: str, target: str, spec: dict[str, Any], layers: set[str]) -> None:
    if target == "entity_type":
        return

    if target == "entry_point":
        try:
            adapter_kind, _ = entry_point_adapter_pair(spec)
        except KeyError as exc:
            raise LayerError(f"{label} uses unsupported entry point adapter") from exc
        required_layer = ENTRY_ADAPTER_LAYER.get(adapter_kind)
        if not required_layer:
            raise LayerError(f"{label} uses unsupported entry point adapter {adapter_kind!r}")
        _require_layers(label, f"entry point adapter {adapter_kind}", {required_layer}, layers)
        try:
            target_kind, _ = entry_point_target_pair(spec)
        except KeyError as exc:
            raise LayerError(f"{label} uses unsupported entry point target") from exc
        if target_kind == "state_machine":
            renderer = entry_state_machine_renderer(spec)
            required_render_layer = RENDER_SURFACE_LAYER.get(renderer or "")
            if not required_render_layer:
                raise LayerError(f"{label} uses unsupported state_machine target renderer {renderer!r}")
            _require_layers(label, f"state machine target renderer {renderer}", {"ui", required_render_layer}, layers)
        return

    if target == "render_profile":
        active_profiles = set(spec) & set(RENDER_PROFILE_LAYER)
        if not active_profiles:
            raise LayerError(f"{label} render_profile must declare at least one viewport profile")
        for field in active_profiles:
            _require_layers(label, f"render_profile.{field}", {RENDER_PROFILE_LAYER[field]}, layers)
        return

    if target == "state_machine":
        for state_name, state in spec.get("view_states", {}).items():
            renderers = state.get("renderers") or {}
            if "html" in renderers:
                _require_layers(label, "state machine view_state renderer html", {"html"}, layers)
            if "textual" in renderers:
                _require_layers(label, "state machine view_state renderer textual", {"textual"}, layers)
        return


def _require_layers(label: str, concept: str, required: set[str], layers: set[str]) -> None:
    if not required.issubset(layers):
        raise LayerError(_blocked(label, concept, required, layers))


def _blocked(label: str, concept: str, required: set[str], layers: set[str]) -> str:
    return (
        f"{label} is outside active authoring layers: {concept} requires "
        f"{', '.join(sorted(required))}; active layers are {', '.join(sorted(layers))}"
    )


class LayerError(ValueError):
    pass


def _allowed_targets(layers: set[str]) -> set[str]:
    allowed = {target for target, required in TARGET_LAYERS.items() if target != "entry_point" and required.issubset(layers)}
    if any(layer in layers for layer in ENTRY_ADAPTER_LAYER.values()):
        allowed.add("entry_point")
    return allowed


def author_schema_for_layers(layers: set[str] | None) -> dict[str, Any]:
    """Return a derived authored-spec schema pruned by layer."""
    full = read_json(ROOT / "schemas" / "author.schema.json")
    if layers is None:
        return full
    layers = normalize_layers(layers)
    schema = copy.deepcopy(full)
    allowed_targets = _allowed_targets(layers or set(LAYERS))
    allowed_sections = {section for section, target in AUTHOR_SECTIONS.items() if target in allowed_targets}
    schema["properties"] = {
        key: value
        for key, value in schema["properties"].items()
        if key == "project" or key in allowed_sections
    }
    schema["title"] = f"Authored product spec schema ({layer_label(layers)} layers)"
    schema["description"] = "Layer-pruned direct authoring schema; runtime layer validation also applies."
    return schema


def write_common_layer_schemas(root: Path | None = None) -> None:
    """Write derived common layer schemas for local editor/tool integration.

    These files are generated artifacts, not checked-in source of truth.
    """
    base = root or ROOT
    out = base / "schemas" / "layers"
    out.mkdir(parents=True, exist_ok=True)
    for name, layers in COMMON_LAYER_SETS.items():
        author_schema = author_schema_for_layers(layers)
        (out / f"{name}.author.schema.json").write_text(json.dumps(author_schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Print or locally write generated layer-pruned authored-spec schemas.")
    parser.add_argument("layers", nargs="?", default="full", help="Comma-separated layers, e.g. core,http or core,ui,textual")
    parser.add_argument(
        "--write-common",
        action="store_true",
        help="Write generated common schemas under ignored schemas/layers/ for local tooling.",
    )
    args = parser.parse_args(argv)
    try:
        if args.write_common:
            write_common_layer_schemas(ROOT)
        else:
            layers = parse_layers(args.layers)
            print(json.dumps(author_schema_for_layers(layers), indent=2, sort_keys=True))
    except (LayerError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
