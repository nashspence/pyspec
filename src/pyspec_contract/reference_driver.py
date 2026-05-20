from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .io import read_json, read_yaml
from .behaviors import command_or_query_resource_kind, command_query_map
from .paths import COMPILED_SPEC_PATH, GENERATED_SPEC_DIR
from .runtime import fixture_namespace, resolve_map
from .binding_refs import resolve_binding_expression
from .targets import (
    external_interface_state_machine_name,
    external_interface_input_mapping,
    external_interface_output_response_handlers,
    external_interface_output_responses,
    external_interface_invoked_ref_pair,
    external_interface_invocation_input_mapping,
)
from .json_schema import entity_type_id, schema_properties


def _workflow_sequence_flow_for_activity_result(workflow: dict[str, Any], activity_id: str, outcome_id: str) -> dict[str, Any]:
    for sequence_flow in workflow["sequence_flows"].values():
        if sequence_flow["source_ref"].get("activity") == activity_id and sequence_flow.get("source_outcome") == outcome_id:
            return sequence_flow
    raise AssertionError(f"Workflow activity {activity_id} has no sequence_flow for outcome {outcome_id}")


def _workflow_sequence_flow_for_gateway(workflow: dict[str, Any], gateway_id: str, namespace: Mapping[str, Any]) -> dict[str, Any]:
    fallback: dict[str, Any] | None = None
    for sequence_flow in workflow["sequence_flows"].values():
        if sequence_flow["source_ref"].get("gateway") != gateway_id:
            continue
        condition = sequence_flow.get("condition")
        if condition is None:
            fallback = sequence_flow
            continue
        try:
            if _resolve_binding(condition, namespace):
                return sequence_flow
        except (KeyError, TypeError):
            continue
    if fallback is not None:
        return fallback
    raise AssertionError(f"Workflow gateway {gateway_id} has no matching sequence_flow")


def _workflow_sequence_flow_target_ref(sequence_flow: Mapping[str, Any]) -> tuple[str, str]:
    return next(iter(sequence_flow["target_ref"].items()))


