# Spec Ontology

This glossary is the vocabulary contract for the authored-source, layer-pruned authored-source, and compiled-output schemas. The authored schema describes sparse human-authored input. Layer-pruned authored schemas are generated from the same source schema and hide sections outside the active authoring layers. The compiled schema describes normalized output in `spec/generated/compiled/spec.yaml`, including generated references, derived events, derived routes, endpoint expansions, and expanded empty-collection states.

## Top-Level Resource Kinds

- <!-- top-level:assets --> `assets`: content assets with media kind, asset role, placeholders, and source-backed resolution when present.
- <!-- top-level:content_cases --> `content_cases`: named content-source examples for dynamic text and asset content.
- <!-- top-level:data_contracts --> `data_contracts`: first-class typed payload/data contracts referenced by type expressions with `data_contract.*` ids.
- <!-- top-level:entry_points --> `entry_points`: external invocation declarations split into explicit adapter and target objects. An entry point is an externally invokable adapter plus a target.
- <!-- top-level:events --> `events`: durable domain/application or system events with payload_schema contracts and compiled emitters.
- <!-- top-level:facts --> `facts`: reusable model presence/absence setup or assertion facts; facts are not broad domain invariants.
- <!-- top-level:fixtures --> `fixtures`: named seed data namespaces used by test cases, facts, content cases, and render audit cases.
- <!-- top-level:models --> `models`: PascalCase product/domain entity type names and lifecycle declarations. Models are not ORM models, API contracts, generated implementation classes, or storage schemas.
- <!-- top-level:operations --> `operations`: executable product operations with typed input, effects, outcomes, emitted events, and optional explicit authorization mapping.
- <!-- top-level:authorization_policies --> `authorization_policies`: authorization policies with subjects, authorization targets, conditions, and effect.
- <!-- top-level:project --> `project`: the project slug for the specification workspace.
- <!-- top-level:refs --> `refs`: compiled-only index of generated references used by projections and tests.
- <!-- top-level:render_profiles --> `render_profiles`: global HTML and Textual viewport profiles for audit/golden-image rendering; state-machine render audit cases do not reference profiles directly.
- <!-- top-level:state_machines --> `state_machines`: UI/component state-machine contracts with context, query invocations, view states, operation invocations, transitions, signals, child state machines, and sync rules.
- <!-- top-level:test_cases --> `test_cases`: formal behavior test cases with subject_ref, given, when, and then contracts.
- <!-- top-level:text_resources --> `text_resources`: text resources used by state-machine slots and content-source projections.
- <!-- top-level:workflows --> `workflows`: asynchronous or long-running flows with workflow triggers, steps, input bindings, exclusive outcome routes, and outcomes.

## ID Namespaces

- `asset_ref`: `asset.<domain>...`; asset declarations, generated asset slots, content cases, and audit evidence.
- `content_case_ref`: `content_case.<domain>...`; content source examples.
- `data_contract_ref`: `data_contract.<domain>...`; reusable typed payload/data contracts in `type_expr.data_contract`.
- `data_signal_name`: local state-machine data-signal name; authored sources do not use global-looking `data_signal.*` references for local data signals.
- `entry_point_ref`: `entry_point.<adapter-or-target>.<domain>...`; entry-point declarations, entry-point delegation targets, and test-case `open_entry_point` or `call_entry_point` actions.
- `event_ref`: `event.<domain>...`; durable domain/application event declarations, operation emissions, workflow triggers, and test-case event assertions.
- `fact_ref`: `fact.<domain>...`; named domain or assertion facts referenced through `fact_use.ref`.
- `fixture_ref`: `fixture.<domain>...`; seed data fixtures used by test cases, content cases, facts, and render audit cases.
- `feature_tag`: unprefixed dotted feature grouping label used by test cases and generated feature files; it is not a typed reference.
- `instance_id`: local child state-machine instance id within a composed view state.
- `message_name`: local state-machine message name; authored sources do not use global-looking `message.*` references for local messages.
- `model_ref`: `PascalCase`; model references are the sole collection-prefix exception because model ids are also type names.
- `operation_ref`: `operation.<domain>...`; operation declarations, state-machine operation/query invocations, workflow steps, entry-point operation targets, and test-case assertions.
- `operation_invocation_id`: local view-state operation invocation name; authored sources do not use global-looking `operation_invocation.*` references for local invocation keys.
- `query_invocation_id`: local state-machine or view-state query invocation name; authored sources do not use global-looking `query_invocation.*` references for local invocation keys.
- `region_id`: local HTML layout region id within one view state.
- `authorization_policy_ref`: `authorization_policy.<domain>...`; authorization-policy declarations, `operation.authorization.policy`, entry-point `authorization_policy` fields, generated authorization projections, and authorization test assertions.
- `render_profile_ref`: `render_profile.<domain>...`; named HTML/Textual viewport profiles.
- `rule_id`: local state-machine signal-sync rule id within one composed view state.
- `state_machine_ref`: `state_machine.<domain>...`; state-machine declarations, `child_state_machines`, state-machine entry-point targets, and test-case state-machine assertions.
- `test_case_ref`: `test_case.<domain>...`; formal test-case declarations and generated feature tags.
- `text_ref`: `text.<domain>...`; text resource declarations, generated text slots, content cases, and content source signatures.
- `container_id`: local Textual layout container id within one view state.
- `viewport_id`: local render-profile viewport id within `html_viewports` or `textual_viewports`.
- `workflow_ref`: `workflow.<domain>...`; workflow declarations, workflow entry-point targets, and generated workflow references.
- Generated refs use `asset`, `authorization_policy`, `cli_command`, `cli_response_handler`, `endpoint`, `entry_point_delegate`, `entry_point_target`, `local_signal_raise`, `operation_invocation`, `operation_outcome_route`, `query_invocation`, `query_outcome_route`, `route`, `runtime_response`, `screen`, `state_machine`, `surface`, `text`, and `workflow` buckets in compiled `refs`.

## Reference Types

