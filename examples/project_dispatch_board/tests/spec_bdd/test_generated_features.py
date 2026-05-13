from __future__ import annotations

from pathlib import Path

from pytest_bdd import scenarios

FEATURES = Path(__file__).resolve().parents[2] / "spec" / "generated" / "features"
scenarios(str(FEATURES))
