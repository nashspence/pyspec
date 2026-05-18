from __future__ import annotations

from typing import Any, Mapping, Protocol


class SpecDriver(Protocol):
    """Implemented by pytest-bdd harness drivers. Generated; do not edit."""

    def given(self, behavior_scenario_id: str, behavior_scenario: Mapping[str, Any]) -> None: ...
    def when(self, behavior_scenario_id: str, behavior_scenario: Mapping[str, Any]) -> None: ...
    def then(self, behavior_scenario_id: str, behavior_scenario: Mapping[str, Any]) -> None: ...
