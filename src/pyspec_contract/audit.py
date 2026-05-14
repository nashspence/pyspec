from __future__ import annotations

import asyncio
import base64
import html
import json
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any, Iterable

from .compile import ContractError
from .content import AssetResult, ContentContext, ContentError, call_asset, call_copy
from .io import write_yaml
from .layout import layout_html, layout_html_regions
from .paths import GENERATED_SPEC_DIR, generated_relative as g
from .project import css_value, default_html_slots, format_attrs, humanize, panels_projection, panel_styles_projection, safe_id
from .runtime import fixture_namespace, resolve

ROOT = Path(__file__).resolve().parent


def _under(relative: str, *parts: str) -> str:
    return "/".join([relative, *parts])


def panel_fsm_file(panel_id: str) -> str:
    return g("audit_evidence", "panels", safe_id(panel_id), "fsm.svg")


def panel_state_root(panel_id: str, state_name: str) -> str:
    return g("audit_evidence", "panels", safe_id(panel_id), "states", safe_id(state_name))


def view_state_root(view_id: str, state_name: str) -> str:
    return g("audit_evidence", "views", safe_id(view_id), "states", safe_id(state_name))


def composition_file(view_id: str) -> str:
    return g("audit_evidence", "composed_views", safe_id(view_id), "composition.svg")


def composed_case_root(view_id: str, case_id: str) -> str:
    return g("audit_evidence", "composed_views", safe_id(view_id), "cases", safe_id(case_id))


def view_case_root(view_id: str, case_id: str) -> str:
    return g("audit_evidence", "views", safe_id(view_id), "cases", safe_id(case_id))


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


def render_panel_file(panel_id: str, state_name: str, profile_id: str, breakpoint_id: str, extension: str) -> str:
    return _under(panel_state_root(panel_id, state_name), "renders", _render_filename(profile_id, breakpoint_id, extension))


def render_case_file(view_id: str, case_id: str, profile_id: str, breakpoint_id: str, extension: str) -> str:
    return _under(composed_case_root(view_id, case_id), "renders", _render_filename(profile_id, breakpoint_id, extension))


def render_view_state_file(view_id: str, state_name: str, profile_id: str, breakpoint_id: str, extension: str) -> str:
    return _under(view_state_root(view_id, state_name), "renders", _render_filename(profile_id, breakpoint_id, extension))


def render_view_case_file(view_id: str, case_id: str, profile_id: str, breakpoint_id: str, extension: str) -> str:
    return _under(view_case_root(view_id, case_id), "renders", _render_filename(profile_id, breakpoint_id, extension))


def _projection_panel_root(panel: dict[str, Any]) -> str:
    if panel["owner_kind"] == "panel":
        return panel_state_root(panel["owner"], panel["state"])
    return view_state_root(panel["owner"], panel["state"])


def _projection_panel_file(panel: dict[str, Any], profile_id: str, breakpoint_id: str, extension: str) -> str:
    if panel["owner_kind"] == "panel":
        return render_panel_file(panel["owner"], panel["state"], profile_id, breakpoint_id, extension)
    return render_view_state_file(panel["owner"], panel["state"], profile_id, breakpoint_id, extension)


def _case_root(contract: dict[str, Any], case_id: str, case: dict[str, Any]) -> str:
    if contract["views"][case["view"]].get("includes"):
        return composed_case_root(case["view"], case_id)
    return view_case_root(case["view"], case_id)


def _case_file(contract: dict[str, Any], case_id: str, case: dict[str, Any], breakpoint_id: str, extension: str) -> str:
    if contract["views"][case["view"]].get("includes"):
        return render_case_file(case["view"], case_id, case["profile"], breakpoint_id, extension)
    return render_view_case_file(case["view"], case_id, case["profile"], breakpoint_id, extension)


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


def _state_needs_data(contract: dict[str, Any], panel: dict[str, Any]) -> bool:
    if panel.get("data") or panel["slots"].get("fields"):
        return True
    copy_refs = panel["slots"].get("copy", [])
    asset_refs = panel["slots"].get("assets", [])
    return any(contract["copies"][ref].get("args") for ref in copy_refs) or any(contract["assets"][ref].get("args") for ref in asset_refs)


def _fixture_ids_for_resource(contract: dict[str, Any], resource_id: str) -> set[str]:
    return {
        fixture_id
        for fixture_id, fixture in contract.get("fixtures", {}).items()
        if _find_resource_records(fixture.get("values", {}), resource_id)
    }


def _fact_ids_for_resource(contract: dict[str, Any], resource_id: str) -> set[str]:
    fact_ids = set()
    for fact_id, fact in contract.get("facts", {}).items():
        _, body = _fact_selector(fact, fact_id)
        if body["resource"] == resource_id:
            fact_ids.add(fact_id)
    return fact_ids


def _fixture_ids_for_facts(contract: dict[str, Any], fact_ids: Iterable[str], resource_id: str) -> set[str]:
    fixture_ids: set[str] = set()
    for fact_id in sorted(fact_ids):
        fact_uses = [{"use": fact_id}]
        try:
            _apply_fact_uses(contract, fact_uses, {}, resource_id, [])
            continue
        except (AssertionError, KeyError, TypeError):
            pass
        for fixture_id in contract.get("fixtures", {}):
            try:
                namespace = fixture_namespace(contract, [fixture_id])
                _apply_fact_uses(contract, fact_uses, namespace, resource_id, [])
            except (AssertionError, KeyError, TypeError):
                continue
            fixture_ids.add(fixture_id)
            break
    return fixture_ids


def _panel_scope_inputs(contract: dict[str, Any], panel: dict[str, Any]) -> tuple[set[str], set[str], set[str], set[str], dict[str, Any]]:
    copy_refs = set(panel["slots"].get("copy", []))
    asset_refs = set(panel["slots"].get("assets", []))
    fixture_ids: set[str] = set()
    fact_ids: set[str] = set()
    if _state_needs_data(contract, panel):
        resource_id = panel_resource(contract, panel)
        fixture_ids = _fixture_ids_for_resource(contract, resource_id)
        fact_ids = _fact_ids_for_resource(contract, resource_id)
        fixture_ids.update(_fixture_ids_for_facts(contract, fact_ids, resource_id))
    return copy_refs, asset_refs, fixture_ids, fact_ids, {}


