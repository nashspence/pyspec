# Chart Ontology

This glossary defines the vocabulary for generated chart artifacts used as visual audit evidence. Chart terms name visual carriers, diagram families, rendered glyphs, edge conventions, and tone roles. They do not redefine the product-domain, projection, workflow, state-machine, behavior, access-control, or visual-audit coverage terms defined by `docs/spec-ontology.md`.

## Ontology Goal and Change Principles

The goal of the chart ontology is to make generated Graphviz charts reviewable as contract evidence. A reviewer should be able to tell which product contract a chart is witnessing without mistaking a visual convention for a new product concept.

When modifying or extending the chart ontology:

- Use chart-owned terms only for visual representation, chart artifact families, layout mechanics, visible text witnesses, edge conventions, glyphs, rows, sections, and tones.
- Do not introduce a chart-owned term that exactly matches a canonical source-ontology term. If a chart displays a source term, qualify the chart carrier, for example `workflow_activity_card`, `access_policy_check_card`, or `domain_event_emission_card`.
- Do not introduce visual synonyms for product concepts. A chart may display a `command`, `query`, `domain_event`, `state_machine_state`, or `access_policy`, but the chart-owned vocabulary must describe the card, edge, row, label, or tone that carries that source concept.
- Prefer stable visualization terms over generic drawing words. Use `chart_card`, `chart_edge`, `chart_card_role`, `chart_section_label`, `chart_tone_role`, or `chart_layout_edge` rather than `box`, `line`, `label`, `color`, or `icon`.
- Treat edge labels, card titles, section labels, and reference prefixes as visible source witnesses. Their text may quote canonical source names or generated reference ids, but that text is not a new chart ontology term.
- Do not introduce a new tone role unless the tone carries a reviewable semantic distinction. Pure aesthetic differences belong in renderer implementation notes, not in the ontology.
- Keep generated chart artifact paths stable. A chart term that maps to a generated file path, function name, schema key, or test fixture should have one canonical spelling.
- Record migration aliases when tightening existing terminology. Deprecated names should point to the canonical chart-owned term instead of remaining parallel vocabulary.

## Scope

The chart ontology covers Graphviz SVG charts generated under `spec/generated/audit_evidence/**` for state machines, state-machine compositions, external interfaces, workflows, commands, and queries.

The chart ontology does not cover rendered application captures, screenshots, scoped audit input files, generated coverage indexes, authored product schemas, compiled product schemas, renderer contracts, OpenAPI projections, AsyncAPI projections, CWL projections, behavior scenarios, or generated code.

## Source-Domain Alignment

Chart vocabulary is intentionally an evidence layer over the source ontology. Each chart-owned carrier should align to exactly one source domain, even when the visible card text includes several source references.

| Chart evidence area | Canonical chart-owned carriers | Source domain witnessed | Boundary rule |
| --- | --- | --- | --- |
| Visual audit evidence | `chart_svg_artifact`, `chart_text_witness` | visual-audit coverage | Coverage pointers, witness requirements, and evidence-set membership remain owned by the spec ontology. |
| Graphviz rendering | `chart_dot_source`, `chart_card`, `chart_edge`, `chart_layout_edge` | renderer implementation | DOT and SVG mechanics explain rendering only; they do not create product resources. |
| State-machine behavior | `state_machine_chart`, `state_machine_state_card`, `state_machine_trigger_card` | state-machine contracts | Cards witness states, triggers, guards, local effects, loads, and raises without redefining state-machine vocabulary. |
| State-machine composition | `state_composition_chart`, `child_machine_mount_card`, `local_signal_emission_card`, `local_signal_sync_rule_card`, `local_signal_send_effect_card`, `state_context_update_card` | composed state-machine contracts | Composition cards witness child instances, local signal synchronization, send effects, and parent context updates. |
| External-interface invocation | `external_interface_flow_chart`, `adapter_boundary_card`, `invocation_target_card`, `invocation_target_preview_card` | adapter and invocation contracts | Adapter-facing shape and invoked target stay separate from command/query/workflow semantics. |
| Adapter responses | `invoked_outcome_response_card`, `adapter_ingress_response_card`, `cli_response_handler_card` | adapter output mappings | Synchronous invoked-outcome responses and asynchronous ingress responses remain separate. |
| Workflow behavior | `workflow_flow_chart`, `workflow_input_card`, `workflow_summary_card`, `workflow_activity_card`, `workflow_gateway_card`, `workflow_outcome_card` | BPMN-like workflow contracts | Workflow card terms may use BPMN-like roles only for workflow charts. |
| Command behavior | `command_flow_chart`, `behavior_input_card`, `authorization_check_card`, `entity_resource_card`, `schema_resource_card`, `behavior_outcome_card`, `domain_event_emission_card` | command contracts | State-changing behavior, authorization, entity changes, outcomes, and durable event emissions remain source-owned. |
| Query behavior | `query_flow_chart`, `behavior_input_card`, `authorization_check_card`, `schema_resource_card`, `behavior_outcome_card` | query contracts | Read-only behavior cards do not imply state changes or domain-event emission. |
| Access control | `authorization_check_card`, `authorization_policy_tone` | access-policy and command-authorization contracts | Authorization cards show policy checks and mapped failures; authorization decisions remain source vocabulary. |
| Reusable data contracts | `chart_schema_field_row`, `chart_reference_field_row`, `entity_resource_card`, `schema_resource_card` | JSON Schema, entity types, reusable schemas | Field rows and resource cards witness declared schemas and refs; they are not generated schemas themselves. |