- `subject_ref`: exactly one typed reference to the resource under test: `entry_point`, `event`, `operation`, `state_machine`, or `workflow`.
- `given`: setup contract split into `seed_fixtures` and `domain_facts`.
- `when`: one executable stimulus: `open_entry_point`, `call_entry_point`, `invoke_operation`, or `emit_event`.
- `then`: assertions for `outcome`, model existence, emitted/not-emitted events, workflow execution, authorization decisions, responses, invoked/enabled/forbidden operations, state-machine state, and `expected_facts`. Compiled state-machine assertions may add `surface`, `composition`, and top-level `requires`.
- `then.requires`: compiled-only derived projection dependencies for a state-machine assertion, split into `surfaces`, `text`, `assets`, `query_invocations`, and `operation_invocations`.
- `entry_point_adapter`: exactly one adapter object: `http_api`, `cli`, `webhook`, `scheduled`, `worker`, or `html_route`.
- `adapter input shape`: HTTP API input may use `path_params`, `query_params`, and `body`; HTML route input may use `path_params` and `query_params`; CLI input uses `args`; worker input uses `payload`; webhook input may use `path_params`, `query_params`, and `payload`; scheduled input has no external input sections.
- `entry_point_target`: exactly one target object: `operation`, `state_machine`, `workflow`, or `entry_point`.
- `operation/state-machine target bindings`: `target.operation.input_bindings` and `target.state_machine.input_bindings` bind adapter input into target input/context and must exactly cover the target fields. Workflow targets use `trigger_bindings` instead of `input_bindings`.
- `state-machine entry target`: `target.state_machine` must declare `renderer: html` or `renderer: textual`. HTML route entries can target only `html`; CLI entries can launch `html` or `textual`; the target state machine must declare the selected renderer in at least one view state.
- `workflow entry target`: `target.workflow.trigger_bindings` binds adapter input into workflow trigger payload fields and must exactly cover the workflow trigger payload.
- `entry-point delegation`: an entry point whose `target.entry_point.ref` points at another entry point. Delegation is general and is not CLI-to-HTTP-specific.
- `delegating entry point`: the outer entry point whose adapter exposes a facade and binds its input into the delegated entry point input shape.
- `delegated entry point`: the inner entry point that receives delegated invocation. Its entry-point `authorization_policy` and the delegated target operation's authorization outcomes remain visible to the delegating entry point.
- `target outcome response`: synchronous adapter response keyed by operation, workflow, state-machine, or delegated entry-point outcome names. HTTP API `responses` and delegated CLI `response_handlers` are target-outcome response surfaces.
- `adapter ingress response`: asynchronous adapter acknowledgement or disposition keyed by adapter-level outcomes, such as accepted, malformed, retry, reject, or dead-letter handling. Worker, webhook, and scheduled adapters use `ingress_responses` when receipt/disposition is distinct from target workflow execution outcomes.
- `response handler`: adapter-specific projection of a target or delegated response outcome.
- `CLI response handler`: maps a named response outcome to stdout, stderr, an exit code, and optionally a retry policy. It does not restate HTTP status classification when the delegated entry point is an HTTP API.
- `retry_safe`: explicit operation or entry-point marker permitting automatic retry of delegated, command, transition, or workflow execution. The default is false. Queries are retry-safe by operation kind.
- `retry safety`: validation that a retry policy applies only to a retry-safe delegated entry point and final target, a query, an explicitly retry-safe operation or entry point, or an ingress/disposition outcome where no target operation has executed. Transport retry, ingress retry, workflow retry, and operation retry are separate scopes.
- `workflow_route`: exclusive route target via `next_step`, `complete_as`, `fail_as`, `retry_policy`, or `dead_letter_as`.
- `state-machine context schema`: explicit `field_schema_map` for local machine context. Each context field declares `type`, `required`, and `nullable`; effects may set a context field to null only when that field is nullable.
- `context_present`: state-machine condition meaning the declared context field is present and non-null. Nullable context fields with a current `null` value are not present for this condition.
- `render profile`: global audit/golden-image viewport map. Renderable state machines require at least one render profile, and profiles must include viewport sets for each declared renderer surface (`html_viewports` for HTML, `textual_viewports` for Textual).
- `render audit case`: view-state-local visual evidence input. It supplies seed fixtures, optional context, optional fact references, and, for composed states, an exact child instance view-state vector; it never names render profiles directly.
- `content source`: a final resolver declaration where `text_resource.source_ref` or `asset.source_ref` equals the resource id. Final content resolvers require at least one matching `content_case`, and case args must exactly match the resource args.
- `rationale`: bounded plain text used on authored resources and on intentionally unobservable routes. Missing top-level resource rationale is filled by a deterministic compiler default.
- `Operation invocation`: local view-state use of a global operation, normally user/action-triggered, including input bindings and outcome routing. A renderer action binds to this local invocation, not directly to `operation_ref`.
- `Query invocation`: local state-machine or view-state use of a query operation for data loading or refresh, including input bindings, load policy, context updates, result binding, and outcome routing. State-machine-level queries load with `on_start`/`on_mount`; view-state-level queries load with `on_enter`.
- `Query invocation effect`: each query outcome route must update context, bind/cache a result, raise a local signal, or explicitly declare a scoped no-signal route. `result_binding.data_key` names the state-machine/view-state result data populated from a binding value.
- `Query refresh signal`: local data signal raised by a mutation or other invalidation route, such as `project_changed`, and consumed by `query_invocation.load.refresh_on`. Loaded/missing/error data signals should come from query outcomes after data has actually been bound or classified.
- `Empty/non-empty query routing`: array-valued query outcomes split the outcome route with `conditional_routes` using `when.result_empty` and `when.result_non_empty`. Both branches must be declared so empty collection states are reachable through authored routing rather than compiler length guesses.
- `Machine-scoped query ownership`: state-machine-level query invocations declare `result_scope: local`, `shared`, or `prefetch`. Machine-scoped result bindings that do not raise a signal must use shared/prefetch ownership with rationale, especially when a child machine also owns visible loading.
- `Field-slot source resolution`: every field slot resolves to exactly one context field or query result binding. A bound model or array item can feed field slots when the slot name exists on the result type; ambiguous or missing sources fail semantic validation.
- `Outcome route`: mapping from an operation/query outcome to context updates, result binding, a local signal raise, or explicit no-signal handling.
- `No-signal route`: explicit declaration that an outcome is covered but intentionally raises no local signal. It is not omission and does not suppress durable/global events. Reasons are scope-sensitive: response-surface handling needs a real adapter/renderer surface, query refresh needs explicit result/context refresh, result-bound-without-signal needs result binding or context/cache update, and failure outcomes must use proven response-surface handling or `intentionally_unobservable` with rationale.
- `Authored value`: explicit literal-or-fixture-reference value used in authored test, fact, content-case, and render-audit value maps. Use `{value: ...}` for JSON literals, including literal strings beginning with `$`, and `{from: $fixture...}` for fixture references. Raw `$...` strings are not interpreted as references.
- `Runtime root`: the first segment of a runtime expression. Operation and query input bindings may use `$context` and `$actor`; operation/query outcome routes may use `$outcome`, `$invocation`, and `$context`; operation event-emission mappings use `$input` and `$outcome`; workflow step bindings use `$trigger` and `$steps`; child context bindings use `$state_machine` for the parent machine context; entry response/delegation handlers use the adapter/delegation-specific `$input`, `$response`, or `$outcome` roots documented by that target. Authored test, fact, content-case, and render-audit value maps use `$fixture` for fixture data.
- `Actor/user binding source`: local operation invocations should bind actor-like input fields such as `actor_id`, `approved_by`, or `reviewer_id` from `$actor.id` or an explicit context source. Literal actor/user ids are linted because they usually hide fixture-only assumptions in authored UI behavior.
- `Local signal raise`: creation of a state-machine-local message or data signal.
- `Data signal`: local state-machine signal commonly used for data refresh, invalidation, loaded/missing states, or render updates. Data signals are not sent between child state-machine instances.
- `Message`: local state-machine signal that may also be sent between child state-machine instances where sync rules support message sends.
- `Durable event`: global event emitted by an operation outcome, distinct from local state-machine messages and data signals.
- `operation_outcome.emits`: durable/global event emission from an operation outcome. It is not used for local state-machine transition routing.
- `operation_invocation.outcome_routes.raise`: local state-machine message or data-signal raise after a user/action operation invocation.
- `query_invocation.outcome_routes.raise`: local state-machine message or data-signal raise after a query load or refresh outcome.
- `no_signal`: explicit local non-routing for an operation/query outcome.
- `signals`: local UI/component/state-machine signal contracts split into accepted message/data-signal maps and emitted message maps with `payload_schema` maps.
- `renderer_contracts`: view-state renderer declarations keyed by concrete target. `renderers.html` and `renderers.textual` each own target-local `layout`, `presentation`, and `style`.
- `renderer placement validation`: HTML slots and child machines must reference declared HTML `region_id`s; Textual widgets and child machines must reference declared Textual `container_id`s. Placement ids are layout ids, not field names.
- `resolver output escaping`: text, SVG, XML, and HTML resolvers must escape dynamic values before placing them in markup text or attributes. Plain-text outputs and alt text must not expose unescaped markup-sensitive values where they may be rendered into HTML/XML.
- `type_expr`: structured primitive, model, data_contract, array, map, nullable whole-value wrapper, enum, or inline object type expression. Object field presence and nullability are controlled only by `field_schema.required` and `field_schema.nullable`.
- `authorization_policy`: direct `authorization_policy_ref` fields identify the authorization policy applied to an entry point or authorization assertion. Operations use `authorization.policy` plus explicit `unauthenticated_as` and `forbidden_as` outcome mappings.
- `operation_authorization`: operation-local authorization mapping with `policy`, `unauthenticated_as`, and `forbidden_as`. The mapped names must be normal operation outcomes with `kind: failure`.
- `authorization policy`: reusable rule set that determines whether a subject may attempt an operation or entry point. Policies with identical subjects, effect, and conditions should be one `authorization_policy` with combined targets, not duplicated per operation.
- `authorization failure outcome`: named failure outcome produced before operation execution when authorization fails. These outcomes live in `operation.outcomes`; they are not a separate `errors` or `authorization_outcomes` collection.
- `unauthenticated`: authorization failure where no acceptable subject identity is available. HTTP examples conventionally map this outcome to `401`; CLI examples map it to stderr plus a nonzero exit code.
- `forbidden`: authorization failure where a subject identity exists but does not satisfy the authorization policy. HTTP examples conventionally map this outcome to `403`; CLI examples map it to stderr plus a nonzero exit code.
- `domain failure outcome`: operation outcome produced by operation execution or domain validation, such as `validation_failed` or `not_found`.
- `transition applicability`: lifecycle source-state check derived from `model.lifecycle.transitions[*]`, not authorization.
- `invalid_state`: transition applicability/domain failure outcome for lifecycle source-state mismatch. It is not an authorization failure and should be asserted with `operation_outcome` or `entry_point_response`, not `authorization_denial`.
- `authorization_condition.model_state`: explicit author-authored access-control condition when model state is truly part of who may attempt an operation. The compiler does not generate this condition from lifecycle transition `from` states; lifecycle source-state mismatch remains transition applicability and maps to `invalid_state`.