def _case_scope_inputs(contract: dict[str, Any], case: dict[str, Any]) -> tuple[set[str], set[str], set[str], set[str], dict[str, Any]]:
    panels = case_render_panels(contract, case)
    copy_refs = {copy_ref for panel in panels for copy_ref in panel["slots"].get("copy", [])}
    asset_refs = {asset_ref for panel in panels for asset_ref in panel["slots"].get("assets", [])}
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
    for panel in _audit_projection_panels(contract, projection):
        _write_audit_scope_inputs(root, contract, _projection_panel_root(panel), *_panel_scope_inputs(contract, panel))
    for case_id, case in sorted(contract.get("render_cases", {}).items()):
        _write_audit_scope_inputs(root, contract, _case_root(contract, case_id, case), *_case_scope_inputs(contract, case))


def _audit_projection_panels(contract: dict[str, Any], projection: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        panel
        for panel in projection["panels"]
        if not (panel["owner_kind"] == "view" and contract["views"][panel["owner"]].get("includes"))
    ]


def audit_expected_files(contract: dict[str, Any]) -> set[str]:
    files: set[str] = set()
    for panel_id in contract.get("panels", {}):
        files.add(panel_fsm_file(panel_id))
    for view_id, view in contract.get("views", {}).items():
        if view.get("includes"):
            files.add(composition_file(view_id))

    projection = panels_projection(contract)
    for panel in _audit_projection_panels(contract, projection):
        scope_root = _projection_panel_root(panel)
        _, asset_refs, _, _, _ = _panel_scope_inputs(contract, panel)
        files.update(_audit_scope_expected_files(scope_root, asset_refs))
        for profile_id, profile in sorted(contract.get("audit_profiles", {}).items()):
            for breakpoint in profile.get("html", {}).get("breakpoints", {}):
                files.add(_projection_panel_file(panel, profile_id, breakpoint, "html"))
                files.add(_projection_panel_file(panel, profile_id, breakpoint, "png"))
            for breakpoint in profile.get("textual", {}).get("breakpoints", {}):
                files.add(_projection_panel_file(panel, profile_id, breakpoint, "py"))
                files.add(_projection_panel_file(panel, profile_id, breakpoint, "svg"))

    for case_id, case in contract.get("render_cases", {}).items():
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


def generate_audit(root: Path, contract: dict[str, Any], tools_root: Path | None = None) -> None:
    audit_root = root / GENERATED_SPEC_DIR / "audit_evidence"
    if audit_root.exists():
        shutil.rmtree(audit_root)
    audit_root.mkdir(parents=True, exist_ok=True)

    projection = panels_projection(contract)
    _write_audit_inputs(root, contract, projection)

    if not contract.get("panels") and not contract.get("render_cases"):
        return
    _render_visual_audit(root, contract, tools_root or root, projection)


def _render_visual_audit_subprocess(root: Path, tools_root: Path) -> None:
    env = os.environ.copy()
    env["PM_CONTRACT_AUDIT_WORKER"] = "1"
    cmd = [sys.executable, "-m", "pyspec_contract.audit", str(root), str(tools_root)]
    result = subprocess.run(cmd, cwd=str(root), env=env, timeout=900)
    if result.returncode != 0:
        raise ContractError(f"Visual audit renderer failed with exit code {result.returncode}")


def _render_visual_audit(root: Path, contract: dict[str, Any], _tools_root: Path, projection: dict[str, Any] | None = None) -> None:
    projection = projection or panels_projection(contract)
    for panel_id, panel in sorted(contract.get("panels", {}).items()):
        path = root / panel_fsm_file(panel_id)
        _write_graphviz_svg(path, panel_fsm_dot(panel_id, panel, contract))
    for view_id, view in sorted(contract.get("views", {}).items()):
        if not view.get("includes"):
            continue
        path = root / composition_file(view_id)
        _write_graphviz_svg(path, composition_dot(view_id, view, contract))

    has_html_audit = bool(
        _audit_projection_panels(contract, projection) and any(profile.get("html") for profile in contract.get("audit_profiles", {}).values())
    ) or any("html" in case["surfaces"] for case in contract.get("render_cases", {}).values())
    if has_html_audit:
        _render_html_audit(root, contract, projection)

    audit_panels = _audit_projection_panels(contract, projection)
    if audit_panels or any("textual" in case["surfaces"] for case in contract.get("render_cases", {}).values()):
        try:
            import textual  # noqa: F401
        except Exception as exc:  # pragma: no cover - dependency absence is environment-specific.
            raise ContractError("Missing Textual dependency; install requirements.txt") from exc
        textual_jobs: list[tuple[Path, list[tuple[str, str]], dict[str, int]]] = []
        for panel in sorted(audit_panels, key=lambda p: p["id"]):
            lines = panel_textual_lines(root, contract, panel, None)
            for profile_id, profile in sorted(contract.get("audit_profiles", {}).items()):
                for name, viewport in sorted(profile.get("textual", {}).get("breakpoints", {}).items()):
                    py_path = root / _projection_panel_file(panel, profile_id, name, "py")
                    svg_path = root / _projection_panel_file(panel, profile_id, name, "svg")
                    _write_textual_source(py_path, lines)
                    textual_jobs.append((svg_path, lines, viewport))
        for case_id, case in sorted(contract.get("render_cases", {}).items()):
            if "textual" not in case["surfaces"]:
                continue
            profile = contract["audit_profiles"][case["profile"]]
            lines = textual_audit_lines(root, contract, case_id, case)
            for name, viewport in sorted(profile.get("textual", {}).get("breakpoints", {}).items()):
                py_path = root / _case_file(contract, case_id, case, name, "py")
                svg_path = root / _case_file(contract, case_id, case, name, "svg")
                _write_textual_source(py_path, lines)
                textual_jobs.append((svg_path, lines, viewport))
        asyncio.run(_render_textual_batch(textual_jobs))


