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
from .project import css_value, default_html_slots, format_attrs, humanize, panels_projection, panel_styles_projection, safe_id
from .runtime import fixture_namespace, resolve

ROOT = Path(__file__).resolve().parents[1]


def audit_expected_files(contract: dict[str, Any]) -> set[str]:
    files: set[str] = {
        "generated/audit/copy.yaml",
        "generated/audit/fixtures.yaml",
    }
    for asset_id in contract.get("assets", {}):
        files.add(f"generated/audit/assets/{safe_id(asset_id)}.svg")
    for panel_id in contract.get("panels", {}):
        files.add(f"generated/audit/fsm/{safe_id(panel_id)}.svg")
    for view_id, view in contract.get("views", {}).items():
        if view.get("includes"):
            files.add(f"generated/audit/composition/{safe_id(view_id)}.svg")

    projection = panels_projection(contract)
    for panel in projection["panels"]:
        for profile_id, profile in sorted(contract.get("audit_profiles", {}).items()):
            panel_path = safe_id(panel["id"])
            for breakpoint in profile.get("html", {}).get("breakpoints", {}):
                stem = f"{safe_id(profile_id)}.{safe_id(breakpoint)}"
                files.add(f"generated/audit/html/panels/{panel_path}/{stem}.html")
                files.add(f"generated/audit/html/panels/{panel_path}/{stem}.png")
            for breakpoint in profile.get("textual", {}).get("breakpoints", {}):
                stem = f"{safe_id(profile_id)}.{safe_id(breakpoint)}"
                files.add(f"generated/audit/textual/panels/{panel_path}/{stem}.py")
                files.add(f"generated/audit/textual/panels/{panel_path}/{stem}.svg")

    for case_id, case in contract.get("render_cases", {}).items():
        profile = contract["audit_profiles"][case["profile"]]
        view_path = safe_id(case["view"])
        case_path = safe_id(case_id)
        profile_path = safe_id(case["profile"])
        if "html" in case["surfaces"]:
            for breakpoint in profile.get("html", {}).get("breakpoints", {}):
                stem = f"{profile_path}.{safe_id(breakpoint)}.{case_path}"
                files.add(f"generated/audit/html/views/{view_path}/{stem}.html")
                files.add(f"generated/audit/html/views/{view_path}/{stem}.png")
        if "textual" in case["surfaces"]:
            for breakpoint in profile.get("textual", {}).get("breakpoints", {}):
                stem = f"{profile_path}.{safe_id(breakpoint)}.{case_path}"
                files.add(f"generated/audit/textual/views/{view_path}/{stem}.py")
                files.add(f"generated/audit/textual/views/{view_path}/{stem}.svg")
    return files


def generate_audit(root: Path, contract: dict[str, Any], tools_root: Path | None = None) -> None:
    audit_root = root / "generated" / "audit"
    if audit_root.exists():
        shutil.rmtree(audit_root)
    audit_root.mkdir(parents=True, exist_ok=True)

    write_yaml(audit_root / "copy.yaml", {"project": contract["project"], "copy": contract.get("copies", {})})
    write_yaml(audit_root / "fixtures.yaml", {"project": contract["project"], "fixtures": contract.get("fixtures", {})})

    for asset_id, asset in sorted(contract.get("assets", {}).items()):
        path = audit_root / "assets" / f"{safe_id(asset_id)}.svg"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(asset_placeholder_svg(asset), encoding="utf-8")

    if not contract.get("panels") and not contract.get("render_cases"):
        return
    _render_visual_audit(root, contract, tools_root or root)


def _render_visual_audit_subprocess(root: Path, tools_root: Path) -> None:
    env = os.environ.copy()
    env["PM_CONTRACT_AUDIT_WORKER"] = "1"
    cmd = [sys.executable, "-m", "pm_contract.audit", str(root), str(tools_root)]
    result = subprocess.run(cmd, cwd=str(root), env=env, timeout=900)
    if result.returncode != 0:
        raise ContractError(f"Visual audit renderer failed with exit code {result.returncode}")


