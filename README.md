# pyspec-contract

`pyspec-contract` is a Python-first, contract-to-artifact tool for whole-app product specifications. It turns a sparse human-authored `contract.yaml` into a strict compiled contract, protocol projections, BDD fixtures/features, generated Python obligations, and visual audit artifacts.

The reusable tool lives in `src/pyspec_contract/`. Product specifications live in project workspaces. The canonical example workspace is:

```text
examples/project_dispatch_board/
  AGENTS.md
  contract.yaml
  contract.py
  sample_app/
  generated/
  tests/
    spec_bdd/
    prod_bdd/
```

`generated/` is intended to be checked in as reviewable product evidence. For now, audit PNGs are retained exactly as generated.

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
```

## Authoring Model

The human source is `contract.yaml`. It is sparse, positive-only, and grouped by product concepts:

```text
contract.yaml
  -> generated/contract.complete.yaml
  -> generated projections required by positive declarations
  -> generated pytest-bdd feature corpus
  -> visual audit artifacts when render cases exist
```

The contract is progressive. If a concern is absent, it has no declaration and no generated projection. The contract does not contain storage implementation details, test-harness routing, dev-environment metadata, review state, release state, or schema-version chatter.

## Layers

Layers are authoring guardrails. They constrain vocabulary during compile/validate but are not written into `generated/contract.complete.yaml`.

Common layer sets:

```text
core
core,http
core,events
core,workflow
core,ui,textual
core,ui,web
full
```

Examples:

```bash
pyspec compile . --layers core,http
pyspec validate . --layers core,http
```

The package ships layer-pruned schemas under `pyspec_contract/schemas/layers/`, including:

```text
core_http.author.schema.json
core_ui_web.author.schema.json
full.author.schema.json
```

## Generated Artifacts

A full-surface project can generate:

```text
generated/
  contract.complete.yaml
  openapi.yaml
  asyncapi.yaml
  workflows.cwl.yaml
  routes.json
  panels.json
  panels.html
  panel_styles.css
  refs.py
  driver_protocol.py
  bdd_steps.py
  content_contract.py
  content_stubs.py
  content_cases.yaml
  features/*.feature
  audit/
    copy.yaml
    fixtures.yaml
    assets/*.svg
    fsm/*.svg
    composition/*.svg
    html/**/*.html
    html/**/*.png
    textual/**/*.py
    textual/**/*.svg
```

Validation treats the generated tree as closed: missing files, extra files, hand-edited text projections, corrupt PNGs, invalid SVGs, or stale compiled contracts fail validation.

## BDD Harnesses

There is exactly one generated Gherkin corpus:

```text
generated/features/*.feature
```

Both pytest-bdd harnesses consume that same corpus. The difference is only the driver fixture outside the contract:

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

Graphviz is required for FSM and composition SVGs. The devcontainer includes it. If `dot` lives elsewhere:

```bash
export CONTRACT_AUDIT_GRAPHVIZ_DOT=/path/to/dot
```

When system Chromium is available:

```bash
export CONTRACT_AUDIT_CHROMIUM=/usr/bin/chromium
```