## Artifact Families

Artifact terms identify generated chart SVG files only. Sibling DOT files, render sources, screenshots, captured application renderings, scoped audit inputs, and coverage indexes are outside this artifact family.

- `chart_svg_artifact`: a generated SVG chart produced from Graphviz DOT source and used as visual contract evidence.
- `state_machine_chart`: a chart at `spec/generated/audit_evidence/state_machines/{state_machine}/state_machine.svg` that shows local state cards and state-machine trigger cards.
- `state_composition_chart`: a chart at `spec/generated/audit_evidence/state_machines/{state_machine}/states/{state_machine_state}/composition.svg` that shows mounted child state machines, emitted local signals, synchronization rules, send effects, and parent context updates for one composed state.
- `external_interface_flow_chart`: a chart at `spec/generated/audit_evidence/external_interfaces/{adapter}/{external_interface}/flow.svg` that shows an adapter-facing boundary, invoked target, optional target preview cards, and adapter response cards.
- `workflow_flow_chart`: a chart at `spec/generated/audit_evidence/workflows/{workflow}/flow.svg` that shows workflow input, workflow summary, activities, gateways, sequence routing, and terminal workflow outcomes.
- `command_flow_chart`: a chart at `spec/generated/audit_evidence/commands/{command}/flow.svg` that shows chronological state-changing product behavior, including input, optional authorization, touched resources, outcomes, and emitted durable events.
- `query_flow_chart`: a chart at `spec/generated/audit_evidence/queries/{query}/flow.svg` that shows chronological read-only product behavior, including input, optional authorization, result resources, and outcomes.

## Graphviz and Card Grammar

- `chart_dot_source`: DOT source generated for a `chart_svg_artifact`. Current DOT source uses left-to-right rank direction, transparent background, spline edges, Arial fonts, and Graphviz HTML-like table nodes.
- `chart_card`: the main visible node carrier. A chart card is currently rendered as a Graphviz HTML-like table with a white body, semantic border, narrow top bar, and tinted header.
- `chart_card_title`: the primary visible identifier or surface title in a chart card. Examples include a local state id, resource reference, route path, CLI command surface, workflow id, signal display name, or outcome id.
- `chart_card_role`: the secondary visible role line under a chart title. It may display text such as state, initial state, transition signal, workflow activity, authorization check, success outcome, or failure response handler. Role text is a visible label, not a source ontology term unless it quotes one.
- `chart_card_rationale`: optional italic body text copied from source rationale. It explains why the represented contract exists; it is not an independent chart node or source term.
- `chart_card_section`: a grouped area of body rows inside a chart card.
- `chart_section_label`: the visible heading for a `chart_card_section`. Section labels may quote source schema keys such as text resources, media assets, query bindings, command bindings, access policies, payload, fields, sequence flows, result, status, disposition, retry, stdout, stderr, or exit code. These labels are source witnesses, not chart-owned terms.
- `chart_field_row`: a body row that displays a field-like item.
- `chart_schema_field_row`: a field row that pairs a field name with a displayed JSON Schema-derived type.
- `chart_transition_field_row`: a field row that displays a source-state to target-state change, currently used for entity lifecycle transitions.
- `chart_reference_field_row`: a field row whose displayed value or type column is a canonical source reference rather than a JSON Schema type.
- `chart_edge`: a directed visible connector between chart cards. Edges currently share one gray stroke unless a renderer implementation explicitly introduces a new reviewed semantic distinction.
- `chart_edge_label`: visible text attached to a `chart_edge`. Edge labels may quote source action names, outcome ids, workflow sequence-flow ids, gateway conditions, or signal names. Edge labels are source-derived witnesses, not chart-owned terms.
- `chart_layout_edge`: an invisible DOT-only edge used to stabilize sibling order and rank layout. It is never visual evidence.

