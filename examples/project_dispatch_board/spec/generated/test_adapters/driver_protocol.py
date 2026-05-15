from __future__ import annotations

from typing import Any, Mapping, Protocol


class SpecDriver(Protocol):
    """Implemented by pytest-bdd harness drivers. Generated; do not edit."""

    def given(self, test_case_id: str, test_case: Mapping[str, Any]) -> None: ...
    def when(self, test_case_id: str, test_case: Mapping[str, Any]) -> None: ...
    def then(self, test_case_id: str, test_case: Mapping[str, Any]) -> None: ...
