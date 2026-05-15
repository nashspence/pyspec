# Spec Ontology

This glossary is the vocabulary contract for the authored-source and compiled-output schemas. The authored schema describes sparse human input. The compiled schema describes the normalized output in `spec/generated/compiled/spec.yaml`, including generated references, derived events, derived routes, endpoint expansions, and empty collection expansions.

## Top-Level Resources

- <!-- top-level:assets --> `assets`: authored or compiled content assets, usually resolver-backed or placeholder SVG evidence.
- <!-- top-level:audit_profiles --> `audit_profiles`: named viewport/profile settings used to render visual audit evidence.
- <!-- top-level:capabilities --> `capabilities`: product operations with typed input, model effects, outcomes, policies, and event emissions.
- <!-- top-level:content_cases --> `content_cases`: named copy/asset resolver examples with fixtures and argument values.
- <!-- top-level:copies --> `copies`: product copy strings or resolver-backed copy resources.
- <!-- top-level:entries --> `entries`: external surfaces such as API endpoints, web routes, CLI commands, workers, schedules, and webhooks.
- <!-- top-level:events --> `events`: product events with typed payloads; authored events may be joined by compiler-derived events.
- <!-- top-level:facts --> `facts`: reusable preconditions that assert model presence or absence.
- <!-- top-level:fixtures --> `fixtures`: named runtime data namespaces used by scenarios, facts, content cases, and audit evidence.
- <!-- top-level:fsms --> `fsms`: UI/state-machine contracts, including context, data queries, states, transitions, messages, mounts, and sync.
- <!-- top-level:models --> `models`: product data contracts and lifecycle states.
- <!-- top-level:project --> `project`: the project slug for the specification workspace.
- <!-- top-level:refs --> `refs`: compiled-only generated reference index for stable constants and projection cross-checks.
- <!-- top-level:scenarios --> `scenarios`: behavior examples compiled into fixtures, semantic scenario YAML, and BDD features.
- <!-- top-level:workflows --> `workflows`: long-running or asynchronous product flows with triggers, capability steps, routes, and outcomes.

## ID Namespaces

Resource IDs use explicit typed namespaces. Top-level mapping keys and references share the same shape so authored source and compiled output can be validated without a generic dotted ID escape hatch:

- `operation_ref`: `operation.<domain>...`, used by `capabilities`, actions, data loads, entry targets, workflow steps, and policy derivation.
- `entry_point_ref`: `entry_point.<surface>.<domain>...`, used by `entries` and scenario entry invocations.
- `event_ref`: `event.<domain>...`, used by `events`, capability emissions, workflow triggers, and scenario event assertions.
- `workflow_ref`: `workflow.<domain>...`, used by `workflows`, entry targets, workflow routes, and generated workflow references.
- `state_machine_ref`: `state_machine.<domain>...`, used by `fsms`, entry FSM targets, mounted FSMs, scenario FSM assertions, and state-machine generated references.
- `scenario_ref`: `scenario.<domain>...`, used by `scenarios`.
- `fixture_ref`: `fixture.<domain>...`, used by `fixtures`, scenarios, facts, content cases, and audit cases.
- `fact_ref`: `fact.<domain>...`, used by `facts` and fact-use references.
- `asset_ref`: `asset.<domain>...`, used by `assets`, asset slots, content cases, audit cases, and generated placeholder artifacts.
- `text_ref`: `text.<domain>...`, used by `copies`, copy slots, content cases, audit cases, generated resolver signatures, and generated text references.
- `message_ref`: `message.<domain>...` for FSM messages, plus `data.<query>` for FSM data-result transition triggers.
- `model_ref`: PascalCase product model names.
- `content_case_ref`: `content.<domain>...`, used by `content_cases`.
- `feature_ref`: `feature.<domain>...`, used by generated pytest-bdd feature files.
- `audit_profile_ref`: lower-case local audit profile IDs.
- `breakpoint_id`, `field_name`, `instance_id`, and `state_name`: lower-case local names scoped by their owning resource.
- `content_resolver_id`: a resolver address in either the `text.` or `asset.` namespace.
- `type_expr`: structured data type expressions such as `{primitive: Text}`, `{model: Project}`, `{array: {model: Project}}`, `{map: {primitive: Text}}`, `{nullable: ...}`, `{optional: ...}`, `{enum: [...]}`, and `{object: {fields: {...}}}`.
- `type_expr_map`: input/payload maps whose values are `type_expr` objects.
- `object_schema`, `field_schema`, and `field_schema_map`: reusable object contracts whose fields explicitly declare `type`, `required`, and `nullable`; model `fields` use this shape.
- `css_class`, `css_property`, `python_identifier`, and `python_class_name`: generated projection implementation names.

