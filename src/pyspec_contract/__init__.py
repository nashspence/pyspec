"""Whole-app specification compiler and generated artifact tooling."""

from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORTS = {
    "ArtifactPolicy": ("pyspec_contract.api", "ArtifactPolicy"),
    "ContractError": ("pyspec_contract.compile", "ContractError"),
    "ProjectConfig": ("pyspec_contract.api", "ProjectConfig"),
    "author_from_source": ("pyspec_contract.compile", "author_from_source"),
    "compile_author": ("pyspec_contract.compile", "compile_author"),
    "compile_project": ("pyspec_contract.api", "compile_project"),
    "compile_source": ("pyspec_contract.compile", "compile_source"),
    "expected_artifacts": ("pyspec_contract.api", "expected_artifacts"),
    "validate_project": ("pyspec_contract.api", "validate_project"),
    "write_generated": ("pyspec_contract.api", "write_generated"),
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:
    if name not in _EXPORTS:
        raise AttributeError(name)
    module_name, attr_name = _EXPORTS[name]
    value = getattr(import_module(module_name), attr_name)
    globals()[name] = value
    return value
