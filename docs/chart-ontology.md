# Chart Ontology

This glossary records the current visual-audit chart ontology as a starting
baseline. It follows the vocabulary boundaries in `docs/spec-ontology.md`: chart
terms should describe visual evidence for the product contract without replacing
the product-domain, projection, behavior, workflow, state-machine, or
access-policy vocabulary they display.

## Ontology Goal and Change Principles

The goal of the chart ontology is to make generated diagrams, rendered audit
captures, symbols, and colors intentional enough that visual evidence can be
reviewed as a contract artifact rather than decorative output.

When modifying or extending the chart ontology:

- Use chart terms only for visual representation. Product concepts such as
  `command`, `query`, `domain_event`, `workflow_activity`, `state_machine_state`,
  `local_signal`, and `access_policy` keep their meanings from
  `docs/spec-ontology.md`.
- Prefer qualified visual terms such as `chart_card`, `card_subtitle`,
  `flow_edge`, `render_capture`, `style_token`, or `placeholder_symbol` over
  generic terms such as `box`, `label`, `line`, `color`, or `icon`.
- Do not introduce a new color role without naming the semantic distinction it
  carries. If the distinction is visual-only, keep it in this document rather
  than the product ontology.
- Keep generated artifact names stable. A chart term that maps to a file path,
  function name, schema key, or visual coverage concept should use one canonical
  spelling.
- Treat generated SVG diagrams and rendered captures differently. Diagrams use
  Graphviz/DOT chart cards; rendered captures use renderer contracts, CSS/TCSS,
  content resolvers, media assets, and viewport profiles.
- Record current behavior before tightening it. If implementation behavior and
  intended semantic color differ, document both rather than silently renaming.

## Scope

The current chart ontology covers:

- Graphviz SVG diagrams generated for state machines, state-machine
  compositions, external interfaces, workflows, commands, and queries.
- HTML render sources and PNG screenshots generated for state-machine renderer
  surfaces and render examples.
- Textual render sources and SVG captures generated for state-machine renderer
  surfaces and render examples.
- Scoped audit inputs generated beside render captures, including
  `text_resources.yaml`, `fixtures.yaml`, and `media_assets/*.svg`.
- Visual coverage metadata in `audit_evidence/coverage.yaml`.

This document does not define OpenAPI, AsyncAPI, CWL, BDD, JSON Schema,
HTML, CSS, Textual, TCSS, or Graphviz vocabulary except where those terms are
used as visual projection vocabulary.

## Artifact Families

- `graphviz_diagram`: a generated SVG produced from DOT source. Current
  diagram families are state-machine diagrams, composition diagrams,
  external-interface flow diagrams, workflow flow diagrams, and command/query
  flow diagrams.
- `state_machine_diagram`: a Graphviz diagram at
  `audit_evidence/state_machines/{state_machine}/state_machine.svg` that shows
  state cards and transition-signal cards.
- `composition_diagram`: a Graphviz diagram at
  `audit_evidence/state_machines/{state_machine}/states/{state}/composition.svg`
  that shows mounted child state machines, emitted local signals, local-signal
  sync rules, sent local signals, and parent context updates.
- `external_interface_flow_diagram`: a Graphviz diagram at
  `audit_evidence/external_interfaces/{adapter}/{external_interface}/flow.svg`
  that shows an adapter-facing external interface, its invoked target, optional
  target tail cards, and response or response-handler cards.
- `workflow_flow_diagram`: a Graphviz diagram at
  `audit_evidence/workflows/{workflow}/flow.svg` that shows workflow input,
  the workflow summary, activities, gateways, sequence-flow edges, and terminal
  workflow outcomes.
- `command_query_flow_diagram`: a Graphviz diagram at
  `audit_evidence/{commands|queries}/{command_or_query}/flow.svg` that shows
  chronological product behavior: input, optional authorization gate, touched
  resources, outcomes, and emitted domain events.
- `render_source`: generated HTML or Python source used to produce a render
  capture.
- `render_capture`: generated PNG or SVG visual output produced from a renderer
  surface and viewport. HTML render captures are PNG screenshots; Textual render
  captures are SVG captures.
- `scoped_audit_input`: generated local input data for a state or render
  example, such as `text_resources.yaml`, `fixtures.yaml`, and scoped
  `media_assets/*.svg`.

