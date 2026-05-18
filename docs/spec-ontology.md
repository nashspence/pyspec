# Spec Ontology

This glossary is the vocabulary contract for the authored-source, layer-pruned authored-source, and compiled-output schemas. The authored schema describes sparse human-authored input. Layer-pruned authored schemas are generated from the same source schema and hide sections outside the active authoring layers. The compiled schema describes normalized output in `spec/generated/compiled/spec.yaml`, including generated references, derived domain events, derived HTML routes, endpoint expansions, and expanded empty-collection states.

## Terminology Boundaries

- `domain_event`: a durable product/domain occurrence that happened. Domain events are emitted by successful command or lifecycle-transition outcomes and may serve as workflow inputs.
- `integration_message`: a wire-level AsyncAPI message in `integration_messages.asyncapi.yaml`. It carries a domain-event payload over a channel, but it is not state-machine vocabulary.
- `local_signal`: a state-machine-local trigger or emitted signal. Local signals may be accepted by transitions, emitted by transitions, and synced between mounted child state-machine instances.
- `data_refresh_signal`: a state-machine-local data refresh or invalidation signal, commonly consumed by `query_binding.load.refresh_on`.

Bare `event` is avoided for durable domain occurrences because CloudEvents and UML/state-machine terminology also use that word. Bare `message` is avoided in state machines because AsyncAPI uses message for transport exchange.

## Top-Level Resource Kinds

- <!-- top-level:entity_types --> `entity_types`: collection-prefixed stable product/domain entity type ids such as `entity_type.project`, each with a PascalCase display/type `name` such as `Project`, fields, and optional `entity_lifecycle` declarations. Entity types are not ORM types, API contracts, generated implementation classes, or storage schemas.
- <!-- top-level:schemas --> `schemas`: first-class reusable JSON Schema payload or object schemas referenced with `schema.*` ids.
- <!-- top-level:commands --> `commands`: state-changing product behavior with `input_schema`, optional authorization, explicit `entity_changes`, outcomes, and `emits_domain_events`.
- <!-- top-level:queries --> `queries`: read-only product behavior with `input_schema`, `result_schema`, and outcomes.
- <!-- top-level:domain_events --> `domain_events`: durable domain/application occurrences with payload_schema contracts and compiled emitters.
- <!-- top-level:workflows --> `workflows`: asynchronous or long-running flows with `inputs`, `steps`, `sequence_flows`, `outputs`, `retry_policies`, and `failure_handlers`.
- <!-- top-level:state_machines --> `state_machines`: UI/component state-machine contracts with `context_schema`, states, transitions, triggers, guards, local_effects, local signals, command bindings, and query bindings.
- <!-- top-level:external_interfaces --> `external_interfaces`: canonical external invocation declarations split into explicit adapter and invocation objects.
- <!-- top-level:access_policies --> `access_policies`: canonical access-control policies with `subject`, `resource`, `action`, `environment`, rules with per-rule `effect`, and `decision`.
- <!-- top-level:fixtures --> `fixtures`: named concrete seed data namespaces used by behavior scenarios, preconditions, assertions, content examples, and render examples.
- <!-- top-level:behavior_scenarios --> `behavior_scenarios`: formal BDD behavior scenarios with system_under_test_ref, given, when, and then contracts.
- <!-- top-level:media_assets --> `media_assets`: canonical content assets with media kind, asset role, placeholders, and source-backed resolution when present.
- <!-- top-level:text_resources --> `text_resources`: text resources used by state-machine slots and content-source projections.
- <!-- top-level:content_examples --> `content_examples`: named content-source examples for dynamic text and asset content.
- <!-- top-level:viewport_profiles --> `viewport_profiles`: canonical global HTML and Textual viewport profiles for audit/golden-image rendering.
- <!-- top-level:reference_index --> `reference_index`: canonical compiled-only index of generated references used by projections and tests.
- <!-- top-level:project --> `project`: the project slug for the specification workspace.
- <!-- top-level:preconditions --> `preconditions`: reusable entity_type presence/absence setup predicates; preconditions are not assertions, invariants, or broad domain rules.
- <!-- top-level:assertions --> `assertions`: reusable entity_type presence/absence expected predicates referenced by behavior-scenario `then.postconditions`; assertions are not setup predicates or invariants.

## ID Namespaces

- `asset_ref`: `asset.<domain>...`; asset declarations, generated asset slots, content examples, and audit evidence.
- `content_example_ref`: `content_example.<domain>...`; content source examples.
- `schema_ref`: `schema.<domain>...`; reusable typed payload schemas referenced through JSON Schema `$ref`.
- `data_refresh_signal_name`: local state-machine data-refresh signal name; authored sources do not use global-looking `data_refresh_signal.*` references for local refresh signals.
- `external_interface_ref`: `external_interface.<domain>...`; external-interface declarations, delegated external-interface invocations, and behavior-scenario `open_external_interface` or `call_external_interface` stimuli.
- `domain_event_ref`: `domain_event.<domain>...`; durable domain-event declarations, command emissions, workflow inputs, and behavior-scenario domain-event assertions.
- `precondition_ref`: `precondition.<domain>...`; named setup predicates referenced through `precondition_use.ref`.
- `assertion_ref`: `assertion.<domain>...`; named expected predicates referenced through `assertion_use.ref`.
- `fixture_ref`: `fixture.<domain>...`; seed data fixtures used by behavior scenarios, content examples, preconditions, assertions, and render examples.
- `feature_tag`: unprefixed dotted feature grouping label used by behavior scenarios and generated feature files; it is not a typed reference.
- `instance_id`: local child state-machine instance id within a composed state.
- `local_signal_name`: local state-machine signal name; authored sources do not use global-looking `local_signal.*` references for local signals.
- `entity_type_ref`: `entity_type.<domain>...`; stable product/domain entity type id. The entity type object carries a separate PascalCase `name` for display/type naming.
- `command_ref`: `command.<domain>...`; state-changing command declarations, state-machine command bindings, workflow steps, external-interface command invocations, and behavior-scenario command assertions.
- `query_ref`: `query.<domain>...`; read-only query declarations, state-machine query bindings, external-interface query invocations, and behavior-scenario query assertions.
- `command_binding_id`: local state command binding name; authored sources do not use global-looking `command_binding.*` references for local invocation keys.
- `query_binding_id`: local state-machine or state query binding name; authored sources do not use global-looking `query_binding.*` references for local invocation keys.
- `region_id`: local HTML layout region id within one state.
- `access_policy_ref`: `access_policy.<domain>...`; access-control policy declarations, `command.authorization.policy`, external-interface `access_policy` fields, generated access-policy projections, and authorization test assertions.
- `viewport_profile_ref`: `viewport_profile.<domain>...`; named HTML/Textual viewport profiles.
- `rule_id`: local state-machine signal-sync rule id within one composed state.
- `state_machine_ref`: `state_machine.<domain>...`; state-machine declarations, `child_state_machines`, state-machine external-interface invocations, and behavior-scenario state-machine assertions.
- `behavior_scenario_ref`: `behavior_scenario.<domain>...`; formal behavior-scenario declarations and generated feature tags.
- `text_ref`: `text.<domain>...`; text resource declarations, generated text slots, content examples, and content source signatures.
- `container_id`: local Textual layout container id within one state.
- `viewport_id`: local viewport id within `html_viewports` or `textual_viewports`.
- `workflow_ref`: `workflow.<domain>...`; workflow declarations, workflow external-interface invocations, and generated workflow references.
- Generated references use `asset`, `access_policy`, `cli_command`, `cli_response_handler`, `endpoint`, `external_interface_delegate`, `external_interface_invocation`, `local_signal_raise`, `command_binding`, `command_binding_local_outcome_effect`, `query_binding`, `query_binding_local_outcome_effect`, `route`, `adapter_response_binding`, `screen`, `state_machine`, `surface`, `text`, and `workflow` buckets in compiled `reference_index`.

