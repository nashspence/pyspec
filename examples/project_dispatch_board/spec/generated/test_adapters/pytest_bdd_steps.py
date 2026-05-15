from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from pytest_bdd import given, parsers, then, when

from pyspec_contract.io import read_yaml


@lru_cache(maxsize=1)
def _test_cases() -> dict[str, Any]:
    path = Path(__file__).resolve().parents[1] / "behavior" / "test_cases.yaml"
    return read_yaml(path)["test_cases"]


def _test_case(test_case_id: str) -> dict[str, Any]:
    try:
        return _test_cases()[test_case_id]
    except KeyError as exc:  # pragma: no cover - generated features should prevent this.
        raise AssertionError(f"Unknown spec test case: {test_case_id}") from exc


@given(parsers.parse('spec test case "{test_case_id}" is given'))
def given_spec_test_case(spec_driver, test_case_id: str) -> None:
    spec_driver.given(test_case_id, _test_case(test_case_id))


@when(parsers.parse('spec test case "{test_case_id}" runs when'))
def when_spec_test_case(spec_driver, test_case_id: str) -> None:
    spec_driver.when(test_case_id, _test_case(test_case_id))


@then(parsers.parse('spec test case "{test_case_id}" then holds'))
def then_spec_test_case(spec_driver, test_case_id: str) -> None:
    spec_driver.then(test_case_id, _test_case(test_case_id))
