from __future__ import annotations

from typing import Any, Mapping, Protocol


class ContractDriver(Protocol):
    """Implemented by pytest-bdd harness drivers. Generated; do not edit."""

    def arrange(self, scenario_id: str, scenario: Mapping[str, Any]) -> None: ...
    def execute(self, scenario_id: str, scenario: Mapping[str, Any]) -> None: ...
    def assert_obligations(self, scenario_id: str, scenario: Mapping[str, Any]) -> None: ...