## Reference Types

- `system_under_test_ref`: exactly one typed reference to the resource under test: `external_interface`, `domain_event`, `command`, `query`, `state_machine`, or `workflow`.
- `given`: setup contract split into `seed_fixtures` and `preconditions`.
- `when`: BDD behavior-scenario stimulus only: `open_external_interface`, `call_external_interface`, `invoke_command`, `invoke_query`, or `emit_domain_event`.
- `then`: assertions for `outcome`, entity existence, emitted/not-emitted domain events, workflow execution, authorization decisions, responses, invoked/enabled/access_denied commands or queries, state-machine state, and `postconditions`. Compiled state-machine assertions may add `surface`, `composition`, and top-level `requires`.
- `then.requires`: compiled-only derived projection dependencies for a state-machine assertion, split into `surfaces`, `text`, `assets`, `query_bindings`, and `command_bindings`.
- `external_interface_adapter`: exactly one adapter object: `http_api`, `cli`, `webhook`, `scheduled`, `worker`, or `html_route`.
- `adapter input shape`: HTTP API input may use `path_params`, `query_params`, and `body`; HTML route input may use `path_params` and `query_params`; CLI input uses `args`; worker input uses `payload`; webhook input may use `path_params`, `query_params`, and `payload`; scheduled input has no external input sections.
- `external_interface_invokes`: exactly one invocation object: `command`, `query`, `state_machine`, `workflow`, or `external_interface`.
- `external_interface_invocation_bindings`: top-level `input_mapping.bindings` binds adapter input into command input, query input, state-machine context, or workflow input and must exactly cover the invoked fields.
- `state-machine external-interface invocation`: `invokes.state_machine` must declare `renderer: html` or `renderer: textual`. HTML route external interfaces can invoke only `html`; CLI external interfaces can launch `html` or `textual`; the invoked state machine must declare the selected renderer in at least one state.
- `workflow external-interface invocation`: `invokes.workflow.ref` names the workflow and `input_mapping.bindings` binds adapter input into workflow input fields.
- `external-interface delegation`: an external interface whose `invokes.external_interface.ref` points at another external interface. `input_mapping.delegated_input` binds adapter input into the delegated external-interface adapter input shape. Delegation is general and is not CLI-to-HTTP-specific.
- `delegating external interface`: the outer external interface whose adapter exposes a facade and binds its input into the delegated external-interface input shape.
- `delegated external interface`: the inner external interface that receives delegated invocation. Its `access_policy` and the delegated command/query authorization outcomes remain visible to the delegating external interface.
- `invoked outcome response`: synchronous adapter response keyed by command, query, workflow, state-machine, or delegated external-interface outcome names. HTTP API `responses` and delegated CLI `response_handlers` are invoked-outcome response surfaces.
- `adapter ingress response`: asynchronous adapter acknowledgement or disposition keyed by adapter-level outcomes, such as accepted, malformed, retry, reject, or dead-letter handling. Worker, webhook, and scheduled adapters use `ingress_responses` when receipt/disposition is distinct from invoked workflow execution outcomes.
- `response handler`: adapter-specific projection of an invoked or delegated response outcome.
- `CLI response handler`: maps a named response outcome to stdout, stderr, an exit code, and optionally a retry policy. It does not restate HTTP status classification when the delegated external interface is an HTTP API.
- `retry_safe`: explicit command or external-interface marker permitting automatic retry of delegated, command, transition, or workflow execution. The default is false. Queries are retry-safe by definition.
- `retry safety`: validation that a retry policy applies only to a retry-safe delegated external interface and final invocation, a query, an explicitly retry-safe command or external interface, or an ingress/disposition outcome where no invoked command has executed. Transport retry, ingress retry, workflow retry, and command retry are separate scopes.
- `workflow_sequence_flow`: exclusive workflow control-flow step via `next_step`, `complete_as`, `fail_as`, `retry_policy`, or `dead_letter_as`.
- `state-machine context schema`: local machine context declared as JSON Schema object `properties` and `required`. Nullability uses JSON Schema type arrays such as `type: [string, null]`; local_effects may set a context field to null only when that field schema allows null.
- `context_present`: state-machine condition meaning the declared context field is present and non-null. Nullable context fields with a current `null` value are not present for this condition.
- `selected.condition`: child state-machine selected-state guard. It uses state-machine condition vocabulary and does not reuse BDD `when`.
- `signal_sync_rule.trigger`: child state-machine local-signal source that starts a signal synchronization rule. It does not reuse BDD `when`.
- `viewport_profile`: global audit/golden-image viewport map. Renderable state machines require at least one viewport profile, and profiles must include viewport sets for each declared renderer surface (`html_viewports` for HTML, `textual_viewports` for Textual).
- `render example`: state-local visual evidence input. It supplies seed fixtures, optional context, optional precondition references, and, for composed states, an exact child instance state vector; it never names viewport profiles directly.
- `content source`: a final resolver declaration where `text_resource.source_ref` or `asset.source_ref` equals the resource id. Final content resolvers require at least one matching `content_example`, and example args must exactly match the resource args.
- `rationale`: bounded plain text used on authored resources and on intentionally unobservable local effects. Missing top-level resource rationale is filled by a deterministic compiler default.
- `Command binding`: local state use of a global command, normally user-triggered, including `input_mapping` and local_effects. A renderer control binds to this local invocation, not directly to `command_ref`.
- `Query binding`: local state-machine or state use of a query for data loading or refresh, including `input_mapping`, load policy, context updates, result binding, and local_effects. State-machine-level queries load with `on_start`/`on_mount`; state-level queries load with `on_enter`.
- `Query binding local_effect`: each query `local_outcome_effect` must update context, bind/cache a result, raise a local signal, or explicitly declare a scoped `no_local_effect`. `result_binding.data_key` names the state-machine/state result data populated from a binding value.
- `Query refresh signal`: local data-refresh signal raised by a mutation, query outcome, or other invalidation `local_effect`, such as `project_changed`, and consumed by `query_binding.load.refresh_on`. Loaded/missing/error data-refresh signals should come from query outcomes after data has actually been bound or classified.
- `Empty/non-empty query handling`: array-valued query outcomes split the local_outcome_effect with `conditional_local_effects` using `result_condition: empty` and `result_condition: non_empty`. Both branches must be declared so empty collection states are reachable through authored handling rather than compiler length guesses.
- `Machine-scoped query ownership`: state-machine-level query bindings declare `result_scope: local`, `shared`, or `prefetch`. Machine-scoped result bindings that do not raise a signal must use shared/prefetch ownership with rationale, especially when a child machine also owns visible loading.
- `Field-slot source resolution`: every field slot resolves to exactly one context field or query result binding. A bound entity_type or array item can feed field slots when the slot name exists on the result type; ambiguous or missing sources fail semantic validation.
- `local_outcome_effect`: mapping from a command/query-binding outcome to context updates, result binding, a local signal raise, or explicit `no_local_effect` handling.
- `No local effect`: explicit declaration that an outcome is covered but intentionally has no local state-machine effect. It is not omission and does not suppress durable domain events. Reasons are scope-sensitive: response-surface handling needs a real adapter/renderer surface, query refresh needs explicit result/context refresh, result-bound-without-signal needs result binding or context/cache update, and failure outcomes must use proven response-surface handling or `intentionally_unobservable` with rationale.
- `Authored value`: explicit literal-or-fixture-reference value used in authored test, precondition, content-example, and render-example value maps. Use `{value: ...}` for JSON literals, including literal strings beginning with `$`, and `{from: $fixture...}` for fixture references. Raw `$...` strings are not interpreted as references.
- `Binding root`: the first segment of a binding expression. Local state-machine bindings use `$state_context`, `$principal`, `$signal.payload`, and `$state_machine`; command domain-event payload mappings use `$command_input` and `$command_outcome`; external-interface response mappings use `$invocation_outcome`; adapter/delegation bindings use `$adapter_input` and `$adapter_response`; workflow step bindings use `$workflow_input` and `$step_outcome`. `$message` is reserved for AsyncAPI/wire-level messages, not local state-machine signaling.
- `Actor/user binding source`: local command bindings should bind actor-like input fields such as `actor_id`, `approved_by`, or `reviewer_id` from `$principal.id` or an explicit context source. Literal actor/user ids are linted because they usually hide fixture-only assumptions in authored UI behavior.
- `Local signal raise`: creation of a state-machine-local `local_signal` or `data_refresh_signal`.
- `Data refresh signal`: local state-machine signal commonly used for data refresh, invalidation, loaded/missing states, or render updates. Data-refresh signals are not sent between child state-machine instances.
- `Local signal`: local state-machine signal that may also be sent between child state-machine instances where sync rules support local-signal sends.
- `Domain event`: durable domain occurrence emitted by a command outcome, distinct from local state-machine signals and AsyncAPI integration messages.
- `Integration message`: AsyncAPI transport-level message projected from a domain event into a channel.
- `emits_domain_events`: command-level durable domain-event emission mapping keyed by successful command outcome. It is not used for local state-machine transition local_effects.
- `command_binding.local_effects.raise`: local state-machine `local_signal` or `data_refresh_signal` raise after a user command binding.
- `query_binding.local_effects.raise`: local state-machine `local_signal` or `data_refresh_signal` raise after a query load or refresh outcome.
- `no_local_effect`: explicit declaration that a command-binding or query-binding outcome has no local state-machine effect.
- `local_signals`: local UI/component/state-machine signal contracts split into accepted `local_signals`/`data_refresh_signals` maps and emitted `local_signals` maps with JSON Schema `payload_schema` declarations.
- `renderer_contracts`: state renderer declarations keyed by concrete renderer surface. `renderers.html` and `renderers.textual` each own renderer-local `layout`, `presentation`, and `style`.
- `renderer placement validation`: HTML slots and child machines must reference declared HTML `region_id`s; Textual widgets and child machines must reference declared Textual `container_id`s. Placement ids are layout ids, not field names.
- `resolver output escaping`: text, SVG, XML, and HTML resolvers must escape dynamic values before placing them in markup text or attributes. Plain-text outputs and alt text must not expose unescaped markup-sensitive values where they may be rendered into HTML/XML.
- `schema`: JSON Schema subset used for payloads, entity types, command inputs/results, query inputs/results, state-machine context, content args, and adapter input sections. It uses `type`, `$ref`, `properties`, `required`, `enum`, `const`, `items`, `additionalProperties`, and `format`; null is represented through JSON Schema type arrays such as `type: ["string", "null"]`.
- `access_policy`: direct `access_policy_ref` fields identify the access policy applied to an external interface or authorization assertion. Commands use `authorization.policy` plus explicit `authentication_required_as` and `access_denied_as` outcome mappings.
- `command_authorization`: command-local access-policy mapping with `policy`, `authentication_required_as`, and `access_denied_as`. The mapped names must be normal command outcomes with `kind: failure`.
- `access policy`: reusable rule set that determines whether `subject` may attempt `action` on `resource` under `environment`. Policies with identical `subject`, `action`, rule `effect` values, `environment`, and `rules` should be one `access_policy`, not duplicated per command or external interface.
- `authorization failure outcome`: named failure outcome produced before command execution when authorization fails. These outcomes live in `command.outcomes`; they are not a separate `errors` or `authorization_outcomes` collection.
- `authentication_required`: authorization failure where no acceptable subject identity is available. HTTP examples conventionally map this outcome to `401`; CLI examples map it to stderr plus a nonzero exit code.
- `access_denied`: authorization failure where a subject identity exists but does not satisfy the access policy. HTTP examples conventionally map this outcome to `403`; CLI examples map it to stderr plus a nonzero exit code.
- `domain failure outcome`: command outcome produced by command execution or domain validation, such as `validation_failed` or `not_found`.
- `transition applicability`: lifecycle source-state check derived from `entity_type.entity_lifecycle.lifecycle_transitions[*]`, not authorization.
- `transition_not_allowed`: transition applicability/domain failure outcome for lifecycle source-state mismatch. It is not an authorization failure and should be asserted with `command_outcome` or `external_interface_response`, not `authorization_denial`.
- `rule.entity_state_condition`: explicit author-authored access-control rule when an entity lifecycle state is truly part of who may attempt a command. The compiler does not generate this rule from lifecycle transition `from` states; lifecycle source-state mismatch remains transition applicability and maps to `transition_not_allowed`.

