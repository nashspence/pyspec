from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from project_dispatch_board.product import ProductApp
from pyspec_contract.runtime import resolve


class ProdDriver:
    """Prod harness adapter. It calls the app surface; it does not use the spec fake."""

    def __init__(self, root: Path):
        self.app = ProductApp(root)

    def given(self, test_case_id: str, test_case: Mapping[str, Any]) -> None:
        self.app.given(test_case["given"])

    def when(self, test_case_id: str, test_case: Mapping[str, Any]) -> None:
        kind, body = next(iter(test_case["when"].items()))
        if kind == "open_entry":
            self.app.open_web_entry(body["ref"], self._resolve_map(body.get("input", {})))
        elif kind == "call_entry":
            self.app.call_entry(body["ref"], self._resolve_map(body.get("input", {})))
        elif kind == "invoke_operation":
            self.app.invoke_operation(body["ref"], self._resolve_map(body.get("input", {})))
        elif kind == "emit_event":
            self.app.emit_event(body["ref"], self._resolve_map(body.get("payload", {})))
        else:  # pragma: no cover - generated test cases prevent this.
            raise AssertionError(f"Unsupported when kind: {kind}")

    def then(self, test_case_id: str, test_case: Mapping[str, Any]) -> None:
        self.app.assert_contract(test_case["then"])

    def _resolve_map(self, values: Mapping[str, Any]) -> dict[str, Any]:
        return {key: self._resolve(value) for key, value in values.items()}

    def _resolve(self, value: Any) -> Any:
        return resolve(value, self.app.fixtures)
