from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from project_dispatch_board.product import ProductApp
from pyspec_contract.runtime import resolve


class ProdDriver:
    """Prod harness adapter. It calls the app surface; it does not use the spec fake."""

    def __init__(self, root: Path):
        self.app = ProductApp(root)

    def given(self, behavior_scenario_id: str, behavior_scenario: Mapping[str, Any]) -> None:
        self.app.given(behavior_scenario["given"])

    def when(self, behavior_scenario_id: str, behavior_scenario: Mapping[str, Any]) -> None:
        kind, body = next(iter(behavior_scenario["when"].items()))
        if kind == "open_external_interface":
            self.app.open_web_entry(body["ref"], self._resolve_map(body.get("input", {})))
        elif kind == "call_external_interface":
            self.app.call_external_interface(body["ref"], self._resolve_map(body.get("input", {})))
        elif kind in {"invoke_command", "invoke_query"}:
            self.app.invoke_behavior(body["ref"], self._resolve_map(body.get("input", {})))
        elif kind == "emit_domain_event":
            self.app.emit_domain_event(body["ref"], self._resolve_map(body.get("payload", {})))
        else:  # pragma: no cover - generated behavior scenarios prevent this.
            raise AssertionError(f"Unsupported when kind: {kind}")

    def then(self, behavior_scenario_id: str, behavior_scenario: Mapping[str, Any]) -> None:
        self.app.assert_contract(behavior_scenario["then"])

    def _resolve_map(self, values: Mapping[str, Any]) -> dict[str, Any]:
        return {key: self._resolve(value) for key, value in values.items()}

    def _resolve(self, value: Any) -> Any:
        return resolve(value, self.app.fixtures)
