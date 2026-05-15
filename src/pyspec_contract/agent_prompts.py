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
    entries = contract.get("entries") or {}
    entry_surfaces = {entry.get("surface") for entry in entries.values()}
    if "api" in entry_surfaces:
        active.add("http")
    if contract.get("events") or "webhook" in entry_surfaces:
        active.add("events")
    if contract.get("workflows") or entry_surfaces & {"cli", "worker", "schedule"}:
        active.add("workflow")
    if _contract_has_ui(contract):
        active.add("ui")
    if _contract_has_web(contract):
        active.update({"ui", "web"})
    if _contract_has_textual(contract):
        active.update({"ui", "textual"})
    return normalize_layers(active) or set(LAYERS)


def _coerce_layers(layers: str | set[str] | None) -> set[str] | None:
    if isinstance(layers, str):
        return parse_layers(layers)
    return normalize_layers(layers) if layers is not None else None


def _contract_has_ui(contract: dict[str, Any]) -> bool:
    return bool(
        contract.get("fsms")
        or contract.get("copies")
        or contract.get("assets")
        or contract.get("content_cases")
        or contract.get("audit_profiles")
    )


def _contract_has_web(contract: dict[str, Any]) -> bool:
    entries = contract.get("entries") or {}
    if any(entry.get("surface") == "web" for entry in entries.values()):
        return True
    if any("html" in case.get("surfaces", []) for case in _contract_audit_cases(contract)):
        return True
    if any("html" in profile for profile in (contract.get("audit_profiles") or {}).values()):
        return True
    for owner in (contract.get("fsms") or {}).values():
        for state in (owner.get("states") or {}).values():
            if "html" in (state.get("layout") or {}):
                return True
            presentation = state.get("presentation") or {}
            if "html" in presentation or "css" in presentation:
                return True
    return False


def _contract_has_textual(contract: dict[str, Any]) -> bool:
    if any("textual" in case.get("surfaces", []) for case in _contract_audit_cases(contract)):
        return True
    if any("textual" in profile for profile in (contract.get("audit_profiles") or {}).values()):
        return True
    for owner in (contract.get("fsms") or {}).values():
        for state in (owner.get("states") or {}).values():
            if "textual" in (state.get("layout") or {}):
                return True
            if "textual" in (state.get("presentation") or {}):
                return True
    return False


