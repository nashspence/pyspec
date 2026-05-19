from __future__ import annotations

from pathlib import Path

import pytest

from pyspec_contract.compile import ContractError, compile_source
from pyspec_contract.content import ContentContext, call_media_asset, call_text_resource
from pyspec_contract.io import read_yaml
from pyspec_contract.paths import COMPILED_SPEC_PATH, SOURCE_SPEC_PATH
from pyspec_contract.projection_validators import validate_content_contract
from tests.helpers import EXAMPLE_ROOT

ROOT = EXAMPLE_ROOT


def test_final_text_resolver_is_contract_declared_and_executable() -> None:
    result = call_text_resource(
        ROOT,
        "text_resource.project.detail.ready.heading",
        {"title": "Replace rooftop condenser fan", "customer": "Atlas Foods"},
        ContentContext(render_surface="test"),
    )
    assert result == "Replace rooftop condenser fan · Atlas Foods"


def test_final_asset_resolver_is_contract_declared_and_svg() -> None:
    result = call_media_asset(
        ROOT,
        "media_asset.project.detail.ready.priority_badge",
        {"priority": "High"},
        ContentContext(render_surface="test"),
    )
    assert result.mime_type == "image/svg+xml"
    assert result.body.lstrip().startswith("<svg")
    assert "High" in result.body
    assert result.alt == "High priority"


def test_priority_badge_escapes_dynamic_svg_values() -> None:
    priority = "High & <urgent> \"quoted\" 'single'"
    result = call_media_asset(
        ROOT,
        "media_asset.project.detail.ready.priority_badge",
        {"priority": priority},
        ContentContext(render_surface="test"),
    )
    assert "High &amp; &lt;urgent&gt;" in result.body
    assert 'aria-label="High &amp; &lt;urgent&gt; &quot;quoted&quot; &#x27;single&#x27; priority"' in result.body
    assert "<urgent>" not in result.body
    assert '"quoted"' in result.body
    assert result.alt == "High &amp; &lt;urgent&gt; &quot;quoted&quot; &#x27;single&#x27; priority"


def test_content_contract_validator_executes_content_examples() -> None:
    validate_content_contract(ROOT, read_yaml(ROOT / COMPILED_SPEC_PATH))


def test_final_content_requires_content_example_coverage() -> None:
    author = read_yaml(ROOT / SOURCE_SPEC_PATH)
    author.pop("content_examples")
    with pytest.raises(ContractError, match="content_example coverage"):
        compile_source(author)


def test_content_example_args_must_match_declared_signature() -> None:
    author = read_yaml(ROOT / SOURCE_SPEC_PATH)
    del author["content_examples"]["content_example.project.detail.heading.high_priority"]["args"]["customer"]
    with pytest.raises(ContractError, match="args"):
        compile_source(author)
