from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml


def read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data or {}


class _NoAliasSafeDumper(yaml.SafeDumper):
    """Safe YAML dumper that never emits anchors or aliases.

    The contract files are human-audited product artifacts, not a serialized
    Python object graph. PyYAML normally preserves shared object identity with
    YAML anchors (``&id001``) and aliases (``*id001``). That is valid YAML, but
    it creates misleading indirection in the canonical contract. Every emitted
    YAML file should be fully expanded and readable on its own.
    """

    def ignore_aliases(self, data: Any) -> bool:  # pragma: no cover - exercised through write_yaml
        return True


def write_yaml(path: Path, data: Any, *, sort_keys: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.dump(
            data,
            f,
            Dumper=_NoAliasSafeDumper,
            sort_keys=sort_keys,
            allow_unicode=True,
            width=120,
        )


def yaml_contains_anchors(path: Path) -> bool:
    """Return True if a YAML file contains actual YAML anchors or aliases."""
    with path.open("r", encoding="utf-8") as f:
        for event in yaml.parse(f):
            if getattr(event, "anchor", None):
                return True
    return False


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")
