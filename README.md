# PM contract starter

This starter is a Python-first, contract-to-test system for a PM/spec agent that must turn imprecise intent into precise implementation obligations without drifting into malformed OpenAPI, AsyncAPI, CWL, UI, routing, persistence, or test contracts.

The PM agent edits only `pm.patch.yaml`. Everything else is compiler-owned.

```text
pm.patch.yaml
  -> contract.yaml
  -> generated/openapi.yaml
  -> generated/asyncapi.yaml
  -> generated/workflows.cwl.yaml
  -> generated/routes.json
  -> generated/panels.json
  -> generated/panels.html
  -> generated/panel_styles.css
  -> generated/textual_contract.py
  -> generated/content_contract.py
  -> generated/content_stubs.py
  -> generated/content_cases.yaml
  -> generated/persistence.json
  -> generated/persistence.sql
  -> generated/features/*/*.feature
  -> generated/scenarios.yaml
  -> generated/audit/*
```

The checked-in canonical example is a small dispatch board app. It is intentionally simple, but it exercises the important surfaces in one coherent contract: HTTP API, event API, workflow execution, composed HTML layout, Textual/TUI view, SQL persistence, generated pytest-bdd scenarios, fixtures, placeholder copy/assets, FSM diagrams, and full visual audit renders.

## Setup

```bash
python -m pip install -r requirements.txt
npm install
python -m playwright install chromium
```

When system Chromium is available, this is also supported:

```bash
export CONTRACT_AUDIT_CHROMIUM=/usr/bin/chromium
```

`node_modules/`, caches, and virtual environments are not part of the artifact.

## Core rule

The PM agent does not author downstream specs. It writes closed patch operations:

```yaml
- op: add
  target: capability
  id: project.create
  spec:
    archetype: create
    resource: Project
    input: {workspace_id: ID, title: Text, customer: Text, priority: Text}
    output: Project
    emits: [project.created]
  basis:
    kind: explicit
    confidence: high
    text: Members can create a new dispatch project.
```

The compiler normalizes those operations into `contract.yaml` and all projections. Unknown fields, unknown refs, stale generated files, extra generated files, malformed UI composition, invalid scenarios, and fake prod harnesses are rejected.

Patch operations are deliberately whole-object and closed:

```yaml
op: add | replace | delete
target: copy | asset | content_case | audit_profile | fixture | resource | capability | panel | view | entry | workflow | scenario | render_case
id: exact item id
spec: required for add/replace, forbidden for delete
basis: always required
```

There are no partial JSONPath-style mutations. `delete` is non-cascading; validation fails if anything still references the deleted item.

## Canonical example model

The canonical app is a dispatch board for `Project` work items.

The root `Project` resource owns fields and lifecycle:

```yaml
fields:
  id: ID
  workspace_id: ID
  title: Text
  customer: Text
  status: ProjectStatus
  priority: Text
  assignee: Text
  summary: Text
  created_at: Timestamp
  updated_at: Timestamp
lifecycle:
  field: status
  initial: draft
  states: [draft, submitted, approved, archived]
```

Capabilities define product verbs:

```text
project.create
project.list
project.submit
project.approve
project.archive
project.send_approval_notice
```

Entries expose those meanings on surfaces:

```text
web.project.board          -> generated/routes.json + HTML audit
textual.project.board      -> generated/textual_contract.py + Textual audit
api.project.create/list    -> generated/openapi.yaml
cli.project.approve        -> generated/workflows.cwl.yaml command tool surface
worker.project.approval_notice -> generated/asyncapi.yaml + generated/workflows.cwl.yaml
```

## Composed FSM views

Atomic views are allowed, but real app screens are often compositions. The canonical app uses a composed board:

```text
project.board
  nav   -> panel.project.list
  main  -> panel.project.detail
  aside -> panel.project.activity
```

Each `target: panel` is its own FSM. For example, `panel.project.list` has `loading`, `empty`, `ready`, and `error` states. Each state declares copy slots, asset slots, field slots, actions, and transitions.

The composed `target: view` declares:

```text
layout      named HTML/Textual slots
includes    panel instances mounted into slots
context     shared view context
sync        explicit event/context synchronization between panel FSMs
```

A scenario asserts a state vector rather than flattening the screen into fake combined states:

```yaml
then:
  view:
    ref: project.board
    state: ready
    panels:
      list: {state: ready}
      detail: {state: ready}
      activity: {state: ready}
```

## Fixture-backed visual audit

Visual audit is not a change report. There is no generated `review.html`, `change_report.md`, or `manifest.json`. Git diffs show what changed. The compiler always emits the complete full-contract audit set.

```text
generated/audit/
  copy.yaml
  fixtures.yaml
  assets/*.svg
  fsm/*.svg
  composition/*.svg
  html/panels/<panel-state>/<profile>.<breakpoint>.html
  html/panels/<panel-state>/<profile>.<breakpoint>.png
  html/views/<view>/<profile>.<breakpoint>.<render-case>.html
  html/views/<view>/<profile>.<breakpoint>.<render-case>.png
  textual/panels/<panel-state>/<profile>.<breakpoint>.py
  textual/panels/<panel-state>/<profile>.<breakpoint>.svg
  textual/views/<view>/<profile>.<breakpoint>.<render-case>.py
  textual/views/<view>/<profile>.<breakpoint>.<render-case>.svg
```

Format rules are fixed:

```text
HTML visual audit       -> PNG only
Textual visual audit    -> SVG only
FSM diagrams            -> SVG only
composition diagrams    -> SVG only
```

