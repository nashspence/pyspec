from __future__ import annotations

from typing import Any


def layout_html(layout: dict[str, Any]) -> dict[str, Any]:
    return layout.get("html") or {}


def layout_textual(layout: dict[str, Any]) -> dict[str, Any]:
    return layout.get("textual") or {}


def layout_html_regions(layout: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return layout_html(layout).get("regions") or {}


def layout_textual_containers(layout: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return layout_textual(layout).get("containers") or {}


def layout_regions(layout: dict[str, Any]) -> dict[str, dict[str, Any]]:
    regions: dict[str, dict[str, Any]] = {}
    for name, region in layout_html_regions(layout).items():
        regions[name] = dict(region)
    for name, container in layout_textual_containers(layout).items():
        item = regions.setdefault(name, {})
        for key in ("order", "required"):
            if key in container and key not in item:
                item[key] = container[key]
    return regions

