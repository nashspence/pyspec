from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from pm_contract.audit import audit_expected_files
from pm_contract.compile import ContractError, compile_patch
from pm_contract.io import read_yaml
from pm_contract.projection_validators import validate_audit_outputs

ROOT = Path(__file__).resolve().parents[1]
PNG_HEADER = bytes([137, 80, 78, 71, 13, 10, 26, 10])


def _contract(root: Path = ROOT) -> dict:
    return read_yaml(root / "contract.yaml")


def _first_change(patch: dict, target: str) -> dict:
    for change in patch["changes"]:
        if change.get("target") == target and change["op"] in {"add", "replace"}:
            return change
    raise AssertionError(f"missing {target} change")


def test_audit_outputs_cover_full_contract() -> None:
    contract = _contract()
    expected = audit_expected_files(contract)
    assert "generated/audit/copy.yaml" in expected
    assert any(path.startswith("generated/audit/fsm/") and path.endswith(".svg") for path in expected)
    assert any(path.startswith("generated/audit/composition/") and path.endswith(".svg") for path in expected)
    assert any(path.startswith("generated/audit/html/panels/") and path.endswith(".png") for path in expected)
    assert any(path.startswith("generated/audit/html/views/") and path.endswith(".html") for path in expected)
    assert any(path.startswith("generated/audit/textual/views/") and path.endswith(".svg") for path in expected)
    validate_audit_outputs(ROOT, contract)


def test_audit_html_sources_render_copy_assets_and_fixture_fields() -> None:
    ready = ROOT / "generated" / "audit" / "html" / "views" / "project_board" / "default.wide.project_board_ready_selected_audit.html"
    text = ready.read_text(encoding="utf-8")
    assert "Dispatch queue" in text
    assert "Replace rooftop condenser fan · Atlas Foods" in text
    assert "Latest activity" in text
    assert "High priority" in text
    assert "Replace rooftop condenser fan" in text
    assert "Atlas Foods" in text
    assert "fixture.projects.audit_records" not in text
    assert "data-audit" not in text

    empty = ROOT / "generated" / "audit" / "html" / "views" / "project_board" / "default.compact.project_board_empty_audit.html"
    empty_text = empty.read_text(encoding="utf-8")
    assert "No dispatch projects yet" in empty_text
    assert "asset.project.list.empty.illustration" in empty_text
    assert "data:image/svg+xml;base64" in empty_text


def test_audit_asset_placeholder_is_generic_and_not_named() -> None:
    asset = ROOT / "generated" / "audit" / "assets" / "asset_project_list_empty_illustration.svg"
    text = asset.read_text(encoding="utf-8")
    assert text.lstrip().startswith("<svg")
    assert "asset.project.list.empty.illustration" not in text
    assert "<text" not in text
    assert "Empty dispatch queue illustration" in text


def test_audit_pngs_are_real_pngs() -> None:
    contract = _contract()
    pngs = [ROOT / path for path in audit_expected_files(contract) if path.endswith(".png")]
    assert pngs
    for path in pngs:
        assert path.read_bytes().startswith(PNG_HEADER), path


def test_copy_placeholder_is_required_for_used_copy_ref() -> None:
    patch = read_yaml(ROOT / "pm.patch.yaml")
    change = _first_change(patch, "copy")
    patch["changes"].remove(change)
    with pytest.raises(ContractError, match="copy placeholders drift"):
        compile_patch(patch)


def test_asset_placeholder_schema_rejects_missing_visual_intent() -> None:
    patch = read_yaml(ROOT / "pm.patch.yaml")
    change = _first_change(patch, "asset")
    del change["spec"]["placeholder"]
    with pytest.raises(ContractError, match="Schema validation failed"):
        compile_patch(patch)


def test_render_case_coverage_is_required() -> None:
    patch = read_yaml(ROOT / "pm.patch.yaml")
    patch["changes"] = [change for change in patch["changes"] if change.get("target") != "render_case"]
    with pytest.raises(ContractError, match="At least one render_case|Missing render_case coverage"):
        compile_patch(patch)


def test_audit_validator_rejects_corrupt_html_png(tmp_path: Path) -> None:
    project = tmp_path / "project"
    shutil.copytree(ROOT, project, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.pyc", "node_modules"))
    contract = read_yaml(project / "contract.yaml")
    png = next(project / path for path in audit_expected_files(contract) if path.endswith(".png"))
    png.write_bytes(b"not-a-png")
    with pytest.raises(ContractError, match="not PNG"):
        validate_audit_outputs(project, contract)


def test_audit_validator_rejects_missing_fsm_svg(tmp_path: Path) -> None:
    project = tmp_path / "project"
    shutil.copytree(ROOT, project, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.pyc", "node_modules"))
    contract = read_yaml(project / "contract.yaml")
    svg = next(project / path for path in audit_expected_files(contract) if "/fsm/" in path)
    svg.unlink()
    with pytest.raises(ContractError, match="audit generated files"):
        validate_audit_outputs(project, contract)
