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

The package is the reusable compiler/tooling. A spec workspace owns its own `spec/spec.yaml`, `spec/spec.py` content source implementation, product app under an app-local `src/` layout, tests, and `spec/generated/` artifacts. Generated agent prompts live under `spec/generated/agent_prompts/` and can be created from layers alone with `pyspec prompts . --layers ...`.

The canonical example intentionally exercises the full layer set so the package has a living end-to-end fixture.
