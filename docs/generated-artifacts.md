# Generated Artifacts

`spec/generated/` is durable product evidence, not a disposable cache. The current policy is to check in every generated artifact, including audit PNG renders exactly as produced.

The tree is organized by artifact purpose:

- `agent_prompts/` contains standalone layer-specific role prompts for PM/design, test, dev, and review agents.
- `compiled/` contains the compiler-normalized spec.
- `product_interfaces/` contains product-facing projections such as OpenAPI, AsyncAPI, CWL, HTML routes, state-machine renderer manifests, and Textual projections.
- `behavior/` contains semantic fixtures and behavior scenarios.
- `content_resolvers/` contains typed signatures, examples, and implementation stubs for `spec/spec.py`.
- `test_adapters/` contains Python and pytest-bdd glue derived from `behavior/`.
- `audit_evidence/` contains subject-local external-interface flows, command/query flows, workflow flows, state-machine diagrams, view-state composition diagrams, scoped inputs, and rendered visual evidence.

Validation enforces a closed generated tree:

- every expected projection must exist
- no extra generated files may be present
- text projections must match compiler output
- audit SVG files must be valid SVG
- audit PNG files must have a PNG header
- BDD features must be the single canonical generated corpus
- agent prompt templates must match the active layers and include the `{{USER_PROMPT}}` substitution point

Future work can add compression or retention knobs, but the default package API already represents that decision through `ArtifactPolicy`.