The compiled `refs` index uses these generated reference namespaces:

- `asset`: asset references from authored assets and expanded slots.
- `command`: generated command references for CLI and FSM command entrypoints.
- `endpoint`: generated API endpoint references.
- `policy`: generated capability policy references.
- `query`: generated query references for FSM data requirements.
- `route`: generated web route references.
- `screen`: generated Textual screen references.
- `state_machine`: state-machine resource references.
- `surface`: generated FSM state surface references.
- `text`: text references from authored copy and expanded slots.
- `workflow`: workflow resource and entry workflow references.

## Reference Types

- `model_refs` lists model IDs affected by a capability.
- `fact_use` references a named fact from a scenario or audit case.
- `entry_target`, `entry_fsm_target`, and `entry_workflow_target` connect an entrypoint to an operation, state machine, or workflow.
- `target` is the scenario target union for operations, entrypoints, events, state machines, and workflows.
- `workflow_trigger_target` references the operation or event that starts a workflow.
- `workflow_routes` and `workflow_route` reference step IDs or terminal workflow outcomes.
- `sync_trigger`, `sync_action`, `sync_effect`, and `sync_send_effect` reference mounted state-machine instances and messages.
- `authored_mount` and `mount_item` reference child state machines and map child context from parent state-machine context.
- `text_ref`, `asset_ref`, `content_resolver_id`, and `audit_profile_ref` are content and audit references used by presentation, content cases, and audit renders.
- JSON Schema `$ref` links are schema-internal only and always point to local `$defs`.

## Runtime Expression Namespaces

Runtime expressions are scoped strings that the compiler validates against the available source types:

- `$fixture.<path>` reads merged fixture data in scenarios, facts, content cases, audit cases, and runtime fixture resolution.
- `$state_machine.<field>` reads parent state-machine context when mounting a child state machine.
- `$message.<field>` reads the current FSM message payload in transition effects and sync sends.
- `$context.<field>` reads current FSM context in transition effects.
- `$input.params.<field>`, `$input.body.<field>`, `$input.args.<field>`, and `$input.payload[.<field>]` read entry input for entry target bindings.
- `$input.<field>` reads capability input in capability event emission bindings.
- `$outcome.result[.<field>]` reads a capability outcome result in capability event emission bindings.
- `$trigger.payload[.<field>]` reads the workflow trigger payload.
- `$steps.<step>.outcomes.<outcome>.result[.<field>]` reads a prior workflow step outcome.
- `data.<query>` is an FSM transition trigger namespace for data query results.

`expression_map`, `value_map`, `entry_bindings`, `workflow_bindings`, `context_bindings`, `capability_emit_bindings`, and `workflow_source` are the schema definitions that constrain these mappings.

## Generated Artifacts

The generated tree is closed under validation. These path families are generated artifacts:

