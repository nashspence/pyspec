from __future__ import annotations

import shutil
from pathlib import Path

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