## Visual Coverage Terms

The visual coverage terms below are defined in `docs/spec-ontology.md` and are
part of the chart ontology because they decide which charts count as evidence.

- `visual_evidence_set`: a shared set of generated diagrams or render captures
  that evidence one or more compiled JSON Pointers.
- `required_visual_pointer`: a compiled JSON Pointer that must have visual
  evidence.
- `required_visual_text_witness`: a durable visible SVG token that proves a
  required value is rendered as text.
- `optional_visual_pointer`: a compiled JSON Pointer that may have visual
  evidence but is allowed to be absent.
- `non_visual_pointer`: compiled metadata intentionally outside visual-audit
  scope.
- `render_presence`: resource-level visibility in actual render captures for
  media assets, text resources, fixtures, preconditions, assertions, and content
  examples.

## Graphviz Grammar

- `dot_graph`: the DOT source generated for a `graphviz_diagram`. Current DOT
  graphs use left-to-right rank direction, transparent background, spline
  edges, Arial fonts, and plain HTML-table nodes.
- `chart_card`: the main visual node shape in Graphviz diagrams. A chart card is
  an HTML table with a white body, a semantic border, a narrow semantic top bar,
  and a tinted header.
- `card_title`: the primary visible identifier or surface title in a chart card.
  Examples include a state id, resource ref, route path, CLI command, workflow
  id, signal name, or outcome id.
- `card_subtitle`: the chart role displayed under a title, such as `state`,
  `initial state`, `transition signal`, `workflow activity`,
  `authorization gate`, `success outcome`, or `failure response handler`.
- `card_rationale`: optional italic body text copied from contract rationale.
  It explains why the represented contract exists; it is not a separate chart
  node.
- `card_section`: a titled group of body rows inside a chart card. Current
  section names include `text_resources`, `media_assets`, `query_bindings`,
  `command_bindings`, `access_policies`, `child_state_machines`, `payload`,
  `fields`, `input mapping`, `sequence flows`, `rules`, `result`, `status`,
  `body schema`, `stdout`, `stderr`, `exit_code`, `disposition`, and `retry`.
- `typed_field_row`: a row that pairs a field name with a rendered type in muted
  type color. This is used for JSON Schema-derived fields, payloads, inputs,
  outputs, query results, command results, and transition fields.
- `transition_field_row`: a typed field row that also displays a state change,
  currently used for `entity_lifecycle_transition` values.
- `reference_field_row`: a typed field row whose type column is a referenced
  resource id rather than a JSON Schema type display.
- `flow_edge`: a directed Graphviz edge between chart cards. Current generated
  edges may carry labels such as `authorize`, `creates`, `reads`, `updates`,
  `deletes`, `success`, `failure`, `emit`, workflow sequence-flow ids,
  source outcomes, or gateway conditions.
- `invisible_order_edge`: a DOT-only edge used to stabilize sibling ordering and
  rank layout. It is not visual evidence.

Current implementation note: `_dot_edge` deliberately strips any `color`
attribute before emitting DOT, so rendered flow edges use the default edge color
even when callers pass semantic edge colors. Pen width, labels, style, and
weight still flow through.

## Diagram-Specific Terms

- `state_card`: a chart card for one local `state_machine_state`. The initial
  state uses initial-state styling; other states use neutral styling.
- `transition_signal_card`: a chart card between source and target states. It
  displays a state-machine trigger as `local_signal.<name>` or
  `data_refresh_signal.<name>` and includes relevant bindings, effects, loads,
  and raises.
- `mount_card`: a composition chart card for a child state-machine instance. Its
  subtitle is the placement mount, such as `nav mount`.
- `emitted_local_signal_card`: a composition chart card for a local signal
  emitted by a mounted child machine.
- `local_signal_sync_card`: a composition chart card for a
  `local_signal_sync_rule`.
- `sent_local_signal_card`: a composition chart card for a sync `send` effect.
- `context_update_card`: a composition chart card for a parent state-machine
  context `set` effect.
- `external_interface_card`: a chart card for the adapter-facing boundary. Its
  title is surface-specific: HTTP method and path, HTML route path, CLI command,
  schedule expression, worker workflow ref, or webhook path.
- `invoked_target_card`: a chart card for the command, query, state machine,
  workflow, delegated external interface, or domain event invoked by an external
  interface.