## Operation Invocation Example

```yaml
view_states:
  ready:
    operation_invocations:
      approve:
        operation: operation.project.approve
        input_bindings:
          project_id:
            from: $context.project_id
        outcome_routes:
          approved:
            raise:
              data_signal: project_changed
          invalid_state:
            raise:
              message: show_invalid_state
              payload_bindings:
                message:
                  from: $outcome.result.message
          forbidden:
            no_signal:
              reason: handled_by_response_surface
              rationale: The response surface reports authorization failure.
```

## Query Invocation Example

```yaml
query_invocations:
  load_project:
    operation: operation.project.read
    input_bindings:
      project_id:
        from: $context.project_id
    load:
      on_enter: true
      refresh_on:
      - data_signal: project_changed
    outcome_routes:
      found:
        result_binding:
          data_key: project
          from:
            from: $outcome.result
        context_updates:
          project_id:
            from: $invocation.input.project_id
        raise:
          data_signal: project_loaded
      not_found:
        raise:
          message: show_project_not_found
      unavailable:
        no_signal:
          reason: intentionally_unobservable
          rationale: The query result is not shown while the current view keeps its existing data.
```

## Collection Query Routing

```yaml
query_invocations:
  list_projects:
    result_scope: local
    operation: operation.project.list
    input_bindings:
      workspace_id:
        from: $context.workspace_id
    outcome_routes:
      listed:
        conditional_routes:
        - when:
            result_empty: true
          result_binding:
            data_key: projects
            from:
              from: $outcome.result
          raise:
            data_signal: project_collection_empty
        - when:
            result_non_empty: true
          result_binding:
            data_key: projects
            from:
              from: $outcome.result
          raise:
            data_signal: projects_loaded
```

