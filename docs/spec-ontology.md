# Spec Ontology

This glossary is the vocabulary contract for the authored-source, layer-pruned authored-source, and compiled-output schemas. The authored schema describes sparse human-authored input. Layer-pruned authored schemas are generated from the same source schema and hide sections outside the active authoring layers. The compiled schema describes normalized output in `spec/generated/compiled/spec.yaml`, including generated references, derived domain events, derived HTML routes, generated `http_operation` OpenAPI projections, and expanded empty-collection states.

## Ontology Goal and Change Principles

The goal of this ontology is to provide a stable, low-overlap vocabulary for describing general software product specifications across authored-source, layer-pruned authored-source, compiled-output, projection, test, and audit schemas.

The ontology should make product intent explicit without borrowing overloaded implementation vocabulary unless that vocabulary belongs to a formal projection layer. New terms should preserve clear boundaries between product-domain behavior, API/interface projections, state-machine behavior, workflow behavior, access-control policy, behavior scenarios, content resolution, and visual audit evidence.

When modifying or extending the ontology:

- Prefer stable formal domain language where a mature standard exists, such as JSON Schema for schemas, OpenAPI for HTTP API projections, AsyncAPI for integration-message projections, BPMN-like vocabulary for authored workflows, BDD/Gherkin vocabulary for behavior scenarios, JSON Pointer for compiled-document locations, and ABAC/XACML-style language for access-control policy.
- Use standard terms only in the layer where they are standard. For example, `http_operation` belongs to OpenAPI projection vocabulary; internal product behavior should use `command` or `query`.
- Avoid bare generic nouns when the same word is meaningful in multiple domains. Qualify terms by layer or role, such as `domain_event`, `integration_message`, `local_signal`, `data_refresh_signal`, `state_machine_state`, `renderer_surface`, or `compiled_json_pointer`.
- Do not introduce synonyms for existing concepts. A new term must either represent a new concept, narrow an existing concept with an explicit qualifier, or replace an existing term through a documented rename.
- A new top-level resource kind should have an independent lifecycle, reference namespace, authored/compiled schema shape, and projection or validation role. Otherwise, model it as a nested contract, local identifier, union reference, or derived compiled artifact.
- Local identifiers must be named by scope, such as `workflow_activity_id`, `state_machine_state_id`, or `local_signal_sync_rule_id`, and must not look like global typed references. Collections with local ids should be keyed by those ids when practical in authored and compiled schemas; compiled output may materialize the key as an object `id` only where a keyed shape is impractical.
- Projection artifacts should use the vocabulary of the target projection layer, while authored product vocabulary should remain projection-neutral.
- Compiled-only generated references should use qualified buckets that identify their layer or projection role, such as `http_operation`, `html_route`, `renderer_surface`, or `adapter_response_binding`.
- Additions must update the ID namespace list, reference-type list, binding-root table, binding-expression namespace list, generated-artifact list, and schema-definition inventory when applicable.
- If a term is intentionally non-canonical prose, it should not appear as a schema key, `$defs` name, reference namespace, generated reference bucket, or binding root.

### New Vocabulary Checklist

Before adding a new term, verify that:

1. No existing canonical term already covers the concept.
2. The term does not collide with a stable meaning in JSON Schema, OpenAPI, AsyncAPI, BPMN, BDD/Gherkin, JSON Pointer, access-control policy, state-machine terminology, or generated-code vocabulary.
3. The term is qualified when it crosses a layer boundary.
4. The term has exactly one canonical spelling.
5. Any corresponding reference namespace, local id, binding root, generated reference bucket, or `$defs` entry is updated consistently.
6. The authored-source meaning and compiled-output meaning are both clear.

## Terminology Boundaries

- `domain_event`: a durable product-domain occurrence that happened. `domain_events` are emitted by successful command or entity_lifecycle_transition outcomes and may serve as workflow inputs.
- `integration_message`: a wire-level AsyncAPI message in `integration_messages.asyncapi.yaml`. It carries a domain-event payload over a channel, but it is not state-machine vocabulary.
- `local_signal`: a state-machine-local trigger or emitted signal. `local_signals` may be accepted by transitions, emitted by transitions, and synced between mounted child state-machine instances.
- `data_refresh_signal`: a state-machine-local data refresh or invalidation signal, commonly consumed by `query_binding.load.refresh_on`.

Bare `event` is avoided for durable domain occurrences because CloudEvents and UML/state-machine terminology also use that word. Bare `message` is avoided in state machines because AsyncAPI uses message for transport exchange.

## Top-Level Resource Kinds

- <!-- top-level:entity_types --> `entity_types`: collection-prefixed stable product/domain entity type ids such as `entity_type.project`, each with a PascalCase display/type `name` such as `Project`, fields, and optional `entity_lifecycle` declarations. Entity types are not ORM types, API contracts, generated implementation classes, or storage schemas.
- <!-- top-level:schemas --> `schemas`: first-class reusable JSON Schema payload or object schemas referenced with `schema.*` ids. JSON Schema `$ref` values may target either `schema.*` reusable schemas or `entity_type.*` entity schemas when a contract returns, accepts, emits, or embeds a product entity type.
- <!-- top-level:commands --> `commands`: state-changing product behavior with `input_schema`, optional authorization, explicit `entity_changes`, outcomes, and `emits_domain_events`.
- <!-- top-level:queries --> `queries`: read-only product behavior with `input_schema`, `result_schema`, and outcomes.
- <!-- top-level:domain_events --> `domain_events`: durable product-domain occurrences with payload_schema contracts and compiled emitters.
- <!-- top-level:workflows --> `workflows`: BPMN-like asynchronous or long-running process contracts with `inputs`, `activities`, `gateways`, top-level `sequence_flows`, `outputs`, `retry_policies`, and `failure_handlers`. CWL is a generated projection target, not the authored workflow vocabulary.
- <!-- top-level:state_machines --> `state_machines`: UI/component state-machine contracts with `context_schema`, states, transitions, triggers, guards, local_effects, local signals, command bindings, and query bindings.
- <!-- top-level:external_interfaces --> `external_interfaces`: canonical external invocation declarations split into explicit adapter and invocation objects.
- <!-- top-level:access_policies --> `access_policies`: canonical access-control policies with `subject`, `resource`, `action`, `environment`, rules, `rule_effect`, and `combining_algorithm`.
- <!-- top-level:fixtures --> `fixtures`: named concrete seed data namespaces used by behavior scenarios, preconditions, assertions, content examples, and `render_example` objects.
- <!-- top-level:behavior_scenarios --> `behavior_scenarios`: formal BDD behavior scenarios with system_under_test_ref, given, when, and then contracts.
- <!-- top-level:media_assets --> `media_assets`: canonical media assets with media kind, asset role, placeholders, and resolver-backed resolution when present.
- <!-- top-level:text_resources --> `text_resources`: text resources used by state-machine slots and content_resolver projections.
- <!-- top-level:content_examples --> `content_examples`: named content_resolver examples for dynamic text and media asset content.
- <!-- top-level:viewport_profiles --> `viewport_profiles`: canonical global HTML and Textual viewport profiles for audit/golden-image rendering.
- <!-- top-level:reference_index --> `reference_index`: canonical compiled-only index of generated references used by projections and tests.
- <!-- top-level:project --> `project`: the project slug for the specification workspace.
- <!-- top-level:preconditions --> `preconditions`: reusable entity_type presence/absence setup predicates; preconditions are not assertions, invariants, or broad domain rules.
- <!-- top-level:assertions --> `assertions`: reusable entity_type presence/absence expected predicates referenced by behavior-scenario `then.postconditions`; assertions are not setup predicates or invariants.

