from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from generated.bdd_steps import *  # noqa: E402,F401,F403 - registers generated pytest-bdd steps
from tests.prod_bdd.driver import ProdDriver  # noqa: E402


@pytest.fixture
def contract_driver() -> ProdDriver:
    return ProdDriver(ROOT)