def _contract_audit_cases(contract: dict[str, Any]) -> list[dict[str, Any]]:
    cases = []
    for fsm in (contract.get("fsms") or {}).values():
        for state in (fsm.get("states") or {}).values():
            cases.extend((state.get("audit") or {}).values())
    return cases


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
            ("entries", self.contract.get("entries") or {}),
            ("workflows", self.contract.get("workflows") or {}),
            ("fsms", self.contract.get("fsms") or {}),
            ("scenarios", self.contract.get("scenarios") or {}),
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
        "- Core: fixtures, facts, models, operations, and product scenarios.",
    ]
    if "http" in context.layers:
        lines.append("- HTTP: API entries that bind operations to externally visible operations.")
    else:
        lines.append("- Do not author API entries or OpenAPI details; the HTTP layer is inactive.")
    if "events" in context.layers:
        lines.append("- Events: event-producing product behavior and webhook-facing contracts when requested.")
    else:
        lines.append("- Do not add event/webhook vocabulary unless the active layers change.")
    if "workflow" in context.layers:
        lines.append("- Workflow: workflows with explicit outcomes, step outcome routing, and CLI/worker/scheduled entries with surface-appropriate responses.")
    else:
        lines.append("- Do not add workflow, CLI, worker, or schedule vocabulary.")
    if "ui" in context.layers:
        lines.append("- UI: FSMs with state-local layouts, mounts, audit cases, copy/assets, content cases, and audit profiles.")
    else:
        lines.append("- Do not author UI FSMs, copy/assets, audit cases, or surface presentation.")
    if "web" in context.layers:
        lines.append("- Web UI: HTML/CSS presentation, web entries, routes, and HTML audit surfaces.")
    elif "ui" in context.layers:
        lines.append("- Do not author HTML/CSS or web routes; the web layer is inactive.")
    if "textual" in context.layers:
        lines.append("- Textual UI: Textual presentation, screen projection, and Textual audit surfaces.")
    elif "ui" in context.layers:
        lines.append("- Do not author Textual/TCSS details; the textual layer is inactive.")
    lines.extend(
        [
            "",
            "Rules:",
            "- Keep `spec/spec.yaml` sparse, positive-only, and grouped by product concepts.",
            "- Declare product meaning once in `spec/spec.yaml`; the compiler owns all generated projections and adapters.",
            "- Keep implementation and storage concerns out of `spec/spec.yaml`.",
            "- Use scenario archetypes from `src/pyspec_contract/patterns.yaml`; define every fixture explicitly.",
            "- Models are product data models: fields, lifecycle, and invariants only.",
            "- Use `basis` or `why` only when it preserves non-obvious product intent.",
            "- For FSM entries, keep invocation and rendering separate: `surface` is the entry surface, while `target.fsm.surface` is `html` or `textual`.",
            "- For workflow entries, bind the entry to the workflow trigger with `target.workflow.name` and `target.workflow.trigger`.",
            "- For composed screens, mount FSM instances through state-local layout, mounts, context, and sync rules.",
            "- Every rendered copy or asset ref must be backed by a declared copy or asset item.",
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
        "- `spec/generated/behavior/scenarios.yaml`",
        "- `spec/generated/behavior/fixtures.yaml`",
        "- `spec/generated/test_adapters/pytest_bdd_features/`",
        "- `spec/generated/test_adapters/driver_protocol.py`",
        "- `spec/generated/test_adapters/python_refs.py`",
        "",
        "Edit boundary:",
        "- Do not edit `spec/spec.yaml` as the test agent.",
        "- Do not edit anything under `spec/generated/`.",
        "- You may edit non-generated test harness code, such as `tests/prod_bdd/`, `tests/spec_bdd/`, shared test helpers, or project test files.",
        "- If the generated scenarios, fixtures, or driver protocol are wrong or incomplete, report the exact needed spec change for the PM/design agent instead of patching around it.",
        "",
        "Rules:",
        "- There is exactly one generated Gherkin corpus; both spec and prod harnesses consume `spec/generated/test_adapters/pytest_bdd_features/`.",
        "- The spec harness may use the generated/reference driver to prove scenario coherence.",
        "- The prod harness must call real product surfaces and must not import the reference driver, fake policy answers, fake emitted events, fake rendered FSM surfaces, or mutate generated scenarios.",
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
        "- Reject implementation/storage concerns in the spec, vague product assertions, missing fixtures, weak scenario coverage, stale generated artifacts, or generated files edited by hand.",
        "- For every PM/design issue, provide a recommended prompt for `pm_design.md` that asks for the smallest spec-side fix.",
        "",
        "Test audit:",
        "- Check whether tests consume generated behavior and exercise real prod surfaces where required.",
        "- Reject tests that mutate generated scenarios, fake policy answers, fake emitted events, fake rendered FSM surfaces, duplicate generated behavior, or mask missing spec coverage.",
        "- For every test issue, provide a recommended prompt for `test.md` that asks for the smallest harness/test fix, or asks the test agent to report a PM/design gap when the spec is wrong.",
        "",
        "Dev audit:",
        "- Check whether implementation consumes generated projections/constants and implements the declared contract without inventing contract surface.",
        "- Reject invented routes, copy, selectors, events, workflows, policies, operations, fixtures, scenario IDs, persistence contracts, or content resolver signatures outside the spec.",
        "- For every dev issue, provide a recommended prompt for `dev.md` that asks for the smallest implementation fix.",
        "",
        "Evidence checks:",
        f"- Run or inspect `pyspec compile . --layers {context.layer_arg}` and `pyspec validate . --layers {context.layer_arg}` for generated-tree freshness and layer correctness.",
        "- Run the project tests that exercise the generated pytest-bdd corpus.",
        "- For UI layers, inspect render/audit evidence and call out visual, accessibility, or composition mismatches.",
        "- For content resolvers, confirm generated signatures/stubs are followed and outputs are deterministic for declared cases.",
        "",
        "Output format:",
        "- Start with `Ready for merge: yes` or `Ready for merge: no`.",
        "- Separate findings under `PM/design findings`, `Test findings`, and `Dev findings`; write `None` for a role only when it has no material issues.",
        "- Within each role, list findings first, ordered by severity, with exact files and lines when possible.",
        "- Each finding should say why it is too fragile, too dangerous, or wrong, and what would make it mergeable.",
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
        "Use generated constants and projections; do not invent routes, strings, FSM surfaces, CSS selectors, Textual widgets, TCSS rules, events, workflows, policies, operations, fixtures, scenario IDs, storage tables, or migrations outside the spec and implementation layer.",
        "",
        "Generated interfaces to consume:",
        "- `spec/generated/behavior/scenarios.yaml` and `spec/generated/behavior/fixtures.yaml`",
        "- `spec/generated/test_adapters/python_refs.py` and `spec/generated/test_adapters/driver_protocol.py`",
    ]
    if "http" in context.layers:
        lines.append("- `spec/generated/product_interfaces/http.openapi.yaml`")
    if "events" in context.layers:
        lines.append("- `spec/generated/product_interfaces/events.asyncapi.yaml`")
    if "workflow" in context.layers:
        lines.append("- `spec/generated/product_interfaces/workflow.cwl.yaml`")
    if "web" in context.layers:
        lines.append("- `spec/generated/product_interfaces/web.routes.json`, `spec/generated/product_interfaces/web.fsms.json`, and HTML audit evidence")
    elif "ui" in context.layers:
        lines.append("- `spec/generated/product_interfaces/web.fsms.json` when FSMs are declared")
    if "textual" in context.layers:
        lines.append("- `spec/generated/product_interfaces/textual.projection.py` and Textual audit evidence")
    if "ui" in context.layers:
        lines.append("- `spec/generated/content_resolvers/` when generated resolver signatures or stubs exist")
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