def _render_visual_audit(root: Path, contract: dict[str, Any], _tools_root: Path) -> None:
    projection = panels_projection(contract)

    for panel_id, panel in sorted(contract.get("panels", {}).items()):
        path = root / "generated" / "audit" / "fsm" / f"{safe_id(panel_id)}.svg"
        _write_graphviz_svg(path, panel_fsm_dot(panel_id, panel, contract))
    for view_id, view in sorted(contract.get("views", {}).items()):
        if not view.get("includes"):
            continue
        path = root / "generated" / "audit" / "composition" / f"{safe_id(view_id)}.svg"
        _write_graphviz_svg(path, composition_dot(view_id, view))

    has_html_audit = bool(
        projection["panels"] and any(profile.get("html") for profile in contract.get("audit_profiles", {}).values())
    ) or any("html" in case["surfaces"] for case in contract.get("render_cases", {}).values())
    if has_html_audit:
        _render_html_audit(root, contract, projection)

    if projection["panels"] or any("textual" in case["surfaces"] for case in contract.get("render_cases", {}).values()):
        try:
            import textual  # noqa: F401
        except Exception as exc:  # pragma: no cover - dependency absence is environment-specific.
            raise ContractError("Missing Textual dependency; install requirements.txt") from exc
        textual_jobs: list[tuple[Path, list[tuple[str, str]], dict[str, int]]] = []
        for panel in sorted(projection["panels"], key=lambda p: p["id"]):
            lines = panel_textual_lines(root, contract, panel, None)
            for profile_id, profile in sorted(contract.get("audit_profiles", {}).items()):
                for name, viewport in sorted(profile.get("textual", {}).get("breakpoints", {}).items()):
                    stem = f"{safe_id(profile_id)}.{safe_id(name)}"
                    base = root / "generated" / "audit" / "textual" / "panels" / safe_id(panel["id"]) / stem
                    _write_textual_source(Path(str(base) + ".py"), lines)
                    textual_jobs.append((Path(str(base) + ".svg"), lines, viewport))
        for case_id, case in sorted(contract.get("render_cases", {}).items()):
            if "textual" not in case["surfaces"]:
                continue
            profile = contract["audit_profiles"][case["profile"]]
            lines = textual_audit_lines(root, contract, case_id, case)
            for name, viewport in sorted(profile.get("textual", {}).get("breakpoints", {}).items()):
                stem = f"{safe_id(case['profile'])}.{safe_id(name)}.{safe_id(case_id)}"
                base = root / "generated" / "audit" / "textual" / "views" / safe_id(case["view"]) / stem
                _write_textual_source(Path(str(base) + ".py"), lines)
                textual_jobs.append((Path(str(base) + ".svg"), lines, viewport))
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
                for panel in sorted(projection["panels"], key=lambda p: p["id"]):
                    for profile_id, profile in sorted(contract.get("audit_profiles", {}).items()):
                        html_profile = profile.get("html")
                        if not html_profile:
                            continue
                        html_doc = audit_html_document(contract, render_panel_audit_html(root, contract, panel, None))
                        for name, viewport in sorted(html_profile["breakpoints"].items()):
                            stem = f"{safe_id(profile_id)}.{safe_id(name)}"
                            base = root / "generated" / "audit" / "html" / "panels" / safe_id(panel["id"]) / stem
                            _write_html_and_png_page(page, html_doc, base, viewport)
                for case_id, case in sorted(contract.get("render_cases", {}).items()):
                    profile = contract["audit_profiles"][case["profile"]]
                    if "html" in case["surfaces"]:
                        html_doc = audit_html_document(contract, render_case_html(root, contract, case_id, case))
                        for name, viewport in sorted(profile.get("html", {}).get("breakpoints", {}).items()):
                            stem = f"{safe_id(case['profile'])}.{safe_id(name)}.{safe_id(case_id)}"
                            base = root / "generated" / "audit" / "html" / "views" / safe_id(case["view"]) / stem
                            _write_html_and_png_page(page, html_doc, base, viewport)
            finally:
                page.close()
        finally:
            browser.close()


