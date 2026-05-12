from __future__ import annotations

import asyncio
import base64
import html
import json
import os
import shutil
import subprocess
import sys
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
            for breakpoint in profile["html"]["breakpoints"]:
                stem = f"{safe_id(profile_id)}.{safe_id(breakpoint)}"
                files.add(f"generated/audit/html/panels/{panel_path}/{stem}.html")
                files.add(f"generated/audit/html/panels/{panel_path}/{stem}.png")
            for breakpoint in profile["textual"]["breakpoints"]:
                stem = f"{safe_id(profile_id)}.{safe_id(breakpoint)}"
                files.add(f"generated/audit/textual/panels/{panel_path}/{stem}.py")
                files.add(f"generated/audit/textual/panels/{panel_path}/{stem}.svg")

    for case_id, case in contract.get("render_cases", {}).items():
        profile = contract["audit_profiles"][case["profile"]]
        view_path = safe_id(case["view"])
        case_path = safe_id(case_id)
        profile_path = safe_id(case["profile"])
        if "html" in case["surfaces"]:
            for breakpoint in profile["html"]["breakpoints"]:
                stem = f"{profile_path}.{safe_id(breakpoint)}.{case_path}"
                files.add(f"generated/audit/html/views/{view_path}/{stem}.html")
                files.add(f"generated/audit/html/views/{view_path}/{stem}.png")
        if "textual" in case["surfaces"]:
            for breakpoint in profile["textual"]["breakpoints"]:
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


def _render_visual_audit(root: Path, contract: dict[str, Any], tools_root: Path) -> None:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover - dependency absence is environment-specific.
        raise ContractError("Missing Playwright dependency; install requirements.txt and run python -m playwright install chromium, or provide system Chromium") from exc

    mermaid_js = _mermaid_js_path(tools_root, root)
    projection = panels_projection(contract)
    with sync_playwright() as pw:
        browser = _launch_chromium(pw)
        try:
            for panel_id, panel in sorted(contract.get("panels", {}).items()):
                diagram = panel_fsm_mermaid(panel_id, panel)
                svg = _render_mermaid_svg(browser, mermaid_js, diagram, safe_id(panel_id))
                path = root / "generated" / "audit" / "fsm" / f"{safe_id(panel_id)}.svg"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(svg, encoding="utf-8")
            for view_id, view in sorted(contract.get("views", {}).items()):
                if not view.get("includes"):
                    continue
                diagram = composition_mermaid(view_id, view)
                svg = _render_mermaid_svg(browser, mermaid_js, diagram, safe_id(view_id))
                path = root / "generated" / "audit" / "composition" / f"{safe_id(view_id)}.svg"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(svg, encoding="utf-8")
        finally:
            browser.close()

        browser = _launch_chromium(pw)
        page = browser.new_page()
        try:
            for panel in sorted(projection["panels"], key=lambda p: p["id"]):
                for profile_id, profile in sorted(contract.get("audit_profiles", {}).items()):
                    html_doc = audit_html_document(contract, render_panel_audit_html(root, contract, panel, None))
                    for name, viewport in sorted(profile["html"]["breakpoints"].items()):
                        stem = f"{safe_id(profile_id)}.{safe_id(name)}"
                        base = root / "generated" / "audit" / "html" / "panels" / safe_id(panel["id"]) / stem
                        _write_html_and_png_page(page, html_doc, base, viewport)
            for case_id, case in sorted(contract.get("render_cases", {}).items()):
                profile = contract["audit_profiles"][case["profile"]]
                if "html" in case["surfaces"]:
                    html_doc = audit_html_document(contract, render_case_html(root, contract, case_id, case))
                    for name, viewport in sorted(profile["html"]["breakpoints"].items()):
                        stem = f"{safe_id(case['profile'])}.{safe_id(name)}.{safe_id(case_id)}"
                        base = root / "generated" / "audit" / "html" / "views" / safe_id(case["view"]) / stem
                        _write_html_and_png_page(page, html_doc, base, viewport)
        finally:
            page.close()
            browser.close()

    if projection["panels"] or any("textual" in case["surfaces"] for case in contract.get("render_cases", {}).values()):
        try:
            import textual  # noqa: F401
        except Exception as exc:  # pragma: no cover - dependency absence is environment-specific.
            raise ContractError("Missing Textual dependency; install requirements.txt") from exc
        textual_jobs: list[tuple[Path, list[tuple[str, str]], dict[str, int]]] = []
        for panel in sorted(projection["panels"], key=lambda p: p["id"]):
            lines = panel_textual_lines(root, contract, panel, None)
            for profile_id, profile in sorted(contract.get("audit_profiles", {}).items()):
                for name, viewport in sorted(profile["textual"]["breakpoints"].items()):
                    stem = f"{safe_id(profile_id)}.{safe_id(name)}"
                    base = root / "generated" / "audit" / "textual" / "panels" / safe_id(panel["id"]) / stem
                    _write_textual_source(Path(str(base) + ".py"), lines)
                    textual_jobs.append((Path(str(base) + ".svg"), lines, viewport))
        for case_id, case in sorted(contract.get("render_cases", {}).items()):
            if "textual" not in case["surfaces"]:
                continue
            profile = contract["audit_profiles"][case["profile"]]
            lines = textual_audit_lines(root, contract, case_id, case)
            for name, viewport in sorted(profile["textual"]["breakpoints"].items()):
                stem = f"{safe_id(case['profile'])}.{safe_id(name)}.{safe_id(case_id)}"
                base = root / "generated" / "audit" / "textual" / "views" / safe_id(case["view"]) / stem
                _write_textual_source(Path(str(base) + ".py"), lines)
                textual_jobs.append((Path(str(base) + ".svg"), lines, viewport))
        asyncio.run(_render_textual_batch(textual_jobs))


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


