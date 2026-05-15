from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from .layers import LAYERS, layer_label, normalize_layers, parse_layers
from .paths import generated_relative as g

USER_PROMPT_PLACEHOLDER = "{{USER_PROMPT}}"

PROMPT_ROLES = ("pm_design", "test", "dev", "review")


def agent_prompt_paths() -> list[str]:
    return [g("agent_prompts", f"{role}.md") for role in PROMPT_ROLES]


def agent_prompt_projection_files(
    contract: dict[str, Any] | None = None,
    *,
    layers: str | set[str] | None = None,
) -> Iterable[tuple[str, str, str]]:
    active_layers = active_prompt_layers(contract, layers=layers)
    context = _PromptContext(contract=contract, layers=active_layers)
    yield g("agent_prompts", "pm_design.md"), _pm_design_prompt(context), "text"
    yield g("agent_prompts", "test.md"), _test_prompt(context), "text"
    yield g("agent_prompts", "dev.md"), _dev_prompt(context), "text"
    yield g("agent_prompts", "review.md"), _review_prompt(context), "text"


def write_agent_prompts(
    root: str | Path,
    *,
    layers: str | set[str] | None = None,
    contract: dict[str, Any] | None = None,
) -> set[str]:
    project_root = Path(root).resolve()
    written: set[str] = set()
    for relative, text, _ in agent_prompt_projection_files(contract, layers=layers):
        path = project_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        written.add(relative)
    return written


def active_prompt_layers(contract: dict[str, Any] | None = None, *, layers: str | set[str] | None = None) -> set[str]:
    explicit = _coerce_layers(layers)
    if explicit is not None:
        return explicit
    if contract is not None:
        return infer_contract_layers(contract)
    return set(LAYERS)


def infer_contract_layers(contract: dict[str, Any]) -> set[str]:
    active = {"core"}
    adapter_kinds = _entry_adapter_kinds(contract)
    if "http_api" in adapter_kinds:
        active.add("http")
    if contract.get("events") or "webhook" in adapter_kinds:
        active.add("events")
    if contract.get("workflows") or adapter_kinds & {"cli", "worker", "scheduled"}:
        active.add("workflow")
    if _contract_has_ui(contract):
        active.add("ui")
    if _contract_has_html(contract):
        active.update({"ui", "html"})
    if _contract_has_textual(contract):
        active.update({"ui", "textual"})
    return normalize_layers(active) or set(LAYERS)


def _coerce_layers(layers: str | set[str] | None) -> set[str] | None:
    if isinstance(layers, str):
        return parse_layers(layers)
    return normalize_layers(layers) if layers is not None else None


def _contract_has_ui(contract: dict[str, Any]) -> bool:
    return bool(
        contract.get("state_machines")
        or contract.get("text_resources")
        or contract.get("assets")
        or contract.get("content_cases")
        or contract.get("render_profiles")
    )


def _contract_has_html(contract: dict[str, Any]) -> bool:
    if "html_route" in _entry_adapter_kinds(contract):
        return True
    if any("html_viewports" in profile for profile in (contract.get("render_profiles") or {}).values()):
        return True
    for owner in (contract.get("state_machines") or {}).values():
        for state in (owner.get("view_states") or {}).values():
            if "html" in (state.get("renderers") or {}):
                return True
    return False


def _contract_has_textual(contract: dict[str, Any]) -> bool:
    if any("textual_viewports" in profile for profile in (contract.get("render_profiles") or {}).values()):
        return True
    for owner in (contract.get("state_machines") or {}).values():
        for state in (owner.get("view_states") or {}).values():
            if "textual" in (state.get("renderers") or {}):
                return True
    return False


def _contract_audit_cases(contract: dict[str, Any]) -> list[dict[str, Any]]:
    cases = []
    for state_machine in (contract.get("state_machines") or {}).values():
        for state in (state_machine.get("view_states") or {}).values():
            cases.extend((state.get("render_audit_cases") or {}).values())
    return cases