- `spec/generated/__init__.py`: generated package marker.
- `spec/generated/compiled/spec.yaml`: compiled-output spec.
- `spec/generated/agent_prompts/pm_design.md`: PM/design prompt.
- `spec/generated/agent_prompts/test.md`: test prompt.
- `spec/generated/agent_prompts/dev.md`: development prompt.
- `spec/generated/agent_prompts/review.md`: review prompt.
- `spec/generated/behavior/fixtures.yaml`: scenario fixture projection.
- `spec/generated/behavior/scenarios.yaml`: semantic scenario projection.
- `spec/generated/product_interfaces/http.openapi.yaml`: OpenAPI projection for API entries.
- `spec/generated/product_interfaces/events.asyncapi.yaml`: AsyncAPI projection for events, workers, webhooks, and event-triggered workflows.
- `spec/generated/product_interfaces/web.routes.json`: web route projection.
- `spec/generated/product_interfaces/web.fsms.json`: FSM surface projection.
- `spec/generated/product_interfaces/textual.projection.py`: Textual projection.
- `spec/generated/product_interfaces/workflow.cwl.yaml`: CWL workflow projection.
- `spec/generated/content_resolvers/__init__.py`: generated content resolver package marker.
- `spec/generated/content_resolvers/signatures.py`: typed text/asset resolver signatures.
- `spec/generated/content_resolvers/stubs.py`: resolver implementation stubs.
- `spec/generated/content_resolvers/cases.yaml`: content resolver case projection.
- `spec/generated/test_adapters/__init__.py`: generated test adapter package marker.
- `spec/generated/test_adapters/python_refs.py`: generated Python reference constants.
- `spec/generated/test_adapters/driver_protocol.py`: generated driver protocol.
- `spec/generated/test_adapters/pytest_bdd_steps.py`: generated pytest-bdd step glue.
- `spec/generated/test_adapters/pytest_bdd_features/{scenario}.feature`: generated BDD features.
- `spec/generated/audit_evidence/entrypoints/{surface}/{entry}/flow.svg`: entrypoint flow diagrams.
- `spec/generated/audit_evidence/workflows/{workflow}/flow.svg`: workflow flow diagrams.
- `spec/generated/audit_evidence/fsms/{fsm}/fsm.svg`: FSM diagrams.
- `spec/generated/audit_evidence/fsms/{fsm}/states/{state}/composition.svg`: mounted FSM composition diagrams.
- `spec/generated/audit_evidence/fsms/{fsm}/states/{state}/copy.yaml`: state-local text evidence.
- `spec/generated/audit_evidence/fsms/{fsm}/states/{state}/fixtures.yaml`: state-local fixture evidence.
- `spec/generated/audit_evidence/fsms/{fsm}/states/{state}/assets/{asset}.svg`: state-local asset evidence.
- `spec/generated/audit_evidence/fsms/{fsm}/states/{state}/renders/html.{profile}.{breakpoint}.source.html`: HTML render source.
- `spec/generated/audit_evidence/fsms/{fsm}/states/{state}/renders/html.{profile}.{breakpoint}.screenshot.png`: HTML screenshot.
- `spec/generated/audit_evidence/fsms/{fsm}/states/{state}/renders/textual.{profile}.{breakpoint}.source.py`: Textual render source.
- `spec/generated/audit_evidence/fsms/{fsm}/states/{state}/renders/textual.{profile}.{breakpoint}.capture.svg`: Textual capture.
- `spec/generated/audit_evidence/fsms/{fsm}/states/{state}/cases/{case}/copy.yaml`: audit-case text evidence.
- `spec/generated/audit_evidence/fsms/{fsm}/states/{state}/cases/{case}/fixtures.yaml`: audit-case fixture evidence.
- `spec/generated/audit_evidence/fsms/{fsm}/states/{state}/cases/{case}/assets/{asset}.svg`: audit-case asset evidence.
- `spec/generated/audit_evidence/fsms/{fsm}/states/{state}/cases/{case}/renders/html.{profile}.{breakpoint}.source.html`: audit-case HTML source.
- `spec/generated/audit_evidence/fsms/{fsm}/states/{state}/cases/{case}/renders/html.{profile}.{breakpoint}.screenshot.png`: audit-case HTML screenshot.
- `spec/generated/audit_evidence/fsms/{fsm}/states/{state}/cases/{case}/renders/textual.{profile}.{breakpoint}.source.py`: audit-case Textual source.
- `spec/generated/audit_evidence/fsms/{fsm}/states/{state}/cases/{case}/renders/textual.{profile}.{breakpoint}.capture.svg`: audit-case Textual capture.

