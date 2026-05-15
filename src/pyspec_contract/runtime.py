from __future__ import annotations

import copy
from typing import Any, Mapping

from .runtime_refs import ReferenceExpressionError, is_reference_expression, parse_reference_expression, resolve_reference_expression


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


def resolve(value: Any, fixtures: Mapping[str, Any]) -> Any:
    if is_reference_expression(value):
        try:
            ref = parse_reference_expression(value)
            if ref.root != "fixture":
                raise FixtureError(f"Unsupported fixture runtime reference root: ${ref.root}")
            return resolve_reference_expression(value, {"fixture": fixtures})
        except ReferenceExpressionError as exc:
            raise FixtureError(str(exc)) from exc
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
