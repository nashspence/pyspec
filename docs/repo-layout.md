# Repo Layout

```text
src/pyspec_contract/
  package code, schemas, generated artifact writers, validators, runtime helpers

examples/project_dispatch_board/
  canonical full-surface product specification workspace

tests/
  package and canonical-example regression tests

docs/
  project notes and packaging guidance
```

The package is the reusable compiler/tooling. A spec workspace owns its own `contract.yaml`, optional `pm.patch.yaml`, resolver implementation, product app, tests, and `generated/` artifacts.

The canonical example intentionally exercises the full layer set so the package has a living end-to-end fixture.