## Edge Roles

Edge roles describe how a visible edge functions in a chart. They do not require separate stroke colors.

- `chart_sequence_edge`: an edge that shows chronological, transition, or control-flow order.
- `chart_invocation_edge`: an edge that shows an adapter boundary invoking a target contract.
- `chart_authorization_edge`: an edge that shows behavior passing through an authorization check before execution.
- `chart_resource_access_edge`: an edge that shows behavior touching an entity or reusable schema resource. The visible label may be source-derived action text such as creates, reads, updates, deletes, or returns.
- `chart_outcome_edge`: an edge that routes behavior, workflow, or adapter flow to a named outcome, response, disposition, or handler.
- `chart_event_emission_edge`: an edge that shows a successful behavior outcome emitting a durable domain-event card.
- `chart_signal_edge`: an edge that shows local-signal or data-refresh-signal routing inside state-machine and composition charts.

## Card Role Vocabulary

### State-machine chart cards

- `state_machine_state_card`: a card for one local state-machine state. The initial state uses `state_entry_tone`; other ordinary states use `neutral_structure_tone`.
- `state_machine_trigger_card`: a card between source and target state cards. It displays the current state-machine trigger and relevant bindings, guards, effects, loads, or raises.

### State composition chart cards

- `child_machine_mount_card`: a composition card for one mounted child state-machine instance. The visible role may include the placement mount, such as nav mount.
- `local_signal_emission_card`: a composition card for a local signal emitted by a mounted child machine.
- `local_signal_sync_rule_card`: a composition card for one local-signal synchronization rule.
- `local_signal_send_effect_card`: a composition card for a synchronization send effect.
- `state_context_update_card`: a composition card for a parent state-machine context set effect.

### External-interface flow cards

- `adapter_boundary_card`: a card for the adapter-facing external boundary. Its title is surface-specific: HTTP method and path, HTML route path, CLI command, schedule expression, worker workflow reference, or webhook path.
- `invocation_target_card`: a card for the command, query, state machine, workflow, delegated external interface, or durable event target invoked through an external interface.
- `invocation_target_preview_card`: a compact companion card appended after an invocation target to expose relevant mounted machines, states, or target details without repeating a full command, query, workflow, or state-machine chart.
- `invoked_outcome_response_card`: a card for a synchronous adapter response keyed by an invoked target outcome.
- `adapter_ingress_response_card`: a card for an asynchronous adapter acknowledgement, disposition, or dead-letter/retry response when receipt handling is distinct from invoked workflow execution.
- `cli_response_handler_card`: a card for a CLI response handler that maps a named response outcome to stdout, stderr, exit code, and optional retry display.

### Workflow flow cards

- `workflow_input_card`: a card for workflow input, often sourced from a durable domain event.
- `workflow_summary_card`: a card that summarizes workflow activities, gateways, retry policies, failure handlers, and terminal outcomes.
- `workflow_activity_card`: a card for one workflow activity, including invoked command metadata, input mapping, and activity-sourced sequence routing.
- `workflow_gateway_card`: a card for one workflow gateway, including gateway type and gateway-sourced routing conditions.
- `workflow_outcome_card`: a terminal workflow outcome card. It uses success, failure, or non-terminal target tone according to the outcome kind displayed from the source contract.

### Command and query flow cards

- `behavior_input_card`: a card for command or query input.
- `authorization_check_card`: a card for the access policy checked before behavior execution, including mapped authentication-required or access-denied outcomes when present.
- `entity_resource_card`: a command/query flow card for an entity type touched by behavior.
- `schema_resource_card`: a command/query flow card for a reusable schema returned, accepted, embedded, or otherwise witnessed by behavior.
- `behavior_outcome_card`: a card for a named command or query outcome.
- `domain_event_emission_card`: a command-flow card for a durable domain event emitted by a successful command outcome.

## Glyph and Visible-Witness Ontology

- `chart_sequence_glyph`: the `→` glyph used inside chart-card text for sequence, transition, destination, retry, and lifecycle-change summaries. It is text inside a card, not a graph edge.
- `chart_binding_source_glyph`: the `←` glyph used inside chart-card text for bindings and source-derived values. It means value comes from source; it is not a graph edge.
- `chart_type_spacing`: non-breaking spacing between a displayed field name and its muted type label in schema-derived rows.
- `chart_reference_prefix_witness`: the convention that canonical typed reference prefixes remain visible on cards, such as command, query, domain event, state machine, external interface, reusable schema, entity type, access policy, text resource, and media asset prefixes.
- `chart_signal_prefix_witness`: the convention that local signal labels are visibly qualified as local-signal or data-refresh-signal displays even though authored signal names are local.
- `chart_text_witness`: any stable visible token intentionally rendered so the visual audit can witness a compiled pointer. Durable ids, typed references, local ids, field names, type labels, and renderer-owned tokens are valid text witnesses; incidental prose and hidden SVG metadata are not.