## Command Binding Example

```yaml
states:
  ready:
    command_bindings:
      approve:
        command: command.project.approve
        input_mapping:
          project_id:
            from: $state_context.project_id
        local_effects:
          approved:
            raise:
              data_refresh_signal: project_changed
          transition_not_allowed:
            raise:
              local_signal: show_transition_not_allowed
              payload_bindings:
                message:
                  from: $command_outcome.result.message
          access_denied:
            no_local_effect:
              reason: handled_by_response_surface
              rationale: The response surface reports authorization failure.
```

## Query Invocation Example

```yaml
query_bindings:
  load_project:
    query: query.project.read
    input_mapping:
      project_id:
        from: $state_context.project_id
    load:
      on_enter: true
      refresh_on:
      - data_refresh_signal: project_changed
    local_effects:
      found:
        result_binding:
          data_key: project
          from:
            from: $query_outcome.result
        context_updates:
          project_id:
            from: $query_binding.input.project_id
        raise:
          data_refresh_signal: project_loaded
      not_found:
        raise:
          local_signal: show_project_not_found
      unavailable:
        no_local_effect:
          reason: intentionally_unobservable
          rationale: The query result is not shown while the current view keeps its existing data.
```

## Collection Query Handling

```yaml
query_bindings:
  list_projects:
    result_scope: local
    query: query.project.list
    input_mapping:
      workspace_id:
        from: $state_context.workspace_id
    local_effects:
      listed:
        conditional_local_effects:
        - result_condition: empty
          result_binding:
            data_key: projects
            from:
              from: $query_outcome.result
          raise:
            data_refresh_signal: project_collection_empty
        - result_condition: non_empty
          result_binding:
            data_key: projects
            from:
              from: $query_outcome.result
          raise:
            data_refresh_signal: projects_loaded
```