def _entry_adapter_kinds(contract: dict[str, Any]) -> set[str]:
    kinds: set[str] = set()
    for entry in (contract.get("entry_points") or {}).values():
        adapter = entry.get("adapter") or {}
        kinds.update(adapter)
    return kinds


class _PromptContext:
    def __init__(self, *, contract: dict[str, Any] | None, layers: set[str]) -> None:
        self.contract = contract
        self.layers = layers

    @property
    def label(self) -> str:
        return layer_label(self.layers)

    @property
    def layer_arg(self) -> str:
        return self.label

    @property
    def has_contract(self) -> bool:
        return self.contract is not None

    @property
    def project_name(self) -> str:
        if not self.contract:
            return "this project"
        return str(self.contract.get("project", "this project"))

    def compiled_summary(self) -> str:
        if not self.contract:
            return "No compiled spec was supplied. Use the active layers as the complete starting context."
        sections = [
            ("models", self.contract.get("models") or {}),
            ("operations", self.contract.get("operations") or {}),
            ("entry_points", self.contract.get("entry_points") or {}),
            ("workflows", self.contract.get("workflows") or {}),
            ("state_machines", self.contract.get("state_machines") or {}),
            ("test_cases", self.contract.get("test_cases") or {}),
        ]
        counts = ", ".join(f"{name}={len(value)}" for name, value in sections if value)
        return f"Compiled project: {self.project_name}" + (f" ({counts})." if counts else ".")


def _pm_design_prompt(context: _PromptContext) -> str:
    lines = [
        "# PM/design prompt",
        "",
        "User request:",
        USER_PROMPT_PLACEHOLDER,
        "",
        "You are the PM/design agent for a pyspec-contract workspace.",
        f"Active layers: {context.label}",
        context.compiled_summary(),
        "",
        "Edit only `spec/spec.yaml` unless the user explicitly asks for a different role.",
        f"After authoring, run `pyspec compile . --layers {context.layer_arg}` and `pyspec validate . --layers {context.layer_arg}`.",
        "",
        "Authoring scope:",
        "- Core: fixtures, facts, models, operations, and product test cases.",
    ]
    if "http" in context.layers:
        lines.append("- HTTP: HTTP entry points that bind operations to externally visible API operations.")
    else:
        lines.append("- Do not author HTTP/API entry points or OpenAPI details; the HTTP layer is inactive.")
    if "events" in context.layers:
        lines.append("- Events: event-producing product behavior and webhook-facing contracts when requested.")
    else:
        lines.append("- Do not add event/webhook vocabulary unless the active layers change.")
    if "workflow" in context.layers:
        lines.append("- Workflow: workflows with explicit outcomes, step outcome routing, and CLI/worker/scheduled entry points with adapter-appropriate responses.")
    else:
        lines.append("- Do not add workflow, CLI, worker, or schedule vocabulary.")
    if "ui" in context.layers:
        lines.append("- UI: state machines with view-state-local layouts, child state machines, render audit cases, text resources/assets, content cases, and render profiles.")
    else:
        lines.append("- Do not author UI state machines, text resources/assets, render audit cases, or surface presentation.")
    if "html" in context.layers:
        lines.append("- HTML UI: html renderer layout, presentation, style, UI entry points, routes, and HTML audit surfaces.")
    elif "ui" in context.layers:
        lines.append("- Do not author html renderer details or html routes; the html layer is inactive.")
    if "textual" in context.layers:
        lines.append("- Textual UI: Textual presentation, screen projection, and Textual audit surfaces.")
    elif "ui" in context.layers:
        lines.append("- Do not author Textual renderer details; the textual layer is inactive.")
    lines.extend(
        [
            "",
            "Rules:",
            "- Keep `spec/spec.yaml` sparse, positive-only, and grouped by product concepts.",
            "- Declare product meaning once in `spec/spec.yaml`; the compiler owns all generated projections and adapters.",
            "- Keep implementation and storage concerns out of `spec/spec.yaml`.",
            "- Use test-case archetypes from `src/pyspec_contract/patterns.yaml`; define every seed fixture explicitly.",
            "- Models are product data models: fields, lifecycle, and invariants only.",
            "- Use `rationale` only when it preserves non-obvious product intent.",
            "- For entry points, declare one explicit `adapter` (`http_api`, `cli`, `webhook`, `scheduled`, `worker`, or `html_route`) and one explicit `target` (`operation`, `state_machine`, or `workflow`).",
            "- For state-machine entry points, keep invocation and rendering separate with adapter input and target `renderer` (`html` or `textual`).",
            "- For workflow entry points, bind the entry point target to the workflow trigger with `target.workflow.ref` and `target.workflow.trigger_source`.",
            "- For rendered screens, put framework-owned `layout`, `presentation`, and `style` under `renderers.html` or `renderers.textual`.",
            "- Every rendered text or asset ref must be backed by a declared text resource or asset item.",
        ]
    )
    return "\n".join(lines) + "\n"


