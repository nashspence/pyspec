from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from pytest_bdd import given, parsers, then, when

from pyspec_contract.io import read_yaml


@lru_cache(maxsize=1)
def _scenarios() -> dict[str, Any]:
    path = Path(__file__).resolve().parent / "scenarios.yaml"
    return read_yaml(path)["scenarios"]


def _scenario(scenario_id: str) -> dict[str, Any]:
    try:
        return _scenarios()[scenario_id]
    except KeyError as exc:  # pragma: no cover - generated features should prevent this.
        raise AssertionError(f"Unknown contract scenario: {scenario_id}") from exc


@given(parsers.parse('contract scenario "{scenario_id}" is arranged'))
def arrange_contract_scenario(contract_driver, scenario_id: str) -> None:
    contract_driver.arrange(scenario_id, _scenario(scenario_id))


@when(parsers.parse('contract scenario "{scenario_id}" is executed'))
def execute_contract_scenario(contract_driver, scenario_id: str) -> None:
    contract_driver.execute(scenario_id, _scenario(scenario_id))


@then(parsers.parse('contract scenario "{scenario_id}" obligations hold'))
def assert_contract_scenario(contract_driver, scenario_id: str) -> None:
    contract_driver.assert_obligations(scenario_id, _scenario(scenario_id))