def _write_html_and_png_page(page: Any, html_doc: str, base: Path, viewport: dict[str, int]) -> None:
    html_path = Path(str(base) + ".html")
    png_path = Path(str(base) + ".png")
    html_path.parent.mkdir(parents=True, exist_ok=True)
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
                    f"pattern: {state['pattern']}",
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
        transition_id = _dot_node_id("transition", f"{index}_{transition['from']}_{transition['to']}_{transition['event']}")
        lines.append(
            _dot_html_node(
                transition_id,
                _dot_card(
                    f"on {transition['event']}",
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


def composition_dot(view_id: str, view: dict[str, Any]) -> str:
    view_node = _dot_node_id("layout_view", view_id)
    slots = sorted(view["layout"]["slots"].items(), key=lambda item: (item[1].get("order", 0), item[0]), reverse=True)
    slot_ids = [_dot_node_id("layout_slot", slot_name) for slot_name, _ in slots]
    slot_order = {slot_name: slot.get("order", 0) for slot_name, slot in view["layout"]["slots"].items()}
    includes = sorted(view.get("includes", []), key=lambda include: (slot_order.get(include["slot"], 0), include["id"]), reverse=True)
    instance_ids = [_dot_node_id("layout_instance", include["id"]) for include in includes]
    lines = [
        f"digraph {_dot_quote('composition_' + safe_id(view_id))} {{",
        '  graph [rankdir="LR", bgcolor="transparent", pad="0.25", nodesep="0.35", ranksep="0.78", splines="spline", compound="true"];',
        '  node [fontname="Arial", fontsize="11"];',
        '  edge [color="#3f3f46", fontname="Arial", fontsize="10", arrowsize="0.8"];',
        "  subgraph cluster_layout {",
        '    label="Layout";',
        '    color="#d4d4d8";',
        '    fontname="Arial";',
        '    fontsize="12";',
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
            indent="    ",
        ),
    ]
    for slot_name, slot in slots:
        slot_id = _dot_node_id("layout_slot", slot_name)
        lines.append(
            _dot_html_node(
                slot_id,
                _dot_card(
                    f"slot: {slot_name}",
                    f"order: {slot.get('order', 0)}",
                    [
                        ("element", [slot.get("element", "")]),
                        ("role", [slot.get("role", "none")]),
                        ("required", [str(slot["required"]).lower()]),
                    ],
                    header_bg="#f8fafc",
                    border="#71717a",
                ),
                indent="    ",
            )
        )
        lines.append(f"    {_dot_quote(view_node)} -> {_dot_quote(slot_id)};")
    for include in includes:
        inst = _dot_node_id("layout_instance", include["id"])
        slot_id = _dot_node_id("layout_slot", include["slot"])
        selected = include.get("selected") or {}
        selected_lines = []
        if selected:
            selected_lines.append(f"selected state: {selected['state']}")
            selected_lines.extend(f"when {key}: {value}" for key, value in selected.get("when", {}).items())
        lines.append(
            _dot_html_node(
                inst,
                _dot_card(
                    f"instance: {include['id']}",
                    include["panel"],
                    [
                        ("slot", [include["slot"]]),
                        ("initial", [include["initial"]]),
                        ("context", _format_mapping(include.get("context", {}))),
                        ("selected", selected_lines),
                    ],
                    header_bg="#fff7ed",
                    border="#c2410c",
                ),
                indent="    ",
            )
        )
        lines.append(f"    {_dot_quote(slot_id)} -> {_dot_quote(inst)};")
    if slot_ids:
        lines.append("    { rank=same; " + " ".join(_dot_quote(slot_id) for slot_id in slot_ids) + " }")
        lines.extend(_dot_invisible_order(slot_ids, indent="    "))
    if instance_ids:
        lines.append("    { rank=same; " + " ".join(_dot_quote(instance_id) for instance_id in instance_ids) + " }")
        lines.extend(_dot_invisible_order(instance_ids, indent="    "))
    lines.append("  }")

    lines.extend(
        [
            "  subgraph cluster_sync {",
            '    label="Sync rules";',
            '    color="#d4d4d8";',
            '    fontname="Arial";',
            '    fontsize="12";',
        ]
    )
    if not view.get("sync"):
        lines.append(_dot_html_node("sync_none", _dot_card("No sync rules", None, [], header_bg="#f8fafc"), indent="    "))
    for rule in view.get("sync", []):
        source = _dot_node_id("sync_source", rule["id"])
        sync_id = _dot_node_id("sync_rule", rule["id"])
        lines.append(
            _dot_html_node(
                source,
                _dot_card(
                    f"{rule['when']['panel']} emits",
                    rule["when"]["emits"],
                    [],
                    header_bg="#eef2ff",
                    border="#4f46e5",
                ),
                indent="    ",
            )
        )
        lines.append(
            _dot_html_node(
                sync_id,
                _dot_card(
                    rule["id"],
                    "sync rule",
                    [
                        ("when", [f"panel: {rule['when']['panel']}", f"emits: {rule['when']['emits']}"]),
                        ("do", _format_sync_effects(rule.get("do", []))),
                    ],
                    header_bg="#fefce8",
                    border="#a16207",
                ),
                indent="    ",
            )
        )
        lines.append(f"    {_dot_quote(source)} -> {_dot_quote(sync_id)};")
        action_ids = []
        indexed_effects = list(enumerate(rule["do"]))
        for index, effect in reversed(indexed_effects):
            action_id = _dot_node_id("sync_action", f"{rule['id']}_{index}")
            action_ids.append(action_id)
            if "send" in effect:
                title = f"send to {effect['send']['panel']}"
                sections = [("event", [effect["send"]["event"]])]
                header_bg = "#fff7ed"
                border = "#c2410c"
            else:
                title = "set view context"
                sections = [("context", [effect["set"]["context"]]), ("from", [effect["set"]["from"]])]
                header_bg = "#f0fdf4"
                border = "#15803d"
            lines.append(_dot_html_node(action_id, _dot_card(title, None, sections, header_bg=header_bg, border=border), indent="    "))
            lines.append(f"    {_dot_quote(sync_id)} -> {_dot_quote(action_id)};")
        if action_ids:
            lines.append("    { rank=same; " + " ".join(_dot_quote(action_id) for action_id in action_ids) + " }")
            lines.extend(_dot_invisible_order(action_ids, indent="    "))
    lines.append("  }")
    lines.append("}")
    return "\n".join(lines) + "\n"


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
    if _is_data_event(transition["event"]):
        bindings = _transition_data_bindings(panel, transition)
        data_sources = [binding["capability"] for binding in bindings]
        queries = [binding["query"] for binding in bindings]
        inputs = _format_data_inputs(panel, bindings, contract)
        if inputs:
            sections.append(("input", inputs))
        if queries:
            sections.append(("query", queries))
        if data_sources:
            sections.append(("data", data_sources))
    else:
        target_bindings = _transition_target_data_bindings(panel, transition)
        data_sources = [binding["capability"] for binding in target_bindings]
        queries = [binding["query"] for binding in target_bindings]
        required_context = _format_data_inputs(panel, target_bindings, contract)
        if data_sources:
            sections.append(("data", data_sources))
        if queries:
            sections.append(("query", queries))
        if required_context:
            sections.append(("requires context", required_context))
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
            lines.append(f"emit {effect['emit']}")
        elif "set" in effect:
            assignment = effect["set"]
            if "from" in assignment:
                lines.append(f"set {assignment['context']} from {assignment['from']}")
            else:
                lines.append(f"set {assignment['context']} to {_format_scalar(assignment['value'])}")
    return lines


def _format_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def _format_sync_effects(effects: Iterable[dict[str, Any]]) -> list[str]:
    lines = []
    for effect in effects:
        if "set" in effect:
            lines.append(f"set {effect['set']['context']} from {effect['set']['from']}")
        elif "send" in effect:
            lines.append(f"send {effect['send']['event']} to {effect['send']['panel']}")
    return lines


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
    .contract-layout-slot { min-height: 120px; display: grid; gap: 12px; align-content: start; }
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
        "<title>contract audit render</title>",
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


def render_composed_case_html(root: Path, contract: dict[str, Any], case: dict[str, Any]) -> str:
    view = contract["views"][case["view"]]
    projection = panels_projection(contract)
    composition = next(item for item in projection["compositions"] if item["id"] == case["view"])
    root_spec = composition["layout"].get("root") or {"element": "section"}
    tag = root_spec.get("element", "section")
    classes = " ".join(["contract-composed-view"] + root_spec.get("classes", []))
    attrs = {"class": classes, "data-contract-composition": composition["id"]}
    if root_spec.get("role") and root_spec["role"] != "none":
        attrs["role"] = root_spec["role"]
    parts = [f"<{tag}{format_attrs(attrs)}>"]
    for slot_name, slot in sorted(view["layout"]["slots"].items(), key=lambda item: item[1].get("order", 0)):
        slot_tag = slot.get("element", "div")
        slot_classes = " ".join(["contract-layout-slot", f"contract-layout-slot--{slot_name}"] + slot.get("classes", []))
        slot_attrs = {"class": slot_classes, "data-layout-slot": slot_name, "data-required": str(slot["required"]).lower()}
        if slot.get("role") and slot["role"] != "none":
            slot_attrs["role"] = slot["role"]
        parts.append(f"<{slot_tag}{format_attrs(slot_attrs)}>")
        for include in [item for item in view["includes"] if item["slot"] == slot_name]:
            state_name = case["panels"][include["id"]]["state"]
            panel = next(item for item in projection["panels"] if item["owner_kind"] == "panel" and item["owner"] == include["panel"] and item["state"] == state_name)
            parts.append(render_panel_audit_html(root, contract, panel, case))
        parts.append(f"</{slot_tag}>")
    parts.append(f"</{tag}>")
    return "\n".join(parts)


def render_panel_audit_html(root: Path, contract: dict[str, Any], panel: dict[str, Any], case: dict[str, Any] | None) -> str:
    presentation = panel.get("presentation") or {}
    html_contract = presentation.get("html") or {}
    root_spec = html_contract.get("root") or {"element": "section"}
    tag = root_spec.get("element", "section")
    classes = " ".join(["contract-panel", f"contract-panel--{panel['pattern']}"] + root_spec.get("classes", []))
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
    fixtures = case.get("fixtures", []) if case else list(contract.get("fixtures", {}))
    records: list[dict[str, Any]] = []
    if case:
        namespace = fixture_namespace(contract, fixtures)
        records.extend(_find_resource_records(namespace, resource_id))
        context = _resolved_case_context(contract, case, namespace)
    else:
        context = {}
        for fixture_id in fixtures:
            records.extend(_find_resource_records(contract["fixtures"][fixture_id]["values"], resource_id))
    selected_id = context.get(f"selected_{resource_id.lower()}_id") or context.get("selected_project_id") or context.get("project_id") or context.get("id")
    if selected_id and panel["pattern"] in {"detail", "summary", "feed"}:
        selected = [record for record in records if record.get("id") == selected_id]
        if selected:
            return selected
    if panel["pattern"] in {"detail", "summary"} and records:
        return records[:1]
    return records


def panel_resource(contract: dict[str, Any], panel: dict[str, Any]) -> str:
    if panel["owner_kind"] == "panel":
        return contract["panels"][panel["owner"]]["resource"]
    return contract["views"][panel["owner"]]["resource"]


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
        print("usage: python -m pm_contract.audit <root> <tools_root>", file=sys.stderr)
        return 2
    root = Path(argv[0]).resolve()
    tools_root = Path(argv[1]).resolve()
    from .io import read_yaml
    from .paths import COMPILED_CONTRACT_PATH
    contract = read_yaml(root / COMPILED_CONTRACT_PATH)
    _render_visual_audit(root, contract, tools_root)
    # Playwright/Textual can leave cleanup state that blocks interpreter shutdown in
    # constrained containers. This worker has completed all file outputs; exit
    # immediately so the compiler process stays deterministic.
    os._exit(0)


if __name__ == "__main__":
    raise SystemExit(main())