## Authoring Layers

Layers are compile/validate guardrails and are not written into `spec/generated/compiled/spec.yaml`.

- `core`: `fixtures`, `facts`, `data_contracts`, `models`, `authorization_policies`, `operations`, `events`, and `test_cases`.
- `http`: HTTP API entry-point adapters.
- `events`: webhook entry-point adapters.
- `workflow`: `workflows` plus CLI, worker, and scheduled entry-point adapters.
- `ui`: `state_machines`, `text_resources`, `assets`, `content_cases`, `render_profiles`, and HTML route entry-point adapters.
- `html`: HTML renderer contracts and `render_profile.html_viewports`.
- `textual`: Textual renderer contracts and `render_profile.textual_viewports`.
- Layer normalization always includes `core`; selecting `html` or `textual` also includes `ui`. Aliases normalize as `api -> http`, `cli -> workflow`, `tui -> textual`, and `all`/`full` -> every layer.
- Common layer-pruned authored schemas are generated for `core`, `core_http`, `core_events`, `core_workflow`, `core_ui_textual`, `core_ui_html`, and `full`.

## Runtime Roots

| Context | Valid roots |
| --- | --- |
| Operation invocation `input_bindings` | `$context`, `$actor` |
| Operation invocation outcome routes | `$outcome`, `$invocation`, `$context` |
| Query invocation `input_bindings` | `$context`, `$actor` |
| Query invocation outcome routes | `$outcome`, `$invocation`, `$context` |
| State-machine transition effects | `$message`, `$context` |
| Child state-machine `context_bindings` and selected-state conditions | `$state_machine` for parent state-machine context |
| Operation event-emission payload mappings | `$input`, `$outcome` |
| Entry-point operation/state-machine/delegation target bindings | `$input` |
| Entry-point workflow `trigger_bindings` | `$input` |
| HTTP API response bodies | `$outcome.result` only |
| CLI operation response handlers | `$input`, `$outcome` |
| CLI delegated response handlers | `$input`, `$response` |
| Workflow step `input_bindings` | `$trigger`, `$steps` |
| Authored test/fact/content-case/render-audit value maps | `$fixture` |

## Visual Audit Coverage

- `visual_evidence_set`: a shared list of generated diagrams or rendered captures (`*.svg` diagrams/captures and `*.png` screenshots) that visually evidence one or more compiled spec paths.
- `required_visual_path`: a compiled spec leaf path that must have at least one `visual_evidence_set`; missing required paths fail validation.
- `required_visual_text_witness`: a stable token that must appear in visible SVG text for a required visual path whose value is explicitly rendered as text. These witnesses are intentionally limited to durable ids, refs, field/type labels, and other renderer-owned tokens; they do not audit hidden SVG metadata, incidental prose, or render-only pixels.
- `optional_visual_path`: a compiled spec leaf path that may have visual evidence but is allowed to be absent from diagrams and render captures.
- `missing_required_visual_path`: a required visual path with no diagram or render-capture evidence.
- `optional_visual_path_not_shown`: an optional visual path with no diagram or render-capture evidence; this is reported but does not fail validation.
- `non_visual_path`: compiled metadata that is intentionally outside visual-audit scope, such as `project` workspace metadata or the compiled `refs` index.
- `render_presence`: resource-level visibility in actual render captures, reported as `rendered` or `not_rendered` for assets, text resources, fixtures, facts, and content cases.

Audit validation fails when any `missing_required_visual_path` exists or when a declared `required_visual_text_witness` is absent from its SVG evidence set. Required paths without a text witness are still required to have diagram or render-capture evidence, but their semantics are audited through the visual artifact rather than a machine-readable token.

The visual audit includes state-machine and composition diagrams, entry-point and workflow flowcharts, plus operation flows. Operation flows are chronological branching data flows for input, authorization, touched resources, outcomes, and emitted events; other diagrams reference operations compactly instead of repeating the same cards.

## Runtime Expression Namespaces

- `$fixture.<path>` reads merged seed fixture data in test cases, facts, content cases, and render audit cases.
- `$state_machine.<field>` reads parent state-machine context in child state-machine context bindings and composition conditions.
- `$message.<field>` reads the current state-machine message payload in transition effects and sync sends.
- `$context.<field>` reads current state-machine context in transition effects, operation/query invocation input bindings, and local outcome-route signal payload binding.
- `$input.path_params.<field>` reads HTTP API or HTML route path parameters in entry target or delegation bindings.
- `$input.query_params.<field>` reads HTTP API or HTML route query parameters in entry target or delegation bindings.
- `$input.body.<field>` reads HTTP request body fields in entry target or delegation bindings.
- `$input.args.<field>` reads CLI argument fields in entry target or delegation bindings.
- `$input.payload[.<field>]` reads worker or webhook payload data in entry target or workflow trigger bindings.
- `$input.<field>` reads operation input during operation event emission mapping.
- `$outcome.result[.<field>]` reads operation outcome result during response, event emission, and local outcome-route mapping.
- `$outcome.kind` reads the operation outcome kind during local outcome-route signal payload binding.
- `$invocation.input.<field>` reads the bound operation invocation input during local outcome-route signal payload binding.
- `$response.body[.<field>]` reads the delegated entry-point response body inside delegating CLI `response_handlers`.
- `$trigger.payload[.<field>]` reads workflow trigger payload.
- `$steps.<step>.outcomes.<outcome>.result[.<field>]` reads previous workflow step result.

Runtime expressions appear inside binding objects. Authored value maps use `{from: ...}` for these expressions and `{value: ...}` for literal JSON values; a raw string beginning with `$` is a literal only when wrapped with `value`.
- The shared grammar is `$source.path.to.field`; semantic validation checks available roots and declared field paths for each context.

