from __future__ import annotations

from pathlib import Path

SPEC_ROOT = Path("spec")
SOURCE_SPEC_PATH = SPEC_ROOT / "spec.yaml"
RESOLVER_SPEC_PATH = SPEC_ROOT / "spec.py"
GENERATED_SPEC_DIR = SPEC_ROOT / "generated"
COMPILED_SPEC_PATH = GENERATED_SPEC_DIR / "spec.complete.yaml"


def generated_relative(*parts: str) -> str:
    return str(GENERATED_SPEC_DIR.joinpath(*parts))
