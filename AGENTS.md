# Agent rules

## PM/spec agent

Edit `pm.patch.yaml` only.

Use the active authoring layer for the current delivery stage. Do not use the full patch vocabulary unless the repo is intentionally delivering a full-surface contract. Common layers are:

```text
core
core,http
core,persistence
core,http,persistence
core,events
core,workflow
core,ui,textual
core,ui,web
full
```

Use the matching layer-pruned schema from `schemas/layers/`. The layer is an authoring constraint, not a product fact; never add roadmap-like surface flags to `contract.yaml` or `pm.patch.yaml`.

Do not edit `contract.yaml`, `generated/*`, schemas, tests, app code, or Gherkin files. The compiler owns all projections.

Do not use YAML anchors or aliases (`&name`, `*name`) in PM patches or generated contract material. They are not part of the DSL. Repeat the value plainly or reference a declared contract ID. Validation rejects YAML anchors and aliases.

Use only the closed patch grammar: `op: add`, `op: replace`, or `op: delete`; one target; one `id`; one `basis`; and, for add/replace only, one closed `spec`. There are no partial mutations. To change one field, replace the whole item. Deletes are non-cascading and must leave no dangling references.

Never author raw OpenAPI, AsyncAPI, CWL, route manifests, panel manifests, HTML/CSS panel artifacts, Textual projections, persistence SQL, pytest-bdd step text, or `.feature` files. Declare product meaning once in the patch language and let the compiler project it.

For API-only work, stay in `core,http`: resources, capabilities, fixtures, scenarios, and API entries. Add `persistence` only when durable storage is explicitly part of the current deliverable. Do not introduce panels, views, copy, assets, render cases, audit profiles, Textual, or HTML/CSS.

For workflow/CI-client work, stay in `core,workflow`: workflows plus CLI/worker/scheduled entries. Do not introduce UI vocabulary unless the requested deliverable is actually a UI.

For Textual/TUI work, use `core,ui,textual`: panels, composed views, copy/assets, render cases, Textual presentation, and Textual SVG audit. Do not add HTML/CSS requirements.

For web work, use `core,ui,web`: panels, composed views, copy/assets, render cases, HTML/CSS presentation, and HTML PNG audit. Do not add Textual requirements.

Choose scenario archetypes from `patterns.yaml`. Define every fixture through `target: fixture`; do not assume hidden driver fixtures. When the user's intent is uncertain, mark the `basis` as `kind: assumed` or `confidence: low`, add `basis.review: true`, or add a blocking `review_flag`. Do not add ad hoc notes or free-form fields.

For exact HTML/CSS or Textual/TCSS requirements, add presentation details inside the relevant `target: view` or `target: panel` state spec only when the active layer permits that surface. For composed product screens, define reusable `target: panel` FSMs first, then mount them through `target: view` layout slots, includes, shared context, and sync rules.

Every rendered copy ref must be backed by `target: copy`. Every rendered asset ref must be backed by `target: asset`. Every view state or composed view state vector must be backed by `target: render_case`. Use `target: audit_profile` for fixed breakpoints. Do not create review reports or manifests; the compiler derives the full audit set from the contract.

For final copy or image assets, declare the typed content signature in `pm.patch.yaml` through `target: copy` or `target: asset` with `args` and `final`. Add `target: content_case` coverage for every final resolver. Do not write resolver bodies as a PM/spec agent; resolver bodies live in `content/resolvers.py` and must implement the generated stubs exactly.

## Final content resolver implementer

Edit `content/resolvers.py` only after the PM/spec contract declares the resolver. Do not add resolver IDs, args, or asset formats in Python. Import generated arg classes and refs, return plain `str` for copy and `AssetResult` with real SVG for image assets, and keep outputs deterministic for declared content cases and render cases.

## Test agent

Do not infer scenarios from prose or implementation. Consume `generated/scenarios.yaml`, `generated/features/{spec,prod}`, `generated/fixtures.yaml`, and `generated/driver_protocol.py`.

The generated `.feature` files are a pytest-bdd adapter, not a source of product truth. The executable scenario meaning is in `generated/scenarios.yaml`.

The spec harness may use the reference/fake driver to prove the scenario is coherent as a specification.

The prod harness must call real product surfaces. It must not import `pm_contract.reference_driver`, monkeypatch policy answers, fake emitted events, fake rendered panels, or mutate generated obligations to make tests pass. Validation rejects obvious fake/spec shortcuts in `tests/prod_bdd`.

## Coding agent

Do not change `pm.patch.yaml` to fix implementation failures unless explicitly acting as the PM/spec agent.

Use generated constants and projections. Do not invent routes, strings, panels, CSS selectors, Textual widgets, TCSS rules, events, workflows, policies, operations, fixtures, SQL tables, or scenario IDs outside the contract.

Before claiming completion for the canonical example, run:

```bash
python -m pm_contract.compile pm.patch.yaml --out . --layers full
python -m pm_contract.validate . --layers full
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q -p pytest_bdd.plugin
```

For narrower repos, replace `full` with the active layer set, such as `core,http` or `core,ui,textual`.