The `.html` and `.py` files beside the rendered images are the exact minimal sources used for rendering. They are included for audit reference; the images themselves do not contain metadata labels such as panel id, view id, render case id, project id, asset id, or fixture id.

Placeholder requirements are strict:

```text
copy id used in a rendered surface    -> requires target: copy with placeholder text
asset id used in a rendered surface   -> requires target: asset with placeholder visual intent
field slot rendered from data         -> requires fixture data for the resource
composed view audit                   -> requires target: render_case with panel state vector
```

The canonical example uses fixture records like this:

```yaml
- resource: Project
  id: project_alpha
  title: Replace rooftop condenser fan
  customer: Atlas Foods
  status: submitted
  priority: High
  assignee: Maya Chen
  summary: Technician needs approval before ordering the replacement fan motor.
```

Those fixture values render into field slots in HTML and Textual audit outputs. The fixture JSON is not dumped into a page.

The canonical example uses exactly two breakpoints:

```text
HTML:    compact, wide
Textual: compact, wide
```

## Final copy and asset resolvers

Placeholders are mandatory from the beginning because they make audits readable before final content exists. Final copy and image assets are still contract-owned; they are added by declaring typed resolver signatures on `target: copy` or `target: asset`, then implementing only the generated resolver obligation in `content/resolvers.py`.

A final copy contract can take typed arguments:

```yaml
- op: add
  target: copy
  id: copy.project.detail.ready.heading
  spec:
    placeholder: Project detail
    max_chars: 80
    args:
      title: Text
      customer: Text
    final:
      status: final_draft
      resolver: copy.project.detail.ready.heading
```

The compiler generates `generated/content_contract.py` and `generated/content_stubs.py`. The editable implementation is small and explicit:

```python
@copy.implements(Copy.COPY_PROJECT_DETAIL_READY_HEADING)
def project_detail_ready_heading(args: CopyProjectDetailReadyHeadingArgs, ctx: ContentContext) -> str:
    return f"{args.title} · {args.customer}"
```

A final image-like asset follows the same pattern and returns an `AssetResult` containing real SVG:

```python
@asset.implements(Asset.ASSET_PROJECT_DETAIL_READY_PRIORITY_BADGE)
def priority_badge(args: AssetProjectDetailReadyPriorityBadgeArgs, ctx: ContentContext) -> AssetResult:
    return AssetResult(mime_type="image/svg+xml", body=svg, alt=f"{args.priority} priority")
```

The PM agent does not invent resolver signatures in Python. It declares `args` and `final` in `pm.patch.yaml`; the compiler generates the required arg dataclasses and refs. Validation rejects missing resolvers, unknown resolver refs, wrong function shape, invalid SVG assets, overlong copy, and final content without `content_case` coverage.

During audit rendering:

```text
final.status = placeholder   -> render the placeholder
final.status = final_draft   -> render the resolver output
final.status = approved      -> render the resolver output; release may require this state
```

`target: content_case` gives the validator deterministic resolver inputs outside a full view render:

```yaml
- op: add
  target: content_case
  id: content.project.detail.heading.high_priority
  spec:
    ref: copy.project.detail.ready.heading
    args:
      title: Replace rooftop condenser fan
      customer: Atlas Foods
```

View and panel renders bind resolver args from the selected fixture-backed record, render context, or declared fixtures. In the canonical audit, the selected project record feeds the final heading and priority badge in the detail panel.

## Generated Gherkin and pytest-bdd

Gherkin is not the source of truth. `generated/scenarios.yaml` carries the executable scenario contract. The `.feature` files exist as a narrow pytest-bdd adapter.

Generated feature text is intentionally generic:

```gherkin
Given contract scenario "project.board.ready" is arranged
When contract scenario "project.board.ready" is executed
Then contract scenario "project.board.ready" obligations hold
```

Both harnesses execute the same scenario obligations:

```text
tests/spec_bdd/  reference/fake spec harness
tests/prod_bdd/  real product harness; fake shortcuts are rejected
```

The prod harness must not import `pm_contract.reference_driver`, `unittest.mock`, `pytest_mock`, or use `monkeypatch`/`mocker` fixtures.

## Running

Regenerate everything:

```bash
python -m pm_contract.compile pm.patch.yaml --out .
```

Validate:

```bash
python -m pm_contract.validate .
```

Run tests:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q -p pytest_bdd.plugin
```

Optional external native validators:

```bash
python -m pip install -r requirements-dev.txt
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q -p pytest_bdd.plugin tests/test_external_spec_validators.py
```

The starter release gate intentionally fails until the contract is approved and blocking review flags are removed:

```bash
python -m pm_contract.validate . --release
```

## What each projection means

`OpenAPI` is generated from API entries and capabilities. The PM agent declares product operations; the compiler emits HTTP method, path, parameters, request body, response schemas, policy extensions, and capability traceability.

`AsyncAPI` is generated from emitted events and worker workflows. The PM agent declares events through capabilities/workflows; the compiler emits event channels, messages, and operations.

`CWL` is generated from capabilities and workflows. The PM agent declares commands/workflows; the compiler emits command-line tools and workflow steps.

`HTML/CSS` is generated from view/panel presentation contracts, layout slots, copy slots, asset slots, field slots, actions, and CSS tokens. The PM agent adds specificity in `pm.patch.yaml`, never in `generated/*`.

`Textual` is generated from textual entries, panel/view presentation contracts, widgets, bindings, TCSS-like declarations, and composed view layout.

`SQL/persistence` is generated from resources, fields, IDs, and lifecycle constraints.

`Visual audit` is generated from all panels, all FSMs, all composed views, render cases, placeholders, and fixtures. It is the primary human surface for auditing complex UI/TUI intent.
