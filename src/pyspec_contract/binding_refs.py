from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping


class BindingExpressionError(ValueError):
    pass


_SEGMENT_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class BindingReference:
    root: str
    path: tuple[str, ...]

    @property
    def source(self) -> str:
        return "$" + ".".join((self.root, *self.path))


def is_binding_expression(value: Any) -> bool:
    return isinstance(value, str) and value.startswith("$")


def parse_binding_expression(value: str) -> BindingReference:
    if not isinstance(value, str) or not value.startswith("$"):
        raise BindingExpressionError(f"Binding expression must start with $: {value!r}")
    body = value[1:]
    parts = tuple(body.split("."))
    if len(parts) < 2 or any(not part for part in parts):
        raise BindingExpressionError(f"Malformed binding expression: {value}")
    root = parts[0]
    if root.lower() != root or not _SEGMENT_RE.fullmatch(root):
        raise BindingExpressionError(f"Malformed binding expression root: {value}")
    for segment in parts[1:]:
        if not _SEGMENT_RE.fullmatch(segment):
            raise BindingExpressionError(f"Malformed binding expression path: {value}")
    return BindingReference(root=root, path=parts[1:])


def resolve_binding_expression(value: str, namespace: Mapping[str, Any]) -> Any:
    ref = parse_binding_expression(value)
    try:
        current: Any = namespace[ref.root]
    except KeyError as exc:
        raise BindingExpressionError(f"Unknown binding expression root: ${ref.root}") from exc
    for segment in ref.path:
        if not isinstance(current, Mapping) or segment not in current:
            raise BindingExpressionError(f"Unresolved binding expression: {value}")
        current = current[segment]
    return current