- `target_tail_card`: a compact card appended after an invoked target to expose
  mounted state machines or state-machine states without repeating full
  command/query flows.
- `response_card`: an external-interface card for a mapped response,
  disposition, or response handler. Success/failure styling follows the invoked
  outcome kind when available; otherwise it is inferred from adapter
  disposition or problem shape.
- `workflow_input_card`: a workflow chart card for workflow input, often a
  `domain_event` input.
- `workflow_summary_card`: a workflow chart card that summarizes activities,
  gateways, and workflow outcomes.
- `workflow_activity_card`: a workflow chart card for one
  `workflow_activity`, including the command, input mapping, sequence flows,
  and command reference metadata.
- `workflow_gateway_card`: a workflow chart card for one `workflow_gateway`,
  including gateway type and gateway-sourced sequence flows.
- `workflow_outcome_card`: a terminal workflow outcome card. It uses
  success/failure/target exit styling according to outcome kind.
- `authorization_gate_card`: a command/query chart card for the access policy
  checked before behavior execution.
- `resource_card`: a command/query chart card for an entity type or reusable
  schema touched by behavior.
- `outcome_card`: a command/query chart card for a named behavior outcome.
- `emitted_domain_event_card`: a command chart card for a domain event emitted
  by a successful outcome.

## Symbol Ontology

- `right_arrow_symbol`: `→` is used inside chart-card text for sequence or
  transition summaries, such as workflow activity-to-command references,
  workflow sequence-flow destinations, retry-policy destinations, and entity
  lifecycle changes.
- `assignment_arrow_symbol`: `←` is used inside chart-card text for bindings
  and source-derived values. It means "value comes from source"; it is not a
  graph edge.
- `typed_field_spacing`: typed rows place the rendered type after the field name
  with non-breaking spacing and muted type color.
- `reference_prefix_symbol`: resource identifiers keep their canonical typed
  prefixes, such as `command.`, `query.`, `domain_event.`, `state_machine.`,
  `external_interface.`, `schema.`, `entity_type.`, `access_policy.`,
  `text_resource.`, and `media_asset.`. These prefixes are semantic witnesses,
  not decoration.
- `signal_prefix_symbol`: local signal labels render as `local_signal.<name>` or
  `data_refresh_signal.<name>` even though authored signal names are local.
- `style_token_reference`: `token.<name>` inside renderer style declarations is
  a symbolic reference to a renderer style token. HTML generation currently
  expands it to `var(--<name-with-dashes>)`.
- `placeholder_symbol`: a media-asset placeholder symbol enum carried by
  `media_asset.placeholder.placeholder_symbol`. Current schema values are
  `folder`, `document`, `chart`, `person`, `box`, `list`, `star`, `circle`,
  `square`, `card`, and `terminal`.

Current implementation note: the generic placeholder SVG does not yet draw
different shapes for each `placeholder_symbol`; it draws the same neutral
abstract SVG for all placeholder symbols. Resolver-backed media assets may draw
their own SVG symbols.

## Color Ontology

Graphviz card colors currently use paired roles: a saturated border/top-bar
color and a pale header tint. Body fill is white.

| Visual role | Border/top bar | Header tint | Current meaning |
| --- | --- | --- | --- |
| `edge` | `#3f3f46` | n/a | Default Graphviz edge stroke and arrow fill. |
| `muted_text` | `#64748b` | n/a | Card subtitles and secondary metadata. |
| `type_text` | `#94a3b8` | n/a | Rendered schema/type labels in typed rows. |
| `audit_text` | `#3f3f46` | n/a | Italic rationale text in cards. |
| `external_interface` | `#0891b2` | `#ecfeff` | Adapter-facing boundary cards. |
| `initial_state` | `#0891b2` | `#ecfeff` | Initial state cards; currently shares the external-interface color pair. |
| `neutral` | `#71717a` | `#f8fafc` | Ordinary states, workflow activities, generic inputs, and fallback cards. |
| `boundary` | `#64748b` | `#f8fafc` | External input cards that are visually neutral but boundary-facing. |
| `target` | `#9333ea` | `#faf5ff` | Invoked state-machine target cards and non-success/non-failure exits. |
| `success_exit` | `#16a34a` | `#f0fdf4` | Success outcomes, responses, and dispositions. |
| `failure_exit` | `#dc2626` | `#fef2f2` | Failure outcomes, responses, dispositions, and problems. |
| `product_behavior` | `#2563eb` | `#eff6ff` | Commands, queries, transition signal cards, and invoked product behavior. |
| `domain_event` | `#4f46e5` | `#eef2ff` | Domain-event cards and currently emitted local-signal cards. |
| `state_machine` | `#047857` | `#ecfdf5` | Child state-machine mount cards. |
| `workflow` | `#a16207` | `#fefce8` | Workflow summary, gateway, and local-signal-sync cards. |
| `message` | `#be185d` | `#fdf2f8` | Sent local-signal cards in composition diagrams. |
| `context` | `#15803d` | `#f0fdf4` | State-machine context update cards. |
| `entity_type` | `#15803d` | `#f0fdfa` | Entity-type resource cards. |
| `schema` | `#7c3aed` | `#f5f3ff` | Reusable schema resource cards. |
| `policy` | `#c2410c` | `#fff7ed` | Access-policy and authorization-gate cards. |

