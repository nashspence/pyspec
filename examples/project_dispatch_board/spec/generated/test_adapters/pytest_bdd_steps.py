from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from pytest_bdd import given, parsers, then, when

from pyspec_contract.io import read_yaml


@lru_cache(maxsize=1)
def _behavior_scenarios() -> dict[str, Any]:
    path = Path(__file__).resolve().parents[1] / "behavior" / "behavior_scenarios.yaml"
    return read_yaml(path)["behavior_scenarios"]


def _behavior_scenario(behavior_scenario_id: str) -> dict[str, Any]:
    try:
        return _behavior_scenarios()[behavior_scenario_id]
    except KeyError as exc:  # pragma: no cover - generated features should prevent this.
        raise AssertionError(f"Unknown spec behavior scenario: {behavior_scenario_id}") from exc


@given(parsers.parse('spec behavior scenario "{behavior_scenario_id}" is given'))
def given_spec_behavior_scenario(spec_driver, behavior_scenario_id: str) -> None:
    spec_driver.given(behavior_scenario_id, _behavior_scenario(behavior_scenario_id))


@when(parsers.parse('spec behavior scenario "{behavior_scenario_id}" runs when'))
def when_spec_behavior_scenario(spec_driver, behavior_scenario_id: str) -> None:
    spec_driver.when(behavior_scenario_id, _behavior_scenario(behavior_scenario_id))


@then(parsers.parse('spec behavior scenario "{behavior_scenario_id}" then holds'))
def then_spec_behavior_scenario(spec_driver, behavior_scenario_id: str) -> None:
    spec_driver.then(behavior_scenario_id, _behavior_scenario(behavior_scenario_id))
