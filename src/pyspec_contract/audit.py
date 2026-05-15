from __future__ import annotations

import asyncio
import base64
import hashlib
import html
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .compile import ContractError, audit_cases
from .content import AssetResult, ContentContext, ContentError, call_asset, call_copy
from .io import write_yaml
from .layout import layout_html, layout_html_regions
from .paths import GENERATED_SPEC_DIR, generated_relative as g
from .project import css_value, default_html_slots, format_attrs, humanize, fsms_projection, fsm_styles_projection, safe_id
from .runtime import fixture_namespace, resolve
from .targets import entry_fsm_surface, entry_target_pair, entry_workflow_trigger
from .type_expr import effective_field_type, type_display

ROOT = Path(__file__).resolve().parent

_DOT_FONT = "Arial"
_DOT_ARROW_FORWARD = "→"
_DOT_ARROW_ASSIGN = "←"

_DOT_SIZE_TITLE = 13
_DOT_SIZE_BODY = 10
_DOT_SIZE_META = 8
_DOT_SIZE_NODE = 9
_DOT_SIZE_DEFAULT_NODE = 11

_DOT_COLOR_EDGE = "#3f3f46"
_DOT_COLOR_MUTED = "#64748b"
_DOT_COLOR_TYPE = "#94a3b8"
_DOT_COLOR_AUDIT_TEXT = "#3f3f46"

_DOT_COLOR_ENTRY = "#0891b2"
_DOT_COLOR_ENTRY_TEXT = "#155e75"
_DOT_COLOR_ENTRY_HEADER = "#ecfeff"

_DOT_COLOR_NEUTRAL_BORDER = "#71717a"
_DOT_COLOR_NEUTRAL_HEADER = "#f8fafc"
_DOT_COLOR_BOUNDARY_BORDER = "#64748b"

_DOT_COLOR_CAPABILITY_BORDER = "#2563eb"
_DOT_COLOR_CAPABILITY_HEADER = "#eff6ff"
_DOT_COLOR_EVENT_BORDER = "#4f46e5"
_DOT_COLOR_EVENT_TEXT = "#312e81"
_DOT_COLOR_EVENT_HEADER = "#eef2ff"

_DOT_COLOR_FSM_BORDER = "#047857"
_DOT_COLOR_FSM_HEADER = "#ecfdf5"
_DOT_COLOR_WORKFLOW_BORDER = "#a16207"
_DOT_COLOR_WORKFLOW_HEADER = "#fefce8"
_DOT_COLOR_MESSAGE_BORDER = "#be185d"
_DOT_COLOR_MESSAGE_HEADER = "#fdf2f8"
_DOT_COLOR_CONTEXT_BORDER = "#15803d"
_DOT_COLOR_CONTEXT_HEADER = "#f0fdf4"

_GRAPHVIZ_INPUT_HASH_PREFIX = "pyspec-contract-input-sha256:"
_TEXTUAL_INPUT_HASH_PREFIX = "pyspec-contract-textual-input-sha256:"


@dataclass(frozen=True)
class _DotCardStyle:
    header_bg: str
    border: str


_DOT_STYLE_ENTRY = _DotCardStyle(header_bg=_DOT_COLOR_ENTRY_HEADER, border=_DOT_COLOR_ENTRY)
_DOT_STYLE_EXTERNAL = _DotCardStyle(header_bg=_DOT_COLOR_NEUTRAL_HEADER, border=_DOT_COLOR_BOUNDARY_BORDER)
_DOT_STYLE_NEUTRAL = _DotCardStyle(header_bg=_DOT_COLOR_NEUTRAL_HEADER, border=_DOT_COLOR_NEUTRAL_BORDER)
_DOT_STYLE_CAPABILITY = _DotCardStyle(header_bg=_DOT_COLOR_CAPABILITY_HEADER, border=_DOT_COLOR_CAPABILITY_BORDER)
_DOT_STYLE_EVENT = _DotCardStyle(header_bg=_DOT_COLOR_EVENT_HEADER, border=_DOT_COLOR_EVENT_BORDER)
_DOT_STYLE_FSM = _DotCardStyle(header_bg=_DOT_COLOR_FSM_HEADER, border=_DOT_COLOR_FSM_BORDER)
_DOT_STYLE_WORKFLOW = _DotCardStyle(header_bg=_DOT_COLOR_WORKFLOW_HEADER, border=_DOT_COLOR_WORKFLOW_BORDER)
_DOT_STYLE_MESSAGE = _DotCardStyle(header_bg=_DOT_COLOR_MESSAGE_HEADER, border=_DOT_COLOR_MESSAGE_BORDER)
_DOT_STYLE_CONTEXT = _DotCardStyle(header_bg=_DOT_COLOR_CONTEXT_HEADER, border=_DOT_COLOR_CONTEXT_BORDER)


def _under(relative: str, *parts: str) -> str:
    return "/".join([relative, *parts])


def fsm_graph_file(fsm_id: str) -> str:
    return g("audit_evidence", "fsms", safe_id(fsm_id), "fsm.svg")


def fsm_state_root(fsm_id: str, state_name: str) -> str:
    return g("audit_evidence", "fsms", safe_id(fsm_id), "states", safe_id(state_name))


def composition_file(fsm_id: str, state_name: str = "ready") -> str:
    return g("audit_evidence", "fsms", safe_id(fsm_id), "states", safe_id(state_name), "composition.svg")


def entrypoint_flow_file(entry_id: str, surface: str) -> str:
    return g("audit_evidence", "entrypoints", safe_id(surface), safe_id(entry_id), "flow.svg")


def workflow_flow_file(workflow_id: str) -> str:
    return g("audit_evidence", "workflows", safe_id(workflow_id), "flow.svg")


def audit_case_root(fsm_id: str, case_id: str, state_name: str = "ready") -> str:
    return g("audit_evidence", "fsms", safe_id(fsm_id), "states", safe_id(state_name), "cases", safe_id(case_id))


def _render_filename(profile_id: str, breakpoint_id: str, extension: str) -> str:
    stem = f"{safe_id(profile_id)}.{safe_id(breakpoint_id)}"
    if extension == "html":
        return f"html.{stem}.source.html"
    if extension == "png":
        return f"html.{stem}.screenshot.png"
    if extension == "py":
        return f"textual.{stem}.source.py"
    if extension == "svg":
        return f"textual.{stem}.capture.svg"
    raise ContractError(f"Unknown audit render extension: {extension}")


def fsm_state_render_file(fsm_id: str, state_name: str, profile_id: str, breakpoint_id: str, extension: str) -> str:
    return _under(fsm_state_root(fsm_id, state_name), "renders", _render_filename(profile_id, breakpoint_id, extension))


def audit_case_render_file(fsm_id: str, case_id: str, profile_id: str, breakpoint_id: str, extension: str, state_name: str = "ready") -> str:
    return _under(audit_case_root(fsm_id, case_id, state_name), "renders", _render_filename(profile_id, breakpoint_id, extension))


def _projection_surface_root(fsm: dict[str, Any]) -> str:
    return fsm_state_root(fsm["owner"], fsm["state"])


def _projection_surface_file(fsm: dict[str, Any], profile_id: str, breakpoint_id: str, extension: str) -> str:
    return fsm_state_render_file(fsm["owner"], fsm["state"], profile_id, breakpoint_id, extension)


def _case_root(contract: dict[str, Any], case_id: str, case: dict[str, Any]) -> str:
    return audit_case_root(case["fsm"], case_id, case["state"])


def _case_file(contract: dict[str, Any], case_id: str, case: dict[str, Any], breakpoint_id: str, extension: str) -> str:
    return audit_case_render_file(case["fsm"], case_id, case["profile"], breakpoint_id, extension, case["state"])


def _scope_copy_file(scope_root: str) -> str:
    return _under(scope_root, "copy.yaml")


def _scope_fixtures_file(scope_root: str) -> str:
    return _under(scope_root, "fixtures.yaml")


def _scope_asset_file(scope_root: str, asset_id: str) -> str:
    return _under(scope_root, "assets", f"{safe_id(asset_id)}.svg")


def _copy_doc(contract: dict[str, Any], copy_refs: Iterable[str]) -> dict[str, Any]:
    return {"project": contract["project"], "copy": {ref: contract["copies"][ref] for ref in sorted(copy_refs)}}


def _fixtures_doc(
    contract: dict[str, Any],
    fixture_ids: Iterable[str],
    fact_ids: Iterable[str],
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "project": contract["project"],
        "fixtures": {fixture_id: contract["fixtures"][fixture_id] for fixture_id in sorted(fixture_ids)},
        "facts": {fact_id: contract["facts"][fact_id] for fact_id in sorted(fact_ids)},
        "context": context or {},
    }


def _state_needs_data(contract: dict[str, Any], fsm: dict[str, Any]) -> bool:
    if fsm.get("data") or fsm["slots"].get("fields"):
        return True
    copy_refs = fsm["slots"].get("copy", [])
    asset_refs = fsm["slots"].get("assets", [])
    return any(contract["copies"][ref].get("args") for ref in copy_refs) or any(contract["assets"][ref].get("args") for ref in asset_refs)


def _fixture_ids_for_model(contract: dict[str, Any], model_id: str) -> set[str]:
    return {
        fixture_id
        for fixture_id, fixture in contract.get("fixtures", {}).items()
        if _find_model_records(fixture.get("values", {}), model_id)
    }


def _fact_ids_for_model(contract: dict[str, Any], model_id: str) -> set[str]:
    fact_ids = set()
    for fact_id, fact in contract.get("facts", {}).items():
        _, body = _fact_selector(fact, fact_id)
        if body["model"] == model_id:
            fact_ids.add(fact_id)
    return fact_ids


def _fixture_ids_for_facts(contract: dict[str, Any], fact_ids: Iterable[str], model_id: str) -> set[str]:
    fixture_ids: set[str] = set()
    for fact_id in sorted(fact_ids):
        fact_uses = [{"use": fact_id}]
        try:
            _apply_fact_uses(contract, fact_uses, {}, model_id, [])
            continue
        except (AssertionError, KeyError, TypeError):
            pass
        for fixture_id in contract.get("fixtures", {}):
            try:
                namespace = fixture_namespace(contract, [fixture_id])
                _apply_fact_uses(contract, fact_uses, namespace, model_id, [])
            except (AssertionError, KeyError, TypeError):
                continue
            fixture_ids.add(fixture_id)
            break
    return fixture_ids


def _surface_scope_inputs(contract: dict[str, Any], fsm: dict[str, Any]) -> tuple[set[str], set[str], set[str], set[str], dict[str, Any]]:
    copy_refs = set(fsm["slots"].get("copy", []))
    asset_refs = set(fsm["slots"].get("assets", []))
    fixture_ids: set[str] = set()
    fact_ids: set[str] = set()
    if _state_needs_data(contract, fsm):
        model_id = fsm_model(contract, fsm)
        fixture_ids = _fixture_ids_for_model(contract, model_id)
        fact_ids = _fact_ids_for_model(contract, model_id)
        fixture_ids.update(_fixture_ids_for_facts(contract, fact_ids, model_id))
    return copy_refs, asset_refs, fixture_ids, fact_ids, {}


def _case_scope_inputs(contract: dict[str, Any], case: dict[str, Any]) -> tuple[set[str], set[str], set[str], set[str], dict[str, Any]]:
    fsms = case_render_fsms(contract, case)
    copy_refs = {copy_ref for fsm in fsms for copy_ref in fsm["slots"].get("copy", [])}
    asset_refs = {asset_ref for fsm in fsms for asset_ref in fsm["slots"].get("assets", [])}
    fixture_ids = set(case.get("fixtures", []))
    fact_ids = {fact_use["use"] for fact_use in case.get("facts", [])}
    return copy_refs, asset_refs, fixture_ids, fact_ids, case.get("context") or {}


def _audit_scope_expected_files(scope_root: str, asset_refs: Iterable[str]) -> set[str]:
    files = {_scope_copy_file(scope_root), _scope_fixtures_file(scope_root)}
    files.update(_scope_asset_file(scope_root, asset_id) for asset_id in asset_refs)
    return files


def _write_audit_scope_inputs(
    root: Path,
    contract: dict[str, Any],
    scope_root: str,
    copy_refs: Iterable[str],
    asset_refs: Iterable[str],
    fixture_ids: Iterable[str],
    fact_ids: Iterable[str],
    context: dict[str, Any] | None = None,
) -> None:
    copy_path = root / _scope_copy_file(scope_root)
    copy_path.parent.mkdir(parents=True, exist_ok=True)
    write_yaml(copy_path, _copy_doc(contract, copy_refs))
    fixtures_path = root / _scope_fixtures_file(scope_root)
    fixtures_path.parent.mkdir(parents=True, exist_ok=True)
    write_yaml(fixtures_path, _fixtures_doc(contract, fixture_ids, fact_ids, context))
    for asset_id in sorted(asset_refs):
        asset_path = root / _scope_asset_file(scope_root, asset_id)
        asset_path.parent.mkdir(parents=True, exist_ok=True)
        asset_path.write_text(asset_placeholder_svg(contract["assets"][asset_id]), encoding="utf-8")


