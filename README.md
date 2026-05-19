# pyspec-contract

`pyspec-contract` is a Python-first, spec-to-artifact tool for whole-app product specifications. It turns a sparse human-authored `spec/spec.yaml` into a strict compiled spec, protocol projections, BDD fixtures/features, generated Python adapters, and visual audit artifacts.

The reusable tool lives in `src/pyspec_contract/`. Product specifications live in project workspaces. The canonical example workspace is:

```text
examples/project_dispatch_board/
  AGENTS.md
  spec/
    spec.yaml
    spec.py
    generated/
  src/
    project_dispatch_board/
  tests/
    spec_bdd/
    prod_bdd/
```

`spec/generated/` is intended to be checked in as reviewable product evidence. For now, audit PNGs are retained exactly as generated.

## Install

From this repository:

```bash
python -m pip install -e ".[dev]"
python -m playwright install chromium
```

From GitHub:

```bash
python -m pip install "git+https://github.com/<org>/<repo>.git"
```

The package exposes the `pyspec` command:

```bash
pyspec compile examples/project_dispatch_board --layers full
pyspec validate examples/project_dispatch_board --layers full
pyspec check examples/project_dispatch_board --layers full
pyspec prompts examples/new_project --layers core,http
```

## Authoring Entity Types

The human source is `spec/spec.yaml`. It is sparse, positive-only, and grouped by product concepts:

```text
spec/spec.yaml
  -> spec/generated/compiled/spec.yaml
  -> product interfaces and behavior projections required by positive declarations
  -> pytest-bdd adapter files derived from behavior/behavior_scenarios.yaml
  -> audit evidence when state-machine states declare render examples
```

The spec is progressive. If a concern is absent, it has no declaration and no generated projection. The spec does not contain storage implementation details, test-harness dispatch, dev-environment metadata, review state, release state, or schema-version chatter.

Reusable top-level `preconditions` name setup predicates, such as an entity that must already exist. Behavior scenarios reference them with `given.preconditions: [{ref: precondition.project.submitted}]`, and state-local render examples use `precondition_refs: [precondition.project.submitted]`. Reusable expected predicates belong in top-level `assertions` and are referenced from `then.postconditions`.

## Layers

Layers are authoring guardrails. They constrain vocabulary during compile/validate but are not written into `spec/generated/compiled/spec.yaml`.

Common layer sets:

```text
core
core,http
core,eventing
core,workflow
core,ui,textual
core,ui,html
full
```

Examples:

```bash
pyspec compile . --layers core,http
pyspec validate . --layers core,http
```

Layer-pruned schemas are generated from `author.schema.json` on demand instead of checked in as duplicate source files:

```bash
python -m pyspec_contract.layers core,http
python -m pyspec_contract.layers --write-common
```

The `--write-common` command writes local editor/tooling copies under the ignored `pyspec_contract/schemas/layers/` directory.

## Generated Artifacts

A full-surface project can generate:

```text
spec/generated/
  agent_prompts/
    pm_design.md
    test.md
    dev.md
    review.md
  compiled/
    spec.yaml
  product_interfaces/
    http.openapi.yaml
    integration_messages.asyncapi.yaml
    workflow.cwl.yaml
    html.routes.json
    html.state_machines.json
    textual.projection.py
  behavior/
    fixtures.yaml
    behavior_scenarios.yaml
  content_resolvers/
    signatures.py
    stubs.py
    examples.yaml
  test_adapters/
    python_refs.py
    driver_protocol.py
    pytest_bdd_steps.py
    pytest_bdd_features/*.feature
  audit_evidence/
    coverage.yaml
    external_interfaces/<adapter>/<external_interface>/
      flow.svg
    workflows/<workflow>/
      flow.svg
    commands/<command>/
      flow.svg
    queries/<query>/
      flow.svg
    state_machines/<state_machine>/
      state_machine.svg
      states/<state_machine_state>/
        composition.svg
        text_resources.yaml
        fixtures.yaml
        media_assets/*.svg
        renders/html.<profile>.<breakpoint>.source.html
        renders/html.<profile>.<breakpoint>.screenshot.png
        renders/textual.<profile>.<breakpoint>.source.py
        renders/textual.<profile>.<breakpoint>.capture.svg
        render_examples/<render_example>/
          text_resources.yaml
          fixtures.yaml
          media_assets/*.svg
          renders/html.<profile>.<breakpoint>.source.html
          renders/html.<profile>.<breakpoint>.screenshot.png
          renders/textual.<profile>.<breakpoint>.source.py
          renders/textual.<profile>.<breakpoint>.capture.svg
```

The role prompt templates are standalone, layer-specific prompts with a stable
`{{USER_PROMPT}}` substitution point. PM/design, test, and dev prompts guide the
slice work; `review.md` checks a completed vertical slice for merge readiness.
`pyspec compile` regenerates them with the rest of the closed generated tree,
and `pyspec prompts . --layers core,http` can write just the prompts before an
authored spec exists. `pyspec init --layers ...` also writes starter prompts
unless `--no-prompts` is passed.

Validation treats the generated tree as closed: missing files, extra files, hand-edited text projections, corrupt PNGs, invalid SVGs, or stale compiled specs fail validation.

## BDD Harnesses

There is exactly one generated Gherkin corpus:

```text
spec/generated/test_adapters/pytest_bdd_features/*.feature
```

Both pytest-bdd harnesses consume that same corpus. The difference is only the driver fixture outside the spec:

```text
tests/spec_bdd/ -> reference/spec driver
tests/prod_bdd/ -> real product driver
```

The canonical example includes both harnesses under `examples/project_dispatch_board/tests/`.

## Python API

The public API is intentionally small:

```python
from pyspec_contract import compile_project, validate_project

compile_project("examples/project_dispatch_board", layers="full")
validate_project("examples/project_dispatch_board", layers="full")
```

Lower-level helpers are also exposed for tooling:

```python
from pyspec_contract import (
    ArtifactPolicy,
    ProjectConfig,
    compile_author,
    compile_source,
    expected_artifacts,
    write_generated,
)
```

## Development

Run the full local check:

```bash
pyspec check examples/project_dispatch_board --layers full
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q -p pytest_bdd.plugin
```

Graphviz is required for external-interface, command/query, workflow, state-machine, and composition SVGs. The devcontainer includes it. If `dot` lives elsewhere:

```bash
export CONTRACT_AUDIT_GRAPHVIZ_DOT=/path/to/dot
```

When system Chromium is available:

```bash
export CONTRACT_AUDIT_CHROMIUM=/usr/bin/chromium
```