## Tone Ontology

Graphviz card colors currently use paired tone roles: a saturated border/top-bar color and a pale header tint. Card body fill is white. Tone role names are chart-owned visual vocabulary; they should not be bare source resource names.

| Tone role | Border/top bar | Header tint | Current meaning |
| --- | --- | --- | --- |
| `chart_edge_tone` | `#3f3f46` | n/a | Default visible edge stroke and arrow fill. |
| `chart_muted_text_tone` | `#64748b` | n/a | Card roles and secondary metadata. |
| `chart_type_text_tone` | `#94a3b8` | n/a | Displayed schema/type labels in schema-derived rows. |
| `chart_rationale_text_tone` | `#3f3f46` | n/a | Italic rationale text in cards. |
| `adapter_boundary_tone` | `#0891b2` | `#ecfeff` | Adapter-facing boundary cards. |
| `state_entry_tone` | `#0369a1` | `#e0f2fe` | Initial state-machine entry cards; not an adapter boundary. |
| `neutral_structure_tone` | `#71717a` | `#f8fafc` | Ordinary states, simple workflow activities, generic inputs, and fallback cards. |
| `adapter_input_tone` | `#64748b` | `#f8fafc` | External input cards that are visually neutral but boundary-facing. |
| `invocation_target_tone` | `#9333ea` | `#faf5ff` | Invoked state-machine target cards and non-success/non-failure target exits. |
| `success_outcome_tone` | `#16a34a` | `#f0fdf4` | Success outcomes, responses, and dispositions. |
| `failure_outcome_tone` | `#dc2626` | `#fef2f2` | Failure outcomes, responses, dispositions, and problem responses. |
| `behavior_card_tone` | `#2563eb` | `#eff6ff` | Command, query, transition-trigger, and invoked product-behavior cards. |
| `durable_event_tone` | `#4f46e5` | `#eef2ff` | Durable domain-event cards and event-emission evidence. |
| `child_machine_tone` | `#047857` | `#ecfdf5` | Mounted child state-machine cards. |
| `workflow_control_tone` | `#a16207` | `#fefce8` | Workflow summary and gateway cards. |
| `local_signal_sync_tone` | `#a16207` | `#fefce8` | Local-signal synchronization rule cards. Current rendering may share the workflow-control palette, but the semantic role is distinct. |
| `local_signal_card_tone` | `#be185d` | `#fdf2f8` | Emitted and sent local-signal cards in composition diagrams. |
| `state_context_effect_tone` | `#0f766e` | `#ccfbf1` | State-machine context update cards. |
| `entity_resource_tone` | `#15803d` | `#f0fdfa` | Entity-type resource cards. |
| `schema_resource_tone` | `#7c3aed` | `#f5f3ff` | Reusable schema resource cards. |
| `authorization_policy_tone` | `#c2410c` | `#fff7ed` | Access-policy and authorization-check cards. |

## Deprecated Name Migration

The following names should be treated as migration aliases only. New code, docs, and tests should use the canonical chart-owned terms.

