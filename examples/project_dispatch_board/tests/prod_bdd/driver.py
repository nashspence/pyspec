from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from sample_app.product import ProductApp


class ProdDriver:
    """Prod harness adapter. It calls the app surface; it does not use the spec fake."""

    def __init__(self, root: Path):
        self.app = ProductApp(root)

    def arrange(self, scenario_id: str, scenario: Mapping[str, Any]) -> None:
        self.app.arrange(scenario["arrange"])

    def execute(self, scenario_id: str, scenario: Mapping[str, Any]) -> None:
        kind, body = next(iter(scenario["execute"].items()))
        if kind == "open_entry":
            self.app.open_web_entry(body["ref"], self._resolve_map(body.get("params", {})))
        elif kind == "call_entry":
            self.app.call_entry(body["ref"], self._resolve_map(body.get("input", {})))
        elif kind == "invoke_capability":
            self.app.invoke_capability(body["ref"], self._resolve_map(body.get("input", {})))
        elif kind == "emit_event":
            self.app.emit_event(body["ref"], self._resolve_map(body.get("payload", {})))
        else:  # pragma: no cover - generated scenarios prevent this.
            raise AssertionError(f"Unsupported execute kind: {kind}")

    def assert_obligations(self, scenario_id: str, scenario: Mapping[str, Any]) -> None:
        self.app.assert_contract(scenario["assert"])

    def _resolve_map(self, values: Mapping[str, Any]) -> dict[str, Any]:
        return {key: self._resolve(value) for key, value in values.items()}

    def _resolve(self, value: Any) -> Any:
        if not isinstance(value, str) or not value.startswith("$fixture."):
            return value
        current: Any = self.app.fixtures
        for part in value[len("$fixture."):].split("."):
            current = current[part]
        return current