## Schema Definition Inventory

Each `$defs` entry in the JSON Schemas is documented exactly once here. The schema-inventory test treats the hidden markers as the authoritative inventory.

- <!-- schema-def:aria_role --> `$defs/aria_role`: allowed ARIA role token for generated HTML projections.
- <!-- schema-def:asset_item --> `$defs/asset_item`: compiled asset record with normalized content metadata.
- <!-- schema-def:asset_placeholder --> `$defs/asset_placeholder`: authored or compiled placeholder asset shape.
- <!-- schema-def:asset_ref --> `$defs/asset_ref`: typed reference in the `asset.` namespace.
- <!-- schema-def:audit_profile_item --> `$defs/audit_profile_item`: compiled audit profile with HTML/Textual breakpoint settings.
- <!-- schema-def:audit_profile_ref --> `$defs/audit_profile_ref`: typed local audit profile reference.
- <!-- schema-def:authored_asset --> `$defs/authored_asset`: human-authored asset source.
- <!-- schema-def:authored_audit_profile --> `$defs/authored_audit_profile`: human-authored audit profile source.
- <!-- schema-def:authored_capability --> `$defs/authored_capability`: human-authored operation source.
- <!-- schema-def:authored_content_case --> `$defs/authored_content_case`: human-authored content resolver case source.
- <!-- schema-def:authored_copy --> `$defs/authored_copy`: human-authored text source.
- <!-- schema-def:authored_entry --> `$defs/authored_entry`: human-authored entrypoint source.
- <!-- schema-def:authored_event --> `$defs/authored_event`: human-authored event source.
- <!-- schema-def:authored_fact --> `$defs/authored_fact`: human-authored fact source.
- <!-- schema-def:authored_fixture --> `$defs/authored_fixture`: human-authored fixture source.
- <!-- schema-def:authored_fsm --> `$defs/authored_fsm`: human-authored state-machine source.
- <!-- schema-def:authored_fsm_state --> `$defs/authored_fsm_state`: human-authored state-machine state source.
- <!-- schema-def:authored_model --> `$defs/authored_model`: human-authored model source.
- <!-- schema-def:authored_mount --> `$defs/authored_mount`: human-authored mounted state-machine source.
- <!-- schema-def:authored_scenario --> `$defs/authored_scenario`: human-authored scenario source.
- <!-- schema-def:authored_workflow --> `$defs/authored_workflow`: human-authored workflow source.
- <!-- schema-def:basis --> `$defs/basis`: required rationale text for authored and compiled records.
- <!-- schema-def:breakpoint_id --> `$defs/breakpoint_id`: local audit breakpoint ID.
- <!-- schema-def:capability_emit --> `$defs/capability_emit`: operation outcome event emission declaration.
- <!-- schema-def:capability_emit_bindings --> `$defs/capability_emit_bindings`: payload field mapping for operation event emissions.
- <!-- schema-def:capability_emit_source --> `$defs/capability_emit_source`: source expression for operation event emission bindings.
- <!-- schema-def:capability_item --> `$defs/capability_item`: compiled operation with generated policy and normalized outcomes.
- <!-- schema-def:capability_outcome --> `$defs/capability_outcome`: success or failure outcome for an operation.
- <!-- schema-def:capability_outcomes --> `$defs/capability_outcomes`: named map of operation outcomes.
- <!-- schema-def:condition_contract --> `$defs/condition_contract`: state-machine composition condition over context.
- <!-- schema-def:content_arg_values --> `$defs/content_arg_values`: concrete resolver argument values.
- <!-- schema-def:content_args --> `$defs/content_args`: resolver argument type declaration.
- <!-- schema-def:content_case_item --> `$defs/content_case_item`: compiled content resolver case.
- <!-- schema-def:content_case_ref --> `$defs/content_case_ref`: typed reference in the `content.` namespace.
- <!-- schema-def:content_resolver_id --> `$defs/content_resolver_id`: resolver ID in the `text.` or `asset.` namespace.
- <!-- schema-def:context_bindings --> `$defs/context_bindings`: context value map for entries, mounts, cases, and sync.
- <!-- schema-def:context_set_effect --> `$defs/context_set_effect`: effect that sets a state-machine context field.
- <!-- schema-def:copy_item --> `$defs/copy_item`: compiled text record with normalized resolver metadata.
- <!-- schema-def:css_class --> `$defs/css_class`: generated or authored CSS class token.
- <!-- schema-def:css_declarations --> `$defs/css_declarations`: CSS property/value map.
- <!-- schema-def:css_property --> `$defs/css_property`: CSS property token.
- <!-- schema-def:css_value --> `$defs/css_value`: safe CSS declaration value.
- <!-- schema-def:datum --> `$defs/datum`: compiled state-machine data query record.
- <!-- schema-def:entry_bindings --> `$defs/entry_bindings`: entry input to target input binding map.
- <!-- schema-def:entry_fsm_target --> `$defs/entry_fsm_target`: state-machine target for an entry.
- <!-- schema-def:entry_input --> `$defs/entry_input`: typed entry input sections.
- <!-- schema-def:entry_item --> `$defs/entry_item`: compiled entry with generated route, endpoint, command, or workflow reference.
- <!-- schema-def:entry_point_ref --> `$defs/entry_point_ref`: typed reference in the `entry_point.` namespace.
- <!-- schema-def:entry_response --> `$defs/entry_response`: entry response declaration.
- <!-- schema-def:entry_response_value --> `$defs/entry_response_value`: entry response body/stdout/stderr value source.
- <!-- schema-def:entry_responses --> `$defs/entry_responses`: named map of entry responses.
- <!-- schema-def:entry_target --> `$defs/entry_target`: entry target union for operation, state machine, or workflow.
- <!-- schema-def:entry_workflow_target --> `$defs/entry_workflow_target`: workflow target for an entry.
- <!-- schema-def:event_item --> `$defs/event_item`: compiled event with normalized payload and emitters.
- <!-- schema-def:event_ref --> `$defs/event_ref`: typed reference in the `event.` namespace.
- <!-- schema-def:expression_map --> `$defs/expression_map`: field map with scalar expression values.
- <!-- schema-def:fact --> `$defs/fact`: authored fact body without top-level basis metadata.
- <!-- schema-def:fact_item --> `$defs/fact_item`: compiled fact with basis metadata.
- <!-- schema-def:fact_ref --> `$defs/fact_ref`: typed reference in the `fact.` namespace.
- <!-- schema-def:fact_use --> `$defs/fact_use`: named fact reference.
- <!-- schema-def:feature_ref --> `$defs/feature_ref`: typed reference in the `feature.` namespace.
- <!-- schema-def:field_schema --> `$defs/field_schema`: object field declaration with explicit type, required, and nullable semantics.
- <!-- schema-def:field_schema_map --> `$defs/field_schema_map`: field map whose values are structured field declarations.
- <!-- schema-def:field_name --> `$defs/field_name`: lower-case field name.
- <!-- schema-def:fixture_item --> `$defs/fixture_item`: compiled fixture with concrete values.
- <!-- schema-def:fixture_ref --> `$defs/fixture_ref`: typed reference in the `fixture.` namespace.
- <!-- schema-def:fsm_audit_case --> `$defs/fsm_audit_case`: state-machine state visual audit case.
- <!-- schema-def:fsm_item --> `$defs/fsm_item`: compiled state machine with normalized states, data, messages, and transitions.
- <!-- schema-def:fsm_message --> `$defs/fsm_message`: state-machine message payload declaration.
- <!-- schema-def:fsm_messages --> `$defs/fsm_messages`: accepted and emitted state-machine message maps.
- <!-- schema-def:fsm_mount_selected --> `$defs/fsm_mount_selected`: selected child-state condition for mounted state machines.
- <!-- schema-def:fsm_state --> `$defs/fsm_state`: compiled state-machine state with normalized slots, surfaces, sync, and data.
- <!-- schema-def:fsm_state_assertion --> `$defs/fsm_state_assertion`: scenario assertion about a state-machine state.
- <!-- schema-def:fsm_sync_assertion --> `$defs/fsm_sync_assertion`: scenario assertion about observed sync rules.
- <!-- schema-def:fsm_transition --> `$defs/fsm_transition`: state-machine transition rule.
- <!-- schema-def:given --> `$defs/given`: scenario setup block.
- <!-- schema-def:html_action_slot --> `$defs/html_action_slot`: HTML action slot projection metadata.
- <!-- schema-def:html_asset_slot --> `$defs/html_asset_slot`: HTML asset slot projection metadata.
- <!-- schema-def:html_contract --> `$defs/html_contract`: HTML presentation contract.
- <!-- schema-def:html_copy_slot --> `$defs/html_copy_slot`: HTML text slot projection metadata.
- <!-- schema-def:html_element --> `$defs/html_element`: allowed HTML element token.
- <!-- schema-def:html_field_slot --> `$defs/html_field_slot`: HTML field slot projection metadata.
- <!-- schema-def:html_root --> `$defs/html_root`: HTML root element metadata.
- <!-- schema-def:html_slot --> `$defs/html_slot`: HTML slot union.
- <!-- schema-def:html_viewport --> `$defs/html_viewport`: HTML audit viewport dimensions.
- <!-- schema-def:instance_id --> `$defs/instance_id`: mounted state-machine instance ID.
- <!-- schema-def:json_value --> `$defs/json_value`: recursive JSON value.
- <!-- schema-def:layout_container --> `$defs/layout_container`: Textual layout container.
- <!-- schema-def:layout_contract --> `$defs/layout_contract`: UI layout contract by surface.
- <!-- schema-def:layout_html --> `$defs/layout_html`: HTML layout declaration.
- <!-- schema-def:layout_region --> `$defs/layout_region`: named HTML layout region.
- <!-- schema-def:layout_root --> `$defs/layout_root`: root layout element.
- <!-- schema-def:layout_textual --> `$defs/layout_textual`: Textual layout declaration.
- <!-- schema-def:message_ref --> `$defs/message_ref`: typed FSM message reference in the `message.` namespace, or a `data.` trigger reference.
- <!-- schema-def:model_item --> `$defs/model_item`: compiled model record.
- <!-- schema-def:model_ref --> `$defs/model_ref`: typed PascalCase model reference.
- <!-- schema-def:model_refs --> `$defs/model_refs`: list of model references.
- <!-- schema-def:mount_item --> `$defs/mount_item`: compiled mounted state-machine record.
- <!-- schema-def:object_schema --> `$defs/object_schema`: structured object contract with per-field required and nullable semantics.
- <!-- schema-def:operation_ref --> `$defs/operation_ref`: typed reference in the `operation.` namespace.
- <!-- schema-def:presentation_contract --> `$defs/presentation_contract`: UI presentation contract by surface.
- <!-- schema-def:python_class_name --> `$defs/python_class_name`: generated Python class name.
- <!-- schema-def:python_identifier --> `$defs/python_identifier`: generated Python identifier.
- <!-- schema-def:runtime_expression --> `$defs/runtime_expression`: shared `$root.path.to.field` runtime reference expression grammar.
- <!-- schema-def:scalar --> `$defs/scalar`: scalar literal value.
- <!-- schema-def:scenario_item --> `$defs/scenario_item`: compiled scenario with normalized arrange/execute/assert sections.
- <!-- schema-def:scenario_ref --> `$defs/scenario_ref`: typed reference in the `scenario.` namespace.
- <!-- schema-def:state_machine_ref --> `$defs/state_machine_ref`: typed reference in the `state_machine.` namespace.
- <!-- schema-def:state_name --> `$defs/state_name`: state-machine state name.
- <!-- schema-def:style_contract --> `$defs/style_contract`: style tokens and rules.
- <!-- schema-def:style_rule --> `$defs/style_rule`: selector plus CSS declarations.
- <!-- schema-def:style_selector --> `$defs/style_selector`: style selector namespace for roots, screens, slots, regions, actions, and mounts.
- <!-- schema-def:sync_action --> `$defs/sync_action`: state-machine sync action union.
- <!-- schema-def:sync_effect --> `$defs/sync_effect`: state-machine sync effect union.
- <!-- schema-def:sync_rule --> `$defs/sync_rule`: state-machine sync rule.
- <!-- schema-def:sync_send_effect --> `$defs/sync_send_effect`: effect that sends a message to a mounted instance.
- <!-- schema-def:sync_trigger --> `$defs/sync_trigger`: trigger from a mounted instance and message.
- <!-- schema-def:target --> `$defs/target`: scenario target union.
- <!-- schema-def:text_ref --> `$defs/text_ref`: typed reference in the `text.` namespace.
- <!-- schema-def:textual_bind --> `$defs/textual_bind`: Textual widget binding union.
- <!-- schema-def:textual_contract --> `$defs/textual_contract`: Textual presentation contract.
- <!-- schema-def:textual_viewport --> `$defs/textual_viewport`: Textual audit viewport dimensions.
- <!-- schema-def:textual_widget --> `$defs/textual_widget`: Textual widget projection metadata.
- <!-- schema-def:then --> `$defs/then`: scenario assertion block.
- <!-- schema-def:type_expr --> `$defs/type_expr`: structured primitive, model, array, map, nullable, optional, enum, or inline object-schema type expression.
- <!-- schema-def:type_expr_map --> `$defs/type_expr_map`: input or payload map whose values are structured type expressions.
- <!-- schema-def:value_map --> `$defs/value_map`: field-to-scalar value map.
- <!-- schema-def:when --> `$defs/when`: scenario action block.
- <!-- schema-def:workflow_bindings --> `$defs/workflow_bindings`: workflow source to operation input binding map.
- <!-- schema-def:workflow_item --> `$defs/workflow_item`: compiled workflow with generated workflow reference.
- <!-- schema-def:workflow_outcome --> `$defs/workflow_outcome`: workflow terminal outcome.
- <!-- schema-def:workflow_outcomes --> `$defs/workflow_outcomes`: named map of workflow terminal outcomes.
- <!-- schema-def:workflow_ref --> `$defs/workflow_ref`: typed reference in the `workflow.` namespace.
- <!-- schema-def:workflow_retry --> `$defs/workflow_retry`: workflow retry policy.
- <!-- schema-def:workflow_route --> `$defs/workflow_route`: workflow step route.
- <!-- schema-def:workflow_routes --> `$defs/workflow_routes`: named map of workflow step routes.
- <!-- schema-def:workflow_source --> `$defs/workflow_source`: source expression for workflow bindings.
- <!-- schema-def:workflow_step --> `$defs/workflow_step`: workflow operation step.
- <!-- schema-def:workflow_trigger_target --> `$defs/workflow_trigger_target`: workflow trigger target reference.
