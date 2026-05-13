# PM contract starter

This starter is a Python-first, contract-to-test system for turning product intent into precise whole-app design obligations without hand-authoring OpenAPI, AsyncAPI, CWL, routing, UI projections, visual audits, or BDD feature files.

The preferred human source is `contract.yaml`. It is sparse, positive-only, and grouped by product concepts. The generated machine contract is written to `generated/contract.complete.yaml`.

```text
contract.yaml
  -> generated/contract.complete.yaml
  -> generated projections required by positive declarations
  -> one generated pytest-bdd feature corpus
  -> full-contract visual audit renders when UI render cases exist
```

`pm.patch.yaml` is still supported, but it is now an optional agent-edit protocol rather than the only human-authoring format. A coding/spec agent may safely propose whole-object patch operations, and the compiler can turn those operations into `contract.yaml` before compiling the strict generated contract.

```text
pm.patch.yaml --compile/apply--> contract.yaml --compile--> generated/contract.complete.yaml
```

The contract is progressive. It never says that web, Textual, HTTP, events, workflow, storage, or any other surface is “not started.” If a concern is absent, it has no declaration and no generated projection.

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

## Authoring formats

### Human-authored contract

`contract.yaml` is the normal source file. It omits derived sections such as `events` and `refs`, omits empty top-level sections, and stores each item once under its natural section.

```yaml
project: project_dispatch_board

resources:
  Project:
    kind: aggregate
    fields:
      id: ID
      workspace_id: ID
      title: Text
      status: ProjectStatus
    lifecycle:
      field: status
      initial: draft
      states: [draft, submitted, approved, archived]
      transitions:
        - {from: draft, to: submitted, by: project.submit}
    basis: A dispatch project is the durable work item displayed by the board.

capabilities:
  project.submit:
    archetype: transition
    resource: Project
    input: {project_id: ID}
    output: Project
    emits: [project.submitted]
    basis: Draft dispatch projects can be submitted for review.
```

The compiler derives the exact transition field/from/to for `project.submit` from the resource lifecycle and expands it in `generated/contract.complete.yaml`.

The authored contract validates through `schemas/author.schema.json`, then compiles through the same semantic validators used by patch input and generated contracts.

### Patch operations

Patch operations remain useful when you want to confine an agent to a small, mechanical edit language. They are whole-object operations only; there are no partial JSONPath-style mutations.

```yaml
project: project_dispatch_board
changes:
  - op: add
    target: capability
    id: project.create
    basis: Members can create a new dispatch project.
    spec:
      archetype: create
      resource: Project
      input: {workspace_id: ID, title: Text, customer: Text, priority: Text}
      output: Project
      emits: [project.created]
```

The compiler accepts either source shape:

```bash
python -m pm_contract.compile contract.yaml --out . --layers full
python -m pm_contract.compile pm.patch.yaml --out . --layers full
```

When compiling from `pm.patch.yaml`, the compiler writes both `contract.yaml` and `generated/contract.complete.yaml`. This makes patch operations usable as an edit assistant while keeping the direct authored contract as the readable source.

## Progressive authoring layers

The full language supports many surfaces, but agents should only see the vocabulary needed for the current delivery stage. Layers are authoring guardrails; they are not written into the contract.

```bash
python -m pm_contract.compile contract.yaml --out . --layers core,http
python -m pm_contract.validate . --layers core,http
```

Common layer sets:

```text
core
  resources, capabilities, fixtures, scenarios

core,http
  core + API entries -> OpenAPI

core,events
  core + webhook/event-surface entries -> AsyncAPI when events are positively exposed

core,workflow
  core + workflows, CLI/worker/scheduled entries -> CWL/workflow projection

core,ui,textual
  core + panels, views, copy/assets, render cases, Textual presentation -> Textual SVG audit

core,ui,web
  core + panels, views, copy/assets, render cases, HTML/CSS presentation -> HTML PNG audit

full
  all layers, used only when the repo intentionally exercises the whole language
```

Projection generation remains graph-driven: OpenAPI is emitted only when API entries exist; AsyncAPI only when event/message surfaces are positively declared; CWL only when workflow surfaces exist; Textual only when Textual entries, presentation, or render cases exist; HTML/CSS only when web entries, presentation, or render cases exist.

For PM-agent tooling, use the layer-pruned schemas under `schemas/layers/`, for example:

```text
schemas/layers/core_http.author.schema.json
schemas/layers/core_http.pm_patch.schema.json
schemas/layers/core_ui_web.author.schema.json
schemas/layers/core_ui_web.pm_patch.schema.json
schemas/layers/full.author.schema.json
schemas/layers/full.pm_patch.schema.json
```

The compiler enforces the active layers at runtime even if the wrong editor schema is used.

## Presentation stance

HTML/CSS and Textual/TCSS are committed surfaces, not vague implementation hints. A composed view can declare semantic slots once, then attach concrete web and Textual surface details where the active layer permits them.

```yaml
views:
  project.board:
    archetype: dashboard
    resource: Project
    context: {workspace_id: ID, selected_project_id: ID}
    includes:
      - id: list
        panel: panel.project.list
        slot: nav
        initial: loading
        context: {workspace_id: $view.workspace_id, selected_project_id: $view.selected_project_id}
    layout:
      kind: slots
      root: {element: section, role: region, classes: [dispatch-board]}
      slots:
        nav: {element: nav, role: navigation, order: 1, required: true, classes: [dispatch-board-nav]}
      css:
        tokens: {gap: 1rem, nav_width: 20rem}
        rules:
          - selector: root
            declarations: {display: grid, gap: token.gap, grid-template-columns: token.nav_width 1fr}
      textual:
        screen_class: ProjectBoardScreen
        containers:
          - {slot: nav, id: nav, kind: Container}
```

This keeps visual precision available without requiring projects that have no UI goal to mention UI at all.

## Pure PM/design contract

The contract describes product meaning, not implementation storage, test routing, development environment details, review workflow, release status, or schema version metadata. Source control owns history and review state; `contract.yaml` and `generated/contract.complete.yaml` stay pure specification.

Scenarios do not declare `spec`, `prod`, or any other harness. There is exactly one generated Gherkin corpus:

```text
generated/features/*.feature
```

Both pytest-bdd harnesses consume that same corpus. The difference is only the driver fixture outside the contract:

```text
tests/spec_bdd/ -> reference/spec driver
tests/prod_bdd/ -> real product driver
```

Resources do not declare persistence dialects, SQL tables, ORM models, migrations, or datastores. The resource contract is the PM/design data model: fields, lifecycle, and product invariants.

## Canonical example model

The checked-in canonical example is a small Project dispatch board. It intentionally uses the full layer set so the template demonstrates the system in one coherent app: HTTP API, event/workflow projection, CLI/workflow entry, composed HTML layout, Textual/TUI view, pytest-bdd scenarios, fixtures, placeholder copy/assets, typed content resolvers, FSM diagrams, and visual audit renders.

Capabilities define product verbs:

```text
project.create
project.list
project.submit
project.approve
project.archive
project.send_approval_notice
```

Entries expose those meanings on positive surfaces:

```text
web.project.board                 -> routes + HTML/CSS + HTML PNG audit
textual.project.board             -> Textual contract + Textual SVG audit
api.project.create/list           -> OpenAPI
cli.project.approve               -> CWL command/tool surface
worker.project.approval_notice    -> AsyncAPI + CWL workflow surface
```

## Composed FSM views

Atomic views are allowed, but real app screens are often compositions. The canonical app uses a composed board:

```text
project.board
  nav   -> panel.project.list
  main  -> panel.project.detail
  aside -> panel.project.activity
```

Each mounted panel is its own FSM. The composed view declares layout slots, included panel instances, shared context, and synchronization rules. Scenarios assert a state vector instead of flattening the screen into fake combined states:

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

Visual audit is not a change report. There is no generated `review.html`, `change_report.md`, or `manifest.json`. Git diffs show what changed. The compiler emits the complete audit set implied by the contract graph.

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

## Final copy and asset resolvers

Placeholders are mandatory from the beginning because they make audits readable before final content exists. Final copy and image assets are contract-owned: declare typed resolver signatures on copy or asset items, then implement only the generated resolver obligation in `content/resolvers.py`.

```yaml
copies:
  copy.project.detail.ready.heading:
    placeholder: Project detail
    max_chars: 80
    args: {title: Text, customer: Text}
    resolver: copy.project.detail.ready.heading
    basis: Final detail heading is resolved from selected project content.
```

Validation rejects missing resolvers, unknown resolver refs, wrong function shape, invalid SVG assets, overlong copy, and resolver-backed content without `content_case` coverage.

## Commands

```bash
python -m pm_contract.compile contract.yaml --out . --layers full
python -m pm_contract.validate . --layers full
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q -p pytest_bdd.plugin
```