## ID Namespaces

- `media_asset_ref`: `media_asset.<domain>...`; media asset declarations, generated media asset slots, content examples, and audit evidence.
- `content_example_ref`: `content_example.<domain>...`; content_resolver examples.
- `schema_ref`: `schema.<domain>...`; reusable typed payload schema ids. JSON Schema `$ref` values may also target `entity_type_ref` for product entity schemas; `schema_ref` names only the reusable `schemas` collection.
- `data_refresh_signal_name`: local state-machine data-refresh signal name; authored sources do not use global-looking `data_refresh_signal.*` references for local refresh signals.
- `external_interface_ref`: `external_interface.<domain>...`; external-interface declarations, delegated external-interface invocations, and behavior-scenario `open_external_interface` or `call_external_interface` stimuli.
- `domain_event_ref`: `domain_event.<domain>...`; durable domain-event declarations, command emissions, workflow inputs, and behavior-scenario domain-event assertions.
- `precondition_ref`: `precondition.<domain>...`; named setup predicates referenced through `precondition_use.ref`.
- `assertion_ref`: `assertion.<domain>...`; named expected predicates referenced through `assertion_use.ref`.
- `fixture_ref`: `fixture.<domain>...`; seed data fixtures used by behavior scenarios, content examples, preconditions, assertions, and `render_example` objects.
- `feature_tag`: unprefixed dotted feature grouping label used by behavior scenarios and generated feature files; it is not a typed reference.
- `instance_id`: local child state-machine instance id within a composed `state_machine_state`.
- `local_signal_name`: local state-machine signal name; authored sources do not use global-looking `local_signal.*` references for local signals.
- `entity_type_ref`: `entity_type.<domain>...`; stable product/domain entity type id. The entity type object carries a separate PascalCase `name` for display/type naming.
- `command_ref`: `command.<domain>...`; state-changing command declarations, state-machine command bindings, workflow activities, external-interface command invocations, and behavior-scenario command assertions.
- `query_ref`: `query.<domain>...`; read-only query declarations, state-machine query bindings, external-interface query invocations, and behavior-scenario query assertions.
- `command_binding_id`: local state command binding name; authored sources do not use global-looking `command_binding.*` references for local invocation keys.
- `query_binding_id`: local state-machine or `state_machine_state` query binding name; authored sources do not use global-looking `query_binding.*` references for local invocation keys.
- `region_id`: local HTML layout region id within one `state_machine_state`.
- `access_policy_ref`: `access_policy.<domain>...`; access-control policy declarations, `command.authorization.policy`, external-interface `access_policy` fields, generated access-policy projections, and authorization behavior-scenario assertions.
- `viewport_profile_ref`: `viewport_profile.<domain>...`; named HTML/Textual viewport profiles.
- `local_signal_sync_rule_id`: local child-machine `local_signal` synchronization rule id within one composed `state_machine_state`.
- `state_machine_ref`: `state_machine.<domain>...`; state-machine declarations, `child_state_machines`, external_interface_state_machine_invocation mappings, and behavior-scenario state-machine assertions.
- `state_machine_state_id`: local state-machine state id within one `state_machine`.
- `render_example_id`: local render_example id within one `state_machine_state`.
- `behavior_scenario_ref`: `behavior_scenario.<domain>...`; formal behavior-scenario declarations and generated feature tags.
- `text_resource_ref`: `text_resource.<domain>...`; text resource declarations, generated text slots, content examples, and content_resolver signatures.
- `container_id`: local Textual layout container id within one `state_machine_state`.
- `viewport_id`: local viewport id within `html_viewports` or `textual_viewports`.
- `workflow_ref`: `workflow.<domain>...`; workflow declarations, workflow external-interface invocations, and generated workflow references.
- `workflow_activity_id`: local workflow activity id within one workflow.
- `workflow_gateway_id`: local workflow gateway id within one workflow.
- `workflow_sequence_flow_id`: local workflow sequence-flow id within one workflow.
- Generated references use `media_asset`, `access_policy`, `cli_command`, `cli_response_handler`, `http_operation`, `external_interface_delegate`, `external_interface_invocation`, `local_signal_raise`, `command_binding`, `command_binding_local_outcome_effect`, `query_binding`, `query_binding_local_outcome_effect`, `html_route`, `adapter_response_binding`, `renderer_screen`, `state_machine`, `renderer_surface`, `text_resource`, and `workflow` buckets in compiled `reference_index`.

## Reference Types