HTML audit render colors are currently baseline renderer chrome, not product
semantic colors:

- `#f7f7f8`: page background.
- `#171717`: page text.
- `#ffffff`: rendered surface background.
- `#d0d0d0`: rendered surface border.
- `#e4e4e7`: audit record border.
- `#52525b`: audit field label text and some resolver-backed media asset
  strokes.
- `#222`: default button border.

Generic media placeholder SVG colors are also visual chrome:

- `#fafafa` to `#e4e4e7`: placeholder background gradient.
- `#a1a1aa`: placeholder outer and inner strokes.
- `#d4d4d8`: placeholder circle fill.
- `#f4f4f5`: placeholder square fill.
- `#71717a`: placeholder path stroke.

Textual capture colors are mostly emitted by Textual itself and should not be
treated as contract-owned semantic colors unless a renderer style rule declares
them. Current generated Textual TCSS owns selectors and declarations, not a
global semantic palette.

## Renderer Style Terms

- `renderer_style_contract`: renderer-local styling for generated browser or
  Textual artifacts. It is projection vocabulary, not product vocabulary.
- `html_style_contract`: HTML-only style contract with `tokens` and CSS
  selector-scoped `rules`.
- `textual_style_contract`: Textual-only style contract with `tokens` and TCSS
  selector-scoped `rules`.
- `style_token`: a renderer-local named value under `style.tokens`. Token names
  are lowercase snake_case. HTML output emits them as CSS custom properties on
  the root selector.
- `style_rule`: a selector plus declarations. Declarations are passed through as
  CSS or TCSS values after `token.<name>` substitution.
- `html_style_selector`: one of `root`, `slot.<slot>`,
  `command_binding.<binding>`, `region.<region>`, or
  `child_state_machine.<instance>`.
- `textual_style_selector`: one of `screen`, `slot.<slot>`,
  `command_binding.<binding>`, `container.<container>`, or
  `child_state_machine.<instance>`.
- `viewport_profile`: visual-audit viewport contract. HTML viewports use
  `width` and `height`; Textual viewports use `columns` and `rows`.

Current example style tokens are layout tokens rather than colors:
`nav_width`, `aside_width`, and `gap`.

## Current Tightening Targets

These are baseline observations, not required changes:

- Edge color intent is present at call sites but not emitted into DOT. Decide
  whether semantic edge colors should remain intentionally suppressed or become
  part of the rendered ontology.
- `initial_state` and `external_interface` currently share a color pair. Decide
  whether that overlap is intentional because both are entry boundaries, or
  whether initial state needs a distinct role color.
- `domain_event` styling is also used for emitted local-signal cards in
  composition diagrams. That may blur the `domain_event` vs `local_signal`
  boundary from `docs/spec-ontology.md`.
- `context` and `entity_type` share a green border. Decide whether they are
  distinct enough through header tint alone.
- `placeholder_symbol` values are schema-level intent, but generic placeholder
  rendering does not yet vary by symbol.
- Renderer style tokens currently allow arbitrary CSS/TCSS values and are not
  separated into color, spacing, sizing, typography, or layout token classes.
- Resolver-backed SVG media assets may introduce colors outside the central
  chart palette. Decide whether final media assets should remain resolver-owned
  or declare their own asset-local color ontology.