## Generated Artifacts

- `spec/generated/compiled/spec.yaml`: compiled-output spec with normalized IDs, generated refs, derived events, and expanded empty collections.
- `spec/generated/agent_prompts/{pm_design,test,dev,review}.md`: layer-specific role prompts.
- `spec/generated/behavior/fixtures.yaml`: seed fixture projection.
- `spec/generated/behavior/test_cases.yaml`: semantic test-case projection.
- `spec/generated/product_interfaces/http.openapi.yaml`: OpenAPI projection generated only from HTTP API entry points.
- `spec/generated/product_interfaces/events.asyncapi.yaml`: AsyncAPI projection for durable top-level events, webhooks, workers, and event-triggered workflows; state-machine signals are not projected as domain events.
- `spec/generated/product_interfaces/html.routes.json`: UI route projection generated from UI entry points.
- `spec/generated/product_interfaces/html.state_machines.json`: state-machine HTML/Textual renderer contract projection, including composition layout and renderer-specific style contracts.
- `spec/generated/product_interfaces/textual.projection.py`: Textual renderer projection generated from `renderers.textual.presentation` widgets, `renderers.textual.style`, and `renderers.textual.layout` containers.
- `spec/generated/product_interfaces/workflow.cwl.yaml`: CWL projection generated for workflow/CLI/worker-relevant execution graphs.
- `spec/generated/product_interfaces/authorization_policies.json`: authorization-policy projection with operation authorization mappings and entry-point policies.
- `spec/generated/content_resolvers/{signatures.py,stubs.py,cases.yaml}`: documented content-resolution contracts and examples.
- `spec/generated/test_adapters/python_refs.py`: Python constants for resource and generated reference IDs.
- `spec/generated/test_adapters/driver_protocol.py`: BDD driver protocol.
- `spec/generated/test_adapters/pytest_bdd_steps.py`: BDD step glue.
- `spec/generated/test_adapters/pytest_bdd_features/{feature}.feature`: generated behavior feature files.
- `spec/generated/audit_evidence/entrypoints/{adapter}/{entry_point}/flow.svg`: entry-point flow diagrams grouped by adapter kind.
- `spec/generated/audit_evidence/coverage.yaml`: generated visual coverage index mapping compiled spec paths to diagram and render-capture evidence, including explicit render coverage gaps for assets, text, fixtures, facts, and content cases.
- `spec/generated/audit_evidence/workflows/{workflow}/flow.svg`: workflow flow diagrams.
- `spec/generated/audit_evidence/operations/{operation}/flow.svg`: chronological operation flows showing input, authorization, touched resources, outcomes, and emitted events.
- `spec/generated/audit_evidence/state_machines/{state_machine}/state_machine.svg`: state-machine diagrams.
- `spec/generated/audit_evidence/state_machines/{state_machine}/view_states/{view_state}/composition.svg`: composed state-machine view-state diagrams.
- `spec/generated/audit_evidence/state_machines/{state_machine}/view_states/{view_state}/{text.yaml,fixtures.yaml,assets/*}`: view-state-scoped audit inputs.
- `spec/generated/audit_evidence/state_machines/{state_machine}/view_states/{view_state}/renders/*`: HTML/Textual view-state render source and captures.
- `spec/generated/audit_evidence/state_machines/{state_machine}/view_states/{view_state}/cases/{case}/**`: audit-case scoped inputs and render captures.

## Schema Definition Inventory

Each `$defs` entry in the JSON Schemas is documented exactly once here. The schema-inventory test treats these hidden markers as the authoritative inventory.