- `system_under_test_ref`: exactly one typed reference to the resource under test: `external_interface`, `domain_event`, `command`, `query`, `state_machine`, or `workflow`.
- `resolver_ref`: union reference to exactly one `text_resource_ref` or `media_asset_ref`; used only by resolver-backed `text_resources` and `media_assets`. It is not a global namespace and does not introduce `resolver.*` ids.
- `given`: setup contract split into `seed_fixtures` and `preconditions`.
- `when`: BDD behavior-scenario stimulus only: `open_external_interface`, `call_external_interface`, `invoke_command`, `invoke_query`, or `emit_domain_event`.
- `then`: non-empty assertions for `outcome`, entity existence, emitted/not-emitted domain events, workflow execution, `authorization_decision`, responses, `authorization_denied_assertion`, command/query availability, invocation, `access_denied` outcome assertions, `state_machine_state`, and `postconditions`. Compiled state-machine assertions may add `renderer_surface`, `state_machine_composition`, and top-level `requires`.
- `then.requires`: compiled-only derived projection dependencies for a state-machine assertion, split into `renderer_surfaces`, `text_resources`, `media_assets`, `query_bindings`, and `command_bindings`.
- `external_interface_adapter`: exactly one adapter object: `http_api`, `cli`, `webhook`, `scheduled`, `worker`, or `html_route`.
- `adapter_input_shape`: HTTP API input may use `path_params`, `query_params`, and `body`; HTML route input may use `path_params` and `query_params`; CLI input uses `args`; worker input uses `payload`; webhook input may use `path_params`, `query_params`, and `payload`; scheduled input has no external input sections.
- `external_interface_invokes`: exactly one invocation object: `command`, `query`, `state_machine`, `workflow`, or `external_interface`.
- `external_interface_invocation_bindings`: top-level `input_mapping.bindings` binds adapter input into command input, query input, state-machine context, or workflow input and must exactly cover the invoked fields.
- `external_interface_state_machine_invocation`: `invokes.state_machine` must declare `renderer: html` or `renderer: textual`. HTML route external interfaces can invoke only `html`; CLI external interfaces can launch `html` or `textual`; the invoked state machine must declare the selected renderer in at least one `state_machine_state`.
- `external_interface_workflow_invocation`: `invokes.workflow.ref` names the workflow and `input_mapping.bindings` binds adapter input into workflow input fields.
- `external_interface_delegation`: an external interface whose `invokes.external_interface.ref` points at another external interface. `input_mapping.delegated_input` binds adapter input into the delegated external-interface `adapter_input_shape`. Delegation is general and is not CLI-to-HTTP-specific.
- `delegating_external_interface`: the outer external interface whose adapter exposes a facade and binds its input into the delegated external-interface input shape.
- `delegated_external_interface`: the inner external interface that receives delegated invocation. Its `access_policy` and the delegated command/query authorization outcomes remain visible to the delegating external interface.
- `invoked_outcome_response`: synchronous adapter response keyed by command, query, workflow, state-machine, or delegated external-interface outcome names. HTTP API `responses` and delegated CLI `response_handlers` are invoked-outcome response mappings.
- `adapter_ingress_response`: asynchronous adapter acknowledgement or disposition keyed by adapter-level outcomes, such as accepted, malformed, retry, reject, or dead-letter handling. Worker, webhook, and scheduled adapters use `ingress_responses` when receipt/disposition is distinct from invoked workflow execution outcomes.
- `response_handler`: generic adapter projection concept; currently only `cli_response_handler` is represented as a concrete schema component.
- `cli_response_handler`: maps a named response outcome to stdout, stderr, an exit code, and optionally a retry policy. It does not restate HTTP status classification when the delegated external interface is an HTTP API.
- `idempotent`: repeated identical command or external-interface execution has the same intended product-state effect as a single execution. Retry policies may rely on this marker. The default is false. Queries are idempotent by definition: repeated query execution does not change product state; it does not imply result determinism. This is idempotency for product behavior, not HTTP safe-method vocabulary.
- `retryable`: explicit command or external-interface marker permitting automatic retry of delegated external-interface, command, `entity_lifecycle_transition`, or workflow execution. Retryable commands must currently also be idempotent; future idempotency-key or proven-non-execution guards may provide other retry proofs. Transport retry, ingress retry, workflow retry, and command retry are separate scopes.
- `workflow_activity`: a BPMN-like unit of workflow work. The current authored schema supports command-invoking workflow activities with `command` and `input_mapping`; future activity kinds may cover subworkflows, workers, or external-interface calls without changing sequence-flow vocabulary.
- `workflow_gateway`: a BPMN-like workflow branching or joining node. Gateways are explicit workflow elements even when a simple workflow has none.
- `workflow_sequence_flow`: a top-level BPMN-like workflow control-flow edge from `source_ref` (`activity` or `gateway`) to `target_ref` (`activity`, `gateway`, or terminal workflow outcome). Activity-sourced flows use `source_outcome` to map the completed `workflow_activity` outcome; gateway-sourced flows may use `condition` expressions and may not use `source_outcome`.
- `state_machine_context_schema`: local machine context declared as JSON Schema object `properties` and `required`. Nullability uses JSON Schema type arrays such as `type: [string, null]`; local_effects may set a context field to null only when that field schema allows null.
- `context_non_null`: state-machine condition meaning the declared context field exists in the current context and its value is not `null`. JSON Schema property presence remains separate: `required` means a property is present even when its value is `null`.
- `selected.condition`: child state-machine selected-state guard. It uses state-machine condition vocabulary and does not reuse BDD `when`.
- `local_signal_sync_rule.trigger`: child state-machine `local_signal` source that starts a local-signal synchronization rule. It does not reuse BDD `when`.
- `viewport_profile`: global audit/golden-image viewport map. Renderable state machines require at least one viewport profile, and profiles must include viewport sets for each declared renderer surface (`html_viewports` for HTML, `textual_viewports` for Textual).
- `render_example`: state_machine_state-local visual evidence input. It supplies seed fixtures, optional context, optional precondition references, and, for composed `state_machine_state` values, an exact child instance state vector; it never names viewport profiles directly.
- `render_examples`: local map of `render_example` objects within one `state_machine_state`; not a top-level resource kind.
- `state_machine_state.intentionally_empty`: authored marker for a state with no authored slots, bindings, renderers, child state machines, local signal sync rules, or render examples. It must be paired with a state-level `rationale`.
- `content_resolver`: a final resolver declaration implemented by a `text_resource` or `media_asset`; `resolver_ref` is a union reference to exactly one `text_resource_ref` or `media_asset_ref` and must equal the containing resource id. `content_resolvers` are not independent top-level resources. Final content_resolvers require at least one matching `content_example`, and example args must exactly match the resource args.
- `rationale`: bounded plain text used on authored resources and on intentionally unobservable local effects. Missing top-level resource rationale is filled by a deterministic compiler default.
- `command_binding`: local state use of a global command, normally user-triggered, including `input_mapping` and local_effects. A renderer control binds to this local invocation, not directly to `command_ref`.
- `query_binding`: local state-machine or state-machine-state use of a query for data loading or refresh, including `input_mapping`, load policy, context updates, result binding, and local_effects. State-machine-level queries load with `on_start`/`on_mount`; state-machine-state queries load with `on_enter`.
- `query_binding_local_effect`: each query `local_outcome_effect` must update context, bind/cache a result, raise a local signal, or explicitly declare a scoped `no_local_effect`. `result_binding.data_key` names the state-machine/state-machine-state result data populated from a binding value.
- `query_refresh_signal`: local data-refresh signal raised by a mutation, query outcome, or other invalidation `local_effect`, such as `project_changed`, and consumed by `query_binding.load.refresh_on`. Loaded/missing/error data-refresh signals should come from query outcomes after data has actually been bound or classified.
- `empty_non_empty_query_handling`: array-valued query outcomes split the local_outcome_effect with `conditional_local_effects` using `result_condition: empty` and `result_condition: non_empty`. Both branches must be declared so empty collection states are reachable through authored handling rather than compiler length guesses.
- `machine_scoped_query_ownership`: state-machine-level query bindings declare `result_scope: local`, `shared`, or `prefetch`. Result bindings that do not raise a signal must use shared/prefetch ownership with rationale, especially when a child machine also owns visible loading.
- `field_slot_source_resolution`: every field slot resolves to exactly one context field or query result binding. A bound entity_type or array item can feed field slots when the slot name exists on the result type; ambiguous or missing sources fail semantic validation.
- `local_outcome_effect`: mapping from a command/query-binding outcome to context updates, result binding, a local signal raise, or explicit `no_local_effect` handling.
- `no_local_effect`: explicit declaration that an outcome is covered but intentionally has no local state-machine effect. It is not omission and does not suppress durable domain events. Reasons are scope-sensitive: response mapping handling needs a real adapter response mapping or renderer surface, query refresh needs explicit result/context refresh, result-bound-without-signal needs result binding or context/cache update, and failure outcomes must use proven response mapping handling or `intentionally_unobservable` with rationale.
- `authored_value`: explicit literal-or-fixture-reference value used in authored behavior-scenario, precondition, assertion, content-example, and render-example value maps. Use `{value: ...}` for JSON literals, including literal strings beginning with `$`, and `{from: $fixture...}` for fixture references. Raw `$...` strings are not interpreted as references.
- `binding_root`: the first segment of a binding expression. Local state-machine bindings use `$state_context`, `$principal`, `$trigger.payload`, and `$state_machine`; command domain-event payload mappings use `$command_input` and `$command_outcome`; external-interface response mappings use `$invocation_outcome`; adapter/delegation bindings use `$adapter_input` and `$adapter_response`; workflow activity bindings use `$workflow_input` and `$activity_outcome`. `$message` is reserved for AsyncAPI/wire-level messages, not local state-machine signaling.
- `state_machine_trigger`: the current state-machine-local trigger, sourced from either a `local_signal` or `data_refresh_signal`.
- `actor_user_binding_source`: local command bindings should bind actor-like input fields such as `actor_id`, `approved_by`, or `reviewer_id` from `$principal.id` or an explicit context source. Literal actor/user ids are linted because they usually hide fixture-only assumptions in authored UI behavior.
- `local_signal_raise`: creation of a state-machine-local `local_signal` or `data_refresh_signal`.
- `emits_domain_events`: command-level durable domain-event emission mapping keyed by successful command outcome. It is not used for local state-machine transition local_effects.
- `state_machine_transition.local_effects.raise`: local state-machine `local_signal` or `data_refresh_signal` raise after a state transition.
- `command_binding.local_effects.raise`: local state-machine `local_signal` or `data_refresh_signal` raise after a user command binding.
- `query_binding.local_effects.raise`: local state-machine `local_signal` or `data_refresh_signal` raise after a query load or refresh outcome.
- `local_signals`: local UI/component/state-machine signal contracts split into accepted `local_signals`/`data_refresh_signals` maps and emitted `local_signals` maps with JSON Schema `payload_schema` declarations.
- `renderer_contracts`: state renderer declarations keyed by concrete renderer surface. `renderers.html` and `renderers.textual` each own renderer-local `layout`, `presentation`, and `style`.
- `renderer_placement_validation`: HTML slots and child machines must reference declared HTML `region_id`s; Textual widgets and child machines must reference declared Textual `container_id`s. Placement ids are layout ids, not field names.
- `resolver_output_escaping`: text, SVG, XML, and HTML resolvers must escape dynamic values before placing them in markup text or attributes. Plain-text outputs and alt text must not expose unescaped markup-sensitive values where they may be rendered into HTML/XML.
- `schema`: JSON Schema subset used for payloads, entity types, command inputs/results, query inputs/results, state-machine context, content args, and adapter input sections. It uses `type`, `$ref`, `properties`, `required`, `enum`, `const`, `items`, `additionalProperties`, and `format`; `$ref` may target `schema.*` or `entity_type.*`; null is represented through JSON Schema type arrays such as `type: ["string", "null"]`.
- `access_policy`: reusable rule set that determines whether `subject` may attempt `action` on `resource` under `environment`. Actor subjects must bind their concrete identity from `$principal...`; anonymous subjects must not carry a source. Direct `access_policy_ref` fields identify the policy applied to an external interface or authorization assertion. Commands use `authorization.policy` plus explicit `authentication_required_as` and `access_denied_as` outcome mappings. Policies with identical `subject`, `resource`, `action`, `environment`, combining behavior, and `rules` should be one `access_policy`.
- `command_authorization`: command-local access-policy mapping with `policy`, `authentication_required_as`, and `access_denied_as`. The mapped names must be normal command outcomes with `kind: failure`.
- `rule_effect`: access-policy rule result vocabulary carried by each rule's `effect`; currently only `permit` is active while `combining_algorithm` is `all_permit_rules_must_match`. Deny rules are not part of the active authored ontology yet.
- `combining_algorithm`: access-policy rule-combining behavior. `all_permit_rules_must_match` means all environment conditions and all permit-rule conditions must match for the evaluated `authorization_decision` to be `permit`; any required condition miss evaluates to `deny`, and evaluation errors produce `indeterminate`.
- `authorization_decision`: evaluated authorization result vocabulary: `permit`, `deny`, or `indeterminate`. Decision vocabulary is reserved for assertions and runtime evaluation, not authored policy-combining metadata.
- `authorization_failure_outcome`: named failure outcome produced before command execution when authorization fails. These outcomes live in `command.outcomes`; they are not a separate `errors` or `authorization_outcomes` collection.
- `authorization_denied_assertion`: behavior-scenario archetype for asserting that the evaluated `authorization_decision` is `deny` through `then.authorization.denied`. It is distinct from the command failure outcome `access_denied`. `authorization_denied_assertion` is an archetype name, not a separate `$defs` schema component.
- `authentication_required`: authorization failure where no acceptable subject identity is available. HTTP examples conventionally map this outcome to `401`; CLI examples map it to stderr plus a nonzero exit code.
- `access_denied`: authorization failure where a subject identity exists but does not satisfy the access policy. HTTP examples conventionally map this outcome to `403`; CLI examples map it to stderr plus a nonzero exit code.
- `domain_failure_outcome`: command outcome produced by command execution or domain validation, such as `validation_failed` or `not_found`.
- `lifecycle_transition_applicability`: entity-lifecycle source-state check derived from `entity_type.entity_lifecycle.lifecycle_transitions[*]`, not authorization.
- `lifecycle_transition_not_allowed`: lifecycle_transition_applicability/domain_failure_outcome for lifecycle source-state mismatch. It is not an authorization failure and should be asserted with `command_outcome` or `external_interface_response`, not the `authorization_denied_assertion` behavior-scenario archetype.
- `rule.entity_state_condition`: explicit author-authored access-control rule when an entity lifecycle state is truly part of who may attempt a command. The compiler does not generate this rule from entity_lifecycle_transition `from` states; lifecycle source-state mismatch remains lifecycle_transition_applicability and maps to `lifecycle_transition_not_allowed`.