def _test_prompt(context: _PromptContext) -> str:
    lines = [
        "# Test prompt",
        "",
        "User request:",
        USER_PROMPT_PLACEHOLDER,
        "",
        "You are the test agent for a pyspec-contract workspace.",
        f"Active layers: {context.label}",
        context.compiled_summary(),
        "",
        "Product truth comes from generated behavior, not prose or implementation guesses:",
        "- `spec/generated/behavior/test_cases.yaml`",
        "- `spec/generated/behavior/fixtures.yaml`",
        "- `spec/generated/test_adapters/pytest_bdd_features/`",
        "- `spec/generated/test_adapters/driver_protocol.py`",
        "- `spec/generated/test_adapters/python_refs.py`",
        "",
        "Edit boundary:",
        "- Do not edit `spec/spec.yaml` as the test agent.",
        "- Do not edit anything under `spec/generated/`.",
        "- You may edit non-generated test harness code, such as `tests/prod_bdd/`, `tests/spec_bdd/`, shared test helpers, or project test files.",
        "- If the generated test cases, fixtures, or driver protocol are wrong or incomplete, report the exact needed spec change for the PM/design agent instead of patching around it.",
        "",
        "Rules:",
        "- There is exactly one generated Gherkin corpus; both spec and prod harnesses consume `spec/generated/test_adapters/pytest_bdd_features/`.",
        "- The spec harness may use the generated/reference driver to prove test-case coherence.",
        "- The prod harness must call real product surfaces and must not import the reference driver, fake authorization decisions, fake emitted events, fake rendered state machine surfaces, or mutate generated test cases.",
        "- If generated behavior files are missing, ask for PM/design authoring and `pyspec compile` before inventing tests.",
        f"- Check freshness with `pyspec validate . --layers {context.layer_arg}`.",
    ]
    return "\n".join(lines) + "\n"


