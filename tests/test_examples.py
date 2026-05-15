from __future__ import annotations

import importlib.util
from pathlib import Path

from pyspec_contract.audit import audit_expected_files, audit_case_render_file
from pyspec_contract.compile import compile_source
from pyspec_contract.io import read_json, read_yaml
from pyspec_contract.paths import COMPILED_SPEC_PATH, SOURCE_SPEC_PATH
from pyspec_contract.project import fsms_projection, projection_files, textual_screen_entries
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
    assert openapi["paths"]["/workspaces/{workspace_id}/projects"]["post"]["operationId"] == "operation.project.create"
    asyncapi = read_yaml(ROOT / "spec" / "generated" / "product_interfaces" / "events.asyncapi.yaml")
    assert any(channel.get("address") == "event.project.approved" for channel in asyncapi["channels"].values() if isinstance(channel, dict))
    cwl = read_yaml(ROOT / "spec" / "generated" / "product_interfaces" / "workflow.cwl.yaml")
    assert "#workflow_project_approval_notice" in {item["id"] for item in cwl["$graph"]}
    assert not (ROOT / "spec" / "generated" / "persistence.sql").exists()
    assert not (ROOT / "spec" / "generated" / "persistence.json").exists()


def test_canonical_textual_contract_imports_and_composes() -> None:
    path = ROOT / "spec" / "generated" / "product_interfaces" / "textual.projection.py"
    spec = importlib.util.spec_from_file_location("canonical_textual_contract", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.SCREENS[0]["id"] == "screen.state_machine.project.board"
    assert "entry" not in module.SCREENS[0]
    assert module.SCREENS[0]["screen_class"] == "ProjectBoardScreen"
    assert module.COMPOSITIONS[0]["id"] == "state_machine.project.board.ready"
    fsm_items = module.compose_contract_fsm("state_machine.project.list.empty")
    assert ("Static", "text.project.list.empty.heading") in fsm_items
    assert ("Static", "asset.project.list.empty.illustration") in fsm_items
    assert ("Button", "operation.project.create") in fsm_items


def test_textual_screens_are_driven_by_textual_fsm_layout() -> None:
    author = read_yaml(ROOT / SOURCE_SPEC_PATH)
    del author["fsms"]["state_machine.project.board"]["states"]["ready"]["layout"]["textual"]
    author["entry_points"]["entry_point.cli.project.board"]["trigger"]["state_machine"]["render"] = "html"
    for audit_case in author["fsms"]["state_machine.project.board"]["states"]["ready"]["audit"].values():
        audit_case["surfaces"] = ["html"]
    contract = compile_source(author)
    projection = fsms_projection(contract)
    assert textual_screen_entries(contract, projection["fsms"], projection["compositions"]) == []


def test_canonical_audit_contains_real_visual_references() -> None:
    html = (ROOT / audit_case_render_file("state_machine.project.board", "state_machine.project.board.ready.ready_selected.audit", "default", "wide", "html")).read_text(encoding="utf-8")
    assert "Replace rooftop condenser fan" in html
    assert "Atlas Foods" in html
    assert "Dispatch queue" in html
    assert (ROOT / audit_case_render_file("state_machine.project.board", "state_machine.project.board.ready.ready_selected.audit", "default", "wide", "png")).exists()
    assert (ROOT / audit_case_render_file("state_machine.project.board", "state_machine.project.board.ready.ready_selected.audit", "default", "wide", "svg")).exists()
