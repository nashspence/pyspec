from __future__ import annotations

from pathlib import Path

import pytest

from pm_contract.compile import ContractError, compile_patch
from pm_contract.content import ContentContext, call_asset, call_copy
from pm_contract.io import read_yaml
from pm_contract.paths import COMPILED_CONTRACT_PATH
from pm_contract.projection_validators import validate_content_contract

ROOT = Path(__file__).resolve().parents[1]


def test_final_copy_resolver_is_contract_declared_and_executable() -> None:
    result = call_copy(
        ROOT,
        "copy.project.detail.ready.heading",
        {"title": "Replace rooftop condenser fan", "customer": "Atlas Foods"},
        ContentContext(surface="test"),
    )
    assert result == "Replace rooftop condenser fan · Atlas Foods"


def test_final_asset_resolver_is_contract_declared_and_svg() -> None:
    result = call_asset(
        ROOT,
        "asset.project.detail.ready.priority_badge",
        {"priority": "High"},
        ContentContext(surface="test"),
    )
    assert result.mime_type == "image/svg+xml"
    assert result.body.lstrip().startswith("<svg")
    assert "High" in result.body
    assert result.alt == "High priority"


def test_content_contract_validator_executes_content_cases() -> None:
    validate_content_contract(ROOT, read_yaml(ROOT / COMPILED_CONTRACT_PATH))


def test_final_content_requires_content_case_coverage() -> None:
    patch = read_yaml(ROOT / "pm.patch.yaml")
    patch["changes"] = [change for change in patch["changes"] if change.get("target") != "content_case"]
    with pytest.raises(ContractError, match="content_case coverage"):
        compile_patch(patch)


def test_content_case_args_must_match_declared_signature() -> None:
    patch = read_yaml(ROOT / "pm.patch.yaml")
    for change in patch["changes"]:
        if change.get("target") == "content_case" and change["id"] == "content.project.detail.heading.high_priority":
            del change["spec"]["args"]["customer"]
            break
    with pytest.raises(ContractError, match="args"):
        compile_patch(patch)
