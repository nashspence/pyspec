from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from pm_contract.io import read_yaml

ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOTS = [ROOT]


def test_generated_openapi_passes_official_validator() -> None:
    validator = pytest.importorskip("openapi_spec_validator")
    for project in PROJECT_ROOTS:
        validator.validate(read_yaml(project / "generated" / "openapi.yaml"))


def test_generated_cwl_passes_cwltool_validate() -> None:
    cwltool = shutil.which("cwltool")
    if not cwltool:
        pytest.skip("cwltool is not installed; install requirements-dev.txt for external CWL validation")
    for project in PROJECT_ROOTS:
        subprocess.run(
            [cwltool, "--validate", str(project / "generated" / "workflows.cwl.yaml")],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
