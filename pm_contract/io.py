from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from yaml.tokens import AliasToken, AnchorToken


class NoAliasSafeDumper(yaml.SafeDumper):
    """Safe YAML dumper that always expands repeated objects.

    PyYAML emits anchors/aliases when the same Python object instance appears
    more than once. That is useful for object identity, but this contract system
    uses explicit ID references instead. Generated YAML must stay fully expanded
    and human-auditable.
    """

    def ignore_aliases(self, data: Any) -> bool:  # pragma: no cover - PyYAML callback
        return True


def assert_yaml_has_no_anchors(path: Path) -> None:
    """Reject YAML anchors/aliases in contract-system YAML files.

    Anchors make generated contracts harder to audit and can falsely imply that
    the DSL has YAML-level reference semantics. Contract references must be
    explicit IDs such as ``panel.project.list`` or ``copy.project.title``.
    """

    text = path.read_text(encoding="utf-8")
    for token in yaml.scan(text):
        if isinstance(token, (AnchorToken, AliasToken)):
            kind = "anchor" if isinstance(token, AnchorToken) else "alias"
            mark = token.start_mark
            raise ValueError(f"YAML {kind} is not allowed in {path}: line {mark.line + 1}, column {mark.column + 1}")


def read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data or {}


def write_yaml(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.dump(data, f, Dumper=NoAliasSafeDumper, sort_keys=True, allow_unicode=True, width=120, default_flow_style=False)


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")
