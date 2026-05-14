# Generated Artifacts

`spec/generated/` is durable product evidence, not a disposable cache. The current policy is to check in every generated artifact, including audit PNG renders exactly as produced.

The tree is organized by why an artifact exists:

- `agent_prompts/` contains standalone layer-specific role prompts for PM/design, test, dev, and review agents.
- `compiled/` contains the compiler-normalized spec.
- `product_interfaces/` contains product-facing projections such as OpenAPI, AsyncAPI, CWL, routes, panel manifests, and Textual projections.
- `behavior/` contains semantic fixtures and scenarios.
- `content_resolvers/` contains typed signatures, cases, and implementation stubs for `spec/spec.py`.
- `test_adapters/` contains Python and pytest-bdd glue derived from `behavior/`.
- `audit_evidence/` contains subject-local entrypoint flows, workflow flows, panel FSMs, composed-view composition diagrams, scoped inputs, and rendered visual evidence.

Validation enforces a closed generated tree:

- every expected projection must exist
- no extra generated files may be present
- text projections must match compiler output
- audit SVG files must be valid SVG
- audit PNG files must have a PNG header
- BDD features must be the single canonical generated corpus
- agent prompt templates must match the active layers and include the `{{USER_PROMPT}}` substitution point

Future work can add compression or retention knobs, but the default package API already models that decision through `ArtifactPolicy`.