- <!-- schema-def:aria_role --> `$defs/aria_role`: renderer contract component scoped to HTML and/or Textual targets.
- <!-- schema-def:asset_placeholder --> `$defs/asset_placeholder`: shared schema component used by authored source or compiled output.
- <!-- schema-def:asset_ref --> `$defs/asset_ref`: typed reference definition for its namespace.
- <!-- schema-def:render_profile_ref --> `$defs/render_profile_ref`: typed reference definition for its namespace.
- <!-- schema-def:authored_asset --> `$defs/authored_asset`: human-authored source object for this resource or nested contract.
- <!-- schema-def:authored_render_profile --> `$defs/authored_render_profile`: human-authored source object for this resource or nested contract.
- <!-- schema-def:authored_child_state_machine --> `$defs/authored_child_state_machine`: human-authored source object for this resource or nested contract.
- <!-- schema-def:authored_content_case --> `$defs/authored_content_case`: human-authored source object for this resource or nested contract.
- <!-- schema-def:authored_text_resource --> `$defs/authored_text_resource`: human-authored source object for this resource or nested contract.
- <!-- schema-def:authored_entry_point --> `$defs/authored_entry_point`: human-authored source object for this resource or nested contract.
- <!-- schema-def:authored_event --> `$defs/authored_event`: human-authored source object for this resource or nested contract.
- <!-- schema-def:authored_fact --> `$defs/authored_fact`: human-authored source object for this resource or nested contract.
- <!-- schema-def:authored_fixture --> `$defs/authored_fixture`: human-authored source object for this resource or nested contract.
- <!-- schema-def:authored_model --> `$defs/authored_model`: human-authored source object for this resource or nested contract.
- <!-- schema-def:authored_authorization_policy --> `$defs/authored_authorization_policy`: human-authored source object for this resource or nested contract.
- <!-- schema-def:authored_operation --> `$defs/authored_operation`: human-authored source object for this resource or nested contract.
- <!-- schema-def:authored_state_machine --> `$defs/authored_state_machine`: human-authored source object for this resource or nested contract.
- <!-- schema-def:authored_view_state --> `$defs/authored_view_state`: human-authored source object for this resource or nested contract.
- <!-- schema-def:authored_workflow --> `$defs/authored_workflow`: human-authored source object for this resource or nested contract.
- <!-- schema-def:rationale --> `$defs/rationale`: shared schema component used by authored source or compiled output.
- <!-- schema-def:child_state_machine_selected --> `$defs/child_state_machine_selected`: state-machine contract component.
- <!-- schema-def:cli_adapter --> `$defs/cli_adapter`: entry-point adapter, target, input, or response contract component.
- <!-- schema-def:cli_adapter_input --> `$defs/cli_adapter_input`: entry-point adapter, target, input, or response contract component.
- <!-- schema-def:cli_output --> `$defs/cli_output`: CLI response handler output text and bindings.
- <!-- schema-def:cli_response_handler --> `$defs/cli_response_handler`: CLI response handler for a named response outcome.
- <!-- schema-def:cli_response_handlers --> `$defs/cli_response_handlers`: map from named response outcomes to CLI response handlers.
- <!-- schema-def:context_condition --> `$defs/context_condition`: state-machine contract component.
- <!-- schema-def:content_args --> `$defs/content_args`: shared schema component used by authored source or compiled output.
- <!-- schema-def:content_case_ref --> `$defs/content_case_ref`: typed reference definition for its namespace.
- <!-- schema-def:content_source_ref --> `$defs/content_source_ref`: typed reference definition for its namespace.
- <!-- schema-def:context_bindings --> `$defs/context_bindings`: shared schema component used by authored source or compiled output.
- <!-- schema-def:context_set_effect --> `$defs/context_set_effect`: state-machine contract component.
- <!-- schema-def:entry_operation_target --> `$defs/entry_operation_target`: entry-point adapter, target, input, or response contract component.
- <!-- schema-def:entry_point_adapter --> `$defs/entry_point_adapter`: entry-point adapter, target, input, or response contract component.
- <!-- schema-def:entry_point_delegate_input_bindings --> `$defs/entry_point_delegate_input_bindings`: adapter-input-shaped bindings from a delegating entry point into a delegated entry point.
- <!-- schema-def:entry_point_delegate_target --> `$defs/entry_point_delegate_target`: entry-point target variant that delegates to another entry point.
- <!-- schema-def:entry_point_ref --> `$defs/entry_point_ref`: typed reference definition for its namespace.
- <!-- schema-def:entry_point_target --> `$defs/entry_point_target`: entry-point adapter, target, input, or response contract component.
- <!-- schema-def:entry_point_response --> `$defs/entry_point_response`: entry-point adapter, target, input, or response contract component.
- <!-- schema-def:entry_point_response_value --> `$defs/entry_point_response_value`: entry-point adapter, target, input, or response contract component.
- <!-- schema-def:entry_point_responses --> `$defs/entry_point_responses`: entry-point adapter, target, input, or response contract component.
- <!-- schema-def:entry_point_retry_policy --> `$defs/entry_point_retry_policy`: bounded automatic retry policy for retry-safe delegated entry points.
- <!-- schema-def:entry_state_machine_target --> `$defs/entry_state_machine_target`: entry-point adapter, target, input, or response contract component.
- <!-- schema-def:entry_workflow_target --> `$defs/entry_workflow_target`: entry-point adapter, target, input, or response contract component.
- <!-- schema-def:event_ref --> `$defs/event_ref`: typed reference definition for its namespace.
- <!-- schema-def:fact --> `$defs/fact`: shared schema component used by authored source or compiled output.
- <!-- schema-def:fact_ref --> `$defs/fact_ref`: typed reference definition for its namespace.
- <!-- schema-def:fact_use --> `$defs/fact_use`: shared schema component used by authored source or compiled output.
- <!-- schema-def:field_name --> `$defs/field_name`: shared schema component used by authored source or compiled output.
- <!-- schema-def:local_name --> `$defs/local_name`: local identifier contract component.
- <!-- schema-def:slot_name --> `$defs/slot_name`: local identifier contract component.
- <!-- schema-def:outcome_name --> `$defs/outcome_name`: local identifier contract component.
- <!-- schema-def:rule_id --> `$defs/rule_id`: local identifier contract component.
- <!-- schema-def:role_name --> `$defs/role_name`: local identifier contract component.
- <!-- schema-def:audit_case_id --> `$defs/audit_case_id`: local identifier contract component.
- <!-- schema-def:field_schema --> `$defs/field_schema`: structured type-expression and object-schema contract component.
- <!-- schema-def:field_schema_map --> `$defs/field_schema_map`: structured type-expression and object-schema contract component.
- <!-- schema-def:fixture_ref --> `$defs/fixture_ref`: typed reference definition for its namespace.
- <!-- schema-def:given --> `$defs/given`: shared schema component used by authored source or compiled output.
- <!-- schema-def:html_element --> `$defs/html_element`: HTML renderer contract component.
- <!-- schema-def:html_viewport --> `$defs/html_viewport`: HTML renderer contract component.
- <!-- schema-def:instance_id --> `$defs/instance_id`: shared schema component used by authored source or compiled output.
- <!-- schema-def:json_value --> `$defs/json_value`: shared schema component used by authored source or compiled output.
- <!-- schema-def:textual_layout_container --> `$defs/textual_layout_container`: Textual renderer contract component.
- <!-- schema-def:html_layout_region --> `$defs/html_layout_region`: HTML renderer contract component.
- <!-- schema-def:html_layout_root --> `$defs/html_layout_root`: HTML renderer contract component.
- <!-- schema-def:message_name --> `$defs/message_name`: state-machine-local message identifier.
- <!-- schema-def:signal_sync_action --> `$defs/signal_sync_action`: state-machine signal synchronization contract component.
- <!-- schema-def:signal_sync_assertion --> `$defs/signal_sync_assertion`: state-machine signal synchronization contract component.
- <!-- schema-def:signal_sync_rule --> `$defs/signal_sync_rule`: state-machine signal synchronization contract component.
- <!-- schema-def:signal_sync_send_effect --> `$defs/signal_sync_send_effect`: state-machine signal synchronization contract component.
- <!-- schema-def:signal_sync_trigger --> `$defs/signal_sync_trigger`: state-machine signal synchronization contract component.
- <!-- schema-def:model_ref --> `$defs/model_ref`: typed reference definition for its namespace.
- <!-- schema-def:object_schema --> `$defs/object_schema`: structured type-expression and object-schema contract component.
- <!-- schema-def:operation_authorization --> `$defs/operation_authorization`: explicit operation authorization policy and mapped authorization failure outcomes.
- <!-- schema-def:operation_emit --> `$defs/operation_emit`: shared schema component used by authored source or compiled output.
- <!-- schema-def:operation_invocation_id --> `$defs/operation_invocation_id`: local view-state operation invocation identifier.
- <!-- schema-def:operation_outcome --> `$defs/operation_outcome`: shared schema component used by authored source or compiled output.
- <!-- schema-def:operation_outcomes --> `$defs/operation_outcomes`: shared schema component used by authored source or compiled output.
- <!-- schema-def:operation_ref --> `$defs/operation_ref`: typed reference definition for its namespace.
- <!-- schema-def:authorization_policy_ref --> `$defs/authorization_policy_ref`: typed reference definition for its namespace.
- <!-- schema-def:python_class_name --> `$defs/python_class_name`: shared schema component used by authored source or compiled output.
- <!-- schema-def:python_identifier --> `$defs/python_identifier`: shared schema component used by authored source or compiled output.
- <!-- schema-def:query_invocation_id --> `$defs/query_invocation_id`: local state-machine or view-state query invocation identifier.
- <!-- schema-def:query_invocation_load_policy --> `$defs/query_invocation_load_policy`: query invocation load and refresh trigger policy.
- <!-- schema-def:query_result_condition --> `$defs/query_result_condition`: explicit query-result shape condition for empty/non-empty array routing.
- <!-- schema-def:query_result_binding --> `$defs/query_result_binding`: explicit query result binding to a named local `data_key`.
- <!-- schema-def:renderer_contracts --> `$defs/renderer_contracts`: renderer contract component scoped to HTML and/or Textual targets.
- <!-- schema-def:runtime_expression --> `$defs/runtime_expression`: shared schema component used by authored source or compiled output.
- <!-- schema-def:runtime_bindings --> `$defs/runtime_bindings`: shared schema component used by authored source or compiled output.
- <!-- schema-def:binding_value --> `$defs/binding_value`: explicit binding value object using either `from` for runtime expressions or `value` for literal JSON.
- <!-- schema-def:authored_value --> `$defs/authored_value`: explicit authored value object using either `from` for runtime expressions or `value` for literal JSON.
- <!-- schema-def:scalar --> `$defs/scalar`: shared schema component used by authored source or compiled output.
- <!-- schema-def:authored_test_case --> `$defs/authored_test_case`: human-authored source object for this resource or nested contract.
- <!-- schema-def:subject_ref --> `$defs/subject_ref`: typed reference definition for its namespace.
- <!-- schema-def:test_case_ref --> `$defs/test_case_ref`: typed reference definition for its namespace.
- <!-- schema-def:scheduled_adapter --> `$defs/scheduled_adapter`: entry-point adapter, target, input, or response contract component.
- <!-- schema-def:slot_binding --> `$defs/slot_binding`: renderer contract component scoped to HTML and/or Textual targets.
- <!-- schema-def:local_no_signal_route --> `$defs/local_no_signal_route`: explicit local non-routing outcome coverage contract component.
- <!-- schema-def:state_machine_operation_invocation --> `$defs/state_machine_operation_invocation`: state-machine operation invocation contract component.
- <!-- schema-def:state_machine_operation_outcome_route --> `$defs/state_machine_operation_outcome_route`: state-machine operation invocation outcome-route contract component.
- <!-- schema-def:state_machine_operation_outcome_routes --> `$defs/state_machine_operation_outcome_routes`: state-machine operation invocation outcome-route map.
- <!-- schema-def:state_machine_query_invocation --> `$defs/state_machine_query_invocation`: state-machine query invocation contract component.
- <!-- schema-def:state_machine_query_conditional_route --> `$defs/state_machine_query_conditional_route`: conditional query route branch with result-shape guard and normal query route effects.
- <!-- schema-def:state_machine_query_outcome_route --> `$defs/state_machine_query_outcome_route`: state-machine query invocation outcome-route contract component.
- <!-- schema-def:state_machine_query_outcome_routes --> `$defs/state_machine_query_outcome_routes`: state-machine query invocation outcome-route map.
- <!-- schema-def:state_machine_render_audit_case --> `$defs/state_machine_render_audit_case`: state-machine contract component.
- <!-- schema-def:state_machine_signal_raise --> `$defs/state_machine_signal_raise`: state-machine local signal raise contract component.
- <!-- schema-def:state_machine_signal_trigger --> `$defs/state_machine_signal_trigger`: tagged local message/data-signal trigger contract component.
- <!-- schema-def:state_machine_signal --> `$defs/state_machine_signal`: state-machine contract component.
- <!-- schema-def:view_state_query_invocation --> `$defs/view_state_query_invocation`: view-state query invocation contract component.
- <!-- schema-def:state_machine_ref --> `$defs/state_machine_ref`: typed reference definition for its namespace.
- <!-- schema-def:state_machine_transition --> `$defs/state_machine_transition`: state-machine contract component.
- <!-- schema-def:text_ref --> `$defs/text_ref`: typed reference definition for its namespace.
- <!-- schema-def:textual_renderer_contract --> `$defs/textual_renderer_contract`: Textual renderer contract component.
- <!-- schema-def:textual_renderer_layout --> `$defs/textual_renderer_layout`: Textual renderer contract component.
- <!-- schema-def:textual_renderer_presentation --> `$defs/textual_renderer_presentation`: Textual renderer contract component.
- <!-- schema-def:textual_viewport --> `$defs/textual_viewport`: Textual renderer contract component.
- <!-- schema-def:textual_widget --> `$defs/textual_widget`: Textual renderer contract component.
- <!-- schema-def:then --> `$defs/then`: shared schema component used by authored source or compiled output.
- <!-- schema-def:type_expr --> `$defs/type_expr`: structured type-expression and object-schema contract component.
- <!-- schema-def:field_type_expr --> `$defs/field_type_expr`: field type expression without nullable or presence wrappers.
- <!-- schema-def:type_expr_map --> `$defs/type_expr_map`: structured type-expression and object-schema contract component.
- <!-- schema-def:html_route_adapter --> `$defs/html_route_adapter`: HTML renderer contract component.
- <!-- schema-def:html_route_adapter_input --> `$defs/html_route_adapter_input`: HTML renderer contract component.
- <!-- schema-def:value_map --> `$defs/value_map`: shared schema component used by authored source or compiled output.
- <!-- schema-def:view_state_assertion --> `$defs/view_state_assertion`: state-machine contract component.
- <!-- schema-def:view_state_name --> `$defs/view_state_name`: state-machine contract component.
- <!-- schema-def:html_renderer_contract --> `$defs/html_renderer_contract`: HTML renderer contract component.
- <!-- schema-def:html_renderer_layout --> `$defs/html_renderer_layout`: HTML renderer contract component.
- <!-- schema-def:html_renderer_presentation --> `$defs/html_renderer_presentation`: HTML renderer contract component.
- <!-- schema-def:html_slot --> `$defs/html_slot`: HTML renderer contract component.
- <!-- schema-def:webhook_adapter --> `$defs/webhook_adapter`: entry-point adapter, target, input, or response contract component.
- <!-- schema-def:webhook_adapter_input --> `$defs/webhook_adapter_input`: entry-point adapter, target, input, or response contract component.
- <!-- schema-def:when --> `$defs/when`: shared schema component used by authored source or compiled output.
- <!-- schema-def:worker_adapter --> `$defs/worker_adapter`: entry-point adapter, target, input, or response contract component.
- <!-- schema-def:worker_adapter_input --> `$defs/worker_adapter_input`: entry-point adapter, target, input, or response contract component.
- <!-- schema-def:workflow_outcome --> `$defs/workflow_outcome`: workflow trigger, step, route, retry, outcome, or binding contract component.
- <!-- schema-def:workflow_outcome_routes --> `$defs/workflow_outcome_routes`: workflow trigger, step, route, retry, outcome, or binding contract component.
- <!-- schema-def:workflow_outcomes --> `$defs/workflow_outcomes`: workflow trigger, step, route, retry, outcome, or binding contract component.
- <!-- schema-def:workflow_ref --> `$defs/workflow_ref`: typed reference definition for its namespace.
- <!-- schema-def:workflow_retry_policy --> `$defs/workflow_retry_policy`: workflow trigger, step, route, retry, outcome, or binding contract component.
- <!-- schema-def:workflow_route --> `$defs/workflow_route`: workflow trigger, step, route, retry, outcome, or binding contract component.
- <!-- schema-def:workflow_step --> `$defs/workflow_step`: workflow trigger, step, route, retry, outcome, or binding contract component.
- <!-- schema-def:workflow_trigger_source --> `$defs/workflow_trigger_source`: workflow trigger, step, route, retry, outcome, or binding contract component.
- <!-- schema-def:data_contract_ref --> `$defs/data_contract_ref`: typed reference definition for its namespace.
- <!-- schema-def:authored_data_contract --> `$defs/authored_data_contract`: human-authored source object for this resource or nested contract.
- <!-- schema-def:feature_tag --> `$defs/feature_tag`: unprefixed test-case feature grouping tag, not a typed reference.
- <!-- schema-def:data_signal_name --> `$defs/data_signal_name`: state-machine-local data signal identifier.
- <!-- schema-def:state_machine_signals --> `$defs/state_machine_signals`: state-machine contract component.
- <!-- schema-def:viewport_id --> `$defs/viewport_id`: local identifier contract component.
- <!-- schema-def:region_id --> `$defs/region_id`: local HTML layout region identifier within a view state.
- <!-- schema-def:container_id --> `$defs/container_id`: local Textual layout container identifier within a view state.
- <!-- schema-def:http_api_adapter --> `$defs/http_api_adapter`: entry-point adapter, target, input, or response contract component.
- <!-- schema-def:http_api_adapter_input --> `$defs/http_api_adapter_input`: entry-point adapter, target, input, or response contract component.
- <!-- schema-def:authorization_assertion --> `$defs/authorization_assertion`: authorization-policy contract component.
- <!-- schema-def:authorization_condition --> `$defs/authorization_condition`: authorization-policy contract component.
- <!-- schema-def:authorization_decision_assertion --> `$defs/authorization_decision_assertion`: authorization-policy contract component.
- <!-- schema-def:authorization_subject --> `$defs/authorization_subject`: authorization-policy contract component.
- <!-- schema-def:authorization_target --> `$defs/authorization_target`: authorization-policy contract component.
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
- <!-- schema-def:render_profile_item --> `$defs/render_profile_item`: compiled-output object for this resource or nested contract.
- <!-- schema-def:child_state_machine_item --> `$defs/child_state_machine_item`: compiled-output object for this resource or nested contract.
- <!-- schema-def:content_case_item --> `$defs/content_case_item`: compiled-output object for this resource or nested contract.
- <!-- schema-def:text_resource_item --> `$defs/text_resource_item`: compiled-output object for this resource or nested contract.
- <!-- schema-def:entry_point_item --> `$defs/entry_point_item`: compiled-output object for this resource or nested contract.
- <!-- schema-def:event_item --> `$defs/event_item`: compiled-output object for this resource or nested contract.
- <!-- schema-def:fact_body --> `$defs/fact_body`: compiled-output object for this resource or nested contract.
- <!-- schema-def:fact_item --> `$defs/fact_item`: compiled-output object for this resource or nested contract.
- <!-- schema-def:fixture_item --> `$defs/fixture_item`: compiled-output object for this resource or nested contract.
- <!-- schema-def:model_item --> `$defs/model_item`: compiled-output object for this resource or nested contract.
- <!-- schema-def:authorization_policy_item --> `$defs/authorization_policy_item`: compiled-output object for this resource or nested contract.
- <!-- schema-def:operation_item --> `$defs/operation_item`: compiled-output object for this resource or nested contract.
- <!-- schema-def:test_case_item --> `$defs/test_case_item`: compiled-output object for this resource or nested contract.
- <!-- schema-def:state_machine_item --> `$defs/state_machine_item`: compiled-output object for this resource or nested contract.
- <!-- schema-def:view_state --> `$defs/view_state`: compiled-output object for this resource or nested contract.
- <!-- schema-def:workflow_item --> `$defs/workflow_item`: compiled-output object for this resource or nested contract.
- <!-- schema-def:data_contract_item --> `$defs/data_contract_item`: compiled-output object for this resource or nested contract.