| Deprecated/current name | Canonical replacement | Reason |
| --- | --- | --- |
| `graphviz_diagram` | `chart_svg_artifact` | Names the generated SVG evidence artifact rather than the renderer technology alone. |
| `dot_graph` | `chart_dot_source` | Keeps DOT source separate from SVG artifact. |
| `state_machine_diagram` | `state_machine_chart` | Uses one artifact-family suffix. |
| `composition_diagram` | `state_composition_chart` | Qualifies composition by state-machine state scope. |
| `command_query_flow_diagram` | `command_flow_chart` and `query_flow_chart` | Keeps state-changing and read-only behavior aligned with separate source domains. |
| `card_title` | `chart_card_title` | Makes the term chart-owned. |
| `card_subtitle` | `chart_card_role` | Avoids subtitle ambiguity and names the visual role line. |
| `card_rationale` | `chart_card_rationale` | Makes the term chart-owned. |
| `card_section` | `chart_card_section` | Makes the term chart-owned. |
| `typed_field_row` | `chart_schema_field_row` | Names the JSON Schema-derived visual row role. |
| `transition_field_row` | `chart_transition_field_row` | Makes the term chart-owned. |
| `reference_field_row` | `chart_reference_field_row` | Makes the term chart-owned. |
| `flow_edge` | `chart_edge` plus a specific edge role | Separates visual connector from semantic edge function. |
| `invisible_order_edge` | `chart_layout_edge` | Clarifies this is layout-only and not evidence. |
| `state_card` | `state_machine_state_card` | Aligns with the source state-machine domain. |
| `transition_signal_card` | `state_machine_trigger_card` | Aligns with the source trigger vocabulary and supports local/data-refresh triggers. |
| `mount_card` | `child_machine_mount_card` | Qualifies mount by composed child state-machine usage. |
| `emitted_local_signal_card` | `local_signal_emission_card` | Names the emission evidence carrier. |
| `sent_local_signal_card` | `local_signal_send_effect_card` | Distinguishes sync send effects from emitted local signals. |
| `context_update_card` | `state_context_update_card` | Qualifies context as state-machine context. |
| `external_interface_card` | `adapter_boundary_card` | Names the visual boundary rather than the source resource. |
| `target_tail_card` | `invocation_target_preview_card` | Clarifies that the card previews target details without expanding the full target chart. |
| `response_card` | `invoked_outcome_response_card` or `adapter_ingress_response_card` | Preserves the source distinction between invoked-outcome response and adapter ingress response. |
| `authorization_gate_card` | `authorization_check_card` | Avoids gate ambiguity with workflow gateways. |
| `resource_card` | `entity_resource_card` or `schema_resource_card` | Avoids generic resource ambiguity with access-policy resources. |
| `outcome_card` | `behavior_outcome_card` | Qualifies outcome by behavior flow usage. |
| `emitted_domain_event_card` | `domain_event_emission_card` | Names the emission evidence rather than the source resource alone. |
| `right_arrow_symbol` | `chart_sequence_glyph` | Uses glyph vocabulary for rendered text. |
| `assignment_arrow_symbol` | `chart_binding_source_glyph` | Uses glyph vocabulary for rendered text. |
| `typed_field_spacing` | `chart_type_spacing` | Makes the spacing convention chart-owned. |
| `reference_prefix_symbol` | `chart_reference_prefix_witness` | Treats prefixes as visible audit witnesses. |
| `signal_prefix_symbol` | `chart_signal_prefix_witness` | Treats signal prefixes as visible audit witnesses. |
| `external_interface` tone | `adapter_boundary_tone` | Avoids bare source-resource naming in tone roles. |
| `initial_state` tone | `state_entry_tone` | Names the visual entry-state distinction. |
| `neutral` tone | `neutral_structure_tone` | Clarifies visual fallback/ordinary structure role. |
| `boundary` tone | `adapter_input_tone` | Qualifies boundary-facing input usage. |
| `target` tone | `invocation_target_tone` | Qualifies target by invocation evidence. |
| `success_exit` tone | `success_outcome_tone` | Aligns success styling with outcome/response/disposition usage. |
| `failure_exit` tone | `failure_outcome_tone` | Aligns failure styling with outcome/response/disposition usage. |
| `product_behavior` tone | `behavior_card_tone` | Avoids conflating command/query behavior with all product concepts. |
| `domain_event` tone | `durable_event_tone` | Avoids bare source-resource naming while preserving durable-event meaning. |
| `state_machine` tone | `child_machine_tone` | Clarifies this tone is for mounted child machine cards. |
| `workflow` tone | `workflow_control_tone` and `local_signal_sync_tone` | Splits workflow control from local-signal synchronization. |
| `local_signal` tone | `local_signal_card_tone` | Makes the tone role visual. |
| `context` tone | `state_context_effect_tone` | Qualifies state-machine context update usage. |
| `entity_type` tone | `entity_resource_tone` | Avoids bare source-resource naming in tone roles. |
| `schema` tone | `schema_resource_tone` | Avoids bare source-resource naming in tone roles. |
| `policy` tone | `authorization_policy_tone` | Qualifies access-policy/authorization visual usage. |

## New Chart Vocabulary Checklist

Before adding a chart-owned term, verify that:

1. The term names a visual carrier, visual role, diagram family, row, edge, glyph, visible witness, layout mechanic, or tone role.
2. The term does not exactly match a canonical source-ontology term.
3. The term is qualified by visual role, source domain, or chart layer when it displays a source concept.
4. The term is not a synonym for an existing chart-owned term.
5. The term maps to exactly one source domain or is explicitly renderer-only.
6. Edge labels and card section labels remain visible source witnesses rather than becoming independent chart terms.
7. Tone roles carry a reviewable distinction and are not merely decorative color names.
8. Generated artifact paths, function names, tests, and documentation are updated to the canonical spelling.
