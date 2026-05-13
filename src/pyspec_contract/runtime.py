from __future__ import annotations

import copy
from typing import Any, Mapping


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
    if isinstance(value, str) and value.startswith("$fixture."):
        current: Any = fixtures
        for part in value[len("$fixture."):].split("."):
            if not isinstance(current, Mapping) or part not in current:
                raise FixtureError(f"Unresolved fixture reference: {value}")
            current = current[part]
        return current
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
