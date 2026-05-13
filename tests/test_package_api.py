from __future__ import annotations

from pyspec_contract import ArtifactPolicy, expected_artifacts, validate_project
from pyspec_contract.io import read_yaml
from pyspec_contract.paths import COMPILED_CONTRACT_PATH
from tests.helpers import EXAMPLE_ROOT


def test_public_api_validates_example_project() -> None:
    validate_project(EXAMPLE_ROOT, layers="full")


def test_artifact_policy_defaults_to_checked_in_pngs() -> None:
    contract = read_yaml(EXAMPLE_ROOT / COMPILED_CONTRACT_PATH)
    paths = expected_artifacts(contract)
    assert any(path.endswith(".png") for path in paths)
    without_png = expected_artifacts(contract, ArtifactPolicy(include_audit_pngs=False))
    assert not any(path.endswith(".png") for path in without_png)
