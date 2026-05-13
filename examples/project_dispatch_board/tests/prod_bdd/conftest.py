from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "spec"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
for parent in [ROOT, *ROOT.parents]:
    src = parent / "src"
    if src.is_dir():
        sys.path.insert(0, str(src))
        break

from generated.test_adapters.pytest_bdd_steps import *  # noqa: E402,F401,F403 - registers generated pytest-bdd steps
from driver import ProdDriver  # noqa: E402


@pytest.fixture
def spec_driver() -> ProdDriver:
    return ProdDriver(ROOT)