def _review_prompt(context: _PromptContext) -> str:
    lines = [
        "# Review prompt",
        "",
        "User request:",
        USER_PROMPT_PLACEHOLDER,
        "",
        "You are the review agent for a pyspec-contract branch containing a proposed completed vertical slice across PM/design, test, and dev work.",
        "Act as a very strict independent third-party auditor. Assume the branch is not mergeable until the evidence proves otherwise.",
        f"Active layers: {context.label}",
        context.compiled_summary(),
        "",
        "Your job is to decide whether the branch is ready to merge.",
        "Do not implement fixes unless the user explicitly asks; review the branch and report precise blockers.",
        "Hold each role to its own responsibilities, and do not let a passing implementation hide a weak spec or fake tests.",
        "",
        "PM/design audit:",
        "- Check whether `spec/spec.yaml` describes the product meaning clearly, sparsely, and at the right layer.",
        "- Reject implementation/storage concerns in the spec, vague product assertions, missing fixtures, weak test-case coverage, stale generated artifacts, or generated files edited by hand.",
        "- For every PM/design issue, provide a recommended prompt for `pm_design.md` that asks for the smallest spec-side fix.",
        "",
        "Test audit:",
        "- Check whether tests consume generated behavior and exercise real prod surfaces where required.",
        "- Reject tests that mutate generated test cases, fake authorization decisions, fake emitted events, fake rendered state machine surfaces, duplicate generated behavior, or mask missing spec coverage.",
        "- For every test issue, provide a recommended prompt for `test.md` that asks for the smallest harness/test fix, or asks the test agent to report a PM/design gap when the spec is wrong.",
        "",
        "Dev audit:",
        "- Check whether implementation consumes generated projections/constants and implements the declared contract without inventing contract surface.",
        "- Reject invented routes, text resources, selectors, events, workflows, authorization_policies, operations, fixtures, test-case IDs, persistence contracts, or content source signatures outside the spec.",
        "- For every dev issue, provide a recommended prompt for `dev.md` that asks for the smallest implementation fix.",
        "",
        "Evidence checks:",
        f"- Run or inspect `pyspec compile . --layers {context.layer_arg}` and `pyspec validate . --layers {context.layer_arg}` for generated-tree freshness and layer correctness.",
        "- Run the project tests that exercise the generated pytest-bdd corpus.",
        "- For UI layers, inspect render/audit evidence and call out visual, accessibility, or composition mismatches.",
        "- For content sources, confirm generated signatures/stubs are followed and outputs are deterministic for declared cases.",
        "",
        "Output format:",
        "- Start with `Ready for merge: yes` or `Ready for merge: no`.",
        "- Separate findings under `PM/design findings`, `Test findings`, and `Dev findings`; write `None` for a role only when it has no material issues.",
        "- Within each role, list findings first, ordered by severity, with exact files and lines when possible.",
        "- Each finding should explain the fragility, risk, or incorrectness, and what would make it mergeable.",
        "- Under each finding, include `Recommended prompt for <role>:` with a concise prompt that can be pasted into the relevant generated role prompt.",
        "- Include commands run and any commands you could not run.",
        "- If everything passes, mention residual risk only if it is material.",
    ]
    return "\n".join(lines) + "\n"


def _dev_prompt(context: _PromptContext) -> str:
    lines = [
        "# Dev prompt",
        "",
        "User request:",
        USER_PROMPT_PLACEHOLDER,
        "",
        "You are the dev agent for a pyspec-contract workspace.",
        f"Active layers: {context.label}",
        context.compiled_summary(),
        "",
        "Do not change `spec/spec.yaml` to fix implementation failures unless the user explicitly switches you into PM/design work.",
        "Use generated constants and projections; do not invent routes, strings, state machine surfaces, CSS selectors, Textual widgets, Textual style rules, events, workflows, authorization_policies, operations, fixtures, test-case IDs, storage tables, or migrations outside the spec and implementation layer.",
        "",
        "Generated interfaces to consume:",
        "- `spec/generated/behavior/test_cases.yaml` and `spec/generated/behavior/fixtures.yaml`",
        "- `spec/generated/test_adapters/python_refs.py` and `spec/generated/test_adapters/driver_protocol.py`",
    ]
    if "http" in context.layers:
        lines.append("- `spec/generated/product_interfaces/http.openapi.yaml`")
    if "events" in context.layers:
        lines.append("- `spec/generated/product_interfaces/events.asyncapi.yaml`")
    if "workflow" in context.layers:
        lines.append("- `spec/generated/product_interfaces/workflow.cwl.yaml`")
    if "html" in context.layers:
        lines.append("- `spec/generated/product_interfaces/html.routes.json`, `spec/generated/product_interfaces/html.state_machines.json`, and HTML audit evidence")
    elif "ui" in context.layers:
        lines.append("- `spec/generated/product_interfaces/html.state_machines.json` when state machines are declared")
    if "textual" in context.layers:
        lines.append("- `spec/generated/product_interfaces/textual.projection.py` and Textual audit evidence")
    if "ui" in context.layers:
        lines.append("- `spec/generated/content_resolvers/` when generated content source signatures or stubs exist")
    lines.extend(
        [
            "",
            "Completion checks:",
            f"- `pyspec compile . --layers {context.layer_arg}`",
            f"- `pyspec validate . --layers {context.layer_arg}`",
            "- Run the project test suite that exercises the generated pytest-bdd corpus.",
        ]
    )
    return "\n".join(lines) + "\n"
