from __future__ import annotations

from typing import Any


def renderers(item: dict[str, Any]) -> dict[str, Any]:
    return item.get("renderers") or {}


def renderer_web(item: dict[str, Any]) -> dict[str, Any]:
    return renderers(item).get("web") or {}


def renderer_textual(item: dict[str, Any]) -> dict[str, Any]:
    return renderers(item).get("textual") or {}


def renderer_web_layout(item: dict[str, Any]) -> dict[str, Any]:
    return renderer_web(item).get("layout") or {}


def renderer_textual_layout(item: dict[str, Any]) -> dict[str, Any]:
    return renderer_textual(item).get("layout") or {}


def renderer_web_presentation(item: dict[str, Any]) -> dict[str, Any]:
    return renderer_web(item).get("presentation") or {}


def renderer_textual_presentation(item: dict[str, Any]) -> dict[str, Any]:
    return renderer_textual(item).get("presentation") or {}


def renderer_web_style(item: dict[str, Any]) -> dict[str, Any]:
    return renderer_web(item).get("style") or {}


def renderer_textual_style(item: dict[str, Any]) -> dict[str, Any]:
    return renderer_textual(item).get("style") or {}


def renderer_web_regions(item: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return renderer_web_layout(item).get("regions") or {}


def renderer_textual_containers(item: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return renderer_textual_layout(item).get("containers") or {}


def renderer_regions(item: dict[str, Any]) -> dict[str, dict[str, Any]]:
    regions: dict[str, dict[str, Any]] = {}
    for name, region in renderer_web_regions(item).items():
        regions[name] = dict(region)
    for name, container in renderer_textual_containers(item).items():
        region_item = regions.setdefault(name, {})
        for key in ("order", "must_render"):
            if key in container and key not in region_item:
                region_item[key] = container[key]
    return regions