## Authoring Layers

Layers are compile/validate guardrails and are not written into `spec/generated/compiled/spec.yaml`.

- `core`: `fixtures`, `preconditions`, `assertions`, `schemas`, `entity_types`, `access_policies`, `commands`, `queries`, `domain_events`, and `behavior_scenarios`.
- `http`: HTTP API external-interface adapters.
- `eventing`: webhook external-interface adapters and AsyncAPI integration-message projections.
- `workflow`: `workflows` plus CLI, worker, and scheduled external-interface adapters.
- `ui`: `state_machines`, `text_resources`, `media_assets`, `content_examples`, `viewport_profiles`, and HTML route external-interface adapters.
- `html`: HTML renderer contracts and `viewport_profiles.*.html_viewports`.
- `textual`: Textual renderer contracts and `viewport_profiles.*.textual_viewports`.
- Layer normalization always includes `core`; selecting `html` or `textual` also includes `ui`. Aliases normalize as `api -> http`, `cli -> workflow`, `tui -> textual`, and `all`/`full` -> every layer.
- Common layer-pruned authored schemas are generated for `core`, `core_http`, `core_eventing`, `core_workflow`, `core_ui_textual`, `core_ui_html`, and `full`.

## Binding Roots

| Context | Valid roots |
| --- | --- |
| Command binding `input_mapping` | `$state_context`, `$principal` |
| Command binding local_effects | `$command_outcome`, `$command_binding`, `$state_context` |
| Query binding `input_mapping` | `$state_context`, `$principal` |
| Query binding local_effects | `$query_outcome`, `$query_binding`, `$state_context` |
| State-machine transition local_effects | `$signal.payload`, `$state_context` |
| Child state-machine `context_bindings` and `selected.condition` guards | `$state_machine` for parent state-machine context |
| Command domain-event-emission payload mappings | `$command_input`, `$command_outcome` |
| External-interface command/query/state-machine/workflow invocation mappings | `$adapter_input` |
| External-interface delegation mappings | `$adapter_input` |
| HTTP API response bodies | `$invocation_outcome.result` only |
| CLI command/query response handlers | `$adapter_input`, `$invocation_outcome` |
| CLI delegated response handlers | `$adapter_input`, `$adapter_response` |
| Workflow step `input_mapping` | `$workflow_input`, `$step_outcome` |
| Authored test/precondition/assertion/content-example/render-example value maps | `$fixture` |

## Visual Audit Coverage

- `visual_evidence_set`: a shared list of generated diagrams or rendered captures (`*.svg` diagrams/captures and `*.png` screenshots) that visually evidence one or more compiled spec paths.
- `required_visual_path`: a compiled spec leaf path that must have at least one `visual_evidence_set`; missing required paths fail validation.
- `required_visual_text_witness`: a stable token that must appear in visible SVG text for a required visual path whose value is explicitly rendered as text. These witnesses are intentionally limited to durable ids, references, field/type labels, and other renderer-owned tokens; they do not audit hidden SVG metadata, incidental prose, or render-only pixels.
- `optional_visual_path`: a compiled spec leaf path that may have visual evidence but is allowed to be absent from diagrams and render captures.
- `missing_required_visual_path`: a required visual path with no diagram or render-capture evidence.
- `optional_visual_path_not_shown`: an optional visual path with no diagram or render-capture evidence; this is reported but does not fail validation.
- `non_visual_path`: compiled metadata that is intentionally outside visual-audit scope, such as `project` workspace metadata or the compiled `reference_index`.
- `render_presence`: resource-level visibility in actual render captures, reported as `rendered` or `not_rendered` for assets, text resources, fixtures, preconditions, assertions, and content examples.

Audit validation fails when any `missing_required_visual_path` exists or when a declared `required_visual_text_witness` is absent from its SVG evidence set. Required paths without a text witness are still required to have diagram or render-capture evidence, but their semantics are audited through the visual artifact rather than a machine-readable token.

The visual audit includes state-machine and composition diagrams, external-interface and workflow flowcharts, plus command/query flows. Command/query flows are chronological branching data flows for input, authorization, touched resources, outcomes, and emitted domain events; other diagrams reference commands and queries compactly instead of repeating the same cards.

## Binding Expression Namespaces

- `$fixture.<path>` reads merged seed fixture data in behavior scenarios, preconditions, assertions, content examples, and render examples.
- `$state_machine.<field>` reads parent state-machine context in child state-machine context bindings and composition guards.
- `$signal.payload.<field>` reads the current state-machine local-signal payload in transition local_effects and sync sends.
- `$state_context.<field>` reads current state-machine context in transition local_effects, command/query binding input mappings, and local_outcome_effect signal payload mappings.
- `$adapter_input.path_params.<field>` reads HTTP API or HTML route path parameters in external-interface invocation or delegation bindings.
- `$adapter_input.query_params.<field>` reads HTTP API or HTML route query parameters in external-interface invocation or delegation bindings.
- `$adapter_input.body.<field>` reads HTTP request body fields in external-interface invocation or delegation bindings.
- `$adapter_input.args.<field>` reads CLI argument fields in external-interface invocation or delegation bindings.
- `$adapter_input.payload[.<field>]` reads worker or webhook payload data in external-interface invocation mappings.
- `$command_input.<field>` reads command input during command domain-event emission mapping and command-scoped access-policy rules.
- `$command_outcome.result[.<field>]` reads command outcome result during domain-event emission and command-binding `local_effects` mapping.
- `$command_outcome.kind` reads the command outcome kind during command-binding `local_effects` payload mappings.
- `$query_outcome.result[.<field>]` reads query outcome result during query-binding `local_effects` mapping.
- `$query_outcome.kind` reads the query outcome kind during query-binding `local_effects` payload mappings.
- `$invocation_outcome.result[.<field>]` reads command or query outcome result during external-interface response mapping.
- `$command_binding.input.<field>` reads the bound command input during command-binding local_effects.
- `$query_binding.input.<field>` reads the bound query input during query-binding local_effects.
- `$adapter_response.body[.<field>]` reads the delegated external-interface response body inside delegating CLI `response_handlers`.
- `$workflow_input.payload[.<field>]` reads workflow input payload.
- `$step_outcome.<step>.<outcome>.result[.<field>]` reads previous workflow step result.