def _render_html_png(browser: Any, html_doc: str, path: Path, viewport: dict[str, int]) -> None:
    page = browser.new_page(viewport={"width": viewport["width"], "height": viewport["height"]})
    try:
        page.set_content(html_doc, wait_until="load")
        page.screenshot(path=str(path), full_page=False, type="png", timeout=10000)
    finally:
        page.close()
    if path.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
        raise ContractError(f"HTML renderer did not produce a PNG: {path}")

def _chromium_executable() -> str | None:
    return os.environ.get("CONTRACT_AUDIT_CHROMIUM") or shutil.which("chromium") or shutil.which("chromium-browser") or shutil.which("google-chrome") or shutil.which("google-chrome-stable")


def _launch_chromium(pw: Any) -> Any:
    executable = _chromium_executable()
    args = ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
    if executable:
        return pw.chromium.launch(executable_path=executable, args=args)
    return pw.chromium.launch(args=args)


def _mermaid_js_path(tools_root: Path, root: Path) -> Path:
    candidates = [
        tools_root / "node_modules" / "mermaid" / "dist" / "mermaid.min.js",
        root / "node_modules" / "mermaid" / "dist" / "mermaid.min.js",
        Path.cwd() / "node_modules" / "mermaid" / "dist" / "mermaid.min.js",
        ROOT / "node_modules" / "mermaid" / "dist" / "mermaid.min.js",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise ContractError("Missing Mermaid dependency; run npm install from the contract project root")


def _render_mermaid_svg(browser: Any, mermaid_js: Path, diagram: str, element_id: str) -> str:
    page = browser.new_page()
    try:
        page.set_content('<!doctype html><html><body><div id="out"></div></body></html>')
        page.add_script_tag(content=mermaid_js.read_text(encoding="utf-8"))
        svg = page.evaluate(
            """async ({diagram, elementId}) => {
                mermaid.initialize({startOnLoad:false, securityLevel:'loose', theme:'default'});
                const result = await mermaid.render(elementId, diagram);
                document.getElementById('out').innerHTML = result.svg;
                return result.svg;
            }""",
            {"diagram": diagram, "elementId": element_id},
        )
    finally:
        page.close()
    if not isinstance(svg, str) or "<svg" not in svg:
        raise ContractError("Mermaid renderer did not produce SVG")
    return svg


def _render_html_png(browser: Any, html_doc: str, path: Path, viewport: dict[str, int]) -> None:
    page = browser.new_page(viewport={"width": viewport["width"], "height": viewport["height"]})
    try:
        page.set_content(html_doc, wait_until="load")
        page.screenshot(path=str(path), full_page=False, type="png", timeout=10000)
    finally:
        page.close()
    if path.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
        raise ContractError(f"HTML renderer did not produce a PNG: {path}")


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


def panel_fsm_mermaid(panel_id: str, panel: dict[str, Any]) -> str:
    lines = ["stateDiagram-v2", f"  [*] --> {safe_id(panel['initial'])}"]
    for state_name in sorted(panel["states"]):
        lines.append(f"  state \"{state_name}\" as {safe_id(state_name)}")
    for transition in panel.get("transitions", []):
        lines.append(f"  {safe_id(transition['from'])} --> {safe_id(transition['to'])}: {transition['event']}")
    return "\n".join(lines) + "\n"


def composition_mermaid(view_id: str, view: dict[str, Any]) -> str:
    lines = ["flowchart LR", "  view((view context))"]
    for slot_name in sorted(view["layout"]["slots"]):
        lines.append(f"  slot_{safe_id(slot_name)}[\"slot: {slot_name}\"]")
        lines.append(f"  view --> slot_{safe_id(slot_name)}")
    for include in view.get("includes", []):
        inst = safe_id(include["id"])
        lines.append(f"  instance_{inst}[\"{include['id']}\"]")
        lines.append(f"  slot_{safe_id(include['slot'])} --> instance_{inst}")
    for rule in view.get("sync", []):
        sync_id = safe_id(rule["id"])
        source = safe_id(rule["when"]["panel"])
        lines.append(f"  sync_{sync_id}{{\"{rule['when']['emits']}\"}}")
        lines.append(f"  instance_{source} --> sync_{sync_id}")
        for effect in rule["do"]:
            if "send" in effect:
                target = safe_id(effect["send"]["panel"])
                lines.append(f"  sync_{sync_id} -->|{effect['send']['event']}| instance_{target}")
            if "set" in effect:
                lines.append(f"  sync_{sync_id} -. set {effect['set']['context']} .-> view")
    return "\n".join(lines) + "\n"


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
    final = item.get("final") or {"status": "placeholder", "resolver": ref}
    if final["status"] == "placeholder":
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
    final = item.get("final") or {"status": "placeholder", "resolver": ref}
    if final["status"] == "placeholder":
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
    contract = read_yaml(root / "contract.yaml")
    _render_visual_audit(root, contract, tools_root)
    # Playwright/Textual can leave cleanup state that blocks interpreter shutdown in
    # constrained containers. This worker has completed all file outputs; exit
    # immediately so the compiler process stays deterministic.
    os._exit(0)


if __name__ == "__main__":
    raise SystemExit(main())