def _render_html_audit(root: Path, contract: dict[str, Any], projection: dict[str, Any]) -> None:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover - dependency absence is environment-specific.
        raise ContractError("Missing Playwright dependency; install requirements.txt and run python -m playwright install chromium, or provide system Chromium") from exc

    with sync_playwright() as pw:
        browser = _launch_chromium(pw)
        try:
            page = browser.new_page()
            try:
                for panel in sorted(_audit_projection_panels(contract, projection), key=lambda p: p["id"]):
                    for profile_id, profile in sorted(contract.get("audit_profiles", {}).items()):
                        html_profile = profile.get("html")
                        if not html_profile:
                            continue
                        html_doc = audit_html_document(contract, render_panel_audit_html(root, contract, panel, None))
                        for name, viewport in sorted(html_profile["breakpoints"].items()):
                            html_path = root / _projection_panel_file(panel, profile_id, name, "html")
                            png_path = root / _projection_panel_file(panel, profile_id, name, "png")
                            _write_html_and_png_page(page, html_doc, html_path, png_path, viewport)
                for case_id, case in sorted(contract.get("render_cases", {}).items()):
                    profile = contract["audit_profiles"][case["profile"]]
                    if "html" in case["surfaces"]:
                        html_doc = audit_html_document(contract, render_case_html(root, contract, case_id, case))
                        for name, viewport in sorted(profile.get("html", {}).get("breakpoints", {}).items()):
                            html_path = root / _case_file(contract, case_id, case, name, "html")
                            png_path = root / _case_file(contract, case_id, case, name, "png")
                            _write_html_and_png_page(page, html_doc, html_path, png_path, viewport)
            finally:
                page.close()
        finally:
            browser.close()


def _write_html_and_png_page(page: Any, html_doc: str, html_path: Path, png_path: Path, viewport: dict[str, int]) -> None:
    html_path.parent.mkdir(parents=True, exist_ok=True)
    png_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(html_doc, encoding="utf-8")
    page.set_viewport_size({"width": viewport["width"], "height": viewport["height"]})
    page.set_content(html_doc, wait_until="load")
    page.screenshot(path=str(png_path), full_page=False, type="png", timeout=10000)
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


def _write_graphviz_svg(path: Path, dot_source: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_render_graphviz_svg(dot_source, path.stem), encoding="utf-8")


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


async def _render_textual_batch(jobs: list[tuple[Path, list[tuple[str, str]], dict[str, int]]]) -> None:
    for path, lines, viewport in jobs:
        await _render_textual_svg(path, lines, viewport)


async def _render_textual_svg(path: Path, lines: list[tuple[str, str]], viewport: dict[str, int]) -> None:
    from textual.app import App, ComposeResult
    from textual.containers import Container
    from textual.widgets import Button, Static

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
    path.write_text(svg, encoding="utf-8")


def panel_fsm_dot(panel_id: str, panel: dict[str, Any], contract: dict[str, Any] | None = None) -> str:
    lines = [
        f"digraph {_dot_quote('fsm_' + safe_id(panel_id))} {{",
        '  graph [rankdir="LR", bgcolor="transparent", pad="0.25", nodesep="0.38", ranksep="0.85", splines="spline"];',
        '  node [fontname="Arial", fontsize="11"];',
        '  edge [color="#3f3f46", fontname="Arial", fontsize="10", arrowsize="0.8"];',
        f"  {_dot_quote('initial')} [shape=\"circle\", label=\"initial\", width=\"0.58\", fixedsize=\"true\", color=\"#0891b2\", fontcolor=\"#155e75\", fontsize=\"9\"];",
    ]
    for state_name in sorted(panel["states"]):
        state = panel["states"][state_name]
        lines.append(
            _dot_html_node(
                _dot_node_id("state", state_name),
                _dot_card(
                    state_name,
                    None,
                    [
                        ("copy", state.get("copy", [])),
                        (f"{panel['resource']} fields", state.get("fields", [])),
                        ("assets", state.get("assets", [])),
                        ("actions", state.get("actions", [])),
                    ],
                    header_bg="#ecfeff" if state_name == panel["initial"] else "#f8fafc",
                    border="#0891b2" if state_name == panel["initial"] else "#71717a",
                ),
            )
        )
    lines.append(f"  {_dot_quote('initial')} -> {_dot_quote(_dot_node_id('state', panel['initial']))};")
    for index, transition in enumerate(panel.get("transitions", [])):
        source = _dot_node_id("state", transition["from"])
        target = _dot_node_id("state", transition["to"])
        transition_id = _dot_node_id("transition", f"{index}_{transition['from']}_{transition['to']}_{transition['on']}")
        lines.append(
            _dot_html_node(
                transition_id,
                _dot_card(
                    f"on {transition['on']}",
                    None,
                    _format_transition_sections(panel, transition, contract),
                    basis=transition.get("basis", ""),
                    header_bg="#eff6ff",
                    border="#2563eb",
                ),
            )
        )
        lines.append(f"  {_dot_quote(source)} -> {_dot_quote(transition_id)};")
        lines.append(f"  {_dot_quote(transition_id)} -> {_dot_quote(target)};")
    lines.append("}")
    return "\n".join(lines) + "\n"