Binding expressions appear inside binding objects. Authored value maps use `{from: ...}` for these expressions and `{value: ...}` for literal JSON values; a raw string beginning with `$` is a literal only when wrapped with `value`.
- The shared grammar is `$source.path.to.field`; semantic validation checks available roots and declared field paths for each context.

## Generated Artifacts

- `spec/generated/compiled/spec.yaml`: compiled-output spec with normalized IDs, generated reference_index entries, derived domain events, and expanded empty collections.
- `spec/generated/agent_prompts/{pm_design,test,dev,review}.md`: layer-specific role prompts.
- `spec/generated/behavior/fixtures.yaml`: seed fixture projection.
- `spec/generated/behavior/behavior_scenarios.yaml`: semantic behavior-scenario projection.
- `spec/generated/product_interfaces/http.openapi.yaml`: OpenAPI projection generated only from HTTP API external interfaces.
- `spec/generated/product_interfaces/integration_messages.asyncapi.yaml`: AsyncAPI projection for durable top-level domain events, webhooks, workers, and domain-event-input workflows; state-machine signals are not projected as domain events.
- `spec/generated/product_interfaces/html.routes.json`: UI route projection generated from HTML route external interfaces.
- `spec/generated/product_interfaces/html.state_machines.json`: state-machine HTML/Textual renderer contract projection, including composition layout and renderer-specific style contracts.
- `spec/generated/product_interfaces/textual.projection.py`: Textual renderer projection generated from `renderers.textual.presentation` widgets, `renderers.textual.style`, and `renderers.textual.layout` containers.
- `spec/generated/product_interfaces/workflow.cwl.yaml`: CWL projection generated for workflow/CLI/worker-relevant execution graphs.
- `spec/generated/product_interfaces/access_policies.json`: access-policy projection with command authorization mappings and external-interface policies.
- `spec/generated/content_resolvers/{signatures.py,stubs.py,examples.yaml}`: documented content-resolution contracts and examples.
- `spec/generated/test_adapters/python_refs.py`: Python constants for resource and generated reference IDs.
- `spec/generated/test_adapters/driver_protocol.py`: BDD driver protocol.
- `spec/generated/test_adapters/pytest_bdd_steps.py`: BDD step glue.
- `spec/generated/test_adapters/pytest_bdd_features/{feature}.feature`: generated behavior feature files.
- `spec/generated/audit_evidence/external_interfaces/{adapter}/{external_interface}/flow.svg`: external-interface flow diagrams grouped by adapter kind.
- `spec/generated/audit_evidence/coverage.yaml`: generated visual coverage index mapping compiled spec paths to diagram and render-capture evidence, including explicit render coverage gaps for assets, text, fixtures, preconditions, assertions, and content examples.
- `spec/generated/audit_evidence/workflows/{workflow}/flow.svg`: workflow flow diagrams.
- `spec/generated/audit_evidence/commands/{command}/flow.svg`: chronological command flows showing input, authorization, touched resources, outcomes, and emitted domain events.
- `spec/generated/audit_evidence/queries/{query}/flow.svg`: chronological query flows showing input, authorization, results, and outcomes.
- `spec/generated/audit_evidence/state_machines/{state_machine}/state_machine.svg`: state-machine diagrams.
- `spec/generated/audit_evidence/state_machines/{state_machine}/states/{state}/composition.svg`: composed state-machine state diagrams.
- `spec/generated/audit_evidence/state_machines/{state_machine}/states/{state}/{text.yaml,fixtures.yaml,assets/*}`: state-scoped audit inputs.
- `spec/generated/audit_evidence/state_machines/{state_machine}/states/{state}/renders/*`: HTML/Textual state render source and captures.
- `spec/generated/audit_evidence/state_machines/{state_machine}/states/{state}/render_examples/{render_example}/**`: render-example scoped inputs and render captures.

## Schema Definition Inventory

Each `$defs` entry in the JSON Schemas is documented exactly once here. The schema-inventory test treats these hidden markers as the authoritative inventory.

