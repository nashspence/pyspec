from __future__ import annotations

from pathlib import Path

import pytest

from pyspec_contract.compile import ContractError, compile_source
from pyspec_contract.content import ContentContext, call_asset, call_copy
from pyspec_contract.io import read_yaml
from pyspec_contract.paths import COMPILED_SPEC_PATH, SOURCE_SPEC_PATH
from pyspec_contract.projection_validators import validate_content_contract
from tests.helpers import EXAMPLE_ROOT

ROOT = EXAMPLE_ROOT


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
    validate_content_contract(ROOT, read_yaml(ROOT / COMPILED_SPEC_PATH))


def test_final_content_requires_content_case_coverage() -> None:
    author = read_yaml(ROOT / SOURCE_SPEC_PATH)
    author.pop("content_cases")
    with pytest.raises(ContractError, match="content_case coverage"):
        compile_source(author)


def test_content_case_args_must_match_declared_signature() -> None:
    author = read_yaml(ROOT / SOURCE_SPEC_PATH)
    del author["content_cases"]["content.project.detail.heading.high_priority"]["args"]["customer"]
    with pytest.raises(ContractError, match="args"):
        compile_source(author)
