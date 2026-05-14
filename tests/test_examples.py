from __future__ import annotations

import importlib.util
from pathlib import Path

from pyspec_contract.audit import audit_expected_files, render_case_file
from pyspec_contract.compile import compile_source
from pyspec_contract.io import read_json, read_yaml
from pyspec_contract.paths import COMPILED_SPEC_PATH, SOURCE_SPEC_PATH
from pyspec_contract.project import panels_projection, projection_files, textual_screen_entries
from tests.helpers import EXAMPLE_ROOT

ROOT = EXAMPLE_ROOT


def test_canonical_example_uses_app_src_layout() -> None:
    assert (ROOT / "src" / "project_dispatch_board" / "product.py").exists()
    assert not (ROOT / "sample_app").exists()


def test_canonical_contract_is_fresh_and_complete() -> None:
    compiled = compile_source(read_yaml(ROOT / SOURCE_SPEC_PATH))
    assert read_yaml(ROOT / COMPILED_SPEC_PATH) == compiled
    expected = {str(COMPILED_SPEC_PATH)} | {relative for relative, _, _ in projection_files(compiled)} | audit_expected_files(compiled)
    actual = {
        str(path.relative_to(ROOT))
        for path in (ROOT / "spec" / "generated").rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
    }
    assert actual == expected
    for relative, content, kind in projection_files(compiled):
        path = ROOT / relative
        assert path.exists(), relative
        if kind == "json":
            assert read_json(path) == content
        elif kind == "yaml":
            assert read_yaml(path) == content
        elif kind == "text":
            assert path.read_text(encoding="utf-8") == content
    for relative in audit_expected_files(compiled):
        path = ROOT / relative
        assert path.exists(), relative
        if relative.endswith(".png"):
            assert path.read_bytes().startswith(bytes([137, 80, 78, 71, 13, 10, 26, 10]))
        elif relative.endswith(".svg"):
            assert path.read_text(encoding="utf-8").lstrip().startswith("<svg")


def test_canonical_openapi_asyncapi_and_cwl_are_visible() -> None:
    openapi = read_yaml(ROOT / "spec" / "generated" / "product_interfaces" / "http.openapi.yaml")
    assert openapi["paths"]["/workspaces/{workspace_id}/projects"]["post"]["operationId"] == "project.create"
    asyncapi = read_yaml(ROOT / "spec" / "generated" / "product_interfaces" / "events.asyncapi.yaml")
    assert any(channel.get("address") == "project.approved" for channel in asyncapi["channels"].values() if isinstance(channel, dict))
    cwl = read_yaml(ROOT / "spec" / "generated" / "product_interfaces" / "workflow.cwl.yaml")
    assert "#project_approval_notice" in {item["id"] for item in cwl["$graph"]}
    assert not (ROOT / "spec" / "generated" / "persistence.sql").exists()
    assert not (ROOT / "spec" / "generated" / "persistence.json").exists()


def test_canonical_textual_contract_imports_and_composes() -> None:
    path = ROOT / "spec" / "generated" / "product_interfaces" / "textual.projection.py"
    spec = importlib.util.spec_from_file_location("canonical_textual_contract", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.SCREENS[0]["id"] == "screen.project.board"
    assert "entry" not in module.SCREENS[0]
    assert module.SCREENS[0]["screen_class"] == "ProjectBoardScreen"
    assert module.COMPOSITIONS[0]["id"] == "project.board"
    panel_items = module.compose_contract_panel("panel.project.list.empty")
    assert ("Static", "copy.project.list.empty.heading") in panel_items
    assert ("Static", "asset.project.list.empty.illustration") in panel_items
    assert ("Button", "project.create") in panel_items


def test_textual_screens_are_driven_by_textual_view_layout() -> None:
    author = read_yaml(ROOT / SOURCE_SPEC_PATH)
    del author["views"]["project.board"]["layout"]["textual"]
    author["entries"]["cli.project.board"]["target"]["view"]["surface"] = "html"
    for render_case in author["render_cases"].values():
        render_case["surfaces"] = ["html"]
    contract = compile_source(author)
    projection = panels_projection(contract)
    assert textual_screen_entries(contract, projection["panels"], projection["compositions"]) == []


def test_canonical_audit_contains_real_visual_references() -> None:
    html = (ROOT / render_case_file("project.board", "project.board.ready_selected.audit", "default", "wide", "html")).read_text(encoding="utf-8")
    assert "Replace rooftop condenser fan" in html
    assert "Atlas Foods" in html
    assert "Dispatch queue" in html
    assert (ROOT / render_case_file("project.board", "project.board.ready_selected.audit", "default", "wide", "png")).exists()
    assert (ROOT / render_case_file("project.board", "project.board.ready_selected.audit", "default", "wide", "svg")).exists()
