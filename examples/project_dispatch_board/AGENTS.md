# Project Dispatch Board Agent Rules

## PM/spec agent

Edit `spec/spec.yaml`. It is the human-authored source spec: sparse, positive-only, and grouped by product concepts.

Use the active authoring layer for the current delivery stage. Do not use the full vocabulary unless the repo is intentionally delivering a full-surface contract. Common layers are:

```text
core
core,http
core,events
core,workflow
core,ui,textual
core,ui,web
full
```

Never author raw OpenAPI, AsyncAPI, CWL, route manifests, panel manifests, HTML/CSS panel artifacts, Textual projections, pytest-bdd step text, `.feature` files, SQL, migrations, ORM models, or datastore-specific fields. Declare product meaning once in `spec/spec.yaml` and let the compiler project only what the positive spec graph requires.

For API-only work, stay in `core,http`: resources, capabilities, fixtures, scenarios, and API entries. Do not introduce UI, content, audit, workflow, or event vocabulary unless that surface is part of the current deliverable.

For workflow/CI-client work, use `core,workflow`: workflows and CLI/worker/scheduled entries. Do not introduce UI contracts unless the requested deliverable is actually a UI.

For Textual/TUI work, use `core,ui,textual`: panels, composed views, copy/assets, render cases, Textual presentation, and Textual SVG audit. Do not add HTML/CSS requirements.

For web work, use `core,ui,web`: panels, composed views, copy/assets, render cases, HTML/CSS presentation, and HTML PNG audit. Do not add Textual requirements.

Choose scenario archetypes from the package reference `src/pyspec_contract/patterns.yaml`. Define every fixture in the spec; do not assume hidden driver fixtures. Scenarios are pure product scenarios. Do not add harness routing such as `spec`, `prod`, `dev`, or `test` to any scenario.

Resources are pure product data models. Declare fields, lifecycle, and product invariants only. Do not declare persistence dialects, SQL tables, ORM details, storage engines, indexes, migrations, or database-specific constraints in the PM/design spec.

For lifecycle state changes, prefer the resource lifecycle as the source of truth. A transition capability may omit `transition.field`, `transition.from`, and `transition.to` when the lifecycle transition names that capability through `by`. The compiled spec expands the details for validators and projections.

Use `basis` or `why` sparingly in `spec/spec.yaml`: include it when a decision is not obvious or when it preserves product intent for future edits. Do not add confidence fields, review flags, status fields, version fields, notes, or other meta-specification content.

For exact HTML/CSS or Textual/TCSS requirements, add presentation details inside the relevant view or panel state only when the active layer permits that surface. HTML/CSS and Textual/TCSS are first-class surface contracts; do not replace precise surface requirements with vague implementation hints.

For composed product screens, define reusable panel FSMs first, then mount them through view layout slots, includes, shared context, and sync rules.

Every rendered copy ref must be backed by a declared copy item. Every rendered asset ref must be backed by a declared asset item. Every view state or composed view state vector must be backed by a render case. Use audit profiles for fixed breakpoints. Do not create review reports or manifests; the compiler derives the full audit set from the spec.

For final copy or image assets, declare the typed content signature in `spec/spec.yaml` through copy or asset items with `args` and `resolver`. Add content-case coverage for every resolver-backed copy or asset. Do not write resolver bodies as a PM/spec agent; resolver bodies live in `spec/spec.py` next to `spec/spec.yaml` and must implement the generated stubs exactly.

## Final content resolver implementer

Edit `spec/spec.py` only after the PM/spec contract declares the resolver. Do not add resolver IDs, args, or asset formats in Python. Import generated arg classes from `spec/generated/content_resolvers/signatures.py` and refs from `spec/generated/test_adapters/python_refs.py`, return plain `str` for copy and `AssetResult` with real SVG for image assets, and keep outputs deterministic for declared content cases and render cases.

## Test agent

Do not infer scenarios from prose or implementation. Consume `spec/generated/behavior/scenarios.yaml`, `spec/generated/test_adapters/pytest_bdd_features/`, `spec/generated/behavior/fixtures.yaml`, and `spec/generated/test_adapters/driver_protocol.py`.

The generated `.feature` files are a pytest-bdd adapter, not a source of product truth. The executable scenario meaning is in `spec/generated/behavior/scenarios.yaml`.

There is exactly one generated Gherkin corpus. The spec harness and prod harness must both consume `spec/generated/test_adapters/pytest_bdd_features/`. The only difference between them is the driver fixture outside the spec.

The spec harness may use the reference/fake driver to prove the scenario is coherent as a specification.

The prod harness must call real product surfaces. It must not import `pyspec_contract.reference_driver`, monkeypatch policy answers, fake emitted events, fake rendered panels, or mutate generated obligations to make tests pass. Validation rejects obvious fake/spec shortcuts in `tests/prod_bdd`.

## Coding agent

Do not change `spec/spec.yaml` to fix implementation failures unless explicitly acting as the PM/spec agent.

Use generated constants and projections. Do not invent routes, strings, panels, CSS selectors, Textual widgets, TCSS rules, events, workflows, policies, operations, fixtures, scenario IDs, storage tables, or database migrations outside the spec and implementation layer.

Before claiming completion for the canonical example, run:

```bash
pyspec compile . --layers full
pyspec validate . --layers full
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q -p pytest_bdd.plugin
```

For narrower repos, replace `full` with the active layer set, such as `core,http` or `core,ui,textual`.