## command_binding Example

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
          lifecycle_transition_not_allowed:
            raise:
              local_signal: show_lifecycle_transition_not_allowed
              payload_bindings:
                message:
                  from: $command_outcome.result.message
          access_denied:
            no_local_effect:
              reason: handled_by_response_mapping
              rationale: The response mapping reports authorization failure.
```

## query_binding Example

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
| `command_binding.input_mapping` | `$state_context`, `$principal` |
| `command_binding.local_effects` | `$command_outcome`, `$command_binding`, `$state_context` |
| `query_binding.input_mapping` | `$state_context`, `$principal` |
| `query_binding.local_effects` | `$query_outcome`, `$query_binding`, `$state_context` |
| `state_machine_transition.local_effects` | `$trigger.payload`, `$state_context` |
| Child state-machine `context_bindings` and `selected.condition` guards | `$state_machine` for parent state-machine context |
| `command_domain_event_emission_payload_mappings` | `$command_input`, `$command_outcome` |
| External-interface command/query/state-machine/workflow invocation mappings | `$adapter_input` |
| External-interface delegation mappings | `$adapter_input` |
| HTTP API response bodies | `$invocation_outcome.result` only |
| `cli_response_handler.invoked` | `$adapter_input`, `$invocation_outcome` |
| `cli_response_handler.delegated` | `$adapter_input`, `$adapter_response` |
| Workflow activity `input_mapping` | `$workflow_input`, `$activity_outcome` |
| Authored behavior-scenario/precondition/assertion/content-example/render-example value maps | `$fixture` |

## Visual Audit Coverage

- `visual_evidence_set`: a shared list of generated chart SVG artifacts or rendered captures (`*.svg` charts/captures and `*.png` screenshots) that visually evidence one or more compiled JSON Pointers.
- `compiled_json_pointer`: a JSON Pointer location inside compiled `spec.yaml`.
- `required_visual_pointer`: a compiled JSON Pointer that must have at least one `visual_evidence_set`; missing required pointers fail validation.
- `required_visual_text_witness`: a stable token that must appear in visible SVG text for a required visual pointer whose value is explicitly rendered as text. These witnesses are intentionally limited to durable ids, references, field/type labels, and other renderer-owned tokens; they do not audit hidden SVG metadata, incidental prose, or render-only pixels.
- `optional_visual_pointer`: a compiled JSON Pointer that may have visual evidence but is allowed to be absent from chart SVG artifacts and render captures.
- `missing_required_visual_pointer`: a required visual pointer with no chart or render-capture evidence.
- `optional_visual_pointer_not_shown`: an optional visual pointer with no chart or render-capture evidence; this is reported but does not fail validation.
- `non_visual_pointer`: compiled metadata that is intentionally outside visual-audit scope, such as `project` workspace metadata or the compiled `reference_index`.
- `render_presence`: resource-level visibility in actual render captures, reported as `rendered` or `not_rendered` for `media_assets`, `text_resources`, `fixtures`, `preconditions`, `assertions`, and `content_examples`.

Audit validation fails when any `missing_required_visual_pointer` exists or when a declared `required_visual_text_witness` is absent from its SVG evidence set. Required pointers without a text witness are still required to have chart or render-capture evidence, but their semantics are audited through the visual artifact rather than a machine-readable token.

The visual audit includes `state_machine_chart`, `state_composition_chart`, `external_interface_flow_chart`, `workflow_flow_chart`, `command_flow_chart`, and `query_flow_chart` SVG artifacts. Command and query flow charts are chronological branching data flows for input, authorization, touched resources, outcomes, and emitted domain events; other charts reference commands and queries compactly instead of repeating the same cards.

## Binding Expression Namespaces

- `$fixture.<path>` reads merged seed fixture data in behavior scenarios, preconditions, assertions, content examples, and `render_example` objects.
- `$state_machine.<field>` reads parent state-machine context in child state-machine context bindings and composition guards.
- `$trigger.payload.<field>` reads the current `state_machine_trigger` payload in transition local_effects and sync sends.
- `$state_context.<field>` reads current state-machine context in transition local_effects, command/query binding input mappings, and local_outcome_effect signal payload mappings.
- `$principal.id` reads the authenticated principal id available to the current state-machine binding.
- `$principal.roles[*]` reads the authenticated principal's role names when role data is available.
- `$principal.<field>` is distinct from access-policy `subject`; policies evaluate subjects, while bindings read the concrete authenticated principal supplied by runtime context.
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
- `$invocation_outcome.result[.<field>]` reads the selected outcome result from the invoked command, query, workflow, state-machine, or delegated external interface during external-interface response mapping.
- `$command_binding.input.<field>` reads the bound command input during command-binding local_effects.
- `$query_binding.input.<field>` reads the bound query input during query-binding local_effects.
- `$adapter_response.body[.<field>]` reads the delegated external-interface response body inside delegating CLI `response_handlers`.
- `$workflow_input.payload[.<field>]` reads workflow input payload.
- `$activity_outcome.<activity>.<outcome>.result[.<field>]` reads a previous workflow activity result.

Binding expressions appear inside binding objects. `authored_value` maps use `{from: $fixture...}` for fixture expressions and `{value: ...}` for literal JSON values; a raw string beginning with `$` is a literal only when wrapped with `value`.
- The shared grammar is `$canonical_root.path.to.field` with optional `[*]` wildcard segments; semantic validation checks available roots and declared field paths for each context.

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
- `spec/generated/product_interfaces/workflow.cwl.yaml`: CWL projection generated from BPMN-like authored workflow processes for workflow/CLI/worker-relevant execution graphs.
- `spec/generated/product_interfaces/access_policies.json`: access-policy projection with command authorization mappings and external-interface policies.
- `spec/generated/content_resolvers/{signatures.py,stubs.py,examples.yaml}`: documented content-resolution contracts and examples.
- `spec/generated/test_adapters/python_refs.py`: Python constants for resource and generated reference IDs.
- `spec/generated/test_adapters/driver_protocol.py`: BDD driver protocol.
- `spec/generated/test_adapters/pytest_bdd_steps.py`: BDD step glue.
- `spec/generated/test_adapters/pytest_bdd_features/{feature}.feature`: generated behavior feature files.
- `spec/generated/audit_evidence/external_interfaces/{adapter}/{external_interface}/flow.svg`: `external_interface_flow_chart` artifacts grouped by adapter kind.
- `spec/generated/audit_evidence/coverage.yaml`: generated visual coverage index mapping compiled JSON Pointers to chart and render-capture evidence, including explicit render coverage gaps for `media_assets`, `text_resources`, `fixtures`, `preconditions`, `assertions`, and `content_examples`.
- `spec/generated/audit_evidence/workflows/{workflow}/flow.svg`: `workflow_flow_chart` artifacts.
- `spec/generated/audit_evidence/commands/{command}/flow.svg`: `command_flow_chart` artifacts showing input, authorization, touched resources, outcomes, and emitted domain events.
- `spec/generated/audit_evidence/queries/{query}/flow.svg`: `query_flow_chart` artifacts showing input, authorization, results, and outcomes.
- `spec/generated/audit_evidence/state_machines/{state_machine}/state_machine.svg`: `state_machine_chart` artifacts.
- `spec/generated/audit_evidence/state_machines/{state_machine}/states/{state_machine_state}/composition.svg`: `state_composition_chart` artifacts.
- `spec/generated/audit_evidence/state_machines/{state_machine}/states/{state_machine_state}/{text_resources.yaml,fixtures.yaml,media_assets/*}`: state-scoped audit inputs.
- `spec/generated/audit_evidence/state_machines/{state_machine}/states/{state_machine_state}/renders/*`: HTML/Textual state render source and captures.
- `spec/generated/audit_evidence/state_machines/{state_machine}/states/{state_machine_state}/render_examples/{render_example}/**`: render_example scoped inputs and render captures.

## Schema Definition Inventory

Each `$defs` entry in the JSON Schemas is documented exactly once here. The schema-inventory test treats these hidden markers as the authoritative inventory.

- <!-- schema-def:aria_role --> `$defs/aria_role`: renderer contract component scoped to HTML and/or Textual invocations.
- <!-- schema-def:media_asset_placeholder --> `$defs/media_asset_placeholder`: shared schema component used by authored source or compiled output.
- <!-- schema-def:media_asset_ref --> `$defs/media_asset_ref`: typed reference definition for its namespace.
- <!-- schema-def:viewport_profile_ref --> `$defs/viewport_profile_ref`: typed reference definition for its namespace.
- <!-- schema-def:authored_media_asset --> `$defs/authored_media_asset`: human-authored source object for this resource or nested contract.
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
- <!-- schema-def:authored_state_machine_state --> `$defs/authored_state_machine_state`: human-authored state_machine_state source object.
- <!-- schema-def:authored_workflow --> `$defs/authored_workflow`: human-authored source object for this resource or nested contract.
- <!-- schema-def:rationale --> `$defs/rationale`: shared schema component used by authored source or compiled output.
- <!-- schema-def:child_state_machine_selected --> `$defs/child_state_machine_selected`: state-machine contract component.
- <!-- schema-def:cli_adapter --> `$defs/cli_adapter`: external-interface adapter, invocation, input, or response contract component.
- <!-- schema-def:cli_output --> `$defs/cli_output`: cli_response_handler output text and bindings.
- <!-- schema-def:cli_response_handler --> `$defs/cli_response_handler`: cli_response_handler for a named response outcome.
- <!-- schema-def:cli_response_handlers --> `$defs/cli_response_handlers`: map from named response outcomes to cli_response_handlers.
- <!-- schema-def:context_condition --> `$defs/context_condition`: state-machine contract component.
- <!-- schema-def:content_args --> `$defs/content_args`: shared schema component used by authored source or compiled output.
- <!-- schema-def:content_example_ref --> `$defs/content_example_ref`: typed reference definition for its namespace.
- <!-- schema-def:resolver_ref --> `$defs/resolver_ref`: union reference to exactly one `text_resource_ref` or `media_asset_ref`; used only by resolver-backed text resources and media assets.
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
- <!-- schema-def:external_interface_response --> `$defs/external_interface_response`: HTTP-style adapter response with required status and optional body or problem.
- <!-- schema-def:external_interface_ingress_response --> `$defs/external_interface_ingress_response`: asynchronous adapter ingress response with required disposition and optional problem.
- <!-- schema-def:external_interface_response_value --> `$defs/external_interface_response_value`: external-interface response payload schema and source binding.
- <!-- schema-def:external_interface_responses --> `$defs/external_interface_responses`: map from named outcomes to HTTP-style adapter responses.
- <!-- schema-def:external_interface_ingress_responses --> `$defs/external_interface_ingress_responses`: map from named adapter-level outcomes to ingress disposition responses.
- <!-- schema-def:external_interface_retry_policy --> `$defs/external_interface_retry_policy`: bounded automatic retry policy for retryable delegated external interfaces.
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
- <!-- schema-def:local_signal_sync_rule_id --> `$defs/local_signal_sync_rule_id`: local child-machine `local_signal` synchronization rule id within one composed `state_machine_state`.
- <!-- schema-def:access_role_name --> `$defs/access_role_name`: access-control role name used by access-policy `subject_has_role` conditions.
- <!-- schema-def:render_example_id --> `$defs/render_example_id`: local render_example id within one `state_machine_state`.
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
- <!-- schema-def:local_signal_sync_local_effect --> `$defs/local_signal_sync_local_effect`: child-machine `local_signal` synchronization contract component.
- <!-- schema-def:local_signal_sync_assertion --> `$defs/local_signal_sync_assertion`: child-machine `local_signal` synchronization assertion component.
- <!-- schema-def:local_signal_sync_rule --> `$defs/local_signal_sync_rule`: child-machine `local_signal` synchronization rule component.
- <!-- schema-def:local_signal_sync_send_local_effect --> `$defs/local_signal_sync_send_local_effect`: child-machine `local_signal` synchronization send effect component.
- <!-- schema-def:local_signal_sync_trigger --> `$defs/local_signal_sync_trigger`: child-machine `local_signal` synchronization trigger component.
- <!-- schema-def:entity_type_ref --> `$defs/entity_type_ref`: typed reference definition for its namespace.
- <!-- schema-def:entity_type_display_name --> `$defs/entity_type_display_name`: PascalCase entity type display/type name separated from the stable `entity_type.*` id.
- <!-- schema-def:schema --> `$defs/schema`: JSON Schema subset used by payload, entity type, input, context, and reusable schema declarations.
- <!-- schema-def:command_authorization --> `$defs/command_authorization`: explicit command access policy and mapped authorization failure outcomes.
- <!-- schema-def:command_binding_id --> `$defs/command_binding_id`: local state command binding identifier.
- <!-- schema-def:command_domain_event_emit --> `$defs/command_domain_event_emit`: command-level domain-event emission mapping keyed by outcome.
- <!-- schema-def:command_entity_changes --> `$defs/command_entity_changes`: non-empty command entity-change summary containing creates, updates, deletes, or entity_lifecycle_transition entries.
- <!-- schema-def:command_ref --> `$defs/command_ref`: typed reference definition for its namespace.
- <!-- schema-def:command_or_query_ref --> `$defs/command_or_query_ref`: union reference to exactly one command_ref or query_ref.
- <!-- schema-def:query_ref --> `$defs/query_ref`: typed reference definition for its namespace.
- <!-- schema-def:command_outcome --> `$defs/command_outcome`: command outcome without embedded domain-event emission metadata.
- <!-- schema-def:command_outcomes --> `$defs/command_outcomes`: map from outcome names to command outcomes.
- <!-- schema-def:query_outcome --> `$defs/query_outcome`: query outcome.
- <!-- schema-def:query_outcomes --> `$defs/query_outcomes`: map from outcome names to query outcomes.
- <!-- schema-def:access_policy_ref --> `$defs/access_policy_ref`: typed reference definition for its namespace.
- <!-- schema-def:python_class_name --> `$defs/python_class_name`: shared schema component used by authored source or compiled output.
- <!-- schema-def:python_identifier --> `$defs/python_identifier`: shared schema component used by authored source or compiled output.
- <!-- schema-def:query_binding_id --> `$defs/query_binding_id`: local state-machine or `state_machine_state` query binding identifier.
- <!-- schema-def:state_machine_query_binding_load_policy --> `$defs/state_machine_query_binding_load_policy`: state-machine-level query load and refresh trigger policy. It allows `on_start`, `on_mount`, or `refresh_on`, and forbids `on_enter`.
- <!-- schema-def:state_machine_state_query_binding_load_policy --> `$defs/state_machine_state_query_binding_load_policy`: state-machine-state-level query load and refresh trigger policy. It allows `on_enter` or `refresh_on`, and forbids `on_start`/`on_mount`.
- <!-- schema-def:query_result_condition --> `$defs/query_result_condition`: explicit query-result shape condition for empty/non-empty array handling.
- <!-- schema-def:query_result_binding --> `$defs/query_result_binding`: explicit query result binding to a named local `data_key`.
- <!-- schema-def:renderer_contracts --> `$defs/renderer_contracts`: renderer contract component scoped to HTML and/or Textual invocations.
- <!-- schema-def:binding_expression --> `$defs/binding_expression`: shared schema component used by authored source or compiled output.
- <!-- schema-def:fixture_binding_expression --> `$defs/fixture_binding_expression`: fixture-only binding expression used by authored value maps.
- <!-- schema-def:principal_binding_expression --> `$defs/principal_binding_expression`: principal-only binding expression used when access-policy actor subjects identify the authenticated principal.
- <!-- schema-def:binding_map --> `$defs/binding_map`: shared schema component used by authored source or compiled output.
- <!-- schema-def:binding_value --> `$defs/binding_value`: explicit binding value object using either `from` for binding expressions or `value` for literal JSON.
- <!-- schema-def:authored_value --> `$defs/authored_value`: explicit authored value object using either `from` for fixture expressions or `value` for literal JSON.
- <!-- schema-def:scalar --> `$defs/scalar`: shared schema component used by authored source or compiled output.
- <!-- schema-def:authored_behavior_scenario --> `$defs/authored_behavior_scenario`: human-authored source object for this resource or nested contract.
- <!-- schema-def:system_under_test_ref --> `$defs/system_under_test_ref`: typed reference definition for its namespace.
- <!-- schema-def:behavior_scenario_ref --> `$defs/behavior_scenario_ref`: typed reference definition for its namespace.
- <!-- schema-def:scheduled_adapter --> `$defs/scheduled_adapter`: external-interface adapter, invocation, input, or response contract component.
- <!-- schema-def:slot_binding --> `$defs/slot_binding`: renderer contract component scoped to HTML and/or Textual invocations.
- <!-- schema-def:no_local_effect --> `$defs/no_local_effect`: explicit no-local-effect outcome coverage contract component.
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
- <!-- schema-def:state_machine_signal --> `$defs/state_machine_signal`: state-machine signal contract with required JSON Schema `payload_schema`; empty payloads use an explicit empty object schema.
- <!-- schema-def:state_machine_signal_payload_schema --> `$defs/state_machine_signal_payload_schema`: explicit object-shaped JSON Schema for a state-machine signal payload.
- <!-- schema-def:state_machine_state_query_binding --> `$defs/state_machine_state_query_binding`: state-machine state query binding contract component.
- <!-- schema-def:state_machine_ref --> `$defs/state_machine_ref`: typed reference definition for its namespace.
- <!-- schema-def:state_machine_transition --> `$defs/state_machine_transition`: state-machine contract component.
- <!-- schema-def:text_resource_ref --> `$defs/text_resource_ref`: typed reference definition for its namespace.
- <!-- schema-def:textual_renderer_contract --> `$defs/textual_renderer_contract`: Textual renderer contract component.
- <!-- schema-def:textual_renderer_layout --> `$defs/textual_renderer_layout`: Textual renderer contract component.
- <!-- schema-def:textual_renderer_presentation --> `$defs/textual_renderer_presentation`: Textual renderer contract component.
- <!-- schema-def:textual_viewport --> `$defs/textual_viewport`: Textual renderer contract component.
- <!-- schema-def:textual_widget --> `$defs/textual_widget`: Textual renderer contract component.
- <!-- schema-def:then --> `$defs/then`: shared schema component used by authored source or compiled output.
- <!-- schema-def:schema_map --> `$defs/schema_map`: map from field or parameter names to JSON Schema fragments.
- <!-- schema-def:html_route_adapter --> `$defs/html_route_adapter`: HTML renderer contract component.
- <!-- schema-def:value_map --> `$defs/value_map`: shared schema component used by authored source or compiled output.
- <!-- schema-def:state_machine_state_assertion --> `$defs/state_machine_state_assertion`: state_machine_state assertion contract component.
- <!-- schema-def:state_machine_state_id --> `$defs/state_machine_state_id`: local state-machine state id within one `state_machine`.
- <!-- schema-def:html_renderer_contract --> `$defs/html_renderer_contract`: HTML renderer contract component.
- <!-- schema-def:html_renderer_layout --> `$defs/html_renderer_layout`: HTML renderer contract component.
- <!-- schema-def:html_renderer_presentation --> `$defs/html_renderer_presentation`: HTML renderer contract component.
- <!-- schema-def:html_slot --> `$defs/html_slot`: HTML renderer contract component.
- <!-- schema-def:webhook_adapter --> `$defs/webhook_adapter`: external-interface adapter, invocation, input, or response contract component.
- <!-- schema-def:when --> `$defs/when`: shared schema component used by authored source or compiled output.
- <!-- schema-def:worker_adapter --> `$defs/worker_adapter`: external-interface adapter, invocation, input, or response contract component.
- <!-- schema-def:workflow_outcome --> `$defs/workflow_outcome`: BPMN-like workflow input, activity, gateway, sequence-flow, retry, output, or binding contract component.
- <!-- schema-def:workflow_sequence_flows --> `$defs/workflow_sequence_flows`: BPMN-like workflow input, activity, gateway, sequence-flow, retry, output, or binding contract component.
- <!-- schema-def:workflow_outputs --> `$defs/workflow_outputs`: BPMN-like workflow input, activity, gateway, sequence-flow, retry, output, or binding contract component.
- <!-- schema-def:workflow_ref --> `$defs/workflow_ref`: typed reference definition for its namespace.
- <!-- schema-def:workflow_activity_id --> `$defs/workflow_activity_id`: local workflow activity id within one workflow.
- <!-- schema-def:workflow_gateway_id --> `$defs/workflow_gateway_id`: local workflow gateway id within one workflow.
- <!-- schema-def:workflow_sequence_flow_id --> `$defs/workflow_sequence_flow_id`: local workflow sequence-flow id within one workflow.
- <!-- schema-def:workflow_retry_policy --> `$defs/workflow_retry_policy`: BPMN-like workflow input, activity, gateway, sequence-flow, retry, output, or binding contract component.
- <!-- schema-def:workflow_sequence_flow --> `$defs/workflow_sequence_flow`: BPMN-like workflow input, activity, gateway, sequence-flow, retry, output, or binding contract component.
- <!-- schema-def:workflow_sequence_flow_source_ref --> `$defs/workflow_sequence_flow_source_ref`: workflow sequence-flow source reference to a local `workflow_activity_id` or `workflow_gateway_id`.
- <!-- schema-def:workflow_sequence_flow_target_ref --> `$defs/workflow_sequence_flow_target_ref`: workflow sequence-flow target reference to a local `workflow_activity_id`, local `workflow_gateway_id`, or terminal workflow outcome.
- <!-- schema-def:workflow_activity --> `$defs/workflow_activity`: BPMN-like workflow activity contract component; currently command-invoking.
- <!-- schema-def:workflow_gateway --> `$defs/workflow_gateway`: BPMN-like workflow gateway contract component.
- <!-- schema-def:workflow_input_source --> `$defs/workflow_input_source`: BPMN-like workflow input, activity, gateway, sequence-flow, retry, output, or binding contract component.
- <!-- schema-def:schema_ref --> `$defs/schema_ref`: typed reference definition for its namespace.
- <!-- schema-def:authored_schema --> `$defs/authored_schema`: human-authored source object for this resource or nested contract.
- <!-- schema-def:feature_tag --> `$defs/feature_tag`: unprefixed behavior-scenario feature grouping tag, not a typed reference.
- <!-- schema-def:data_refresh_signal_name --> `$defs/data_refresh_signal_name`: state-machine-local data-refresh signal identifier.
- <!-- schema-def:state_machine_local_signals --> `$defs/state_machine_local_signals`: state-machine contract component.
- <!-- schema-def:viewport_id --> `$defs/viewport_id`: local identifier contract component.
- <!-- schema-def:region_id --> `$defs/region_id`: local HTML layout region identifier within one `state_machine_state`.
- <!-- schema-def:container_id --> `$defs/container_id`: local Textual layout container identifier within one `state_machine_state`.
- <!-- schema-def:http_api_adapter --> `$defs/http_api_adapter`: external-interface adapter, invocation, input, or response contract component.
- <!-- schema-def:authorization_assertion --> `$defs/authorization_assertion`: access-policy contract component.
- <!-- schema-def:access_policy_condition --> `$defs/access_policy_condition`: access-policy rule predicate component used by policy `environment` and `rules` lists.
- <!-- schema-def:authorization_decision_assertion --> `$defs/authorization_decision_assertion`: access-policy contract component.
- <!-- schema-def:access_policy_subject --> `$defs/access_policy_subject`: access-policy subject component used by policy `subject` fields.
- <!-- schema-def:access_policy_resource --> `$defs/access_policy_resource`: access-policy resource component used by policy `resource` fields.
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
- <!-- schema-def:media_asset_item --> `$defs/media_asset_item`: compiled-output object for this resource or nested contract.
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
- <!-- schema-def:state_machine_state --> `$defs/state_machine_state`: compiled state_machine_state object.
- <!-- schema-def:workflow_item --> `$defs/workflow_item`: compiled-output object for this resource or nested contract.
- <!-- schema-def:schema_item --> `$defs/schema_item`: compiled-output object for this resource or nested contract.
