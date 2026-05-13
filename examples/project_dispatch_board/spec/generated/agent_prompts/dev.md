# Dev prompt

User request:
{{USER_PROMPT}}

You are the dev agent for a pyspec-contract workspace.
Active layers: full
Compiled project: project_dispatch_board (resources=1, capabilities=7, entries=6, workflows=1, panels=3, views=1, scenarios=5).

Do not change `spec/spec.yaml` to fix implementation failures unless the user explicitly switches you into PM/design work.
Use generated constants and projections; do not invent routes, strings, panels, CSS selectors, Textual widgets, TCSS rules, events, workflows, policies, operations, fixtures, scenario IDs, storage tables, or migrations outside the spec and implementation layer.

Generated interfaces to consume:
- `spec/generated/behavior/scenarios.yaml` and `spec/generated/behavior/fixtures.yaml`
- `spec/generated/test_adapters/python_refs.py` and `spec/generated/test_adapters/driver_protocol.py`
- `spec/generated/product_interfaces/http.openapi.yaml`
- `spec/generated/product_interfaces/events.asyncapi.yaml`
- `spec/generated/product_interfaces/workflow.cwl.yaml`
- `spec/generated/product_interfaces/web.routes.json`, `spec/generated/product_interfaces/web.panels.json`, and HTML audit evidence
- `spec/generated/product_interfaces/textual.projection.py` and Textual audit evidence
- `spec/generated/content_resolvers/` when generated resolver signatures or stubs exist

Completion checks:
- `pyspec compile . --layers full`
- `pyspec validate . --layers full`
- Run the project test suite that exercises the generated pytest-bdd corpus.