def composition_dot(view_id: str, view: dict[str, Any], contract: dict[str, Any] | None = None) -> str:
    view_node = _dot_node_id("view", view_id)
    route_panel_order: list[str] = []
    for rule in view.get("sync", []):
        route_panel_order.append(rule["when"]["instance"])
        route_panel_order.extend(effect["send"]["panel"] for effect in rule.get("do", []) if "send" in effect)
    route_panel_index = {panel_id: index for index, panel_id in enumerate(dict.fromkeys(route_panel_order))}
    includes = sorted(
        view.get("includes", []),
        key=lambda include: (route_panel_index.get(include["id"], len(route_panel_index)), include["id"]),
    )
    include_by_id = {include["id"]: include for include in includes}
    instance_node_by_id = {include["id"]: _dot_node_id("panel_instance", include["id"]) for include in includes}
    instance_node_ids = [instance_node_by_id[include["id"]] for include in includes]
    has_sync = bool(view.get("sync"))
    lines = [
        f"digraph {_dot_quote('composition_' + safe_id(view_id))} {{",
        '  graph [rankdir="LR", bgcolor="transparent", pad="0.25", nodesep="0.38", ranksep="0.85", splines="spline"];',
        '  node [fontname="Arial", fontsize="11"];',
        '  edge [color="#3f3f46", fontname="Arial", fontsize="10", arrowsize="0.8"];',
        _dot_html_node(
            view_node,
            _dot_card(
                view_id,
                f"{view['archetype']} view",
                [
                    ("resource", [view["resource"]]),
                    ("context", _format_mapping(view.get("context", {}))),
                    ("data", _format_data_bindings(view.get("data", []))),
                ],
                basis=view.get("basis", ""),
                header_bg="#f0fdf4",
                border="#15803d",
            ),
        ),
    ]
    for include in includes:
        lines.append(_dot_html_node(instance_node_by_id[include["id"]], _dot_instance_card(include)))
    if instance_node_ids:
        lines.append(f"  {_dot_quote(view_node)} -> {_dot_quote(instance_node_ids[0])} [style=\"invis\", weight=\"10\"];")
        if not has_sync:
            lines.extend(_dot_invisible_order(instance_node_ids, indent="  "))
    if not has_sync:
        lines.append(_dot_html_node("message_route_none", _dot_card("No message routes", None, [], header_bg="#f8fafc")))
    for rule in view.get("sync", []):
        emit_id = _dot_node_id("message_emit", f"{rule['id']}_{rule['when']['instance']}_{rule['when']['message']}")
        sync_id = _dot_node_id("message_route", rule["id"])
        effect_ids = [_dot_node_id("message_effect", f"{rule['id']}_{index}") for index, _ in enumerate(rule.get("do", []))]
        lines.append(
            _dot_html_node(
                emit_id,
                _dot_card(
                    rule["when"]["message"],
                    "emitted message",
                    [
                        ("source", _emitting_transition_refs(rule["when"]["instance"], rule["when"]["message"], include_by_id, contract)),
                        ("data", _emitted_message_data_lines(rule["when"]["instance"], rule["when"]["message"], include_by_id, contract)),
                    ],
                    header_bg="#eef2ff",
                    border="#4f46e5",
                ),
            )
        )
        lines.append(
            _dot_html_node(
                sync_id,
                _dot_card(
                    rule["id"],
                    "message route",
                    [("data", _route_data_lines(rule))],
                    header_bg="#fefce8",
                    border="#a16207",
                ),
            )
        )
        for index, effect in enumerate(rule.get("do", [])):
            effect_id = _dot_node_id("message_effect", f"{rule['id']}_{index}")
            lines.append(_dot_html_node(effect_id, _dot_sync_effect_card(effect, include_by_id, contract)))
        if effect_ids:
            lines.append("  { rank=same; " + " ".join(_dot_quote(effect_id) for effect_id in effect_ids) + " }")
            lines.extend(_dot_invisible_order(effect_ids, indent="  "))
    if not has_sync:
        lines.append(f"  {_dot_quote(view_node)} -> {_dot_quote('message_route_none')} [style=\"invis\", weight=\"10\"];")
    for rule in view.get("sync", []):
        emit_id = _dot_node_id("message_emit", f"{rule['id']}_{rule['when']['instance']}_{rule['when']['message']}")
        sync_id = _dot_node_id("message_route", rule["id"])
        source = instance_node_by_id.get(rule["when"]["instance"])
        if source:
            lines.append(f"  {_dot_quote(source)} -> {_dot_quote(emit_id)} [color=\"#4f46e5\", penwidth=\"1.4\"];")
        lines.append(f"  {_dot_quote(emit_id)} -> {_dot_quote(sync_id)} [color=\"#4f46e5\", penwidth=\"1.2\"];")
        for index, effect in enumerate(rule.get("do", [])):
            effect_id = _dot_node_id("message_effect", f"{rule['id']}_{index}")
            edge_attrs = 'color="#be185d", penwidth="1.3"'
            if "set" in effect:
                edge_attrs = 'color="#15803d", penwidth="1.3", style="dotted"'
            lines.append(f"  {_dot_quote(sync_id)} -> {_dot_quote(effect_id)} [{edge_attrs}];")
            if "send" not in effect:
                continue
            target = instance_node_by_id.get(effect["send"]["panel"])
            if not target:
                continue
            lines.append(f"  {_dot_quote(effect_id)} -> {_dot_quote(target)} [color=\"#be185d\", penwidth=\"1.4\"];")
    lines.append("}")
    return "\n".join(lines) + "\n"


def _dot_instance_card(include: dict[str, Any]) -> str:
    return _dot_card(
        f"instance: {include['id']}",
        include["panel"],
        [
            ("region", [include["region"]]),
            ("initial", [include["initial"]]),
            ("context binding", _format_data_flow(include.get("context", {}), identity_scope=None)),
        ],
        header_bg="#fff7ed",
        border="#c2410c",
    )


def _dot_sync_effect_card(
    effect: dict[str, Any],
    include_by_id: dict[str, dict[str, Any]],
    contract: dict[str, Any] | None,
) -> str:
    if "send" in effect:
        send = effect["send"]
        return _dot_card(
            send["message"],
            "sent message",
            [
                ("causes", _receiving_transition_refs(send["panel"], send["message"], include_by_id, contract)),
                ("data", _sent_message_data_lines(send)),
            ],
            header_bg="#fdf2f8",
            border="#be185d",
        )
    assignment = effect["set"]
    return _dot_card(
        f"set {assignment['context']}",
        "view context",
        [
            ("flow", [_format_flow_assignment(assignment["context"], _assignment_value(assignment))]),
        ],
        header_bg="#f0fdf4",
        border="#15803d",
    )


def _emitted_message_data_lines(
    instance_id: str,
    emitted: str,
    include_by_id: dict[str, dict[str, Any]],
    contract: dict[str, Any] | None,
) -> list[str]:
    lines: list[str] = []
    seen: set[str] = set()
    for emit in _emitting_transition_emits(instance_id, emitted, include_by_id, contract):
        for line in _format_data_flow(emit.get("data", {})):
            if line not in seen:
                lines.append(line)
                seen.add(line)
    return lines