def _write_audit_inputs(root: Path, contract: dict[str, Any], projection: dict[str, Any]) -> None:
    for fsm in _audit_projection_surfaces(contract, projection):
        _write_audit_scope_inputs(root, contract, _projection_surface_root(fsm), *_surface_scope_inputs(contract, fsm))
    for case_id, case in sorted(audit_cases(contract).items()):
        _write_audit_scope_inputs(root, contract, _case_root(contract, case_id, case), *_case_scope_inputs(contract, case))


def _audit_projection_surfaces(contract: dict[str, Any], projection: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        fsm
        for fsm in projection["fsms"]
        if not contract["fsms"][fsm["owner"]]["states"][fsm["state"]].get("mounts")
    ]


def audit_expected_files(contract: dict[str, Any]) -> set[str]:
    files: set[str] = set()
    for fsm_id in contract.get("fsms", {}):
        files.add(fsm_graph_file(fsm_id))
    for fsm_id, fsm in contract.get("fsms", {}).items():
        for state_name, state in fsm.get("states", {}).items():
            if state.get("mounts"):
                files.add(composition_file(fsm_id, state_name))
    for entry_id, entry in contract.get("entries", {}).items():
        files.add(entrypoint_flow_file(entry_id, entry["surface"]))
    for workflow_id in contract.get("workflows", {}):
        files.add(workflow_flow_file(workflow_id))

    projection = fsms_projection(contract)
    for fsm in _audit_projection_surfaces(contract, projection):
        scope_root = _projection_surface_root(fsm)
        _, asset_refs, _, _, _ = _surface_scope_inputs(contract, fsm)
        files.update(_audit_scope_expected_files(scope_root, asset_refs))
        for profile_id, profile in sorted(contract.get("audit_profiles", {}).items()):
            for breakpoint in profile.get("html", {}).get("breakpoints", {}):
                files.add(_projection_surface_file(fsm, profile_id, breakpoint, "html"))
                files.add(_projection_surface_file(fsm, profile_id, breakpoint, "png"))
            for breakpoint in profile.get("textual", {}).get("breakpoints", {}):
                files.add(_projection_surface_file(fsm, profile_id, breakpoint, "py"))
                files.add(_projection_surface_file(fsm, profile_id, breakpoint, "svg"))

    for case_id, case in audit_cases(contract).items():
        profile = contract["audit_profiles"][case["profile"]]
        scope_root = _case_root(contract, case_id, case)
        _, asset_refs, _, _, _ = _case_scope_inputs(contract, case)
        files.update(_audit_scope_expected_files(scope_root, asset_refs))
        if "html" in case["surfaces"]:
            for breakpoint in profile.get("html", {}).get("breakpoints", {}):
                files.add(_case_file(contract, case_id, case, breakpoint, "html"))
                files.add(_case_file(contract, case_id, case, breakpoint, "png"))
        if "textual" in case["surfaces"]:
            for breakpoint in profile.get("textual", {}).get("breakpoints", {}):
                files.add(_case_file(contract, case_id, case, breakpoint, "py"))
                files.add(_case_file(contract, case_id, case, breakpoint, "svg"))
    return files


def generate_audit(
    root: Path,
    contract: dict[str, Any],
    tools_root: Path | None = None,
    previous_audit_root: Path | None = None,
) -> None:
    root = root.resolve()
    audit_root = root / GENERATED_SPEC_DIR / "audit_evidence"
    backup_parent: Path | None = None
    restore_audit_root: Path | None = None
    if audit_root.exists():
        backup_container = root / GENERATED_SPEC_DIR.parent
        backup_container.mkdir(parents=True, exist_ok=True)
        backup_parent = Path(tempfile.mkdtemp(prefix=".pyspec-audit-backup-", dir=str(backup_container)))
        restore_audit_root = backup_parent / "audit_evidence"
        shutil.move(str(audit_root), str(restore_audit_root))
        previous_audit_root = restore_audit_root
    audit_root.mkdir(parents=True, exist_ok=True)

    try:
        projection = fsms_projection(contract)
        _write_audit_inputs(root, contract, projection)

        if audit_expected_files(contract):
            _render_visual_audit_subprocess(root, tools_root or root, previous_audit_root)
    except BaseException:
        if audit_root.exists():
            shutil.rmtree(audit_root)
        if restore_audit_root and restore_audit_root.exists():
            shutil.move(str(restore_audit_root), str(audit_root))
        raise
    finally:
        if backup_parent and backup_parent.exists():
            shutil.rmtree(backup_parent, ignore_errors=True)


