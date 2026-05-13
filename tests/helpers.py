from __future__ import annotations

import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_ROOT = REPO_ROOT / "examples" / "project_dispatch_board"

PROJECT_COPY_IGNORE = shutil.ignore_patterns(
    "__pycache__",
    ".pytest_cache",
    ".devcontainer",
    ".git",
    "*.pyc",
    "node_modules",
)


def copy_project_tree(source: Path, destination: Path) -> None:
    shutil.copytree(source, destination, ignore=PROJECT_COPY_IGNORE)
