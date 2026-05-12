from __future__ import annotations

import ast
from pathlib import Path

from .compile import ContractError

FORBIDDEN_IMPORTS = {
    "pm_contract.reference_driver",
    "unittest.mock",
    "mock",
    "pytest_mock",
}
FORBIDDEN_FIXTURE_ARGS = {"monkeypatch", "mocker"}
FORBIDDEN_IMPORTED_NAMES = {"ReferenceSpecDriver", "Mock", "MagicMock", "patch"}


def assert_prod_harness_is_real(root: Path) -> None:
    """Reject obvious fake/spec shortcuts in the prod pytest-bdd harness."""
    prod_dir = root / "tests" / "prod_bdd"
    if not prod_dir.exists():
        raise ContractError("Missing tests/prod_bdd prod harness")
    files = sorted(path for path in prod_dir.rglob("*.py") if path.name != "__init__.py")
    if not files:
        raise ContractError("Prod harness has no Python test/driver files")
    for path in files:
        _check_file(root, path)


def _check_file(root: Path, path: Path) -> None:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        raise ContractError(f"Prod harness file has invalid Python: {path.relative_to(root)}") from exc
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in FORBIDDEN_IMPORTS:
                    _fail(root, path, f"forbidden import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module in FORBIDDEN_IMPORTS:
                _fail(root, path, f"forbidden import from {module}")
            for alias in node.names:
                if alias.name in FORBIDDEN_IMPORTED_NAMES:
                    _fail(root, path, f"forbidden imported name {alias.name}")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            arg_names = {arg.arg for arg in [*node.args.args, *node.args.kwonlyargs]}
            bad = sorted(arg_names & FORBIDDEN_FIXTURE_ARGS)
            if bad:
                _fail(root, path, "forbidden prod harness fixture arg " + ", ".join(bad))


def _fail(root: Path, path: Path, reason: str) -> None:
    raise ContractError(f"Prod harness must be real/no-fake: {path.relative_to(root)} uses {reason}")
