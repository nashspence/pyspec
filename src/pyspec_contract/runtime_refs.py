from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping


class ReferenceExpressionError(ValueError):
    pass


_SEGMENT_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class RuntimeReference:
    root: str
    path: tuple[str, ...]

    @property
    def source(self) -> str:
        return "$" + ".".join((self.root, *self.path))


def is_reference_expression(value: Any) -> bool:
    return isinstance(value, str) and value.startswith("$")


def parse_reference_expression(value: str) -> RuntimeReference:
    if not isinstance(value, str) or not value.startswith("$"):
        raise ReferenceExpressionError(f"Runtime reference must start with $: {value!r}")
    body = value[1:]
    parts = tuple(body.split("."))
    if len(parts) < 2 or any(not part for part in parts):
        raise ReferenceExpressionError(f"Malformed runtime reference: {value}")
    root = parts[0]
    if root.lower() != root or not _SEGMENT_RE.fullmatch(root):
        raise ReferenceExpressionError(f"Malformed runtime reference root: {value}")
    for segment in parts[1:]:
        if not _SEGMENT_RE.fullmatch(segment):
            raise ReferenceExpressionError(f"Malformed runtime reference path: {value}")
    return RuntimeReference(root=root, path=parts[1:])


def resolve_reference_expression(value: str, namespace: Mapping[str, Any]) -> Any:
    ref = parse_reference_expression(value)
    try:
        current: Any = namespace[ref.root]
    except KeyError as exc:
        raise ReferenceExpressionError(f"Unknown runtime reference root: ${ref.root}") from exc
    for segment in ref.path:
        if not isinstance(current, Mapping) or segment not in current:
            raise ReferenceExpressionError(f"Unresolved runtime reference: {value}")
        current = current[segment]
    return current