def _render_visual_audit_subprocess(root: Path, tools_root: Path, previous_audit_root: Path | None = None) -> None:
    env = os.environ.copy()
    env["PM_CONTRACT_AUDIT_WORKER"] = "1"
    src_root = str(ROOT.parent)
    env["PYTHONPATH"] = src_root if not env.get("PYTHONPATH") else src_root + os.pathsep + env["PYTHONPATH"]
    cmd = [sys.executable, "-m", "pyspec_contract.audit", str(root), str(tools_root)]
    if previous_audit_root:
        cmd.append(str(previous_audit_root))
    result = subprocess.run(
        cmd,
        cwd=str(root),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=900,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        suffix = f":\n{detail}" if detail else ""
        raise ContractError(f"Visual audit renderer failed with exit code {result.returncode}{suffix}")


def _render_visual_audit(
    root: Path,
    contract: dict[str, Any],
    _tools_root: Path,
    projection: dict[str, Any] | None = None,
    previous_audit_root: Path | None = None,
) -> None:
    projection = projection or fsms_projection(contract)
    for fsm_id, fsm in sorted(contract.get("fsms", {}).items()):
        path = root / fsm_graph_file(fsm_id)
        _write_graphviz_svg(path, fsm_dot(fsm_id, fsm, contract), _previous_audit_path(root, previous_audit_root, path))
    for fsm_id, fsm in sorted(contract.get("fsms", {}).items()):
        for state_name, state in sorted(fsm.get("states", {}).items()):
            if not state.get("mounts"):
                continue
            path = root / composition_file(fsm_id, state_name)
            _write_graphviz_svg(
                path,
                composition_dot(f"{fsm_id}.{state_name}", {"context": fsm.get("context", {}), **state}, contract),
                _previous_audit_path(root, previous_audit_root, path),
            )
    for entry_id, entry in sorted(contract.get("entries", {}).items()):
        path = root / entrypoint_flow_file(entry_id, entry["surface"])
        _write_graphviz_svg(path, entrypoint_flow_dot(entry_id, entry, contract), _previous_audit_path(root, previous_audit_root, path))
    for workflow_id, workflow in sorted(contract.get("workflows", {}).items()):
        path = root / workflow_flow_file(workflow_id)
        _write_graphviz_svg(path, workflow_flow_dot(workflow_id, workflow, contract), _previous_audit_path(root, previous_audit_root, path))

    has_html_audit = bool(
        _audit_projection_surfaces(contract, projection) and any(profile.get("html") for profile in contract.get("audit_profiles", {}).values())
    ) or any("html" in case["surfaces"] for case in audit_cases(contract).values())
    if has_html_audit:
        _render_html_audit(root, contract, projection, previous_audit_root)

    audit_fsms = _audit_projection_surfaces(contract, projection)
    if audit_fsms or any("textual" in case["surfaces"] for case in audit_cases(contract).values()):
        try:
            import textual  # noqa: F401
        except Exception as exc:  # pragma: no cover - dependency absence is environment-specific.
            raise ContractError("Missing Textual dependency; install requirements.txt") from exc
        textual_jobs: list[tuple[Path, list[tuple[str, str]], dict[str, int], Path | None, Path | None]] = []
        for fsm in sorted(audit_fsms, key=lambda p: p["id"]):
            lines = fsm_textual_lines(root, contract, fsm, None)
            for profile_id, profile in sorted(contract.get("audit_profiles", {}).items()):
                for name, viewport in sorted(profile.get("textual", {}).get("breakpoints", {}).items()):
                    py_path = root / _projection_surface_file(fsm, profile_id, name, "py")
                    svg_path = root / _projection_surface_file(fsm, profile_id, name, "svg")
                    _write_textual_source(py_path, lines)
                    textual_jobs.append((
                        svg_path,
                        lines,
                        viewport,
                        _previous_audit_path(root, previous_audit_root, py_path),
                        _previous_audit_path(root, previous_audit_root, svg_path),
                    ))
        for case_id, case in sorted(audit_cases(contract).items()):
            if "textual" not in case["surfaces"]:
                continue
            profile = contract["audit_profiles"][case["profile"]]
            lines = textual_audit_lines(root, contract, case_id, case)
            for name, viewport in sorted(profile.get("textual", {}).get("breakpoints", {}).items()):
                py_path = root / _case_file(contract, case_id, case, name, "py")
                svg_path = root / _case_file(contract, case_id, case, name, "svg")
                _write_textual_source(py_path, lines)
                textual_jobs.append((
                    svg_path,
                    lines,
                    viewport,
                    _previous_audit_path(root, previous_audit_root, py_path),
                    _previous_audit_path(root, previous_audit_root, svg_path),
                ))
        asyncio.run(_render_textual_batch(textual_jobs))


def _render_html_audit(root: Path, contract: dict[str, Any], projection: dict[str, Any], previous_audit_root: Path | None = None) -> None:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover - dependency absence is environment-specific.
        raise ContractError("Missing Playwright dependency; install requirements.txt and run python -m playwright install chromium, or provide system Chromium") from exc

    with sync_playwright() as pw:
        try:
            browser = _launch_chromium(pw)
        except Exception as exc:  # pragma: no cover - browser launch depends on the host image.
            raise ContractError(f"HTML audit renderer could not launch Chromium: {exc}") from exc
        try:
            page = browser.new_page()
            try:
                for fsm in sorted(_audit_projection_surfaces(contract, projection), key=lambda p: p["id"]):
                    for profile_id, profile in sorted(contract.get("audit_profiles", {}).items()):
                        html_profile = profile.get("html")
                        if not html_profile:
                            continue
                        html_doc = audit_html_document(contract, render_fsm_audit_html(root, contract, fsm, None), fsm_surface_ids={fsm["id"]})
                        for name, viewport in sorted(html_profile["breakpoints"].items()):
                            html_path = root / _projection_surface_file(fsm, profile_id, name, "html")
                            png_path = root / _projection_surface_file(fsm, profile_id, name, "png")
                            _write_html_and_png_page(
                                page,
                                html_doc,
                                html_path,
                                png_path,
                                viewport,
                                _previous_audit_path(root, previous_audit_root, html_path),
                                _previous_audit_path(root, previous_audit_root, png_path),
                            )
                for case_id, case in sorted(audit_cases(contract).items()):
                    profile = contract["audit_profiles"][case["profile"]]
                    if "html" in case["surfaces"]:
                        html_doc = audit_html_document(
                            contract,
                            render_audit_case_html(root, contract, case_id, case),
                            fsm_surface_ids={fsm["id"] for fsm in case_render_fsms(contract, case)},
                            composition_ids=_case_composition_ids(contract, case),
                        )
                        for name, viewport in sorted(profile.get("html", {}).get("breakpoints", {}).items()):
                            html_path = root / _case_file(contract, case_id, case, name, "html")
                            png_path = root / _case_file(contract, case_id, case, name, "png")
                            _write_html_and_png_page(
                                page,
                                html_doc,
                                html_path,
                                png_path,
                                viewport,
                                _previous_audit_path(root, previous_audit_root, html_path),
                                _previous_audit_path(root, previous_audit_root, png_path),
                            )
            finally:
                page.close()
        finally:
            browser.close()


def _write_html_and_png_page(
    page: Any,
    html_doc: str,
    html_path: Path,
    png_path: Path,
    viewport: dict[str, int],
    previous_html_path: Path | None = None,
    previous_png_path: Path | None = None,
) -> None:
    html_path.parent.mkdir(parents=True, exist_ok=True)
    png_path.parent.mkdir(parents=True, exist_ok=True)
    if (
        previous_html_path
        and previous_png_path
        and _text_file_equals(previous_html_path, html_doc)
        and _png_matches_viewport(previous_png_path, viewport)
    ):
        shutil.copy2(previous_html_path, html_path)
        shutil.copy2(previous_png_path, png_path)
        return
    html_path.write_text(html_doc, encoding="utf-8")
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            page.set_viewport_size({"width": viewport["width"], "height": viewport["height"]})
            page.set_content(html_doc, wait_until="load")
            page.screenshot(path=str(png_path), full_page=False, type="png", timeout=10000)
            last_error = None
            break
        except Exception as exc:  # pragma: no cover - renderer failure details come from Playwright.
            last_error = exc
            if attempt < 2:
                page.wait_for_timeout(100)
    if last_error is not None:
        raise ContractError(f"HTML renderer failed for {png_path}: {last_error}") from last_error
    if png_path.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
        raise ContractError(f"HTML renderer did not produce a PNG: {png_path}")


def _chromium_executable() -> str | None:
    return os.environ.get("CONTRACT_AUDIT_CHROMIUM") or shutil.which("chromium") or shutil.which("chromium-browser") or shutil.which("google-chrome") or shutil.which("google-chrome-stable")


def _launch_chromium(pw: Any) -> Any:
    executable = _chromium_executable()
    args = ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
    if executable:
        return pw.chromium.launch(executable_path=executable, args=args)
    return pw.chromium.launch(args=args)


def _graphviz_dot_executable() -> str:
    executable = os.environ.get("CONTRACT_AUDIT_GRAPHVIZ_DOT") or shutil.which("dot")
    if not executable:
        raise ContractError("Missing Graphviz dependency; install graphviz so the dot executable is available")
    return executable


def _write_graphviz_svg(path: Path, dot_source: str, previous_path: Path | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    input_hash = _input_hash(dot_source)
    if previous_path and _svg_has_input_hash(previous_path, input_hash):
        shutil.copy2(previous_path, path)
        return
    path.write_text(_svg_with_input_hash(_render_graphviz_svg(dot_source, path.stem), input_hash), encoding="utf-8")


def _render_graphviz_svg(dot_source: str, graph_id: str) -> str:
    try:
        result = subprocess.run(
            [_graphviz_dot_executable(), "-Tsvg"],
            input=dot_source,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ContractError(f"Graphviz renderer timed out for {graph_id}") from exc
    if result.returncode != 0:
        detail = result.stderr.strip() or f"exit code {result.returncode}"
        raise ContractError(f"Graphviz renderer failed for {graph_id}: {detail}")
    svg = _strip_svg_preamble(result.stdout)
    if not svg.lstrip().startswith("<svg") or "</svg>" not in svg:
        raise ContractError("Graphviz renderer did not produce SVG")
    return svg


def _strip_svg_preamble(svg: str) -> str:
    start = svg.find("<svg")
    end = svg.rfind("</svg>")
    if start == -1 or end == -1:
        return svg
    return svg[start : end + len("</svg>")] + "\n"


def _input_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _svg_has_input_hash(path: Path, input_hash: str, prefix: str = _GRAPHVIZ_INPUT_HASH_PREFIX) -> bool:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    marker = f"<!-- {prefix} {input_hash} -->"
    return text.lstrip().startswith("<svg") and marker in text and "</svg>" in text


def _svg_with_input_hash(svg: str, input_hash: str, prefix: str = _GRAPHVIZ_INPUT_HASH_PREFIX) -> str:
    marker = f"\n<!-- {prefix} {input_hash} -->"
    insert_at = svg.find(">")
    if insert_at == -1:
        return svg
    return svg[: insert_at + 1] + marker + svg[insert_at + 1:]


def _previous_audit_path(root: Path, previous_audit_root: Path | None, path: Path) -> Path | None:
    if previous_audit_root is None:
        return None
    try:
        relative = path.relative_to(root / GENERATED_SPEC_DIR / "audit_evidence")
    except ValueError:
        return None
    previous = previous_audit_root / relative
    return previous if previous.exists() else None


def _text_file_equals(path: Path, text: str) -> bool:
    try:
        return path.read_text(encoding="utf-8") == text
    except OSError:
        return False


def _png_matches_viewport(path: Path, viewport: dict[str, int]) -> bool:
    try:
        from PIL import Image

        if path.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
            return False
        with Image.open(path) as image:
            return image.size == (viewport["width"], viewport["height"])
    except Exception:
        return False


def _write_textual_source(path: Path, lines: list[tuple[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textual_source(lines), encoding="utf-8")


def textual_source(lines: list[tuple[str, str]]) -> str:
    return f'''from __future__ import annotations

from textual.app import App, ComposeResult
from textual.containers import Container
from textual.widgets import Button, Static

LINES = {lines!r}


class AuditApp(App[None]):
    CSS = """
    Screen {{ layout: vertical; }}
    #root {{ padding: 1; }}
    Static {{ margin: 0 0 1 0; }}
    Button {{ margin: 0 0 1 0; width: auto; }}
    """

    def compose(self) -> ComposeResult:
        with Container(id="root"):
            for index, (kind, value) in enumerate(LINES):
                if kind == "button":
                    yield Button(value, id=f"button_{{index}}")
                else:
                    yield Static(value, id=f"line_{{index}}")


if __name__ == "__main__":
    AuditApp().run()
'''


async def _render_textual_batch(
    jobs: list[tuple[Path, list[tuple[str, str]], dict[str, int], Path | None, Path | None]],
) -> None:
    for path, lines, viewport, previous_source_path, previous_svg_path in jobs:
        await _render_textual_svg(path, lines, viewport, previous_source_path, previous_svg_path)


async def _render_textual_svg(
    path: Path,
    lines: list[tuple[str, str]],
    viewport: dict[str, int],
    previous_source_path: Path | None = None,
    previous_svg_path: Path | None = None,
) -> None:
    from textual.app import App, ComposeResult
    from textual.containers import Container
    from textual.widgets import Button, Static

    source = textual_source(lines)
    input_hash = _input_hash(json.dumps({"source": source, "viewport": viewport}, sort_keys=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    if (
        previous_source_path
        and previous_svg_path
        and _text_file_equals(previous_source_path, source)
        and _svg_has_input_hash(previous_svg_path, input_hash, _TEXTUAL_INPUT_HASH_PREFIX)
    ):
        shutil.copy2(previous_svg_path, path)
        return

    class AuditApp(App[None]):
        CSS = """
        Screen { layout: vertical; }
        #root { padding: 1; }
        Static { margin: 0 0 1 0; }
        Button { margin: 0 0 1 0; width: auto; }
        """

        def compose(self) -> ComposeResult:
            with Container(id="root"):
                for index, (kind, value) in enumerate(lines):
                    if kind == "button":
                        yield Button(value, id=f"button_{index}")
                    else:
                        yield Static(value, id=f"line_{index}")

    app = AuditApp()
    async with app.run_test(size=(viewport["columns"], viewport["rows"])) as pilot:
        await pilot.pause()
        svg = app.export_screenshot()
    if not isinstance(svg, str) or "<svg" not in svg:
        raise ContractError("Textual renderer did not produce SVG")
    path.write_text(_svg_with_input_hash(svg, input_hash, _TEXTUAL_INPUT_HASH_PREFIX), encoding="utf-8")


def fsm_dot(fsm_id: str, fsm: dict[str, Any], contract: dict[str, Any]) -> str:
    lines = _dot_graph_preamble("fsm_" + safe_id(fsm_id))
    lines.append(_dot_circle_node("initial", "initial", width="0.58", color=_DOT_COLOR_ENTRY, fontcolor=_DOT_COLOR_ENTRY_TEXT))
    for state_name in sorted(fsm["states"]):
        state = fsm["states"][state_name]
        sections: list[tuple[str, Iterable[object]]] = [
            ("copy", state.get("copy", [])),
            ("assets", state.get("assets", [])),
            (_state_field_section_title(fsm, state_name, state), _format_state_fields(fsm, state, contract)),
            ("actions", _format_operation_outputs(state.get("actions", []), contract)),
            ("mounts", _format_mounts(state.get("mounts", []))),
            ("sync", [rule["id"] for rule in state.get("sync", [])]),
        ]
        lines.append(
            _dot_html_node(
                _dot_node_id("state", state_name),
                _dot_card(
                    state_name,
                    "initial state" if state_name == fsm["initial"] else "state",
                    sections,
                    style=_DOT_STYLE_ENTRY if state_name == fsm["initial"] else _DOT_STYLE_NEUTRAL,
                ),
            )
        )
    lines.append(_dot_edge("initial", _dot_node_id("state", fsm["initial"])))
    for index, transition in enumerate(fsm.get("transitions", [])):
        source = _dot_node_id("state", transition["from"])
        target = _dot_node_id("state", transition["to"])
        transition_id = _dot_node_id("transition", f"{index}_{transition['from']}_{transition['to']}_{transition['on']}")
        lines.append(
            _dot_html_node(
                transition_id,
                _dot_card(
                    transition["on"],
                    "transition event",
                    _format_transition_sections(fsm, transition, contract),
                    basis=transition.get("basis", ""),
                    style=_DOT_STYLE_CAPABILITY,
                ),
            )
        )
        lines.append(_dot_edge(source, transition_id))
        lines.append(_dot_edge(transition_id, target))
    lines.append("}")
    return "\n".join(lines) + "\n"


def composition_dot(fsm_id: str, fsm: dict[str, Any], contract: dict[str, Any]) -> str:
    route_fsm_order: list[str] = []
    for rule in fsm.get("sync", []):
        route_fsm_order.append(rule["when"]["instance"])
        route_fsm_order.extend(effect["send"]["instance"] for effect in rule.get("do", []) if "send" in effect)
    route_fsm_index = {fsm_id: index for index, fsm_id in enumerate(dict.fromkeys(route_fsm_order))}
    mounts = sorted(
        fsm.get("mounts", []),
        key=lambda mount: (route_fsm_index.get(mount["id"], len(route_fsm_index)), mount["id"]),
    )
    mount_by_id = {mount["id"]: mount for mount in mounts}
    mount_node_by_id = {mount["id"]: _dot_node_id("fsm_mount", mount["id"]) for mount in mounts}
    mount_node_ids = [mount_node_by_id[mount["id"]] for mount in mounts]
    has_sync = bool(fsm.get("sync"))
    lines = _dot_graph_preamble("composition_" + safe_id(fsm_id))
    for mount in mounts:
        lines.append(_dot_html_node(mount_node_by_id[mount["id"]], _dot_mount_card(mount)))
    if mount_node_ids and not has_sync:
        lines.extend(_dot_invisible_order(mount_node_ids, indent="  "))
    if not has_sync:
        lines.append(_dot_html_node("message_route_none", _dot_card("No message routes", "message routing", [], style=_DOT_STYLE_NEUTRAL)))
    for rule in fsm.get("sync", []):
        emit_id = _dot_node_id("message_emit", f"{rule['id']}_{rule['when']['instance']}_{rule['when']['message']}")
        sync_id = _dot_node_id("message_route", rule["id"])
        send_effects = [(index, effect) for index, effect in enumerate(rule.get("do", [])) if "send" in effect]
        effect_ids = [_dot_node_id("message_effect", f"{rule['id']}_{index}") for index, _ in send_effects]
        lines.append(
            _dot_html_node(
                emit_id,
                _dot_card(
                    rule["when"]["message"],
                    "emitted message",
                    [
                        ("source", _emitting_transition_refs(rule["when"]["instance"], rule["when"]["message"], mount_by_id, contract)),
                        ("data", _emitted_message_data_lines(rule["when"]["instance"], rule["when"]["message"], mount_by_id, contract)),
                    ],
                    style=_DOT_STYLE_EVENT,
                ),
            )
        )
        lines.append(
            _dot_html_node(
                sync_id,
                _dot_card(
                    rule["id"],
                    "message route",
                    [("set", _route_set_lines(rule, fsm))],
                    style=_DOT_STYLE_WORKFLOW,
                ),
            )
        )
        for index, effect in send_effects:
            effect_id = _dot_node_id("message_effect", f"{rule['id']}_{index}")
            lines.append(_dot_html_node(effect_id, _dot_sync_effect_card(effect, mount_by_id, contract)))
        if effect_ids:
            lines.append("  { rank=same; " + " ".join(_dot_quote(effect_id) for effect_id in effect_ids) + " }")
            lines.extend(_dot_invisible_order(effect_ids, indent="  "))
    for rule in fsm.get("sync", []):
        emit_id = _dot_node_id("message_emit", f"{rule['id']}_{rule['when']['instance']}_{rule['when']['message']}")
        sync_id = _dot_node_id("message_route", rule["id"])
        source = mount_node_by_id.get(rule["when"]["instance"])
        if source:
            lines.append(_dot_edge(source, emit_id, {"color": _DOT_COLOR_EVENT_BORDER, "penwidth": "1.4"}))
        lines.append(_dot_edge(emit_id, sync_id, {"color": _DOT_COLOR_EVENT_BORDER, "penwidth": "1.2"}))
        for index, effect in enumerate(rule.get("do", [])):
            if "send" not in effect:
                continue
            effect_id = _dot_node_id("message_effect", f"{rule['id']}_{index}")
            lines.append(_dot_edge(sync_id, effect_id, {"color": _DOT_COLOR_MESSAGE_BORDER, "penwidth": "1.3"}))
            target = mount_node_by_id.get(effect["send"]["instance"])
            if not target:
                continue
            lines.append(_dot_edge(effect_id, target, {"color": _DOT_COLOR_MESSAGE_BORDER, "penwidth": "1.4"}))
    lines.append("}")
    return "\n".join(lines) + "\n"


def entrypoint_flow_dot(entry_id: str, entry: dict[str, Any], contract: dict[str, Any]) -> str:
    target_kind, target_value = entry_target_pair(entry["target"])
    target_surface = entry_fsm_surface(entry) if target_kind == "fsm" else None
    target_trigger = entry_workflow_trigger(entry) if target_kind == "workflow" else None
    start_id = "entry_start"
    entry_node = _dot_node_id("entrypoint", entry_id)
    input_node = _dot_node_id("entrypoint_input", entry_id)
    target_node = _dot_node_id("entrypoint_target", target_value)
    response_nodes = _entry_response_nodes(entry_id, entry, contract)
    exit_id = "entry_exit"
    target_tail = [] if target_kind == "fsm" else _entry_target_tail_nodes(target_kind, target_value, contract)
    input_sections = _entry_input_sections(entry, contract)
    input_title, output_title = _entry_io_card_titles(entry["surface"])
    lines = _dot_graph_preamble("entrypoint_" + safe_id(entry_id))
    lines.extend(
        [
            _dot_circle_node(start_id, "entry", width="0.58", color=_DOT_COLOR_ENTRY, fontcolor=_DOT_COLOR_ENTRY_TEXT),
            _dot_html_node(
                entry_node,
                _dot_card(
                    _entry_surface_title(entry),
                    f"{entry['surface']} entry",
                    _entry_binding_sections(entry),
                    basis=entry.get("basis", ""),
                    style=_DOT_STYLE_ENTRY,
                ),
            ),
        ]
    )
    if input_sections:
        lines.append(
            _dot_html_node(
                input_node,
                _dot_card(input_title, "external data", input_sections, style=_DOT_STYLE_EXTERNAL),
            )
        )
    lines.append(_dot_html_node(target_node, _entry_target_card(target_kind, target_value, contract, surface=target_surface, trigger=target_trigger)))
    if response_nodes:
        lines.append(_dot_circle_node(exit_id, "exit", width="0.58", color=_DOT_COLOR_ENTRY, fontcolor=_DOT_COLOR_ENTRY_TEXT, shape="doublecircle"))
        lines.extend(
            _dot_html_node(
                node_id,
                _dot_card(outcome_id if subtitle else output_title, subtitle or outcome_id, sections, style=_DOT_STYLE_EXTERNAL),
            )
            for node_id, outcome_id, subtitle, sections in response_nodes
        )
    lines.extend(_dot_html_node(node_id, label) for node_id, label in target_tail)
    lines.append(_dot_edge(start_id, entry_node))
    if input_sections:
        lines.append(_dot_edge(entry_node, input_node))
        lines.append(_dot_edge(input_node, target_node))
    else:
        lines.append(_dot_edge(entry_node, target_node))
    for node_id, _ in target_tail:
        lines.append(_dot_edge(target_node, node_id))
    if response_nodes:
        for node_id, _, _, _ in response_nodes:
            lines.append(_dot_edge(target_node, node_id))
            lines.append(_dot_edge(node_id, exit_id))
        if len(response_nodes) > 1:
            lines.append("  { rank=same; " + " ".join(_dot_quote(node_id) for node_id, _, _, _ in response_nodes) + " }")
            lines.extend(_dot_invisible_order([node_id for node_id, _, _, _ in response_nodes], indent="  "))
    if len(target_tail) > 1:
        lines.append("  { rank=same; " + " ".join(_dot_quote(node_id) for node_id, _ in target_tail) + " }")
        lines.extend(_dot_invisible_order([node_id for node_id, _ in target_tail], indent="  "))
    lines.append("}")
    return "\n".join(lines) + "\n"


def _entry_io_card_titles(surface: str) -> tuple[str, str]:
    if surface in {"api", "web", "webhook"}:
        return "request", "response"
    if surface == "cli":
        return "command input", "command output"
    if surface == "worker":
        return "event payload", "message disposition"
    if surface == "schedule":
        return "schedule trigger", "trigger disposition"
    return "input", "output"


def workflow_flow_dot(workflow_id: str, workflow: dict[str, Any], contract: dict[str, Any]) -> str:
    trigger_kind, trigger_value = _target_pair(workflow["trigger"])
    start_id = "workflow_start"
    trigger_node = _dot_node_id("workflow_trigger", f"{trigger_kind}_{trigger_value}")
    workflow_node = _dot_node_id("workflow", workflow_id)
    step_nodes = [(_dot_node_id("workflow_step", f"{workflow_id}_{step['id']}"), step) for step in workflow["steps"]]
    outcome_nodes = [
        (_dot_node_id("workflow_outcome", f"{workflow_id}_{outcome_id}"), outcome_id, outcome)
        for outcome_id, outcome in sorted(workflow["outcomes"].items())
    ]
    step_node_by_id = {step["id"]: node_id for node_id, step in step_nodes}
    outcome_node_by_id = {outcome_id: node_id for node_id, outcome_id, _ in outcome_nodes}
    lines = _dot_graph_preamble("workflow_" + safe_id(workflow_id))
    lines.extend(
        [
            _dot_circle_node(start_id, "trigger", width="0.68", color=_DOT_COLOR_EVENT_BORDER, fontcolor=_DOT_COLOR_EVENT_TEXT),
            _dot_html_node(trigger_node, _workflow_trigger_card(trigger_kind, trigger_value, contract)),
            _dot_html_node(
                workflow_node,
                _dot_card(
                    workflow_id,
                    "workflow",
                    [
                        ("ref", [workflow.get("ref", "")]),
                        ("steps", [f"{step['id']} {_DOT_ARROW_FORWARD} {step['operation']}" for step in workflow["steps"]]),
                        ("outcomes", [_DotTypedField(outcome_id, outcome["result"], outcome["kind"]) for outcome_id, outcome in sorted(workflow["outcomes"].items())]),
                    ],
                    basis=workflow.get("basis", ""),
                    style=_DOT_STYLE_WORKFLOW,
                ),
            ),
        ]
    )
    for node_id, step in step_nodes:
        lines.append(_dot_html_node(node_id, _workflow_step_card(step, contract)))
    for node_id, outcome_id, outcome in outcome_nodes:
        lines.append(_dot_html_node(node_id, _workflow_outcome_card(outcome_id, outcome)))
    lines.append(_dot_edge(start_id, trigger_node))
    lines.append(_dot_edge(trigger_node, workflow_node))
    if step_nodes:
        lines.append(_dot_edge(workflow_node, step_nodes[0][0]))
    for node_id, step in step_nodes:
        for outcome_id, route in sorted(step["on"].items()):
            attrs = {"label": outcome_id}
            if "next" in route:
                lines.append(_dot_edge(node_id, step_node_by_id[route["next"]], attrs))
            elif "complete" in route:
                lines.append(_dot_edge(node_id, outcome_node_by_id[route["complete"]], attrs))
            elif "fail" in route:
                lines.append(_dot_edge(node_id, outcome_node_by_id[route["fail"]], attrs))
    if outcome_nodes:
        lines.append("  { rank=same; " + " ".join(_dot_quote(node_id) for node_id, _, _ in outcome_nodes) + " }")
        lines.extend(_dot_invisible_order([node_id for node_id, _, _ in outcome_nodes], indent="  "))
    lines.append("}")
    return "\n".join(lines) + "\n"


def _entry_surface_title(entry: dict[str, Any]) -> str:
    surface = entry["surface"]
    if surface == "api":
        return f"{entry.get('method', '').upper()} {entry.get('path', '')}".strip()
    if surface in {"web", "webhook"}:
        return entry.get("path", surface)
    if surface == "cli":
        return entry.get("command", surface)
    if surface == "schedule":
        return entry.get("schedule", surface)
    if surface == "worker":
        return entry.get("workflow_ref", surface)
    return surface


def _entry_binding_sections(entry: dict[str, Any]) -> list[tuple[str, list[object]]]:
    labels = {
        "route": "route",
        "screen": "screen",
        "endpoint": "endpoint",
        "command_ref": "command",
        "workflow_ref": "workflow",
        "schedule": "schedule",
    }
    return [(label, [entry[key]]) for key, label in labels.items() if entry.get(key)]


def _entry_input_sections(entry: dict[str, Any], contract: dict[str, Any]) -> list[tuple[str, list[object]]]:
    sections: list[tuple[str, list[object]]] = []
    entry_input = entry.get("input", {})
    if entry_input.get("params"):
        sections.append(("params", _typed_fields(entry_input["params"])))
    if entry_input.get("body"):
        sections.append(("body", _typed_fields(entry_input["body"])))
    if entry_input.get("args"):
        sections.append(("args", _typed_fields(entry_input["args"])))
    if entry_input.get("payload"):
        sections.append(("payload", [_DotTypedField("payload", entry_input["payload"])]))
    return sections


def _entry_response_nodes(entry_id: str, entry: dict[str, Any], contract: dict[str, Any]) -> list[tuple[str, str, str | None, list[tuple[str, list[object]]]]]:
    responses = entry.get("responses", {})
    if not responses:
        return []
    target_kind, target_value = entry_target_pair(entry["target"])
    outcomes = contract["operations"][target_value]["outcomes"] if target_kind == "operation" else {}
    nodes = []
    for outcome_id, response in sorted(responses.items()):
        outcome = outcomes.get(outcome_id)
        subtitle = f"{outcome['kind']} response" if outcome else None
        node_id = _dot_node_id("entrypoint_response", f"{entry_id}_{outcome_id}")
        nodes.append((node_id, outcome_id, subtitle, _entry_response_sections(response)))
    return nodes


def _entry_response_sections(response: dict[str, Any]) -> list[tuple[str, list[object]]]:
    sections: list[tuple[str, list[object]]] = []
    if "status" in response:
        sections.append(("status", [str(response["status"])]))
    if "body" in response:
        body = response["body"]
        sections.append(("body", [_DotTypedField("body", body["type"], body.get("from"))]))
    if "stdout" in response:
        stdout = response["stdout"]
        sections.append(("stdout", [_DotTypedField("stdout", stdout["type"], stdout.get("from"))]))
    if "stderr" in response:
        stderr = response["stderr"]
        sections.append(("stderr", [_DotTypedField("stderr", stderr["type"], stderr.get("from"))]))
    if "exit_code" in response:
        sections.append(("exit_code", [str(response["exit_code"])]))
    if "disposition" in response:
        sections.append(("disposition", [response["disposition"]]))
    if "problem" in response:
        sections.append(("problem", [_DotTypedField("problem", response["problem"])]))
    return sections


def _entry_target_card(
    target_kind: str,
    target_value: str,
    contract: dict[str, Any],
    *,
    surface: str | None = None,
    trigger: dict[str, str] | None = None,
) -> str:
    if target_kind == "fsm":
        fsm = contract["fsms"][target_value]
        return _dot_card(
            target_value,
            f"target FSM ({surface})" if surface else "target FSM",
            _fsm_summary_sections(fsm, contract),
            basis=fsm.get("basis", ""),
            style=_DOT_STYLE_FSM,
        )
    if target_kind == "operation":
        operation = contract["operations"][target_value]
        return _dot_card(
            target_value,
            "target operation",
            _operation_sections(operation, contract),
            basis=operation.get("basis", ""),
            style=_DOT_STYLE_CAPABILITY,
        )
    if target_kind == "workflow":
        workflow = contract["workflows"][target_value]
        target_subtitle = "target workflow"
        if trigger:
            target_subtitle = f"target workflow ({_target_label(*_target_pair(trigger))})"
        return _dot_card(
            target_value,
            target_subtitle,
            [
                ("trigger", [_target_label(*_target_pair(workflow["trigger"]))]),
                ("steps", [f"{step['id']} {_DOT_ARROW_FORWARD} {step['operation']}" for step in workflow["steps"]]),
                ("outcomes", [_DotTypedField(outcome_id, outcome["result"], outcome["kind"]) for outcome_id, outcome in sorted(workflow["outcomes"].items())]),
            ],
            basis=workflow.get("basis", ""),
            style=_DOT_STYLE_WORKFLOW,
        )
    if target_kind == "event":
        return _event_card(target_value, contract)
    return _dot_card(target_value, f"target {target_kind}", [], style=_DOT_STYLE_NEUTRAL)


def _entry_target_tail_nodes(target_kind: str, target_value: str, contract: dict[str, Any]) -> list[tuple[str, str]]:
    if target_kind != "fsm":
        return []
    fsm = contract["fsms"][target_value]
    nodes: list[tuple[str, str]] = []
    for state_name, state in sorted(fsm.get("states", {}).items()):
        if state.get("mounts"):
            nodes.extend(
                (_dot_node_id("entrypoint_mount", f"{target_value}_{state_name}_{mount['id']}"), _dot_mount_card(mount))
                for mount in state["mounts"]
            )
        else:
            nodes.append((_dot_node_id("entrypoint_fsm_state", f"{target_value}_{state_name}"), _fsm_state_card(fsm, state_name, state, contract)))
    return nodes


def _fsm_summary_sections(fsm: dict[str, Any], contract: dict[str, Any]) -> list[tuple[str, list[object]]]:
    sections: list[tuple[str, list[object]]] = []
    bindings = _unique_data_bindings(fsm.get("data", []))
    inputs = _format_data_inputs(fsm, bindings, contract)
    queries = [binding["query"] for binding in bindings]
    loads = _format_operation_outputs([binding["operation"] for binding in bindings], contract)
    if inputs:
        sections.append(("input", inputs))
    if queries:
        sections.append(("query", queries))
    if loads:
        sections.append(("load", loads))
    sections.append(("model", [fsm["model"]]))
    sync_ids = [rule["id"] for state in fsm.get("states", {}).values() for rule in state.get("sync", [])]
    if sync_ids:
        sections.append(("sync", sync_ids))
    return sections


def _fsm_state_card(fsm: dict[str, Any], state_name: str, state: dict[str, Any], contract: dict[str, Any]) -> str:
    return _dot_card(
        state_name,
        "fsm state",
        [
            ("copy", state.get("copy", [])),
            ("assets", state.get("assets", [])),
            (_state_field_section_title(fsm, state_name, state), _format_state_fields(fsm, state, contract)),
            ("actions", _format_operation_outputs(state.get("actions", []), contract)),
            ("mounts", _format_mounts(state.get("mounts", []))),
            ("sync", [rule["id"] for rule in state.get("sync", [])]),
        ],
        style=_DOT_STYLE_NEUTRAL,
    )


def _workflow_trigger_card(trigger_kind: str, trigger_value: str, contract: dict[str, Any]) -> str:
    if trigger_kind == "event":
        return _event_card(trigger_value, contract, subtitle="event trigger")
    if trigger_kind == "operation":
        operation = contract["operations"][trigger_value]
        return _dot_card(
            trigger_value,
            "operation trigger",
            _operation_sections(operation, contract),
            basis=operation.get("basis", ""),
            style=_DOT_STYLE_EVENT,
        )
    return _dot_card(trigger_value, f"{trigger_kind} trigger", [], style=_DOT_STYLE_EVENT)


def _workflow_step_card(step: dict[str, Any], contract: dict[str, Any]) -> str:
    operation = contract["operations"][step["operation"]]
    return _dot_card(
        step["id"],
        "workflow step",
        [
            ("operation", [step["operation"]]),
            ("with", [f"{name} {_DOT_ARROW_ASSIGN} {source}" for name, source in sorted(step["with"].items())]),
            ("routes", _workflow_route_lines(step)),
        ] + _operation_sections(operation, contract),
        basis=operation.get("basis", ""),
        style=_DOT_STYLE_NEUTRAL,
    )


def _workflow_route_lines(step: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for outcome_id, route in sorted(step["on"].items()):
        if "complete" in route:
            target = f"complete {_DOT_ARROW_FORWARD} {route['complete']}"
        elif "fail" in route:
            target = f"fail {_DOT_ARROW_FORWARD} {route['fail']}"
        else:
            target = f"next {_DOT_ARROW_FORWARD} {route['next']}"
        details = []
        if "retry" in route:
            retry = route["retry"]
            details.append(f"retry {retry['attempts']} {retry['backoff']}")
        if route.get("dead_letter") is True:
            details.append("dead letter")
        suffix = f" ({', '.join(details)})" if details else ""
        lines.append(f"{outcome_id}: {target}{suffix}")
    return lines


def _workflow_outcome_card(outcome_id: str, outcome: dict[str, Any]) -> str:
    return _dot_card(
        outcome_id,
        f"{outcome['kind']} workflow outcome",
        [("result", [_DotTypedField("result", outcome["result"])])],
        style=_DOT_STYLE_EXTERNAL,
    )


def _event_card(event_id: str, contract: dict[str, Any], *, subtitle: str = "target event") -> str:
    event = contract.get("events", {}).get(event_id, {})
    sections: list[tuple[str, list[object]]] = []
    if event.get("payload"):
        sections.append(("payload", [_DotTypedField("payload", event["payload"])]))
    if event.get("emitted_by"):
        sections.append(("emitted by", event["emitted_by"]))
    return _dot_card(
        event_id,
        subtitle,
        sections,
        basis=event.get("basis", ""),
        style=_DOT_STYLE_EVENT,
    )


def _operation_sections(operation: dict[str, Any], contract: dict[str, Any], *, include_output: bool = True) -> list[tuple[str, list[object]]]:
    sections: list[tuple[str, list[object]]] = []
    for field in ["creates", "reads", "updates", "deletes"]:
        if operation.get(field):
            sections.append((field, operation[field]))
    if operation.get("transition"):
        transition = operation["transition"]
        type_name = effective_field_type(contract["models"][transition["model"]]["fields"][transition["field"]])
        sections.append(
            (
                "transitions",
                [
                    _DotTransitionField(
                        f"{transition['model']}.{transition['field']}",
                        type_name,
                        f"{transition['from']} {_DOT_ARROW_FORWARD} {transition['to']}",
                    )
                ],
            )
        )
    if operation.get("input"):
        sections.append(("input", _typed_fields(operation["input"])))
    if include_output:
        sections.extend(_operation_outcome_sections(operation))
    sections.extend(_operation_emit_sections(operation, contract))
    return sections


def _operation_outcome_sections(operation: dict[str, Any]) -> list[tuple[str, list[object]]]:
    sections: list[tuple[str, list[object]]] = []
    for outcome_id, outcome in sorted(operation["outcomes"].items()):
        sections.append((outcome["kind"], [_DotTypedField(outcome_id, outcome["result"])]))
    return sections


def _operation_emit_sections(operation: dict[str, Any], contract: dict[str, Any]) -> list[tuple[str, list[object]]]:
    sections: list[tuple[str, list[object]]] = []
    for outcome_id, outcome in sorted(operation["outcomes"].items()):
        for event_id in outcome.get("emits", []):
            event_ref = event_id["event"] if isinstance(event_id, dict) else event_id
            sections.append(("emit", [f"{outcome_id} {_DOT_ARROW_FORWARD} {event_ref}"]))
            event = contract.get("events", {}).get(event_ref, {})
            if event.get("payload"):
                sections.append(("payload", [_DotTypedField("payload", event["payload"])]))
    return sections


def _typed_fields(fields: dict[str, str]) -> list[_DotTypedField]:
    return [_DotTypedField(name, type_name) for name, type_name in sorted(fields.items())]


def _target_pair(target: dict[str, str]) -> tuple[str, str]:
    return next(iter(target.items()))


def _target_label(kind: str, value: str) -> str:
    return f"{kind} {value}"


def _format_mounts(mounts: Iterable[dict[str, Any]]) -> list[_DotTypedField]:
    lines: list[_DotTypedField] = []
    for mount in sorted(mounts, key=lambda item: (item["region"], item["id"])):
        lines.append(_DotTypedField(mount["region"], mount["fsm"]))
    return lines


def _dot_mount_card(mount: dict[str, Any]) -> str:
    return _dot_card(
        mount["id"],
        f"{mount['region']} mount",
        [
            ("fsm", [mount["fsm"]]),
            ("initial", [mount["initial"]]),
        ],
        style=_DOT_STYLE_FSM,
    )


def _dot_sync_effect_card(
    effect: dict[str, Any],
    mount_by_id: dict[str, dict[str, Any]],
    contract: dict[str, Any],
) -> str:
    if "send" in effect:
        send = effect["send"]
        return _dot_card(
            send["message"],
            "sent message",
            [
                ("causes", _receiving_transition_refs(send["instance"], send["message"], mount_by_id, contract)),
                ("data", _sent_message_data_lines(send, mount_by_id, contract)),
            ],
            style=_DOT_STYLE_MESSAGE,
        )
    assignment = effect["set"]
    return _dot_card(
        f"set {assignment['context']}",
        "FSM context update",
        [
            ("set", [_format_flow_assignment(assignment["context"], _assignment_value(assignment), identity_scope=None)]),
        ],
        style=_DOT_STYLE_CONTEXT,
    )


def _emitted_message_data_lines(
    instance_id: str,
    emitted: str,
    mount_by_id: dict[str, dict[str, Any]],
    contract: dict[str, Any],
) -> list[_DotTypedField]:
    payload = _message_payload_for_instance(instance_id, "emits", emitted, mount_by_id, contract)
    lines: list[_DotTypedField] = []
    seen: set[str] = set()
    for emit in _emitting_transition_emits(instance_id, emitted, mount_by_id, contract):
        for line in _format_typed_data_flow(emit.get("data", {}), payload):
            signature = str(line)
            if signature not in seen:
                lines.append(line)
                seen.add(signature)
    return lines


def _route_set_lines(rule: dict[str, Any], fsm: dict[str, Any]) -> list[_DotTypedField]:
    lines = []
    context = fsm["context"]
    for effect in rule.get("do", []):
        assignment = effect.get("set")
        if not assignment:
            continue
        target = assignment["context"]
        lines.append(_format_typed_flow_assignment(target, context[target], _assignment_value(assignment), identity_scope=None))
    return lines


def _sent_message_data_lines(
    send: dict[str, Any],
    mount_by_id: dict[str, dict[str, Any]],
    contract: dict[str, Any],
) -> list[_DotTypedField]:
    payload = _message_payload_for_instance(send["instance"], "accepts", send["message"], mount_by_id, contract)
    return _format_typed_data_flow(send.get("data", {}), payload)


def _assignment_value(assignment: dict[str, Any]) -> Any:
    return assignment.get("from", assignment.get("value", ""))


def _message_payload_for_instance(
    instance_id: str,
    direction: str,
    message: str,
    mount_by_id: dict[str, dict[str, Any]],
    contract: dict[str, Any],
) -> dict[str, str]:
    mount = mount_by_id[instance_id]
    fsm = contract["fsms"][mount["fsm"]]
    return fsm["messages"][direction][message]["payload"]


def _emitting_transition_emits(
    instance_id: str,
    emitted: str,
    mount_by_id: dict[str, dict[str, Any]],
    contract: dict[str, Any],
) -> list[dict[str, Any]]:
    mount = mount_by_id[instance_id]
    fsm = contract["fsms"][mount["fsm"]]
    emits = []
    for transition in fsm.get("transitions", []):
        for effect in transition.get("effects", []):
            emit = effect.get("emit")
            if emit and emit["message"] == emitted:
                emits.append(emit)
    return emits


def _emitting_transition_refs(
    instance_id: str,
    emitted: str,
    mount_by_id: dict[str, dict[str, Any]],
    contract: dict[str, Any] | None,
) -> list[str]:
    refs = []
    if not contract:
        return refs
    mount = mount_by_id.get(instance_id)
    if not mount:
        return refs
    fsm = contract.get("fsms", {}).get(mount["fsm"])
    if not fsm:
        return refs
    for transition in fsm.get("transitions", []):
        if any(effect.get("emit", {}).get("message") == emitted for effect in transition.get("effects", [])):
            refs.append(transition["on"])
    return refs


def _receiving_transition_refs(
    instance_id: str,
    message: str,
    mount_by_id: dict[str, dict[str, Any]],
    contract: dict[str, Any] | None,
) -> list[str]:
    if not contract:
        return []
    mount = mount_by_id.get(instance_id)
    if not mount:
        return []
    fsm = contract.get("fsms", {}).get(mount["fsm"])
    if not fsm:
        return []
    target_sources: dict[str, list[str]] = {}
    for transition in fsm.get("transitions", []):
        if transition["on"] == message:
            target_sources.setdefault(transition["to"], []).append(transition["from"])
    if len(target_sources) == 1:
        target = next(iter(target_sources))
        return [f"to {target}"]
    return [f"to {target} (from {', '.join(sorted(sources))})" for target, sources in sorted(target_sources.items())]


def _dot_node_id(prefix: str, value: str) -> str:
    return f"{prefix}_{safe_id(value)}"


def _dot_graph_preamble(graph_id: str) -> list[str]:
    return [
        f"digraph {_dot_quote(graph_id)} {{",
        '  graph [rankdir="LR", bgcolor="transparent", pad="0.25", nodesep="0.38", ranksep="0.85", splines="spline"];',
        f'  node [fontname="{_DOT_FONT}", fontsize="{_DOT_SIZE_DEFAULT_NODE}"];',
        f'  edge [color="{_DOT_COLOR_EDGE}", fontname="{_DOT_FONT}", fontsize="{_DOT_SIZE_BODY}", arrowsize="0.8"];',
    ]


def _dot_circle_node(
    node_id: str,
    label: str,
    *,
    width: str,
    color: str,
    fontcolor: str,
    shape: str = "circle",
) -> str:
    return _dot_plain_node(
        node_id,
        {
            "shape": shape,
            "label": label,
            "width": width,
            "fixedsize": "true",
            "color": color,
            "fontcolor": fontcolor,
            "fontsize": str(_DOT_SIZE_NODE),
        },
    )


def _dot_plain_node(node_id: str, attrs: dict[str, object], indent: str = "  ") -> str:
    return f"{indent}{_dot_quote(node_id)}{_dot_attrs(attrs)};"


def _dot_edge(source: str, target: str, attrs: dict[str, object] | None = None, indent: str = "  ") -> str:
    return f"{indent}{_dot_quote(source)} -> {_dot_quote(target)}{_dot_attrs(attrs or {})};"


def _dot_invisible_order(node_ids: list[str], indent: str) -> list[str]:
    return [
        _dot_edge(source, target, {"style": "invis", "weight": "100"}, indent=indent)
        for source, target in zip(node_ids, node_ids[1:])
    ]


class _DotHtml(str):
    pass


class _DotTypedField:
    def __init__(self, field: str, type_name: Any, source: str | None = None) -> None:
        self.field = field
        self.type_name = type_display(type_name)
        self.source = source

    def __str__(self) -> str:
        suffix = f" {_DOT_ARROW_ASSIGN} {self.source}" if self.source is not None else ""
        return f"{self.field} {self.type_name}{suffix}"


class _DotTransitionField:
    def __init__(self, field: str, type_name: Any, change: str) -> None:
        self.field = field
        self.type_name = type_display(type_name)
        self.change = change

    def __str__(self) -> str:
        return f"{self.field} {self.type_name} {self.change}"


def _dot_html_node(node_id: str, label: str, attrs: dict[str, object] | None = None, indent: str = "  ") -> str:
    node_attrs: dict[str, object] = {"shape": "plain", "label": _DotHtml(label)}
    node_attrs.update(attrs or {})
    return _dot_plain_node(node_id, node_attrs, indent=indent)


def _dot_card(
    title: str,
    subtitle: str | None,
    sections: Iterable[tuple[str, Iterable[object]]],
    *,
    basis: str | None = None,
    style: _DotCardStyle = _DOT_STYLE_NEUTRAL,
) -> str:
    header_bg = style.header_bg
    border = style.border
    rows = [
        f'<TR><TD BGCOLOR="{border}" HEIGHT="3" FIXEDSIZE="false"></TD></TR>',
        _dot_header_row(title, subtitle, header_bg=header_bg),
    ]
    if basis:
        rows.extend(_dot_text_rows(_wrap_dot_text(basis, width=50), point_size=_DOT_SIZE_BODY, italic=True, color=_DOT_COLOR_AUDIT_TEXT))
    rows.extend(_dot_section_rows(sections))
    return (
        f'<TABLE BORDER="1" CELLBORDER="0" CELLSPACING="0" CELLPADDING="4" COLOR="{border}" BGCOLOR="#ffffff">'
        + "".join(rows)
        + "</TABLE>"
    )


def _dot_header_row(title: str, subtitle: str | None, *, header_bg: str) -> str:
    header_rows = [
        f'<TR><TD ALIGN="LEFT"><FONT POINT-SIZE="{_DOT_SIZE_TITLE}"><B>{_dot_html_text(title)}</B></FONT></TD></TR>',
    ]
    if subtitle:
        header_rows.extend(
            f'<TR><TD ALIGN="LEFT"><FONT POINT-SIZE="{_DOT_SIZE_META}" COLOR="{_DOT_COLOR_MUTED}">{_dot_html_text(line)}</FONT></TD></TR>'
            for line in _wrap_dot_text(subtitle)
        )
    header = (
        '<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="0" CELLPADDING="0">'
        + "".join(header_rows)
        + "</TABLE>"
    )
    return (
        f'<TR><TD BGCOLOR="{header_bg}" ALIGN="LEFT">'
        f"{header}</TD></TR>"
    )


def _dot_text_rows(lines: Iterable[str], *, point_size: int, italic: bool = False, color: str | None = None) -> list[str]:
    inner_rows = []
    font_attrs = [f'POINT-SIZE="{point_size}"']
    if color:
        font_attrs.append(f'COLOR="{color}"')
    open_font = "<FONT " + " ".join(font_attrs) + ">"
    for line in lines:
        text = _dot_html_text(line)
        if italic:
            text = f"<I>{text}</I>"
        inner_rows.append(f'<TR><TD ALIGN="LEFT">{open_font}{text}</FONT></TD></TR>')
    if not inner_rows:
        return []
    return [_dot_nested_rows(inner_rows)]


def _dot_section_rows(sections: Iterable[tuple[str, Iterable[object]]]) -> list[str]:
    rows: list[str] = []
    compact_rows: list[str] = []
    for title, values in sections:
        section = _dot_section_inner_rows(title, values)
        if not section:
            continue
        is_compact, inner_rows = section
        if is_compact:
            compact_rows.extend(inner_rows)
            continue
        if compact_rows:
            rows.append(_dot_nested_rows(compact_rows, cell_spacing=1))
            compact_rows = []
        rows.append(_dot_nested_rows(inner_rows))
    if compact_rows:
        rows.append(_dot_nested_rows(compact_rows, cell_spacing=1))
    return rows


def _dot_section_inner_rows(title: str, values: Iterable[object]) -> tuple[bool, list[str]] | None:
    values = list(values)
    if values and all(isinstance(value, _DotTransitionField) for value in values):
        return _dot_transition_field_section_inner_rows(title, values)
    if values and all(isinstance(value, _DotTypedField) for value in values):
        return _dot_typed_field_section_inner_rows(title, values)
    wrapped_values = [wrapped for value in values if (wrapped := _wrap_dot_text(value))]
    if not wrapped_values:
        return None
    inner_rows: list[str] = []
    is_compact = len(wrapped_values) == 1 and len(wrapped_values[0]) == 1
    if len(wrapped_values) == 1:
        wrapped = wrapped_values[0]
        inner_rows.append(_dot_key_value_row(title, wrapped[0]))
        for line in wrapped[1:]:
            inner_rows.append(_dot_key_value_row("", line))
        return is_compact, inner_rows
    for wrapped in wrapped_values:
        if not inner_rows:
            inner_rows.append(f'<TR><TD ALIGN="LEFT"><FONT POINT-SIZE="{_DOT_SIZE_BODY}"><B>{_dot_html_text(title)}</B></FONT></TD></TR>')
        inner_rows.append(f'<TR><TD ALIGN="LEFT"><FONT POINT-SIZE="{_DOT_SIZE_BODY}">{_dot_html_text(wrapped[0])}</FONT></TD></TR>')
        for line in wrapped[1:]:
            inner_rows.append(f'<TR><TD ALIGN="LEFT"><FONT POINT-SIZE="{_DOT_SIZE_BODY}">{_dot_html_text(line)}</FONT></TD></TR>')
    return False, inner_rows


def _dot_typed_field_section_inner_rows(title: str, values: list[object]) -> tuple[bool, list[str]]:
    if (title in {"input", "output", "payload", "data", "set", "load"} or title == "actions") and len(values) == 1:
        rows = []
        for index, value in enumerate(values):
            if isinstance(value, _DotTypedField):
                rows.append(_dot_typed_field_key_value_row(title if index == 0 else "", value))
        return True, rows
    inner_rows = [f'<TR><TD ALIGN="LEFT"><FONT POINT-SIZE="{_DOT_SIZE_BODY}"><B>{_dot_html_text(title)}</B></FONT></TD></TR>']
    inner_rows.extend(_dot_typed_field_row(value) for value in values if isinstance(value, _DotTypedField))
    return False, inner_rows


def _dot_transition_field_section_inner_rows(title: str, values: list[object]) -> tuple[bool, list[str]]:
    inner_rows = [f'<TR><TD ALIGN="LEFT"><FONT POINT-SIZE="{_DOT_SIZE_BODY}"><B>{_dot_html_text(title)}</B></FONT></TD></TR>']
    inner_rows.extend(_dot_transition_field_row(value) for value in values if isinstance(value, _DotTransitionField))
    return False, inner_rows


def _dot_transition_field_row(value: _DotTransitionField) -> str:
    return (
        '<TR><TD ALIGN="LEFT" VALIGN="MIDDLE" HEIGHT="11">'
        f'<FONT POINT-SIZE="{_DOT_SIZE_BODY}">{_dot_html_text(value.field)}</FONT>'
        f'<FONT POINT-SIZE="{_DOT_SIZE_META}" COLOR="{_DOT_COLOR_TYPE}">&#160;&#160;{_dot_html_text(value.type_name)}</FONT>'
        f'<FONT POINT-SIZE="{_DOT_SIZE_META}">&#160;&#160;{_dot_html_text(value.change)}</FONT>'
        "</TD></TR>"
    )


def _dot_typed_field_row(value: _DotTypedField) -> str:
    source = _dot_typed_field_source(value)
    return (
        '<TR><TD ALIGN="LEFT" VALIGN="MIDDLE" HEIGHT="11">'
        f'<FONT POINT-SIZE="{_DOT_SIZE_BODY}">{_dot_html_text(value.field)}</FONT>'
        f'<FONT POINT-SIZE="{_DOT_SIZE_META}" COLOR="{_DOT_COLOR_TYPE}">&#160;&#160;{_dot_html_text(value.type_name)}</FONT>'
        f"{source}"
        "</TD></TR>"
    )


def _dot_typed_field_key_value_row(title: str, value: _DotTypedField) -> str:
    key = f"<B>{_dot_html_text(title)}:</B>&#160;&#160;" if title else "&#160;&#160;"
    source = _dot_typed_field_source(value)
    return (
        '<TR><TD ALIGN="LEFT" VALIGN="MIDDLE" HEIGHT="11">'
        f'<FONT POINT-SIZE="{_DOT_SIZE_BODY}">{key}{_dot_html_text(value.field)}</FONT>'
        f'<FONT POINT-SIZE="{_DOT_SIZE_META}" COLOR="{_DOT_COLOR_TYPE}">&#160;&#160;{_dot_html_text(value.type_name)}</FONT>'
        f"{source}"
        "</TD></TR>"
    )


def _dot_typed_field_source(value: _DotTypedField) -> str:
    if value.source is None:
        return ""
    return f'<FONT POINT-SIZE="{_DOT_SIZE_META}">&#160;{_DOT_ARROW_ASSIGN}&#160;{_dot_html_text(value.source)}</FONT>'


def _dot_key_value_text(title: str, value: str) -> str:
    key = f"<B>{_dot_html_text(title)}:</B>&#160;&#160;" if title else "&#160;&#160;"
    return f"{key}{_dot_html_text(value)}"


def _dot_key_value_row(title: str, value: str) -> str:
    return (
        f'<TR><TD ALIGN="LEFT" VALIGN="MIDDLE" HEIGHT="11"><FONT POINT-SIZE="{_DOT_SIZE_BODY}">'
        f"{_dot_key_value_text(title, value)}</FONT></TD></TR>"
    )


def _dot_nested_rows(inner_rows: list[str], *, cell_spacing: int = 0) -> str:
    inner = (
        f'<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="{cell_spacing}" CELLPADDING="0">'
        + "".join(inner_rows)
        + "</TABLE>"
    )
    return f'<TR><TD ALIGN="LEFT">{inner}</TD></TR>'


def _wrap_dot_text(value: object, width: int = 58) -> list[str]:
    text = str(value)
    if not text:
        return []
    chunks: list[str] = []
    for chunk in textwrap.wrap(text, width=width, break_long_words=False, break_on_hyphens=False):
        if len(chunk) <= width:
            chunks.append(chunk)
        else:
            chunks.extend(_wrap_dot_token(chunk, width))
    if chunks:
        return chunks
    return _wrap_dot_token(text, width)


def _wrap_dot_token(text: str, width: int) -> list[str]:
    if len(text) <= width:
        return [text]
    parts = text.split(".")
    lines: list[str] = []
    current = ""
    for part in parts:
        candidate = part if not current else f"{current}.{part}"
        if len(candidate) <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = part
    if current:
        lines.append(current)
    return lines or [text]


def _format_data_flow(mapping: dict[str, Any], *, identity_scope: str | None = "message") -> list[str]:
    return [_format_flow_assignment(key, value, identity_scope=identity_scope) for key, value in sorted(mapping.items())]


def _format_typed_data_flow(
    mapping: dict[str, Any],
    field_types: dict[str, str],
    *,
    identity_scope: str | None = "message",
) -> list[_DotTypedField]:
    return [
        _format_typed_flow_assignment(key, field_types[key], value, identity_scope=identity_scope)
        for key, value in sorted(mapping.items())
    ]


def _format_typed_flow_assignment(
    target: str,
    type_name: Any,
    value: Any,
    *,
    identity_scope: str | None = "message",
) -> _DotTypedField:
    source = _format_flow_source(value)
    if identity_scope and source == f"{identity_scope}.{target}":
        return _DotTypedField(target, type_name)
    if source.startswith("message."):
        source = source[len("message.") :]
    return _DotTypedField(target, type_name, source)


def _format_flow_assignment(target: str, value: Any, *, identity_scope: str | None = "message") -> str:
    source = _format_flow_source(value)
    if identity_scope and source == f"{identity_scope}.{target}":
        return target
    if source.startswith("message."):
        source = source[len("message.") :]
    return f"{target} {_DOT_ARROW_ASSIGN} {source}"


def _format_flow_source(value: Any) -> str:
    if isinstance(value, str) and value.startswith("$"):
        return value[1:]
    return _format_scalar(value)


def _format_transition_sections(
    fsm: dict[str, Any], transition: dict[str, Any], contract: dict[str, Any]
) -> list[tuple[str, list[object]]]:
    sections: list[tuple[str, list[object]]] = []
    if _is_data_event(transition["on"]):
        bindings = _transition_data_bindings(fsm, transition)
        data_sources = _format_operation_outputs([binding["operation"] for binding in bindings], contract)
        queries = [binding["query"] for binding in bindings]
        inputs = _format_data_inputs(fsm, bindings, contract)
        if inputs:
            sections.append(("input", inputs))
        if queries:
            sections.append(("query", queries))
        if data_sources:
            sections.append(("load", data_sources))
    else:
        target_bindings = _transition_target_data_bindings(fsm, transition)
        data_sources = _format_operation_outputs([binding["operation"] for binding in target_bindings], contract)
        queries = [binding["query"] for binding in target_bindings]
        required_context = _format_data_inputs(fsm, target_bindings, contract)
        if required_context:
            sections.append(("input", required_context))
        if queries:
            sections.append(("query", queries))
        if data_sources:
            sections.append(("load", data_sources))
    sections.extend(_format_transition_effect_sections(fsm, transition))
    return sections


def _transition_target_data_bindings(fsm: dict[str, Any], transition: dict[str, Any]) -> list[dict[str, Any]]:
    target_state = fsm.get("states", {}).get(transition["to"], {})
    return _unique_data_bindings(target_state.get("data", []))


def _state_field_section_title(fsm: dict[str, Any], state_name: str, state: dict[str, Any]) -> str:
    operations = [binding["operation"] for binding in _state_field_data_bindings(fsm, state_name, state) if binding.get("operation")]
    unique = sorted(dict.fromkeys(operations))
    if len(unique) == 1:
        return f"{unique[0]} fields"
    if unique:
        return "data fields"
    return f"{fsm['model']} fields"


def _state_field_data_bindings(fsm: dict[str, Any], state_name: str, state: dict[str, Any]) -> list[dict[str, Any]]:
    bindings = _unique_data_bindings(state.get("data", []))
    if bindings:
        return bindings
    incoming_data_bindings: list[dict[str, Any]] = []
    for transition in fsm.get("transitions", []):
        if transition["to"] == state_name and _is_data_event(transition["on"]):
            incoming_data_bindings.extend(_transition_data_bindings(fsm, transition))
    if incoming_data_bindings:
        return _unique_data_bindings(incoming_data_bindings)
    return _unique_data_bindings(fsm.get("data", []))


def _format_state_fields(fsm: dict[str, Any], state: dict[str, Any], contract: dict[str, Any]) -> list[_DotTypedField]:
    model_fields = contract["models"][fsm["model"]]["fields"]
    return [_DotTypedField(field, effective_field_type(model_fields[field])) for field in state["fields"]]


def _format_operation_outputs(operation_ids: Iterable[str], contract: dict[str, Any]) -> list[_DotTypedField]:
    operations = contract["operations"]
    fields: list[_DotTypedField] = []
    for operation_id in operation_ids:
        for _, outcome in sorted(operations[operation_id]["outcomes"].items()):
            if outcome["kind"] == "success":
                fields.append(_DotTypedField(operation_id, outcome["result"]))
    return fields


def _format_data_inputs(
    fsm: dict[str, Any], bindings: Iterable[dict[str, Any]], contract: dict[str, Any]
) -> list[_DotTypedField]:
    context = fsm.get("context", {})
    operations = contract["operations"]
    inputs: list[_DotTypedField] = []
    seen: set[str] = set()
    for binding in bindings:
        operation = operations[binding["operation"]]
        for key in sorted(operation["input"]):
            signature = f"{key} {context[key]}"
            if signature not in seen:
                inputs.append(_DotTypedField(key, context[key]))
                seen.add(signature)
    return inputs


def _is_data_event(event: str) -> bool:
    return event.startswith("data.")


def _transition_data_bindings(fsm: dict[str, Any], transition: dict[str, Any]) -> list[dict[str, Any]]:
    source_state = fsm.get("states", {}).get(transition["from"], {})
    bindings = source_state.get("data", []) or fsm.get("data", [])
    return _unique_data_bindings(bindings)


def _unique_data_bindings(bindings: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    seen: set[tuple[Any, Any]] = set()
    for binding in bindings:
        key = (binding.get("operation"), binding.get("query"))
        if key not in seen:
            unique.append(binding)
            seen.add(key)
    return unique


def _format_transition_effect_sections(fsm: dict[str, Any], transition: dict[str, Any]) -> list[tuple[str, list[object]]]:
    sections: list[tuple[str, list[object]]] = []
    for effect in transition.get("effects", []):
        if "emit" in effect:
            emit = effect["emit"]
            sections.append(("emit", [emit["message"]]))
            payload_types = fsm["messages"]["emits"][emit["message"]]["payload"]
            payload = _format_typed_data_flow(emit.get("data", {}), payload_types)
            if payload:
                sections.append(("payload", payload))
        elif "set" in effect:
            assignment = effect["set"]
            target = assignment["context"]
            sections.append((
                "set",
                [_format_typed_flow_assignment(target, fsm["context"][target], _assignment_value(assignment), identity_scope=None)],
            ))
    return sections


def _format_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def _dot_attrs(attrs: dict[str, object]) -> str:
    return " [" + ", ".join(f"{name}={_dot_attr_value(value)}" for name, value in attrs.items()) + "]"


def _dot_attr_value(value: object) -> str:
    if isinstance(value, _DotHtml):
        return f"<{value}>"
    return _dot_quote(value)


def _dot_html_text(value: object) -> str:
    return html.escape(str(value), quote=False)


def _dot_quote(value: object) -> str:
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def audit_html_document(
    contract: dict[str, Any],
    body: str,
    *,
    fsm_surface_ids: Iterable[str] | None = None,
    composition_ids: Iterable[str] | None = None,
) -> str:
    css = fsm_styles_projection(contract, surface_ids=fsm_surface_ids, composition_ids=composition_ids)
    extra_css = """
    body { margin: 0; font-family: ui-sans-serif, system-ui, sans-serif; background: #f7f7f8; color: #171717; }
    main { padding: 24px; }
    .contract-fsm-surface, .contract-fsm-composition { background: white; border: 1px solid #d0d0d0; border-radius: 12px; padding: 16px; box-sizing: border-box; }
    .contract-fsm-composition { display: grid; grid-template-columns: minmax(180px, 1fr) minmax(280px, 2fr) minmax(180px, 1fr); gap: 16px; max-width: none; }
    .contract-layout-region { min-height: 120px; display: grid; gap: 12px; align-content: start; }
    .audit-records { display: grid; gap: 0.75rem; }
    .audit-record { border: 1px solid #e4e4e7; border-radius: 10px; padding: 0.75rem; display: grid; gap: 0.35rem; }
    .audit-field { display: grid; gap: 0.15rem; }
    .audit-field-label { color: #52525b; font-size: 0.75rem; }
    .audit-field-value { font-weight: 600; }
    img.audit-asset { max-width: 100%; height: auto; border-radius: 8px; }
    button { padding: 0.5rem 0.75rem; border: 1px solid #222; border-radius: 6px; background: #fff; justify-self: start; }
    @media (max-width: 700px) { .contract-fsm-composition { grid-template-columns: 1fr; } }
    """
    return "\n".join([
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        "<title>spec audit render</title>",
        "<style>", css, extra_css, "</style>",
        "</head>",
        "<body>",
        "<main>",
        body,
        "</main>",
        "</body>",
        "</html>",
    ])


def render_audit_case_html(root: Path, contract: dict[str, Any], case_id: str, case: dict[str, Any]) -> str:
    fsm = contract["fsms"][case["fsm"]]
    state = fsm["states"][case["state"]]
    if state.get("mounts"):
        return render_composed_case_html(root, contract, case)
    projection = fsms_projection(contract)
    fsm = next(item for item in projection["fsms"] if item["owner_kind"] == "fsm" and item["owner"] == case["fsm"] and item["state"] == case["state"])
    return render_fsm_audit_html(root, contract, fsm, case)


def case_render_fsms(contract: dict[str, Any], case: dict[str, Any]) -> list[dict[str, Any]]:
    projection = fsms_projection(contract)
    fsm = contract["fsms"][case["fsm"]]
    state = fsm["states"][case["state"]]
    if state.get("mounts"):
        fsms = []
        for mount in state["mounts"]:
            state_name = case["instances"][mount["id"]]["state"]
            fsms.append(next(item for item in projection["fsms"] if item["owner_kind"] == "fsm" and item["owner"] == mount["fsm"] and item["state"] == state_name))
        return fsms
    return [next(item for item in projection["fsms"] if item["owner_kind"] == "fsm" and item["owner"] == case["fsm"] and item["state"] == case["state"])]


def _case_composition_ids(contract: dict[str, Any], case: dict[str, Any]) -> set[str]:
    state = contract["fsms"][case["fsm"]]["states"][case["state"]]
    if state.get("mounts"):
        return {f"{case['fsm']}.{case['state']}"}
    return set()


def render_composed_case_html(root: Path, contract: dict[str, Any], case: dict[str, Any]) -> str:
    fsm = contract["fsms"][case["fsm"]]
    state = fsm["states"][case["state"]]
    projection = fsms_projection(contract)
    composition = next(item for item in projection["compositions"] if item["fsm"] == case["fsm"] and item["state"] == case["state"])
    html_layout = layout_html(composition["layout"])
    root_spec = html_layout.get("root") or {"element": "section"}
    tag = root_spec.get("element", "section")
    classes = " ".join(["contract-fsm-composition"] + root_spec.get("classes", []))
    attrs = {"class": classes, "data-contract-composition": composition["id"]}
    if root_spec.get("role") and root_spec["role"] != "none":
        attrs["role"] = root_spec["role"]
    parts = [f"<{tag}{format_attrs(attrs)}>"]
    for region_name, region in sorted(layout_html_regions(state["layout"]).items(), key=lambda item: item[1].get("order", 0)):
        region_tag = region.get("element", "div")
        region_classes = " ".join(["contract-layout-region", f"contract-layout-region--{region_name}"] + region.get("classes", []))
        region_attrs = {"class": region_classes, "data-layout-region": region_name, "data-required": str(region["required"]).lower()}
        if region.get("role") and region["role"] != "none":
            region_attrs["role"] = region["role"]
        parts.append(f"<{region_tag}{format_attrs(region_attrs)}>")
        for mount in [item for item in state["mounts"] if item["region"] == region_name]:
            state_name = case["instances"][mount["id"]]["state"]
            fsm = next(item for item in projection["fsms"] if item["owner_kind"] == "fsm" and item["owner"] == mount["fsm"] and item["state"] == state_name)
            parts.append(render_fsm_audit_html(root, contract, fsm, case))
        parts.append(f"</{region_tag}>")
    parts.append(f"</{tag}>")
    return "\n".join(parts)


def render_fsm_audit_html(root: Path, contract: dict[str, Any], fsm: dict[str, Any], case: dict[str, Any] | None) -> str:
    presentation = fsm.get("presentation") or {}
    html_contract = presentation.get("html") or {}
    root_spec = html_contract.get("root") or {"element": "section"}
    tag = root_spec.get("element", "section")
    classes = " ".join(["contract-fsm-surface"] + root_spec.get("classes", []))
    attrs = {
        "class": classes,
        "data-contract-fsm-surface": fsm["id"],
        "data-contract-state": fsm["state"],
    }
    if root_spec.get("role") and root_spec["role"] != "none":
        attrs["role"] = root_spec["role"]
    lines = [f"<{tag}{format_attrs(attrs)}>"]
    slots = html_contract.get("slots") or default_html_slots(fsm)
    field_slots = [slot for slot in slots if slot["kind"] == "field"]
    for slot in slots:
        if slot["kind"] == "field":
            continue
        records = records_for_fsm(contract, fsm, case)
        record = records[0] if records else {}
        context = render_context(contract, case)
        namespace = render_namespace(contract, case)
        lines.extend(render_html_slot_runtime(root, contract, fsm, slot, record, context, namespace))
    if field_slots:
        records = records_for_fsm(contract, fsm, case)
        lines.append('<div class="audit-records">')
        for record in records[:4] or [{}]:
            lines.append('<article class="audit-record">')
            for slot in field_slots:
                lines.extend(render_html_field_slot(record, slot))
            lines.append('</article>')
        lines.append('</div>')
    lines.append(f"</{tag}>")
    return "\n".join(lines)


def render_html_slot_runtime(root: Path, contract: dict[str, Any], fsm: dict[str, Any], slot: dict[str, Any], record: dict[str, Any], context: dict[str, Any], namespace: dict[str, Any]) -> list[str]:
    kind = slot["kind"]
    tag = slot["element"]
    classes = slot.get("classes", [])
    attrs: dict[str, str] = {"data-contract-slot": slot.get("slot", slot.get("ref", "action"))}
    if classes:
        attrs["class"] = " ".join(classes)
    if slot.get("role") and slot["role"] != "none":
        attrs["role"] = slot["role"]
    if kind == "copy":
        copy_ref = slot_ref(fsm, "copy", slot["slot"])
        attrs["data-copy"] = copy_ref
        if slot.get("level"):
            attrs["aria-level"] = str(slot["level"])
        text = resolve_copy_text(root, contract, copy_ref, record, context, namespace)
        return [f"<{tag}{format_attrs(attrs)}>{html.escape(text)}</{tag}>"]
    if kind == "asset":
        asset_ref = slot_ref(fsm, "asset", slot["slot"])
        attrs["data-asset"] = asset_ref
        if slot.get("alt_copy_slot"):
            attrs["data-alt-copy"] = slot_ref(fsm, "copy", slot["alt_copy_slot"])
        asset_result = resolve_asset_result(root, contract, asset_ref, record, context, namespace)
        label = asset_result.alt or contract["assets"][asset_ref]["placeholder"]["label"]
        if tag == "img":
            attrs.setdefault("alt", label)
            svg = asset_result.body
            attrs.setdefault("src", "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii"))
            attrs.setdefault("class", (attrs.get("class", "") + " audit-asset").strip())
            return [f"<img{format_attrs(attrs)}>"]
        return [f"<{tag}{format_attrs(attrs)} aria-label={html.escape(label, quote=True)!r}></{tag}>"]
    action = slot["ref"]
    attrs["data-action"] = action
    if tag == "a":
        attrs.setdefault("href", "#")
    if tag == "button":
        attrs.setdefault("type", "button")
    return [f"<{tag}{format_attrs(attrs)}>{html.escape(humanize(action))}</{tag}>"]


def render_html_field_slot(record: dict[str, Any], slot: dict[str, Any]) -> list[str]:
    tag = slot["element"]
    field = slot["slot"]
    attrs: dict[str, str] = {"class": "audit-field", "data-contract-slot": field, "data-field": field}
    if slot.get("classes"):
        attrs["class"] += " " + " ".join(slot["classes"])
    if slot.get("role") and slot["role"] != "none":
        attrs["role"] = slot["role"]
    label = slot.get("label") or humanize(field)
    value = record.get(field, "—")
    return [
        f"<{tag}{format_attrs(attrs)}>",
        f'<span class="audit-field-label">{html.escape(label)}</span>',
        f'<span class="audit-field-value">{html.escape(str(value))}</span>',
        f"</{tag}>",
    ]


def slot_ref(fsm: dict[str, Any], kind: str, slot: str) -> str:
    key = "copy" if kind == "copy" else "assets"
    for ref in fsm["slots"][key]:
        if ref.rsplit(".", 1)[-1] == slot:
            return ref
    raise KeyError(f"{fsm['id']} has no {kind} slot {slot}")


def textual_audit_lines(root: Path, contract: dict[str, Any], case_id: str, case: dict[str, Any]) -> list[tuple[str, str]]:
    projection = fsms_projection(contract)
    fsm = contract["fsms"][case["fsm"]]
    state = fsm["states"][case["state"]]
    lines: list[tuple[str, str]] = []
    if state.get("mounts"):
        for mount in state["mounts"]:
            state_name = case["instances"][mount["id"]]["state"]
            fsm = next(item for item in projection["fsms"] if item["owner_kind"] == "fsm" and item["owner"] == mount["fsm"] and item["state"] == state_name)
            lines.extend(fsm_textual_lines(root, contract, fsm, case))
    else:
        fsm = next(item for item in projection["fsms"] if item["owner_kind"] == "fsm" and item["owner"] == case["fsm"] and item["state"] == case["state"])
        lines.extend(fsm_textual_lines(root, contract, fsm, case))
    return lines or [("static", " ")]


def fsm_textual_lines(root: Path, contract: dict[str, Any], fsm: dict[str, Any], case: dict[str, Any] | None) -> list[tuple[str, str]]:
    lines: list[tuple[str, str]] = []
    textual = (fsm.get("presentation") or {}).get("textual") or {}
    widgets = textual.get("widgets") or []
    if widgets:
        records = records_for_fsm(contract, fsm, case)
        record = records[0] if records else {}
        context = render_context(contract, case)
        namespace = render_namespace(contract, case)
        for widget in widgets:
            bind_kind, bind_value = next(iter(widget["bind"].items()))
            if bind_kind == "copy":
                ref = slot_ref(fsm, "copy", bind_value)
                lines.append(("static", resolve_copy_text(root, contract, ref, record, context, namespace)))
            elif bind_kind == "asset":
                ref = slot_ref(fsm, "asset", bind_value)
                lines.append(("static", resolve_asset_result(root, contract, ref, record, context, namespace).alt or contract["assets"][ref]["placeholder"]["label"]))
            elif bind_kind == "field":
                lines.append(("static", str(record.get(bind_value, "—"))))
            elif bind_kind == "action":
                lines.append(("button", humanize(bind_value)))
            elif bind_kind == "literal":
                lines.append(("static", str(bind_value)))
        return lines
    records = records_for_fsm(contract, fsm, case)
    record = records[0] if records else {}
    context = render_context(contract, case)
    namespace = render_namespace(contract, case)
    for copy_ref in fsm["slots"]["copy"]:
        lines.append(("static", resolve_copy_text(root, contract, copy_ref, record, context, namespace)))
    for asset_ref in fsm["slots"]["assets"]:
        lines.append(("static", resolve_asset_result(root, contract, asset_ref, record, context, namespace).alt or contract["assets"][asset_ref]["placeholder"]["label"]))
    fields = fsm["slots"].get("fields", [])
    if fields:
        for record in (records_for_fsm(contract, fsm, case)[:4] or [{}]):
            for field in fields:
                lines.append(("static", f"{humanize(field)}: {record.get(field, '—')}"))
    for action in fsm["slots"]["actions"]:
        lines.append(("button", humanize(action)))
    return lines or [("static", " ")]


def records_for_fsm(contract: dict[str, Any], fsm: dict[str, Any], case: dict[str, Any] | None) -> list[dict[str, Any]]:
    model_id = fsm_model(contract, fsm)
    model_key = f"{model_id.lower()}_id"
    owner_context = fsm_owner_context(contract, fsm)
    fixtures = case.get("fixtures", []) if case else sorted(contract.get("fixtures", {}))
    records: list[dict[str, Any]] = []
    if case:
        namespace = fixture_namespace(contract, fixtures)
        records.extend(_find_model_records(namespace, model_id))
        records = _apply_fact_uses(contract, case.get("facts", []), namespace, model_id, records)
        context = _resolved_case_context(contract, case, namespace)
    else:
        context = {}
        for fixture_id in fixtures:
            records.extend(_find_model_records(contract["fixtures"][fixture_id]["values"], model_id))
        records = _apply_facts_with_available_fixtures(contract, model_id, records)
    selected_id = context.get(model_key)
    if not selected_id and model_key in owner_context:
        selected_id = context.get(f"selected_{model_key}")
    if selected_id and model_key in owner_context:
        selected = [record for record in records if record.get("id") == selected_id]
        if selected:
            return selected
    if model_key in owner_context and records:
        return records[:1]
    return records


def fsm_model(contract: dict[str, Any], fsm: dict[str, Any]) -> str:
    return contract["fsms"][fsm["owner"]]["model"]


def fsm_owner_context(contract: dict[str, Any], fsm: dict[str, Any]) -> dict[str, Any]:
    return contract["fsms"][fsm["owner"]].get("context", {})


def _resolved_case_context(contract: dict[str, Any], case: dict[str, Any], namespace: dict[str, Any]) -> dict[str, Any]:
    context = {}
    for key, value in (case.get("context") or {}).items():
        context[key] = resolve(value, namespace)
    return context


def _find_model_records(value: Any, model_id: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if value.get("model") == model_id:
            record = dict(value)
            record.pop("model", None)
            records.append(record)
        for child in value.values():
            records.extend(_find_model_records(child, model_id))
    elif isinstance(value, list):
        for item in value:
            records.extend(_find_model_records(item, model_id))
    return records


def _apply_facts_with_available_fixtures(contract: dict[str, Any], model_id: str, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    current = list(records)
    namespaces = [{}]
    for fixture_id in sorted(contract.get("fixtures", {})):
        try:
            namespaces.append(fixture_namespace(contract, [fixture_id]))
        except (AssertionError, KeyError, TypeError):
            continue
    for fact_id in sorted(contract.get("facts", {})):
        fact_uses = [{"use": fact_id}]
        for namespace in namespaces:
            try:
                next_records = _apply_fact_uses(contract, fact_uses, namespace, model_id, current)
            except (AssertionError, KeyError, TypeError):
                continue
            current = _dedupe_records(next_records)
            break
    return current


def _apply_fact_uses(contract: dict[str, Any], fact_uses: list[dict[str, str]], namespace: dict[str, Any], model_id: str, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    current = list(records)
    for fact_use in fact_uses:
        fact_id = fact_use["use"]
        kind, body = _fact_selector(contract["facts"][fact_id], fact_id)
        if body["model"] != model_id:
            continue
        if kind == "present":
            current.append(resolve(body["values"], namespace))
        elif kind == "absent":
            where = resolve(body["where"], namespace)
            current = [record for record in current if not _record_matches(record, where)]
    return _dedupe_records(current)


def _fact_selector(fact: dict[str, Any], fact_id: str) -> tuple[str, dict[str, Any]]:
    items = [(key, fact[key]) for key in ("absent", "present") if key in fact]
    if len(items) != 1:
        raise ContractError(f"Fact {fact_id} must contain exactly one fact selector")
    return items[0]


def _record_matches(record: dict[str, Any], where: dict[str, Any]) -> bool:
    return all(record.get(key) == value for key, value in where.items())


def _dedupe_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in records:
        key = json.dumps(record, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(record)
    return deduped


def render_namespace(contract: dict[str, Any], case: dict[str, Any] | None) -> dict[str, Any]:
    if case:
        return fixture_namespace(contract, case.get("fixtures", []))
    return {}


def render_context(contract: dict[str, Any], case: dict[str, Any] | None) -> dict[str, Any]:
    if not case:
        return {}
    namespace = render_namespace(contract, case)
    return _resolved_case_context(contract, case, namespace)


def content_args(contract: dict[str, Any], ref: str, item: dict[str, Any], record: dict[str, Any], context: dict[str, Any], namespace: dict[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for name in item.get("args", {}):
        if name in record:
            values[name] = record[name]
        elif name in context:
            values[name] = context[name]
        elif name in namespace:
            values[name] = namespace[name]
        else:
            raise ContractError(f"Cannot bind content arg {ref}.{name} from record, render context, or fixtures")
    return values


def resolve_copy_text(root: Path, contract: dict[str, Any], ref: str, record: dict[str, Any], context: dict[str, Any], namespace: dict[str, Any]) -> str:
    item = contract["copies"][ref]
    resolver = item.get("resolver")
    if not resolver:
        text = item["placeholder"]
    else:
        try:
            text = call_copy(root, ref, content_args(contract, ref, item, record, context, namespace), ContentContext(surface="audit"))
        except ContentError as exc:
            raise ContractError(str(exc)) from exc
    max_chars = item.get("max_chars")
    if max_chars is not None and len(text) > max_chars:
        raise ContractError(f"Copy resolver {ref} exceeds max_chars")
    if not text.strip():
        raise ContractError(f"Copy resolver {ref} returned empty text")
    return text


def resolve_asset_result(root: Path, contract: dict[str, Any], ref: str, record: dict[str, Any], context: dict[str, Any], namespace: dict[str, Any]) -> AssetResult:
    item = contract["assets"][ref]
    resolver = item.get("resolver")
    if not resolver:
        return AssetResult(mime_type="image/svg+xml", body=asset_placeholder_svg(item), alt=item["placeholder"]["label"])
    try:
        result = call_asset(root, ref, content_args(contract, ref, item, record, context, namespace), ContentContext(surface="audit"))
    except ContentError as exc:
        raise ContractError(str(exc)) from exc
    if result.mime_type != "image/svg+xml":
        raise ContractError(f"Asset resolver {ref} must return image/svg+xml")
    if not result.body.lstrip().startswith("<svg") or "</svg>" not in result.body:
        raise ContractError(f"Asset resolver {ref} did not return SVG")
    return result


def asset_placeholder_svg(asset: dict[str, Any]) -> str:
    placeholder = asset["placeholder"]
    label = placeholder["label"]
    ratio = placeholder.get("aspect_ratio", "4:3")
    w_raw, h_raw = ratio.split(":")
    width = 320
    height = max(120, int(width * int(h_raw) / int(w_raw)))
    cx, cy = width / 2, height / 2
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(label, quote=True)}">
  <title>{html.escape(label)}</title>
  <defs>
    <linearGradient id="g" x1="0" x2="1" y1="0" y2="1">
      <stop offset="0" stop-color="#fafafa"/>
      <stop offset="1" stop-color="#e4e4e7"/>
    </linearGradient>
  </defs>
  <rect width="100%" height="100%" rx="18" fill="url(#g)" stroke="#a1a1aa" stroke-width="2"/>
  <circle cx="{cx-54:.0f}" cy="{cy-18:.0f}" r="38" fill="#d4d4d8"/>
  <rect x="{cx-18:.0f}" y="{cy-58:.0f}" width="92" height="92" rx="16" fill="#f4f4f5" stroke="#a1a1aa" stroke-width="2"/>
  <path d="M{cx-72:.0f} {cy+54:.0f} C{cx-28:.0f} {cy+6:.0f}, {cx+32:.0f} {cy+88:.0f}, {cx+92:.0f} {cy+18:.0f}" fill="none" stroke="#71717a" stroke-width="8" stroke-linecap="round"/>
</svg>
'''


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) not in {2, 3}:
        print("usage: pyspec audit <root> <tools_root> [previous_audit_root]", file=sys.stderr)
        return 2
    root = Path(argv[0]).resolve()
    tools_root = Path(argv[1]).resolve()
    previous_audit_root = Path(argv[2]).resolve() if len(argv) == 3 else None
    from .io import read_yaml
    from .paths import COMPILED_SPEC_PATH
    contract = read_yaml(root / COMPILED_SPEC_PATH)
    try:
        _render_visual_audit(root, contract, tools_root, previous_audit_root=previous_audit_root)
    except (ContractError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    # Playwright/Textual can leave cleanup state that blocks interpreter shutdown in
    # constrained containers. This worker has completed all file outputs; exit
    # immediately so the compiler process stays deterministic.
    os._exit(0)


if __name__ == "__main__":
    raise SystemExit(main())