def _route_data_lines(rule: dict[str, Any]) -> list[str]:
    lines = []
    for effect in rule.get("do", []):
        assignment = effect.get("set")
        if not assignment:
            continue
        lines.append(_format_flow_assignment(assignment["context"], _assignment_value(assignment)))
    return lines


def _sent_message_data_lines(send: dict[str, Any]) -> list[str]:
    return _format_data_flow(send.get("data", {}))


def _assignment_value(assignment: dict[str, Any]) -> Any:
    return assignment.get("from", assignment.get("value", ""))


def _emitting_transition_emits(
    instance_id: str,
    emitted: str,
    include_by_id: dict[str, dict[str, Any]],
    contract: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not contract:
        return []
    include = include_by_id.get(instance_id)
    if not include:
        return []
    panel = contract.get("panels", {}).get(include["panel"])
    if not panel:
        return []
    emits = []
    for transition in panel.get("transitions", []):
        for effect in transition.get("effects", []):
            emit = effect.get("emit")
            if emit and emit["message"] == emitted:
                emits.append(emit)
    return emits


def _emitting_transition_refs(
    instance_id: str,
    emitted: str,
    include_by_id: dict[str, dict[str, Any]],
    contract: dict[str, Any] | None,
) -> list[str]:
    refs = []
    if not contract:
        return refs
    include = include_by_id.get(instance_id)
    if not include:
        return refs
    panel = contract.get("panels", {}).get(include["panel"])
    if not panel:
        return refs
    for transition in panel.get("transitions", []):
        if any(effect.get("emit", {}).get("message") == emitted for effect in transition.get("effects", [])):
            refs.append(transition["on"])
    return refs


def _receiving_transition_refs(
    instance_id: str,
    message: str,
    include_by_id: dict[str, dict[str, Any]],
    contract: dict[str, Any] | None,
) -> list[str]:
    if not contract:
        return []
    include = include_by_id.get(instance_id)
    if not include:
        return []
    panel = contract.get("panels", {}).get(include["panel"])
    if not panel:
        return []
    target_sources: dict[str, list[str]] = {}
    for transition in panel.get("transitions", []):
        if transition["on"] == message:
            target_sources.setdefault(transition["to"], []).append(transition["from"])
    if len(target_sources) == 1:
        target = next(iter(target_sources))
        return [f"to {target}"]
    return [f"to {target} (from {', '.join(sorted(sources))})" for target, sources in sorted(target_sources.items())]


def _dot_node_id(prefix: str, value: str) -> str:
    return f"{prefix}_{safe_id(value)}"


def _dot_invisible_order(node_ids: list[str], indent: str) -> list[str]:
    return [
        f"{indent}{_dot_quote(source)} -> {_dot_quote(target)} [style=\"invis\", weight=\"100\"];"
        for source, target in zip(node_ids, node_ids[1:])
    ]


class _DotHtml(str):
    pass


def _dot_html_node(node_id: str, label: str, attrs: dict[str, object] | None = None, indent: str = "  ") -> str:
    node_attrs: dict[str, object] = {"shape": "plain", "label": _DotHtml(label)}
    node_attrs.update(attrs or {})
    return f"{indent}{_dot_quote(node_id)}{_dot_attrs(node_attrs)};"


def _dot_card(
    title: str,
    subtitle: str | None,
    sections: Iterable[tuple[str, Iterable[object]]],
    *,
    basis: str | None = None,
    header_bg: str,
    border: str = "#71717a",
) -> str:
    rows = [
        f'<TR><TD BGCOLOR="{border}" HEIGHT="3" FIXEDSIZE="false"></TD></TR>',
        f'<TR><TD BGCOLOR="{header_bg}" ALIGN="LEFT"><FONT POINT-SIZE="14"><B>{_dot_html_text(title)}</B></FONT></TD></TR>',
    ]
    if subtitle:
        rows.extend(_dot_text_rows(_wrap_dot_text(subtitle), point_size=10))
    if basis:
        rows.extend(_dot_text_rows(_wrap_dot_text(basis, width=50), point_size=10, italic=True, color="#3f3f46"))
    rows.extend(_dot_section_rows(sections))
    return (
        f'<TABLE BORDER="1" CELLBORDER="0" CELLSPACING="0" CELLPADDING="5" COLOR="{border}" BGCOLOR="#ffffff">'
        + "".join(rows)
        + "</TABLE>"
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
            inner_rows.append(f'<TR><TD ALIGN="LEFT"><FONT POINT-SIZE="10"><B>{_dot_html_text(title)}</B></FONT></TD></TR>')
        inner_rows.append(f'<TR><TD ALIGN="LEFT"><FONT POINT-SIZE="10">{_dot_html_text(wrapped[0])}</FONT></TD></TR>')
        for line in wrapped[1:]:
            inner_rows.append(f'<TR><TD ALIGN="LEFT"><FONT POINT-SIZE="10">{_dot_html_text(line)}</FONT></TD></TR>')
    return False, inner_rows


def _dot_key_value_text(title: str, value: str) -> str:
    key = f"<B>{_dot_html_text(title)}:</B>&#160;&#160;" if title else "&#160;&#160;"
    return f"{key}{_dot_html_text(value)}"


def _dot_key_value_row(title: str, value: str) -> str:
    return (
        '<TR><TD ALIGN="LEFT" VALIGN="MIDDLE" HEIGHT="11"><FONT POINT-SIZE="10">'
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


def _format_mapping(mapping: dict[str, Any]) -> list[str]:
    return [f"{key}: {value}" for key, value in sorted(mapping.items())]


def _format_data_flow(mapping: dict[str, Any], *, identity_scope: str | None = "message") -> list[str]:
    return [_format_flow_assignment(key, value, identity_scope=identity_scope) for key, value in sorted(mapping.items())]


def _format_flow_assignment(target: str, value: Any, *, identity_scope: str | None = "message") -> str:
    source = _format_flow_source(value)
    if identity_scope and source == f"{identity_scope}.{target}":
        return target
    if source.startswith("message."):
        source = source[len("message.") :]
    return f"{target} <- {source}"


def _format_flow_source(value: Any) -> str:
    if isinstance(value, str) and value.startswith("$"):
        return value[1:]
    return _format_scalar(value)


def _format_data_bindings(bindings: Iterable[dict[str, Any]]) -> list[str]:
    bindings = list(bindings)
    lines: list[str] = []
    for index, binding in enumerate(bindings, start=1):
        if len(bindings) > 1:
            lines.append(f"binding {index}")
        lines.extend(f"{key}: {value}" for key, value in sorted(binding.items()))
    return lines


def _format_transition_sections(
    panel: dict[str, Any], transition: dict[str, Any], contract: dict[str, Any] | None = None
) -> list[tuple[str, list[str]]]:
    sections: list[tuple[str, list[str]]] = []
    if _is_data_event(transition["on"]):
        bindings = _transition_data_bindings(panel, transition)
        data_sources = [binding["capability"] for binding in bindings]
        queries = [binding["query"] for binding in bindings]
        inputs = _format_data_inputs(panel, bindings, contract)
        if inputs:
            sections.append(("input", inputs))
        if queries:
            sections.append(("query", queries))
        if data_sources:
            sections.append(("load", data_sources))
    else:
        target_bindings = _transition_target_data_bindings(panel, transition)
        data_sources = [binding["capability"] for binding in target_bindings]
        queries = [binding["query"] for binding in target_bindings]
        required_context = _format_data_inputs(panel, target_bindings, contract)
        if required_context:
            sections.append(("input", required_context))
        if queries:
            sections.append(("query", queries))
        if data_sources:
            sections.append(("load", data_sources))
    effects = _format_transition_effects(transition)
    if effects:
        sections.append(("effects", effects))
    return sections


def _transition_target_data_bindings(panel: dict[str, Any], transition: dict[str, Any]) -> list[dict[str, Any]]:
    target_state = panel.get("states", {}).get(transition["to"], {})
    return _unique_data_bindings(target_state.get("data", []))


def _format_data_inputs(
    panel: dict[str, Any], bindings: Iterable[dict[str, Any]], contract: dict[str, Any] | None
) -> list[str]:
    if not contract:
        return []
    context = panel.get("context", {})
    capabilities = contract.get("capabilities", {})
    inputs: list[str] = []
    seen: set[str] = set()
    for binding in bindings:
        capability = capabilities.get(binding.get("capability"), {})
        for key, value_type in sorted((capability.get("input") or {}).items()):
            if key not in context:
                continue
            line = f"{key}: {context.get(key, value_type)}"
            if line not in seen:
                inputs.append(line)
                seen.add(line)
    return inputs


def _is_data_event(event: str) -> bool:
    return event.startswith("data.")


def _transition_data_bindings(panel: dict[str, Any], transition: dict[str, Any]) -> list[dict[str, Any]]:
    source_state = panel.get("states", {}).get(transition["from"], {})
    bindings = source_state.get("data", []) or panel.get("data", [])
    return _unique_data_bindings(bindings)


def _unique_data_bindings(bindings: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    seen: set[tuple[Any, Any]] = set()
    for binding in bindings:
        key = (binding.get("capability"), binding.get("query"))
        if key not in seen:
            unique.append(binding)
            seen.add(key)
    return unique


def _format_transition_effects(transition: dict[str, Any]) -> list[str]:
    lines = []
    for effect in transition.get("effects", []):
        if "emit" in effect:
            emit = effect["emit"]
            lines.append(f"emit {emit['message']}")
            lines.extend(f"  {line}" for line in _format_data_flow(emit.get("data", {})))
        elif "set" in effect:
            assignment = effect["set"]
            lines.append(_format_flow_assignment(assignment["context"], _assignment_value(assignment), identity_scope=None))
    return lines


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


def audit_html_document(contract: dict[str, Any], body: str) -> str:
    css = panel_styles_projection(contract)
    extra_css = """
    body { margin: 0; font-family: ui-sans-serif, system-ui, sans-serif; background: #f7f7f8; color: #171717; }
    main { padding: 24px; }
    .contract-panel, .contract-composed-view { background: white; border: 1px solid #d0d0d0; border-radius: 12px; padding: 16px; box-sizing: border-box; }
    .contract-composed-view { display: grid; grid-template-columns: minmax(180px, 1fr) minmax(280px, 2fr) minmax(180px, 1fr); gap: 16px; max-width: none; }
    .contract-layout-region { min-height: 120px; display: grid; gap: 12px; align-content: start; }
    .audit-records { display: grid; gap: 0.75rem; }
    .audit-record { border: 1px solid #e4e4e7; border-radius: 10px; padding: 0.75rem; display: grid; gap: 0.35rem; }
    .audit-field { display: grid; gap: 0.15rem; }
    .audit-field-label { color: #52525b; font-size: 0.75rem; }
    .audit-field-value { font-weight: 600; }
    img.audit-asset { max-width: 100%; height: auto; border-radius: 8px; }
    button { padding: 0.5rem 0.75rem; border: 1px solid #222; border-radius: 6px; background: #fff; justify-self: start; }
    @media (max-width: 700px) { .contract-composed-view { grid-template-columns: 1fr; } }
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


def render_case_html(root: Path, contract: dict[str, Any], case_id: str, case: dict[str, Any]) -> str:
    view = contract["views"][case["view"]]
    if view.get("includes"):
        return render_composed_case_html(root, contract, case)
    projection = panels_projection(contract)
    panel = next(item for item in projection["panels"] if item["owner_kind"] == "view" and item["owner"] == case["view"] and item["state"] == case["state"])
    return render_panel_audit_html(root, contract, panel, case)


def case_render_panels(contract: dict[str, Any], case: dict[str, Any]) -> list[dict[str, Any]]:
    projection = panels_projection(contract)
    view = contract["views"][case["view"]]
    if view.get("includes"):
        panels = []
        for include in view["includes"]:
            state_name = case["panels"][include["id"]]["state"]
            panels.append(next(item for item in projection["panels"] if item["owner_kind"] == "panel" and item["owner"] == include["panel"] and item["state"] == state_name))
        return panels
    return [next(item for item in projection["panels"] if item["owner_kind"] == "view" and item["owner"] == case["view"] and item["state"] == case["state"])]


def render_composed_case_html(root: Path, contract: dict[str, Any], case: dict[str, Any]) -> str:
    view = contract["views"][case["view"]]
    projection = panels_projection(contract)
    composition = next(item for item in projection["compositions"] if item["id"] == case["view"])
    html_layout = layout_html(composition["layout"])
    root_spec = html_layout.get("root") or {"element": "section"}
    tag = root_spec.get("element", "section")
    classes = " ".join(["contract-composed-view"] + root_spec.get("classes", []))
    attrs = {"class": classes, "data-contract-composition": composition["id"]}
    if root_spec.get("role") and root_spec["role"] != "none":
        attrs["role"] = root_spec["role"]
    parts = [f"<{tag}{format_attrs(attrs)}>"]
    for region_name, region in sorted(layout_html_regions(view["layout"]).items(), key=lambda item: item[1].get("order", 0)):
        region_tag = region.get("element", "div")
        region_classes = " ".join(["contract-layout-region", f"contract-layout-region--{region_name}"] + region.get("classes", []))
        region_attrs = {"class": region_classes, "data-layout-region": region_name, "data-required": str(region["required"]).lower()}
        if region.get("role") and region["role"] != "none":
            region_attrs["role"] = region["role"]
        parts.append(f"<{region_tag}{format_attrs(region_attrs)}>")
        for include in [item for item in view["includes"] if item["region"] == region_name]:
            state_name = case["panels"][include["id"]]["state"]
            panel = next(item for item in projection["panels"] if item["owner_kind"] == "panel" and item["owner"] == include["panel"] and item["state"] == state_name)
            parts.append(render_panel_audit_html(root, contract, panel, case))
        parts.append(f"</{region_tag}>")
    parts.append(f"</{tag}>")
    return "\n".join(parts)


def render_panel_audit_html(root: Path, contract: dict[str, Any], panel: dict[str, Any], case: dict[str, Any] | None) -> str:
    presentation = panel.get("presentation") or {}
    html_contract = presentation.get("html") or {}
    root_spec = html_contract.get("root") or {"element": "section"}
    tag = root_spec.get("element", "section")
    classes = " ".join(["contract-panel"] + root_spec.get("classes", []))
    attrs = {
        "class": classes,
        "data-contract-panel": panel["id"],
        "data-contract-state": panel["state"],
    }
    if root_spec.get("role") and root_spec["role"] != "none":
        attrs["role"] = root_spec["role"]
    lines = [f"<{tag}{format_attrs(attrs)}>"]
    slots = html_contract.get("slots") or default_html_slots(panel)
    field_slots = [slot for slot in slots if slot["kind"] == "field"]
    for slot in slots:
        if slot["kind"] == "field":
            continue
        records = records_for_panel(contract, panel, case)
        record = records[0] if records else {}
        context = render_context(contract, case)
        namespace = render_namespace(contract, case)
        lines.extend(render_html_slot_runtime(root, contract, panel, slot, record, context, namespace))
    if field_slots:
        records = records_for_panel(contract, panel, case)
        lines.append('<div class="audit-records">')
        for record in records[:4] or [{}]:
            lines.append('<article class="audit-record">')
            for slot in field_slots:
                lines.extend(render_html_field_slot(record, slot))
            lines.append('</article>')
        lines.append('</div>')
    lines.append(f"</{tag}>")
    return "\n".join(lines)


def render_html_slot_runtime(root: Path, contract: dict[str, Any], panel: dict[str, Any], slot: dict[str, Any], record: dict[str, Any], context: dict[str, Any], namespace: dict[str, Any]) -> list[str]:
    kind = slot["kind"]
    tag = slot["element"]
    classes = slot.get("classes", [])
    attrs: dict[str, str] = {"data-contract-slot": slot.get("slot", slot.get("ref", "action"))}
    if classes:
        attrs["class"] = " ".join(classes)
    if slot.get("role") and slot["role"] != "none":
        attrs["role"] = slot["role"]
    if kind == "copy":
        copy_ref = slot_ref(panel, "copy", slot["slot"])
        attrs["data-copy"] = copy_ref
        if slot.get("level"):
            attrs["aria-level"] = str(slot["level"])
        text = resolve_copy_text(root, contract, copy_ref, record, context, namespace)
        return [f"<{tag}{format_attrs(attrs)}>{html.escape(text)}</{tag}>"]
    if kind == "asset":
        asset_ref = slot_ref(panel, "asset", slot["slot"])
        attrs["data-asset"] = asset_ref
        if slot.get("alt_copy_slot"):
            attrs["data-alt-copy"] = slot_ref(panel, "copy", slot["alt_copy_slot"])
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


def slot_ref(panel: dict[str, Any], kind: str, slot: str) -> str:
    key = "copy" if kind == "copy" else "assets"
    for ref in panel["slots"][key]:
        if ref.rsplit(".", 1)[-1] == slot:
            return ref
    raise KeyError(f"{panel['id']} has no {kind} slot {slot}")


def textual_audit_lines(root: Path, contract: dict[str, Any], case_id: str, case: dict[str, Any]) -> list[tuple[str, str]]:
    projection = panels_projection(contract)
    view = contract["views"][case["view"]]
    lines: list[tuple[str, str]] = []
    if view.get("includes"):
        for include in view["includes"]:
            state_name = case["panels"][include["id"]]["state"]
            panel = next(item for item in projection["panels"] if item["owner_kind"] == "panel" and item["owner"] == include["panel"] and item["state"] == state_name)
            lines.extend(panel_textual_lines(root, contract, panel, case))
    else:
        panel = next(item for item in projection["panels"] if item["owner_kind"] == "view" and item["owner"] == case["view"] and item["state"] == case["state"])
        lines.extend(panel_textual_lines(root, contract, panel, case))
    return lines or [("static", " ")]


def panel_textual_lines(root: Path, contract: dict[str, Any], panel: dict[str, Any], case: dict[str, Any] | None) -> list[tuple[str, str]]:
    lines: list[tuple[str, str]] = []
    textual = (panel.get("presentation") or {}).get("textual") or {}
    widgets = textual.get("widgets") or []
    if widgets:
        records = records_for_panel(contract, panel, case)
        record = records[0] if records else {}
        context = render_context(contract, case)
        namespace = render_namespace(contract, case)
        for widget in widgets:
            bind_kind, bind_value = next(iter(widget["bind"].items()))
            if bind_kind == "copy":
                ref = slot_ref(panel, "copy", bind_value)
                lines.append(("static", resolve_copy_text(root, contract, ref, record, context, namespace)))
            elif bind_kind == "asset":
                ref = slot_ref(panel, "asset", bind_value)
                lines.append(("static", resolve_asset_result(root, contract, ref, record, context, namespace).alt or contract["assets"][ref]["placeholder"]["label"]))
            elif bind_kind == "field":
                lines.append(("static", str(record.get(bind_value, "—"))))
            elif bind_kind == "action":
                lines.append(("button", humanize(bind_value)))
            elif bind_kind == "literal":
                lines.append(("static", str(bind_value)))
        return lines
    records = records_for_panel(contract, panel, case)
    record = records[0] if records else {}
    context = render_context(contract, case)
    namespace = render_namespace(contract, case)
    for copy_ref in panel["slots"]["copy"]:
        lines.append(("static", resolve_copy_text(root, contract, copy_ref, record, context, namespace)))
    for asset_ref in panel["slots"]["assets"]:
        lines.append(("static", resolve_asset_result(root, contract, asset_ref, record, context, namespace).alt or contract["assets"][asset_ref]["placeholder"]["label"]))
    fields = panel["slots"].get("fields", [])
    if fields:
        for record in (records_for_panel(contract, panel, case)[:4] or [{}]):
            for field in fields:
                lines.append(("static", f"{humanize(field)}: {record.get(field, '—')}"))
    for action in panel["slots"]["actions"]:
        lines.append(("button", humanize(action)))
    return lines or [("static", " ")]


def records_for_panel(contract: dict[str, Any], panel: dict[str, Any], case: dict[str, Any] | None) -> list[dict[str, Any]]:
    resource_id = panel_resource(contract, panel)
    resource_key = f"{resource_id.lower()}_id"
    owner_context = panel_owner_context(contract, panel)
    fixtures = case.get("fixtures", []) if case else list(contract.get("fixtures", {}))
    records: list[dict[str, Any]] = []
    if case:
        namespace = fixture_namespace(contract, fixtures)
        records.extend(_find_resource_records(namespace, resource_id))
        records = _apply_fact_uses(contract, case.get("facts", []), namespace, resource_id, records)
        context = _resolved_case_context(contract, case, namespace)
    else:
        context = {}
        for fixture_id in fixtures:
            records.extend(_find_resource_records(contract["fixtures"][fixture_id]["values"], resource_id))
        records = _apply_facts_with_available_fixtures(contract, resource_id, records)
    selected_id = context.get(resource_key)
    if not selected_id and resource_key in owner_context:
        selected_id = context.get(f"selected_{resource_key}")
    if selected_id and resource_key in owner_context:
        selected = [record for record in records if record.get("id") == selected_id]
        if selected:
            return selected
    if resource_key in owner_context and records:
        return records[:1]
    return records


def panel_resource(contract: dict[str, Any], panel: dict[str, Any]) -> str:
    if panel["owner_kind"] == "panel":
        return contract["panels"][panel["owner"]]["resource"]
    return contract["views"][panel["owner"]]["resource"]


def panel_owner_context(contract: dict[str, Any], panel: dict[str, Any]) -> dict[str, Any]:
    if panel["owner_kind"] == "panel":
        return contract["panels"][panel["owner"]].get("context", {})
    return contract["views"][panel["owner"]].get("context", {})


def _resolved_case_context(contract: dict[str, Any], case: dict[str, Any], namespace: dict[str, Any]) -> dict[str, Any]:
    context = {}
    for key, value in (case.get("context") or {}).items():
        context[key] = resolve(value, namespace)
    return context


def _find_resource_records(value: Any, resource_id: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if value.get("resource") == resource_id:
            record = dict(value)
            record.pop("resource", None)
            records.append(record)
        for child in value.values():
            records.extend(_find_resource_records(child, resource_id))
    elif isinstance(value, list):
        for item in value:
            records.extend(_find_resource_records(item, resource_id))
    return records


def _apply_facts_with_available_fixtures(contract: dict[str, Any], resource_id: str, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    current = list(records)
    namespaces = [{}]
    for fixture_id in contract.get("fixtures", {}):
        try:
            namespaces.append(fixture_namespace(contract, [fixture_id]))
        except (AssertionError, KeyError, TypeError):
            continue
    for fact_id in contract.get("facts", {}):
        fact_uses = [{"use": fact_id}]
        for namespace in namespaces:
            try:
                next_records = _apply_fact_uses(contract, fact_uses, namespace, resource_id, current)
            except (AssertionError, KeyError, TypeError):
                continue
            current = _dedupe_records(next_records)
            break
    return current


def _apply_fact_uses(contract: dict[str, Any], fact_uses: list[dict[str, str]], namespace: dict[str, Any], resource_id: str, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    current = list(records)
    for fact_use in fact_uses:
        fact_id = fact_use["use"]
        kind, body = _fact_selector(contract["facts"][fact_id], fact_id)
        if body["resource"] != resource_id:
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
    if len(argv) != 2:
        print("usage: pyspec audit <root>", file=sys.stderr)
        return 2
    root = Path(argv[0]).resolve()
    tools_root = Path(argv[1]).resolve()
    from .io import read_yaml
    from .paths import COMPILED_SPEC_PATH
    contract = read_yaml(root / COMPILED_SPEC_PATH)
    _render_visual_audit(root, contract, tools_root)
    # Playwright/Textual can leave cleanup state that blocks interpreter shutdown in
    # constrained containers. This worker has completed all file outputs; exit
    # immediately so the compiler process stays deterministic.
    os._exit(0)


if __name__ == "__main__":
    raise SystemExit(main())
