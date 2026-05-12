# PM contract starter

This starter is a Python-first, contract-to-test system for a PM/spec agent that must turn imprecise product intent into precise design obligations without drifting into malformed OpenAPI, AsyncAPI, CWL, routing, UI, content, visual-audit, or BDD contracts.

The PM agent edits only `pm.patch.yaml`. The compiler owns `contract.yaml` and every file under `generated/`.

```text
pm.patch.yaml
  -> contract.yaml
  -> generated projections required by positive contract declarations
  -> one generated pytest-bdd feature corpus
  -> generated full-contract visual audit renders
```

The contract is sparse and positive-only. It never says that web, Textual, AsyncAPI, CLI, storage, or any other surface is “not started.” If a concern is absent, it simply has no declaration and no generated projection.

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

## Progressive authoring layers

The full contract language supports many surfaces, but the PM agent should only see the vocabulary needed for the current delivery stage. That is handled with authoring layers, not with product roadmap flags in the contract.

```bash
python -m pm_contract.compile pm.patch.yaml --out . --layers core,http
python -m pm_contract.validate . --layers core,http
```

Common layer sets:

```text
core
  resource, capability, fixture, scenario, content cases

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

Layer selection is an authoring constraint only. It is not written to `contract.yaml`. Projection generation remains graph-driven: OpenAPI is emitted only when API entries exist; AsyncAPI only when event/message surfaces are positively declared; CWL only when workflows/command surfaces exist; Textual only when Textual entries/presentation/render cases exist; HTML/CSS only when web entries/presentation/render cases exist.

For PM-agent tooling, use the layer-pruned schemas under `schemas/layers/`, for example:

```text
schemas/layers/core_http.pm_patch.schema.json
schemas/layers/core_workflow.pm_patch.schema.json
schemas/layers/core_ui_textual.pm_patch.schema.json
schemas/layers/core_ui_web.pm_patch.schema.json
schemas/layers/full.pm_patch.schema.json
```

The full internal schema still exists at `schemas/pm_patch.schema.json`, and the compiler enforces the active layers even if the wrong schema is used.

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

Patch operations are deliberately whole-object and closed:

```yaml
op: add | replace | delete
target: copy | asset | content_case | audit_profile | fixture | resource | capability | panel | view | entry | workflow | scenario | render_case
id: exact item id
spec: required for add/replace, forbidden for delete
basis: always required
```

There are no partial JSONPath-style mutations. `delete` is non-cascading; validation fails if anything still references the deleted item.

## Pure PM/design contract

The contract should describe product meaning, not implementation storage, test routing, or development environment details.

Scenarios do not declare `spec`, `prod`, or any other harness. There is exactly one generated Gherkin corpus:

```text
generated/features/*.feature
```

Both pytest-bdd harnesses consume that same corpus. The difference is only the driver fixture outside the contract:

```text
tests/spec_bdd/ -> reference/spec driver
tests/prod_bdd/ -> real product driver
```

Resources do not declare a persistence dialect, SQL table, ORM model, migration, or datastore. The `resource` contract is the PM/design data model: fields, lifecycle, and product invariants. Concrete storage is an implementation concern and must not be smuggled into `pm.patch.yaml`.

## Canonical example model

The checked-in canonical example is a small **Project dispatch board**. It intentionally uses the full layer set so the template demonstrates the system in one coherent app: HTTP API, event/workflow projection, CLI/workflow entry, composed HTML layout, Textual/TUI view, pytest-bdd scenarios, fixtures, placeholder copy/assets, typed final content resolvers, FSM diagrams, and visual audit renders.

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

Each `target: panel` is its own FSM. The composed `target: view` declares layout slots, included panel instances, shared context, and synchronization rules. Scenarios assert a state vector instead of flattening the screen into fake combined states:

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

Visual audit is not a change report. There is no generated `review.html`, `change_report.md`, or `manifest.json`. Git diffs show what changed. The compiler always emits the complete audit set implied by the contract graph.

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

The `.html` and `.py` files beside the rendered images are the exact minimal sources used for rendering. The images themselves do not contain metadata labels such as panel id, view id, render case id, project id, asset id, or fixture id.

Placeholder requirements are strict:

```text
copy id used in a rendered surface    -> requires target: copy with placeholder text
asset id used in a rendered surface   -> requires target: asset with placeholder visual intent
field slot rendered from data         -> requires fixture data for the resource
composed view audit                   -> requires target: render_case with panel state vector
```

The canonical example uses exactly two breakpoints:

```text
HTML:    compact, wide
Textual: compact, wide
```

## Final copy and asset resolvers

Placeholders are mandatory from the beginning because they make audits readable before final content exists. Final copy and image assets are still contract-owned; they are added by declaring typed resolver signatures on `target: copy` or `target: asset`, then implementing only the generated resolver obligation in `content/resolvers.py`.

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

Validation rejects missing resolvers, unknown resolver refs, wrong function shape, invalid SVG assets, overlong copy, and final content without `content_case` coverage.

## Commands

```bash
python -m pm_contract.compile pm.patch.yaml --out . --layers full
python -m pm_contract.validate . --layers full
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q -p pytest_bdd.plugin
```

For an API-only repo, use `--layers core,http` and the `schemas/layers/core_http.pm_patch.schema.json` authoring schema instead of `full`.