class ReferenceSpecDriver:
    """A fake/reference world for spec BDD. It proves behavior scenarios are coherent, not that prod works."""

    def __init__(self, root: Path):
        self.root = root
        self.contract = read_yaml(root / COMPILED_SPEC_PATH)
        self.surfaces = {p["id"]: p for p in read_json(root / GENERATED_SPEC_DIR / "product_interfaces" / "html.state_machines.json")["state_machines"]}
        self.reset()

    def reset(self) -> None:
        self.fixtures: dict[str, Any] = {}
        self.store: dict[str, list[dict[str, Any]]] = {rid: [] for rid in self.contract["entity_types"]}
        self.emitted: list[str] = []
        self.invoked: list[str] = []
        self.workflows_executed: list[str] = []
        self.workflow_outputs: dict[str, str] = {}
        self.authorization_decisions: dict[tuple[str, str, str], bool] = {}
        self.last_state_machine: dict[str, Any] | None = None
        self.response: dict[str, Any] | None = None
        self.last_result: Any = None
        self.last_outcome: str | None = None

    def given(self, behavior_scenario_id: str, behavior_scenario: Mapping[str, Any]) -> None:
        self.reset()
        self.fixtures = fixture_namespace(self.contract, list(behavior_scenario.get("given", {}).get("seed_fixtures", [])))
        for precondition in behavior_scenario.get("given", {}).get("preconditions", []):
            kind, body = next(iter(precondition.items()))
            if kind == "absent":
                where = self._resolve_map(body["where"])
                self.store[body["entity_type"]] = [r for r in self.store[body["entity_type"]] if not _matches(r, where)]
            elif kind == "present":
                values = self._complete_record(body["entity_type"], self._resolve_map(body["values"]))
                self.store[body["entity_type"]].append(values)
            else:  # pragma: no cover - schema prevents this.
                raise AssertionError(f"Unsupported precondition kind: {kind}")

    def when(self, behavior_scenario_id: str, behavior_scenario: Mapping[str, Any]) -> None:
        kind, body = next(iter(behavior_scenario["when"].items()))
        if kind == "open_external_interface":
            self.last_state_machine = self._open_external_interface(body["ref"], self._resolve_map(body.get("input", {})))
        elif kind == "call_external_interface":
            self.response = self._call_external_interface(body["ref"], self._resolve_map(body.get("input", {})), behavior_scenario["then"].get("outcome"))
        elif kind in {"invoke_command", "invoke_query"}:
            self.last_result = self._invoke(body["ref"], self._resolve_map(body.get("input", {})), behavior_scenario["then"].get("outcome"))
        elif kind == "emit_domain_event":
            self._emit(body["ref"], self._resolve_map(body.get("payload", {})))
        else:  # pragma: no cover - schema prevents this.
            raise AssertionError(f"Unsupported when kind: {kind}")

    def then(self, behavior_scenario_id: str, behavior_scenario: Mapping[str, Any]) -> None:
        assertions = behavior_scenario["then"]
        if "state_machine" in assertions:
            assert self.last_state_machine is not None, "Expected a rendered state machine"
            expected = assertions["state_machine"]
            assert self.last_state_machine["ref"] == expected["ref"]
            if "state" in expected:
                assert self.last_state_machine["state"] == expected["state"]
                assert self.last_state_machine["renderer_surface"] == expected["renderer_surface"]
            if "instances" in expected:
                assert set(self.last_state_machine["instances"]) == set(expected["instances"])
                for instance_id, state_machine_expected in expected["instances"].items():
                    actual = self.last_state_machine["instances"][instance_id]
                    assert actual["state"] == state_machine_expected["state"]
                    assert actual["renderer_surface"] == state_machine_expected["renderer_surface"]
                for sync_id in (expected.get("local_signal_sync_rules") or {}).get("observed_rules", []):
                    assert sync_id in self.last_state_machine.get("local_signal_sync_rules", [])
        requires = assertions.get("requires", {})
        if requires:
            assert self.last_state_machine is not None, "state-machine requirements need a rendered state machine"
            rendered_state_machines = self._rendered_state_machine_ids()
            rendered_text = self._rendered_values("text_resources")
            rendered_assets = self._rendered_values("media_assets")
            rendered_command_bindings = self._rendered_values("command_bindings")
            for state_machine in requires.get("renderer_surfaces", []):
                assert state_machine in self.surfaces
                assert state_machine in rendered_state_machines
            for key in requires.get("text_resources", []):
                assert key in rendered_text
            for key in requires.get("media_assets", []):
                assert key in rendered_assets
            for command_binding_id in requires.get("command_bindings", []):
                assert command_binding_id in rendered_command_bindings
            rendered_queries = self._rendered_values("query_bindings")
            for query in requires.get("query_bindings", []):
                assert query in rendered_queries
        for behavior_ref in assertions.get("enables", []):
            assert behavior_ref in self._rendered_command_query_refs()
        for behavior_ref in assertions.get("forbids", []):
            assert behavior_ref not in self._rendered_command_query_refs()
        exists = (assertions.get("entity_type") or {}).get("exists")
        if exists:
            where = self._resolve_map(exists["where"])
            assert any(_matches(record, where) for record in self.store[exists["entity_type"]]), f"Missing entity_type {exists}"
        domain_events = assertions.get("domain_events") or {}
        for domain_event_id in domain_events.get("emitted", []):
            assert domain_event_id in self.emitted
        for domain_event_id in domain_events.get("not_emitted", []):
            assert domain_event_id not in self.emitted
        workflow = assertions.get("workflow")
        if workflow:
            if workflow["executed"]:
                assert workflow["ref"] in self.workflows_executed
            else:
                assert workflow["ref"] not in self.workflows_executed
            if "outcome" in workflow:
                assert self.workflow_outputs.get(workflow["ref"]) == workflow["outcome"]
        for behavior_ref in assertions.get("invoked", []):
            assert behavior_ref in self.invoked
        response = assertions.get("response")
        if response:
            assert self.response is not None
            for key in ("status", "exit_code"):
                if key in response:
                    assert self.response[key] == response[key]
        outcome = assertions.get("outcome")
        if outcome:
            assert self.last_outcome == outcome
        policy = assertions.get("authorization") or {}
        for assertion in policy.get("allowed", []):
            assert self._authorization_assertion_allowed(assertion), f"Expected access policy to permit {assertion}"
        for assertion in policy.get("denied", []):
            assert not self._authorization_assertion_allowed(assertion), f"Expected access policy to deny {assertion}"
        for assertion in assertions.get("postconditions", []):
            kind, body = next(iter(assertion.items()))
            if kind == "present":
                values = self._resolve_map(body["values"])
                assert any(_matches(record, values) for record in self.store[body["entity_type"]]), f"Missing assertion {body}"
            elif kind == "absent":
                where = self._resolve_map(body["where"])
                assert not any(_matches(record, where) for record in self.store[body["entity_type"]]), f"Unexpected assertion {body}"

    def _open_external_interface(self, external_interface_id: str, input_values: dict[str, Any]) -> dict[str, Any]:
        external_interface = self.contract["external_interfaces"][external_interface_id]
        state_machine_id = external_interface_state_machine_name(external_interface)
        state_machine = self.contract["state_machines"][state_machine_id]
        context = self._external_interface_target_input(external_interface, input_values)
        records = self._filter(state_machine["entity_type"], context) if state_machine.get("entity_type") else []
        parent_state_name = "ready" if "ready" in state_machine.get("states", {}) else next(iter(state_machine.get("states", {"ready": {}})))
        state = state_machine["states"].get(parent_state_name, {"renderer_surface": None, "text_resources": [], "media_assets": [], "command_bindings": {}, "query_bindings": {}})
        if state.get("child_state_machines"):
            parent_state_machine = state_machine
            state_machines: dict[str, Any] = {}
            for mount in state["child_state_machines"]:
                source_id = mount["state_machine"]
                child_state_machine = self.contract["state_machines"][source_id]
                child_state_name = self._choose_state_machine_state(child_state_machine, mount, records, context)
                child_state = child_state_machine["states"][child_state_name]
                state_machines[mount["id"]] = {
                    "source": source_id,
                    "state": child_state_name,
                    "renderer_surface": child_state["renderer_surface"],
                    "query_bindings": {
                        **child_state_machine.get("query_bindings", {}),
                        **child_state.get("query_bindings", {}),
                    },
                    "text_resources": child_state["text_resources"],
                    "media_assets": child_state["media_assets"],
                    "command_bindings": child_state["command_bindings"],
                }
            return {
                "ref": state_machine_id,
                "state": parent_state_name,
                "renderer_surface": state.get("renderer_surface"),
                "query_bindings": {
                    **parent_state_machine.get("query_bindings", {}),
                    **state.get("query_bindings", {}),
                },
                "text_resources": state.get("text_resources", []),
                "media_assets": state.get("media_assets", []),
                "command_bindings": state.get("command_bindings", {}),
                "context": context,
                "instances": state_machines,
                "local_signal_sync_rules": [rule["id"] for rule in state.get("local_signal_sync_rules", [])],
            }
        state_name = "empty" if not records and "empty" in state_machine["states"] else "ready"
        state = state_machine["states"][state_name]
        return {
            "ref": state_machine_id,
            "state": state_name,
            "renderer_surface": state["renderer_surface"],
            "text_resources": state["text_resources"],
            "media_assets": state["media_assets"],
            "query_bindings": {
                **state_machine.get("query_bindings", {}),
                **state.get("query_bindings", {}),
            },
            "command_bindings": state["command_bindings"],
        }

    def _choose_state_machine_state(self, state_machine: dict[str, Any], mount: dict[str, Any], records: list[dict[str, Any]], context: dict[str, Any]) -> str:
        selected = mount.get("selected")
        if selected:
            if _condition_matches(selected["condition"], context):
                return selected["state"]
            return mount["initial_state"]
        if records and "ready" in state_machine["states"] and (state_machine.get("query_bindings") or state_machine["states"]["ready"].get("query_bindings")):
            return "ready"
        if not records and "empty" in state_machine["states"]:
            return "empty"
        return mount["initial_state"]

    def _rendered_state_machine_ids(self) -> set[str]:
        if not self.last_state_machine:
            return set()
        if "instances" in self.last_state_machine:
            state_machines = {state_machine["renderer_surface"] for state_machine in self.last_state_machine["instances"].values()}
            if self.last_state_machine.get("renderer_surface"):
                state_machines.add(self.last_state_machine["renderer_surface"])
            return state_machines
        return {self.last_state_machine["renderer_surface"]}

    def _rendered_values(self, key: str) -> set[str]:
        if not self.last_state_machine:
            return set()
        if "instances" in self.last_state_machine:
            values: set[str] = set()
            values.update(self.last_state_machine.get(key, []))
            for state_machine in self.last_state_machine["instances"].values():
                values.update(state_machine.get(key, []))
            return values
        return set(self.last_state_machine.get(key, []))

    def _rendered_command_query_refs(self) -> set[str]:
        if not self.last_state_machine:
            return set()

        def command_query_refs(item: dict[str, Any]) -> set[str]:
            invocations = item.get("command_bindings") or {}
            return {invocation.get("command") or invocation.get("query") for invocation in invocations.values()}

        if "instances" in self.last_state_machine:
            refs = command_query_refs(self.last_state_machine)
            for state_machine in self.last_state_machine["instances"].values():
                refs.update(command_query_refs(state_machine))
            return refs
        return command_query_refs(self.last_state_machine)

    def _call_external_interface(self, external_interface_id: str, input_values: dict[str, Any], outcome_id: str | None = None) -> dict[str, Any]:
        external_interface = self.contract["external_interfaces"][external_interface_id]
        target_kind, target_ref = external_interface_invoked_ref_pair(external_interface)
        policy_id = external_interface.get("access_policy")
        if policy_id:
            self.authorization_decisions[("external_interface", external_interface_id, policy_id)] = self._evaluate_policy(policy_id, "external_interface", external_interface_id, input_values)
        if target_kind == "external_interface":
            target_input = self._external_interface_delegate_input(external_interface, input_values)
            delegated_response = self._call_external_interface(target_ref, target_input, outcome_id)
            handler = external_interface_output_response_handlers(external_interface)[self.last_outcome]
            if "stdout" in handler:
                return {"exit_code": handler["exit_code"], "stdout": self._cli_output(handler["stdout"], delegated_response, input_values)}
            return {"exit_code": handler["exit_code"], "stderr": self._cli_output(handler["stderr"], delegated_response, input_values)}
        assert target_kind in {"command", "query"}
        target_input = self._external_interface_target_input(external_interface, input_values)
        result = self._invoke(target_ref, target_input, outcome_id)
        response = _external_interface_response(external_interface, self.last_outcome)
        if "status" in response:
            return {"status": response["status"], "body": result}
        if "stdout" in response:
            return {"exit_code": response["exit_code"], "stdout": self._cli_output(response["stdout"], {"body": result}, input_values)}
        return {"exit_code": response["exit_code"], "stderr": self._cli_output(response["stderr"], {"body": result}, input_values)}

    def _external_interface_target_input(self, external_interface: dict[str, Any], input_values: dict[str, Any]) -> dict[str, Any]:
        namespace = {"adapter_input": {}}
        for section in ("path_params", "query_params", "body", "args"):
            fields = external_interface_input_mapping(external_interface).get(section, {})
            if fields:
                namespace["adapter_input"][section] = {name: input_values[name] for name in fields}
        bindings = external_interface_invocation_input_mapping(external_interface)
        return {name: _resolve_binding(source, namespace) for name, source in bindings.items()}

    def _external_interface_delegate_input(self, external_interface: dict[str, Any], input_values: dict[str, Any]) -> dict[str, Any]:
        namespace = {"adapter_input": {}}
        for section in ("path_params", "query_params", "body", "args"):
            fields = external_interface_input_mapping(external_interface).get(section, {})
            if fields:
                namespace["adapter_input"][section] = {name: input_values[name] for name in fields}
        if "payload" in external_interface_input_mapping(external_interface):
            namespace["adapter_input"]["payload"] = input_values.get("payload", input_values)
        delegated_input: dict[str, Any] = {}
        for section, section_bindings in external_interface_invocation_input_mapping(external_interface).items():
            if section == "payload" and isinstance(section_bindings, Mapping) and "from" in section_bindings:
                delegated_input["payload"] = _resolve_binding(section_bindings, namespace)
                continue
            if isinstance(section_bindings, Mapping):
                for name, source in section_bindings.items():
                    delegated_input[name] = _resolve_binding(source, namespace)
        return delegated_input

    def _cli_output(self, output: Mapping[str, Any], response: Mapping[str, Any], input_values: Mapping[str, Any]) -> dict[str, Any]:
        namespace = {"adapter_response": response, "invocation_outcome": {"result": response.get("body")}, "adapter_input": dict(input_values)}
        return {
            "text": output["text"],
            "bindings": {
                name: _resolve_binding(binding, namespace)
                for name, binding in (output.get("bindings") or {}).items()
            },
        }

    def _invoke(self, behavior_ref: str, input_values: dict[str, Any], outcome_id: str | None = None) -> Any:
        behavior = command_query_map(self.contract)[behavior_ref]
        authorization = behavior.get("authorization")
        if authorization:
            policy_id = authorization["policy"]
            resource_kind = command_or_query_resource_kind(behavior_ref)
            allowed = self._evaluate_policy(policy_id, resource_kind, behavior_ref, input_values)
            self.authorization_decisions[(resource_kind, behavior_ref, policy_id)] = allowed
            if not allowed:
                policy = self.contract["access_policies"][policy_id]
                outcome_id = (
                    authorization["access_denied_as"]
                    if self._subject_available(policy, input_values)
                    else authorization["authentication_required_as"]
                )
                self.last_outcome = outcome_id
                self.last_result = {"code": outcome_id, "message": outcome_id.replace("_", " ")}
                return self.last_result
        self.invoked.append(behavior_ref)
        outcome_id = outcome_id or _success_outcome_id(behavior)
        outcome = behavior["outcomes"][outcome_id]
        self.last_outcome = outcome_id
        if outcome["kind"] == "failure":
            self.last_result = {"code": outcome_id, "message": outcome_id.replace("_", " ")}
            return self.last_result
        behavior_kind = behavior["behavior_kind"]
        if behavior_kind == "command" and behavior.get("creates"):
            entity_type_ref = _single_entity_type(behavior, "creates")
            record = self._complete_record(entity_type_ref, input_values)
            entity_lifecycle = self.contract["entity_types"][entity_type_ref].get("entity_lifecycle")
            if entity_lifecycle and entity_lifecycle["field"] not in record:
                record[entity_lifecycle["field"]] = entity_lifecycle["initial_state"]
            self.store[entity_type_ref].append(record)
            for emit in outcome.get("emits", []):
                domain_event_id, payload = self._domain_event_payload_from_emit(emit, behavior, outcome, input_values, record)
                self._record_domain_event(domain_event_id, payload)
            self.last_result = record
            return record
        query_entity_type_ref = _result_entity_type(outcome["result"]) if behavior_kind == "query" else None
        if behavior_kind == "query" and query_entity_type_ref:
            entity_type_ref = query_entity_type_ref
            entity_key = _entity_input_key(entity_type_ref)
            selected_id = input_values.get(entity_key) or input_values.get("id")
            self.last_result = (
                self._filter(entity_type_ref, input_values)
                if _is_array_schema(outcome["result"])
                else self._find(entity_type_ref, {"id": selected_id})
            )
            return self.last_result
        if behavior_kind == "entity_lifecycle_transition":
            entity_lifecycle_transition = behavior["entity_lifecycle_transition"]
            entity_type_ref = entity_lifecycle_transition["entity_type"]
            entity_key = _entity_input_key(entity_type_ref)
            selected_id = input_values.get(entity_key) or input_values.get("id")
            record = self._find(entity_type_ref, {"id": selected_id})
            assert record[entity_lifecycle_transition["field"]] == entity_lifecycle_transition["from"]
            record[entity_lifecycle_transition["field"]] = entity_lifecycle_transition["to"]
            for emit in outcome.get("emits", []):
                domain_event_id, payload = self._domain_event_payload_from_emit(emit, behavior, outcome, input_values, record)
                self._record_domain_event(domain_event_id, payload)
            self.last_result = record
            return record
        # Commands and queries without a richer reference behavior are recorded as behavior outcomes.
        result = {"ok": True, "behavior": behavior_ref, **input_values}
        self.last_result = result
        return result

    def _emit(self, domain_event_id: str, payload: dict[str, Any]) -> None:
        self._record_domain_event(domain_event_id, payload)
        for workflow_id, workflow in self.contract["workflows"].items():
            if workflow["inputs"] == {"domain_event": domain_event_id}:
                self.workflows_executed.append(workflow_id)
                self.workflow_outputs[workflow_id] = self._run_workflow(workflow, payload)

    def _run_workflow(self, workflow: dict[str, Any], payload: dict[str, Any]) -> str:
        activity_by_id = workflow["activities"]
        current_kind = "activity"
        current_id = next(iter(activity_by_id))
        namespace: dict[str, Any] = {"workflow_input": {"payload": payload}, "activity_outcome": {}}
        while True:
            if current_kind == "activity":
                activity = activity_by_id[current_id]
                input_values = {name: _resolve_binding(source, namespace) for name, source in activity["input_mapping"].items()}
                result = self._invoke(activity["command"], input_values)
                outcome_id = self.last_outcome
                assert outcome_id is not None
                namespace["activity_outcome"].setdefault(current_id, {})[outcome_id] = {"result": result}
                transition = _workflow_sequence_flow_for_activity_result(workflow, current_id, outcome_id)
            else:
                transition = _workflow_sequence_flow_for_gateway(workflow, current_id, namespace)
            current_kind, current_id = _workflow_sequence_flow_target_ref(transition)
            if current_kind == "terminal":
                return current_id

    def _domain_event_payload_from_emit(
        self,
        emit: Any,
        behavior: Mapping[str, Any],
        outcome: Mapping[str, Any],
        input_values: Mapping[str, Any],
        result: Mapping[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        if isinstance(emit, str):
            return emit, dict(result)
        namespace = {"command_input": dict(input_values), "command_outcome": {"result": dict(result)}}
        if "payload_source" in emit:
            return emit["domain_event"], _resolve_binding(emit["payload_source"], namespace)
        return emit["domain_event"], {field: _resolve_binding(source, namespace) for field, source in emit["payload_bindings"].items()}

    def _record_domain_event(self, domain_event_id: str, payload: dict[str, Any]) -> None:
        self.emitted.append(domain_event_id)

    def _filter(self, entity_type_id: str, where: dict[str, Any]) -> list[dict[str, Any]]:
        return [record for record in self.store[entity_type_id] if _matches(record, where)]

    def _find(self, entity_type_id: str, where: dict[str, Any]) -> dict[str, Any]:
        matches = self._filter(entity_type_id, where)
        assert matches, f"No {entity_type_id} found for {where}"
        return matches[0]

    def _complete_record(self, entity_type_id: str, values: dict[str, Any]) -> dict[str, Any]:
        fields = schema_properties(self.contract["entity_types"][entity_type_id]["schema"])
        record = dict(values)
        if "id" in fields and "id" not in record:
            record["id"] = f"{entity_type_id.lower()}_{len(self.store[entity_type_id]) + 1}"
        if "created_at" in fields and "created_at" not in record:
            record["created_at"] = "2026-05-10T00:00:00Z"
        if "updated_at" in fields and "updated_at" not in record:
            record["updated_at"] = "2026-05-10T00:00:00Z"
        return record

    def _resolve_map(self, values: Mapping[str, Any]) -> dict[str, Any]:
        return resolve_map(values, self.fixtures)

    def _authorization_assertion_allowed(self, assertion: Mapping[str, Any]) -> bool:
        kind = next((candidate for candidate in ("command", "query", "external_interface") if candidate in assertion), "external_interface")
        resource_ref = assertion[kind]
        access_policy = assertion.get("access_policy")
        if access_policy:
            policy_id = access_policy
        elif kind in {"command", "query"}:
            authorization = command_query_map(self.contract)[resource_ref].get("authorization")
            if not authorization:
                return False
            policy_id = authorization["policy"]
        else:
            policy_id = self.contract["external_interfaces"][resource_ref]["access_policy"]
        recorded = self.authorization_decisions.get((kind, resource_ref, policy_id))
        if recorded is not None:
            return recorded
        input_values = {}
        if self.last_state_machine and "context" in self.last_state_machine:
            input_values.update(self.last_state_machine["context"])
        return self._evaluate_policy(policy_id, kind, resource_ref, input_values)

    def _evaluate_policy(self, policy_id: str, kind: str, resource_ref: str, input_values: Mapping[str, Any]) -> bool:
        policy = self.contract["access_policies"][policy_id]
        if not _access_policy_covers_resource(policy, kind, resource_ref):
            if kind == "external_interface":
                invoked_kind, invoked_ref = external_interface_invoked_ref_pair(self.contract["external_interfaces"][resource_ref])
                if not _access_policy_covers_resource(policy, invoked_kind, invoked_ref):
                    return False
            else:
                return False
        try:
            matched_environment = all(self._condition_matches(rule, input_values) for rule in policy.get("environment", []))
            matched_rules = all(self._condition_matches(rule["condition"], input_values) for rule in policy.get("rules", []))
            decision = _evaluate_access_policy_decision(policy, matched_environment, matched_rules)
        except (BindingExpressionError, KeyError, TypeError):
            decision = "indeterminate"
        return decision == "permit"

    def _subject_available(self, policy: Mapping[str, Any], input_values: Mapping[str, Any]) -> bool:
        for subject in policy.get("subject", []):
            if subject.get("kind") != "actor":
                continue
            source = subject.get("source")
            if source:
                try:
                    return _resolve_binding({"from": source}, {"command_input": dict(input_values), "fixture": self.fixtures}) is not None
                except (KeyError, BindingExpressionError):
                    return False
            actor = self.fixtures.get("actor", {})
            if actor.get("id"):
                return True
        return False

    def _condition_matches(self, condition: Mapping[str, Any], input_values: Mapping[str, Any]) -> bool:
        if "unconditional" in condition:
            return bool(condition["unconditional"])
        if "input_present" in condition:
            field = condition["input_present"]
            return field in input_values and input_values[field] is not None
        if "entity_exists" in condition:
            return bool(self._authorization_records(condition["entity_exists"]["entity_type"], input_values))
        if "entity_state_condition" in condition:
            body = condition["entity_state_condition"]
            return any(record.get(body["field"]) == body["equals"] for record in self._authorization_records(body["entity_type"], input_values))
        if "subject_has_role" in condition:
            role = condition["subject_has_role"]
            actor = self.fixtures.get("actor", {})
            return role in actor.get("roles", [])
        if "value_equals" in condition:
            body = condition["value_equals"]
            namespace = {"command_input": dict(input_values), "fixture": self.fixtures}
            return _resolve_binding(body["left"], namespace) == _resolve_binding(body["right"], namespace)
        return False

    def _authorization_records(self, entity_type_ref: str, input_values: Mapping[str, Any]) -> list[dict[str, Any]]:
        records = list(self.store[entity_type_ref])
        entity_key = _entity_input_key(entity_type_ref)
        selected_id = input_values.get(entity_key) or input_values.get("id")
        if selected_id is not None:
            records = [record for record in records if record.get("id") == selected_id]
        for scope_key in ("workspace_id", "tenant_id", "organization_id"):
            if scope_key in input_values:
                records = [record for record in records if record.get(scope_key) == input_values[scope_key]]
        return records


def _matches(record: Mapping[str, Any], where: Mapping[str, Any]) -> bool:
    return all(record.get(key) == value for key, value in where.items())


def _single_entity_type(behavior: Mapping[str, Any], field: str) -> str:
    entity_types = behavior[field]
    assert len(entity_types) == 1, f"Expected exactly one {field} entity_type"
    return entity_types[0]


def _entity_input_key(entity_type_ref: str) -> str:
    return f"{entity_type_ref.removeprefix('entity_type.')}_id"


def _is_array_schema(schema: Mapping[str, Any]) -> bool:
    return schema.get("type") == "array"


def _result_entity_type(schema: Mapping[str, Any]) -> str | None:
    direct = entity_type_id(schema)
    if direct:
        return direct
    if _is_array_schema(schema):
        return entity_type_id(schema.get("items", {}))
    return None


def _success_outcome_id(behavior: Mapping[str, Any]) -> str:
    successes = [outcome_id for outcome_id, outcome in behavior["outcomes"].items() if outcome["kind"] == "success"]
    assert len(successes) == 1, "Expected exactly one success outcome"
    return successes[0]


def _external_interface_response(external_interface: Mapping[str, Any], outcome_id: str | None) -> Mapping[str, Any]:
    assert outcome_id is not None
    responses = external_interface_output_responses(dict(external_interface))
    if outcome_id in responses:
        return responses[outcome_id]
    return external_interface_output_response_handlers(dict(external_interface))[outcome_id]


def _resolve_binding(binding: Any, namespace: Mapping[str, Any]) -> Any:
    if isinstance(binding, Mapping):
        if "from" in binding:
            return resolve_binding_expression(binding["from"], namespace)
        if "value" in binding:
            return binding["value"]
    return resolve_binding_expression(binding, namespace)


def _condition_matches(condition: Mapping[str, Any], context: Mapping[str, Any]) -> bool:
    if "context_non_null" in condition:
        key = condition["context_non_null"]
        return key in context and context[key] is not None
    if "context_equals" in condition:
        body = condition["context_equals"]
        return context.get(body["field"]) == body["value"]
    return False


def _authorization_resource_kind(kind: str) -> str:
    return "action" if kind in {"command", "query"} else kind


def _access_policy_covers_resource(policy: Mapping[str, Any], kind: str, resource_ref: str) -> bool:
    resource_kind = _authorization_resource_kind(kind)
    if resource_kind == "action":
        return resource_ref in policy.get("action", [])
    return any(resource == {resource_kind: resource_ref} for resource in policy.get("resource", []))


def _evaluate_access_policy_decision(policy: Mapping[str, Any], matched_environment: bool, matched_rules: bool) -> str:
    if policy["combining_algorithm"] != "all_permit_rules_must_match":
        return "indeterminate"
    if not (matched_environment and matched_rules):
        return "deny"
    return "permit"
