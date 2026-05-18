from __future__ import annotations

import copy
from typing import Any, Mapping

from .binding_refs import BindingExpressionError, is_binding_expression, parse_binding_expression, resolve_binding_expression


class FixtureError(AssertionError):
    pass


def fixture_namespace(contract: Mapping[str, Any], fixture_ids: list[str]) -> dict[str, Any]:
    namespace: dict[str, Any] = {}
    for fixture_id in fixture_ids:
        try:
            values = contract["fixtures"][fixture_id]["values"]
        except KeyError as exc:
            raise FixtureError(f"Unknown fixture: {fixture_id}") from exc
        _deep_merge(namespace, copy.deepcopy(values), fixture_id)
    return namespace


def resolve_map(values: Mapping[str, Any], fixtures: Mapping[str, Any]) -> dict[str, Any]:
    return {key: resolve(value, fixtures) for key, value in values.items()}


def resolve_binding(binding: Any, namespace: Mapping[str, Any]) -> Any:
    if isinstance(binding, Mapping):
        if "from" in binding:
            try:
                return resolve_binding_expression(binding["from"], namespace)
            except BindingExpressionError as exc:
                raise FixtureError(str(exc)) from exc
        if "value" in binding:
            return binding["value"]
    return resolve(binding, namespace.get("fixture", namespace))


def resolve_bindings(bindings: Mapping[str, Any], namespace: Mapping[str, Any]) -> dict[str, Any]:
    return {key: resolve_binding(value, namespace) for key, value in bindings.items()}


def resolve(value: Any, fixtures: Mapping[str, Any]) -> Any:
    if isinstance(value, Mapping) and set(value) == {"from"}:
        try:
            ref = parse_binding_expression(value["from"])
            if ref.root != "fixture":
                raise FixtureError(f"Unsupported fixture binding expression root: ${ref.root}")
            return resolve_binding_expression(value["from"], {"fixture": fixtures})
        except BindingExpressionError as exc:
            raise FixtureError(str(exc)) from exc
    if isinstance(value, Mapping) and set(value) == {"value"}:
        return value["value"]
    if is_binding_expression(value):
        raise FixtureError(f"Raw binding expression strings are not allowed in authored value maps: {value}")
    if isinstance(value, list):
        return [resolve(item, fixtures) for item in value]
    if isinstance(value, dict):
        return {key: resolve(item, fixtures) for key, item in value.items()}
    return value


def _deep_merge(target: dict[str, Any], source: dict[str, Any], label: str) -> None:
    for key, value in source.items():
        if key not in target:
            target[key] = value
            continue
        existing = target[key]
        if isinstance(existing, dict) and isinstance(value, dict):
            _deep_merge(existing, value, label)
        elif existing != value:
            raise FixtureError(f"Conflicting fixture value at {key} while applying {label}")