- <!-- schema-def:aria_role --> `$defs/aria_role`: renderer contract component scoped to HTML and/or Textual invocations.
- <!-- schema-def:asset_placeholder --> `$defs/asset_placeholder`: shared schema component used by authored source or compiled output.
- <!-- schema-def:asset_ref --> `$defs/asset_ref`: typed reference definition for its namespace.
- <!-- schema-def:viewport_profile_ref --> `$defs/viewport_profile_ref`: typed reference definition for its namespace.
- <!-- schema-def:authored_asset --> `$defs/authored_asset`: human-authored source object for this resource or nested contract.
- <!-- schema-def:authored_viewport_profile --> `$defs/authored_viewport_profile`: human-authored source object for this resource or nested contract.
- <!-- schema-def:authored_child_state_machine --> `$defs/authored_child_state_machine`: human-authored source object for this resource or nested contract.
- <!-- schema-def:authored_content_example --> `$defs/authored_content_example`: human-authored source object for this resource or nested contract.
- <!-- schema-def:authored_text_resource --> `$defs/authored_text_resource`: human-authored source object for this resource or nested contract.
- <!-- schema-def:authored_external_interface --> `$defs/authored_external_interface`: human-authored source object for this resource or nested contract.
- <!-- schema-def:authored_domain_event --> `$defs/authored_domain_event`: human-authored source object for this resource or nested contract.
- <!-- schema-def:authored_precondition --> `$defs/authored_precondition`: human-authored source object for this resource or nested contract.
- <!-- schema-def:authored_assertion --> `$defs/authored_assertion`: human-authored source object for this resource or nested contract.
- <!-- schema-def:authored_fixture --> `$defs/authored_fixture`: human-authored source object for this resource or nested contract.
- <!-- schema-def:authored_entity_type --> `$defs/authored_entity_type`: human-authored source object for this resource or nested contract.
- <!-- schema-def:authored_access_policy --> `$defs/authored_access_policy`: human-authored source object for this resource or nested contract.
- <!-- schema-def:access_policy_rule --> `$defs/access_policy_rule`: access-control rule containing a `condition` and formal access-policy `effect`.
- <!-- schema-def:authored_command --> `$defs/authored_command`: human-authored command with input_schema, authorization, entity_changes, outcomes, and emitted domain-event mappings.
- <!-- schema-def:authored_query --> `$defs/authored_query`: human-authored query with input_schema, result_schema, and outcomes.
- <!-- schema-def:authored_state_machine --> `$defs/authored_state_machine`: human-authored source object for this resource or nested contract.
- <!-- schema-def:authored_state --> `$defs/authored_state`: human-authored source object for this resource or nested contract.
- <!-- schema-def:authored_workflow --> `$defs/authored_workflow`: human-authored source object for this resource or nested contract.
- <!-- schema-def:rationale --> `$defs/rationale`: shared schema component used by authored source or compiled output.
- <!-- schema-def:child_state_machine_selected --> `$defs/child_state_machine_selected`: state-machine contract component.
- <!-- schema-def:cli_adapter --> `$defs/cli_adapter`: external-interface adapter, invocation, input, or response contract component.
- <!-- schema-def:cli_output --> `$defs/cli_output`: CLI response handler output text and bindings.
- <!-- schema-def:cli_response_handler --> `$defs/cli_response_handler`: CLI response handler for a named response outcome.
- <!-- schema-def:cli_response_handlers --> `$defs/cli_response_handlers`: map from named response outcomes to CLI response handlers.
- <!-- schema-def:context_condition --> `$defs/context_condition`: state-machine contract component.
- <!-- schema-def:content_args --> `$defs/content_args`: shared schema component used by authored source or compiled output.
- <!-- schema-def:content_example_ref --> `$defs/content_example_ref`: typed reference definition for its namespace.
- <!-- schema-def:content_source_ref --> `$defs/content_source_ref`: typed reference definition for its namespace.
- <!-- schema-def:context_bindings --> `$defs/context_bindings`: shared schema component used by authored source or compiled output.
- <!-- schema-def:context_set_local_effect --> `$defs/context_set_local_effect`: state-machine contract component.
- <!-- schema-def:external_interface_command_invocation --> `$defs/external_interface_command_invocation`: external-interface adapter, invocation, input, or response contract component.
- <!-- schema-def:external_interface_query_invocation --> `$defs/external_interface_query_invocation`: external-interface adapter, invocation, input, or response contract component.
- <!-- schema-def:external_interface_adapter --> `$defs/external_interface_adapter`: external-interface adapter, invocation, input, or response contract component.
- <!-- schema-def:external_interface_delegated_input_mapping --> `$defs/external_interface_delegated_input_mapping`: adapter-input-shaped bindings from a delegating external interface into a delegated external interface.
- <!-- schema-def:external_interface_delegate_invocation --> `$defs/external_interface_delegate_invocation`: external-interface invocation variant that delegates to another external interface.
- <!-- schema-def:external_interface_input_mapping --> `$defs/external_interface_input_mapping`: external-interface adapter input declarations and invocation input bindings.
- <!-- schema-def:external_interface_ref --> `$defs/external_interface_ref`: typed reference definition for its namespace.
- <!-- schema-def:external_interface_invokes --> `$defs/external_interface_invokes`: exactly one invoked command, query, state machine, workflow, or delegated external interface.
- <!-- schema-def:external_interface_output_mapping --> `$defs/external_interface_output_mapping`: external-interface adapter response, response-handler, or ingress-disposition mapping.
- <!-- schema-def:external_interface_response --> `$defs/external_interface_response`: external-interface adapter, invocation, input, or response contract component.
- <!-- schema-def:external_interface_response_value --> `$defs/external_interface_response_value`: external-interface adapter, invocation, input, or response contract component.
- <!-- schema-def:external_interface_responses --> `$defs/external_interface_responses`: external-interface adapter, invocation, input, or response contract component.
- <!-- schema-def:external_interface_retry_policy --> `$defs/external_interface_retry_policy`: bounded automatic retry policy for retry-safe delegated external interfaces.
- <!-- schema-def:external_interface_state_machine_invocation --> `$defs/external_interface_state_machine_invocation`: external-interface adapter, invocation, input, or response contract component.
- <!-- schema-def:external_interface_workflow_invocation --> `$defs/external_interface_workflow_invocation`: external-interface adapter, invocation, input, or response contract component.
- <!-- schema-def:domain_event_ref --> `$defs/domain_event_ref`: typed reference definition for its namespace.
- <!-- schema-def:precondition --> `$defs/precondition`: shared schema component used by authored source or compiled output.
- <!-- schema-def:precondition_ref --> `$defs/precondition_ref`: typed reference definition for its namespace.
- <!-- schema-def:precondition_use --> `$defs/precondition_use`: shared schema component used by authored source or compiled output.
- <!-- schema-def:assertion --> `$defs/assertion`: shared schema component used by authored source.
- <!-- schema-def:assertion_ref --> `$defs/assertion_ref`: typed reference definition for its namespace.
- <!-- schema-def:assertion_use --> `$defs/assertion_use`: shared schema component used by authored source or compiled output.
- <!-- schema-def:field_name --> `$defs/field_name`: shared schema component used by authored source or compiled output.
- <!-- schema-def:local_name --> `$defs/local_name`: local identifier contract component.
- <!-- schema-def:slot_name --> `$defs/slot_name`: local identifier contract component.
- <!-- schema-def:outcome_name --> `$defs/outcome_name`: local identifier contract component.
- <!-- schema-def:rule_id --> `$defs/rule_id`: local identifier contract component.
- <!-- schema-def:role_name --> `$defs/role_name`: local identifier contract component.
- <!-- schema-def:render_example_id --> `$defs/render_example_id`: local identifier contract component.
- <!-- schema-def:fixture_ref --> `$defs/fixture_ref`: typed reference definition for its namespace.
- <!-- schema-def:given --> `$defs/given`: shared schema component used by authored source or compiled output.
- <!-- schema-def:html_element --> `$defs/html_element`: HTML renderer contract component.
- <!-- schema-def:html_viewport --> `$defs/html_viewport`: HTML renderer contract component.
- <!-- schema-def:instance_id --> `$defs/instance_id`: shared schema component used by authored source or compiled output.
- <!-- schema-def:json_value --> `$defs/json_value`: shared schema component used by authored source or compiled output.
- <!-- schema-def:textual_layout_container --> `$defs/textual_layout_container`: Textual renderer contract component.
- <!-- schema-def:html_layout_region --> `$defs/html_layout_region`: HTML renderer contract component.
- <!-- schema-def:html_layout_root --> `$defs/html_layout_root`: HTML renderer contract component.
- <!-- schema-def:local_signal_name --> `$defs/local_signal_name`: state-machine-local signal identifier.
- <!-- schema-def:signal_sync_local_effect --> `$defs/signal_sync_local_effect`: state-machine signal synchronization contract component.
- <!-- schema-def:signal_sync_assertion --> `$defs/signal_sync_assertion`: state-machine signal synchronization contract component.
- <!-- schema-def:signal_sync_rule --> `$defs/signal_sync_rule`: state-machine signal synchronization contract component.
- <!-- schema-def:signal_sync_send_local_effect --> `$defs/signal_sync_send_local_effect`: state-machine signal synchronization contract component.
- <!-- schema-def:signal_sync_trigger --> `$defs/signal_sync_trigger`: state-machine signal synchronization contract component.
- <!-- schema-def:entity_type_ref --> `$defs/entity_type_ref`: typed reference definition for its namespace.
- <!-- schema-def:entity_type_display_name --> `$defs/entity_type_display_name`: PascalCase entity type display/type name separated from the stable `entity_type.*` id.
- <!-- schema-def:schema --> `$defs/schema`: JSON Schema subset used by payload, entity type, input, context, and reusable schema declarations.
- <!-- schema-def:command_authorization --> `$defs/command_authorization`: explicit command access policy and mapped authorization failure outcomes.
- <!-- schema-def:command_binding_id --> `$defs/command_binding_id`: local state command binding identifier.
- <!-- schema-def:command_domain_event_emit --> `$defs/command_domain_event_emit`: command-level domain-event emission mapping keyed by outcome.
- <!-- schema-def:command_entity_changes --> `$defs/command_entity_changes`: command entity-change summary containing creates, updates, deletes, or lifecycle_transition entries.
- <!-- schema-def:command_ref --> `$defs/command_ref`: typed reference definition for its namespace.
- <!-- schema-def:query_ref --> `$defs/query_ref`: typed reference definition for its namespace.
- <!-- schema-def:command_outcome --> `$defs/command_outcome`: command outcome without embedded domain-event emission metadata.
- <!-- schema-def:command_outcomes --> `$defs/command_outcomes`: map from outcome names to command outcomes.
- <!-- schema-def:query_outcome --> `$defs/query_outcome`: query outcome.
- <!-- schema-def:query_outcomes --> `$defs/query_outcomes`: map from outcome names to query outcomes.
- <!-- schema-def:access_policy_ref --> `$defs/access_policy_ref`: typed reference definition for its namespace.
- <!-- schema-def:python_class_name --> `$defs/python_class_name`: shared schema component used by authored source or compiled output.
- <!-- schema-def:python_identifier --> `$defs/python_identifier`: shared schema component used by authored source or compiled output.
- <!-- schema-def:query_binding_id --> `$defs/query_binding_id`: local state-machine or state query binding identifier.
- <!-- schema-def:query_binding_load_policy --> `$defs/query_binding_load_policy`: query binding load and refresh trigger policy.
- <!-- schema-def:query_result_condition --> `$defs/query_result_condition`: explicit query-result shape condition for empty/non-empty array handling.
- <!-- schema-def:query_result_binding --> `$defs/query_result_binding`: explicit query result binding to a named local `data_key`.
- <!-- schema-def:renderer_contracts --> `$defs/renderer_contracts`: renderer contract component scoped to HTML and/or Textual invocations.
- <!-- schema-def:binding_expression --> `$defs/binding_expression`: shared schema component used by authored source or compiled output.
- <!-- schema-def:binding_map --> `$defs/binding_map`: shared schema component used by authored source or compiled output.
- <!-- schema-def:binding_value --> `$defs/binding_value`: explicit binding value object using either `from` for binding expressions or `value` for literal JSON.
- <!-- schema-def:authored_value --> `$defs/authored_value`: explicit authored value object using either `from` for binding expressions or `value` for literal JSON.
- <!-- schema-def:scalar --> `$defs/scalar`: shared schema component used by authored source or compiled output.
- <!-- schema-def:authored_behavior_scenario --> `$defs/authored_behavior_scenario`: human-authored source object for this resource or nested contract.
- <!-- schema-def:system_under_test_ref --> `$defs/system_under_test_ref`: typed reference definition for its namespace.
- <!-- schema-def:behavior_scenario_ref --> `$defs/behavior_scenario_ref`: typed reference definition for its namespace.
- <!-- schema-def:scheduled_adapter --> `$defs/scheduled_adapter`: external-interface adapter, invocation, input, or response contract component.
- <!-- schema-def:slot_binding --> `$defs/slot_binding`: renderer contract component scoped to HTML and/or Textual invocations.
- <!-- schema-def:local_no_effect --> `$defs/local_no_effect`: explicit local no-effect outcome coverage contract component.
- <!-- schema-def:state_machine_command_binding --> `$defs/state_machine_command_binding`: state-machine command binding contract component.
- <!-- schema-def:state_machine_command_binding_local_outcome_effect --> `$defs/state_machine_command_binding_local_outcome_effect`: state-machine command binding local_outcome_effect contract component.
- <!-- schema-def:state_machine_command_binding_local_effects --> `$defs/state_machine_command_binding_local_effects`: state-machine command binding local_outcome_effect map.
- <!-- schema-def:state_machine_query_binding --> `$defs/state_machine_query_binding`: state-machine query binding contract component.
- <!-- schema-def:state_machine_query_conditional_local_effect --> `$defs/state_machine_query_conditional_local_effect`: conditional query local_effect branch with result-shape guard and normal query local_effects.
- <!-- schema-def:state_machine_query_binding_local_outcome_effect --> `$defs/state_machine_query_binding_local_outcome_effect`: state-machine query binding local_outcome_effect contract component.
- <!-- schema-def:state_machine_query_binding_local_effects --> `$defs/state_machine_query_binding_local_effects`: state-machine query binding local_outcome_effect map.
- <!-- schema-def:render_example --> `$defs/render_example`: state-machine contract component.
- <!-- schema-def:state_machine_signal_raise --> `$defs/state_machine_signal_raise`: state-machine local signal raise contract component.
- <!-- schema-def:state_machine_signal_trigger --> `$defs/state_machine_signal_trigger`: tagged local signal/data-refresh-signal trigger contract component.
- <!-- schema-def:state_machine_signal --> `$defs/state_machine_signal`: state-machine contract component.
- <!-- schema-def:state_query_binding --> `$defs/state_query_binding`: state query binding contract component.
- <!-- schema-def:state_machine_ref --> `$defs/state_machine_ref`: typed reference definition for its namespace.
- <!-- schema-def:state_machine_transition --> `$defs/state_machine_transition`: state-machine contract component.
- <!-- schema-def:text_ref --> `$defs/text_ref`: typed reference definition for its namespace.
- <!-- schema-def:textual_renderer_contract --> `$defs/textual_renderer_contract`: Textual renderer contract component.
- <!-- schema-def:textual_renderer_layout --> `$defs/textual_renderer_layout`: Textual renderer contract component.
- <!-- schema-def:textual_renderer_presentation --> `$defs/textual_renderer_presentation`: Textual renderer contract component.
- <!-- schema-def:textual_viewport --> `$defs/textual_viewport`: Textual renderer contract component.
- <!-- schema-def:textual_widget --> `$defs/textual_widget`: Textual renderer contract component.
- <!-- schema-def:then --> `$defs/then`: shared schema component used by authored source or compiled output.
- <!-- schema-def:schema_map --> `$defs/schema_map`: map from field or parameter names to JSON Schema fragments.
- <!-- schema-def:html_route_adapter --> `$defs/html_route_adapter`: HTML renderer contract component.
- <!-- schema-def:value_map --> `$defs/value_map`: shared schema component used by authored source or compiled output.
- <!-- schema-def:state_assertion --> `$defs/state_assertion`: state-machine contract component.
- <!-- schema-def:state_id --> `$defs/state_id`: state-machine contract component.
- <!-- schema-def:html_renderer_contract --> `$defs/html_renderer_contract`: HTML renderer contract component.
- <!-- schema-def:html_renderer_layout --> `$defs/html_renderer_layout`: HTML renderer contract component.
- <!-- schema-def:html_renderer_presentation --> `$defs/html_renderer_presentation`: HTML renderer contract component.
- <!-- schema-def:html_slot --> `$defs/html_slot`: HTML renderer contract component.
- <!-- schema-def:webhook_adapter --> `$defs/webhook_adapter`: external-interface adapter, invocation, input, or response contract component.
- <!-- schema-def:when --> `$defs/when`: shared schema component used by authored source or compiled output.
- <!-- schema-def:worker_adapter --> `$defs/worker_adapter`: external-interface adapter, invocation, input, or response contract component.
- <!-- schema-def:workflow_outcome --> `$defs/workflow_outcome`: workflow input, step, sequence-flow, retry, output, or binding contract component.
- <!-- schema-def:workflow_sequence_flows --> `$defs/workflow_sequence_flows`: workflow input, step, sequence-flow, retry, output, or binding contract component.
- <!-- schema-def:workflow_outputs --> `$defs/workflow_outputs`: workflow input, step, sequence-flow, retry, output, or binding contract component.
- <!-- schema-def:workflow_ref --> `$defs/workflow_ref`: typed reference definition for its namespace.
- <!-- schema-def:workflow_retry_policy --> `$defs/workflow_retry_policy`: workflow input, step, sequence-flow, retry, output, or binding contract component.
- <!-- schema-def:workflow_sequence_flow --> `$defs/workflow_sequence_flow`: workflow input, step, sequence-flow, retry, output, or binding contract component.
- <!-- schema-def:workflow_step --> `$defs/workflow_step`: workflow input, step, sequence-flow, retry, output, or binding contract component.
- <!-- schema-def:workflow_input_source --> `$defs/workflow_input_source`: workflow input, step, sequence-flow, retry, output, or binding contract component.
- <!-- schema-def:schema_ref --> `$defs/schema_ref`: typed reference definition for its namespace.
- <!-- schema-def:authored_schema --> `$defs/authored_schema`: human-authored source object for this resource or nested contract.
- <!-- schema-def:feature_tag --> `$defs/feature_tag`: unprefixed behavior-scenario feature grouping tag, not a typed reference.
- <!-- schema-def:data_refresh_signal_name --> `$defs/data_refresh_signal_name`: state-machine-local data-refresh signal identifier.
- <!-- schema-def:state_machine_local_signals --> `$defs/state_machine_local_signals`: state-machine contract component.
- <!-- schema-def:viewport_id --> `$defs/viewport_id`: local identifier contract component.
- <!-- schema-def:region_id --> `$defs/region_id`: local HTML layout region identifier within a state.
- <!-- schema-def:container_id --> `$defs/container_id`: local Textual layout container identifier within a state.
- <!-- schema-def:http_api_adapter --> `$defs/http_api_adapter`: external-interface adapter, invocation, input, or response contract component.
- <!-- schema-def:authorization_assertion --> `$defs/authorization_assertion`: access-policy contract component.
- <!-- schema-def:condition --> `$defs/condition`: access-policy rule predicate component used by policy `environment` and `rules` lists.
- <!-- schema-def:authorization_decision_assertion --> `$defs/authorization_decision_assertion`: access-policy contract component.
- <!-- schema-def:subject --> `$defs/subject`: access-policy contract component.
- <!-- schema-def:resource --> `$defs/resource`: access-policy contract component.
- <!-- schema-def:html_css_class --> `$defs/html_css_class`: HTML renderer contract component.
- <!-- schema-def:html_css_property --> `$defs/html_css_property`: HTML renderer contract component.
- <!-- schema-def:html_css_value --> `$defs/html_css_value`: HTML renderer contract component.
- <!-- schema-def:html_css_declarations --> `$defs/html_css_declarations`: HTML renderer contract component.
- <!-- schema-def:html_css_selector --> `$defs/html_css_selector`: HTML renderer contract component.
- <!-- schema-def:html_css_rule --> `$defs/html_css_rule`: HTML renderer contract component.
- <!-- schema-def:html_style_contract --> `$defs/html_style_contract`: HTML renderer contract component.
- <!-- schema-def:textual_tcss_class --> `$defs/textual_tcss_class`: Textual renderer contract component.
- <!-- schema-def:textual_tcss_property --> `$defs/textual_tcss_property`: Textual renderer contract component.
- <!-- schema-def:textual_tcss_value --> `$defs/textual_tcss_value`: Textual renderer contract component.
- <!-- schema-def:textual_tcss_declarations --> `$defs/textual_tcss_declarations`: Textual renderer contract component.
- <!-- schema-def:textual_tcss_selector --> `$defs/textual_tcss_selector`: Textual renderer contract component.
- <!-- schema-def:textual_tcss_rule --> `$defs/textual_tcss_rule`: Textual renderer contract component.
- <!-- schema-def:textual_style_contract --> `$defs/textual_style_contract`: Textual renderer contract component.
- <!-- schema-def:asset_item --> `$defs/asset_item`: compiled-output object for this resource or nested contract.
- <!-- schema-def:viewport_profile_item --> `$defs/viewport_profile_item`: compiled-output object for this resource or nested contract.
- <!-- schema-def:child_state_machine_item --> `$defs/child_state_machine_item`: compiled-output object for this resource or nested contract.
- <!-- schema-def:content_example_item --> `$defs/content_example_item`: compiled-output object for this resource or nested contract.
- <!-- schema-def:text_resource_item --> `$defs/text_resource_item`: compiled-output object for this resource or nested contract.
- <!-- schema-def:external_interface_item --> `$defs/external_interface_item`: compiled-output object for this resource or nested contract.
- <!-- schema-def:domain_event_item --> `$defs/domain_event_item`: compiled-output object for this resource or nested contract.
- <!-- schema-def:precondition_body --> `$defs/precondition_body`: compiled-output object for this resource or nested contract.
- <!-- schema-def:precondition_item --> `$defs/precondition_item`: compiled-output object for this resource or nested contract.
- <!-- schema-def:assertion_body --> `$defs/assertion_body`: compiled-output object for this resource or nested contract.
- <!-- schema-def:assertion_item --> `$defs/assertion_item`: compiled-output object for this resource or nested contract.
- <!-- schema-def:fixture_item --> `$defs/fixture_item`: compiled-output object for this resource or nested contract.
- <!-- schema-def:entity_type_item --> `$defs/entity_type_item`: compiled-output object for this resource or nested contract.
- <!-- schema-def:access_policy_item --> `$defs/access_policy_item`: compiled-output object for this resource or nested contract.
- <!-- schema-def:command_item --> `$defs/command_item`: compiled command with input_schema, entity_changes, outcomes, and emitted domain-event mappings.
- <!-- schema-def:query_item --> `$defs/query_item`: compiled query with input_schema, result_schema, and outcomes.
- <!-- schema-def:behavior_scenario_item --> `$defs/behavior_scenario_item`: compiled-output object for this resource or nested contract.
- <!-- schema-def:state_machine_item --> `$defs/state_machine_item`: compiled-output object for this resource or nested contract.
- <!-- schema-def:state --> `$defs/state`: compiled-output object for this resource or nested contract.
- <!-- schema-def:workflow_item --> `$defs/workflow_item`: compiled-output object for this resource or nested contract.
- <!-- schema-def:schema_item --> `$defs/schema_item`: compiled-output object for this resource or nested contract.
