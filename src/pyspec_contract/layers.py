from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any

from .io import read_json

ROOT = Path(__file__).resolve().parent

LAYERS = {"core", "http", "events", "workflow", "ui", "textual", "web"}
LAYER_ALIASES = {"full": "full", "all": "full", "api": "http", "cli": "workflow", "tui": "textual"}

# Coarse target gates. Field-level surface gates below remain stricter.
TARGET_LAYERS: dict[str, set[str]] = {
    "fixture": {"core"},
    "fact": {"core"},
    "resource": {"core"},
    "capability": {"core"},
    "scenario": {"core"},
    "workflow": {"workflow"},
    "panel": {"ui"},
    "view": {"ui"},
    "copy": {"ui"},
    "asset": {"ui"},
    "content_case": {"ui"},
    "audit_profile": {"ui"},
    "render_case": {"ui"},
    # entry is surface-specific and handled separately.
    "entry": set(),
}

ENTRY_SURFACE_LAYER = {
    "api": "http",
    "web": "web",
    "textual": "textual",
    "cli": "workflow",
    "worker": "workflow",
    "schedule": "workflow",
    "webhook": "events",
}

AUTHOR_SECTIONS: dict[str, str] = {
    "copies": "copy",
    "assets": "asset",
    "content_cases": "content_case",
    "audit_profiles": "audit_profile",
    "render_cases": "render_case",
    "fixtures": "fixture",
    "facts": "fact",
    "resources": "resource",
    "capabilities": "capability",
    "panels": "panel",
    "views": "view",
    "entries": "entry",
    "workflows": "workflow",
    "scenarios": "scenario",
}


RENDER_SURFACE_LAYER = {"html": "web", "textual": "textual"}
AUDIT_PROFILE_LAYER = {"html": "web", "textual": "textual"}

COMMON_LAYER_SETS: dict[str, set[str]] = {
    "core": {"core"},
    "core_http": {"core", "http"},
    "core_events": {"core", "events"},
    "core_workflow": {"core", "workflow"},
    "core_ui_textual": {"core", "ui", "textual"},
    "core_ui_web": {"core", "ui", "web"},
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
    if "web" in result or "textual" in result:
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
            if target != "entry":
                required = TARGET_LAYERS[target]
                if required and not required.issubset(layers):
                    raise LayerError(_blocked(label, target, required, layers))
            spec = copy.deepcopy(item)
            spec.pop("basis", None)
            _validate_author_spec_layers(label, target, spec, layers)


def _validate_author_spec_layers(label: str, target: str, spec: dict[str, Any], layers: set[str]) -> None:
    if target == "resource":
        return

    if target == "entry":
        surface = spec.get("surface")
        required_layer = ENTRY_SURFACE_LAYER.get(surface)
        if not required_layer:
            raise LayerError(f"{label} uses unsupported entry surface {surface!r}")
        _require_layers(label, f"entry surface {surface}", {required_layer}, layers)
        if surface in {"web", "textual"}:
            _require_layers(label, f"entry surface {surface}", {"ui"}, layers)
        return

    if target == "audit_profile":
        active_profiles = set(spec) & set(AUDIT_PROFILE_LAYER)
        if not active_profiles:
            raise LayerError(f"{label} audit_profile must declare at least one surface profile")
        for surface in active_profiles:
            _require_layers(label, f"audit_profile.{surface}", {AUDIT_PROFILE_LAYER[surface]}, layers)
        return

    if target == "render_case":
        for surface in spec.get("surfaces", []):
            required_layer = RENDER_SURFACE_LAYER.get(surface)
            if not required_layer:
                raise LayerError(f"{label} uses unsupported render surface {surface!r}")
            _require_layers(label, f"render_case surface {surface}", {required_layer}, layers)
        return

    if target == "panel":
        for state_name, state in spec.get("states", {}).items():
            _validate_presentation_layers(f"{label} state {state_name}", state.get("presentation", {}), layers)
        return

    if target == "view":
        layout = spec.get("layout") or {}
        if "html" in layout:
            _require_layers(label, "view layout html", {"web"}, layers)
        if "textual" in layout:
            _require_layers(label, "view layout textual", {"textual"}, layers)
        for state_name, state in spec.get("states", {}).items():
            _validate_presentation_layers(f"{label} state {state_name}", state.get("presentation", {}), layers)
        return


def _validate_presentation_layers(label: str, presentation: dict[str, Any], layers: set[str]) -> None:
    if not presentation:
        return
    if "html" in presentation or "css" in presentation:
        _require_layers(label, "HTML/CSS presentation", {"web"}, layers)
    if "textual" in presentation:
        _require_layers(label, "Textual presentation", {"textual"}, layers)


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
    allowed = {target for target, required in TARGET_LAYERS.items() if target != "entry" and required.issubset(layers)}
    if any(layer in layers for layer in ENTRY_SURFACE_LAYER.values()):
        allowed.add("entry")
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
    base = root or ROOT
    out = base / "schemas" / "layers"
    out.mkdir(parents=True, exist_ok=True)
    for name, layers in COMMON_LAYER_SETS.items():
        author_schema = author_schema_for_layers(layers)
        (out / f"{name}.author.schema.json").write_text(json.dumps(author_schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Print or write layer-pruned authored-spec schemas.")
    parser.add_argument("layers", nargs="?", default="full", help="Comma-separated layers, e.g. core,http or core,ui,textual")
    parser.add_argument("--write-common", action="store_true", help="Write the common schemas under schemas/layers/")
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
