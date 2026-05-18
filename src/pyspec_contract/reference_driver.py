from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .io import read_json, read_yaml
from .paths import COMPILED_SPEC_PATH, GENERATED_SPEC_DIR
from .runtime import fixture_namespace, resolve_map
from .runtime_refs import resolve_reference_expression
from .targets import (
    entry_state_machine_name,
    entry_point_input,
    entry_point_response_handlers,
    entry_point_responses,
    entry_target_pair,
    entry_point_input_bindings,
)
from .json_schema import is_array_of_entity_type, entity_type_id, schema_properties


class ReferenceSpecDriver:
    """A fake/reference world for spec BDD. It proves test cases are coherent, not that prod works."""

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
        self.workflow_outcomes: dict[str, str] = {}
        self.authorization_decisions: dict[tuple[str, str, str], bool] = {}
        self.last_state_machine: dict[str, Any] | None = None
        self.response: dict[str, Any] | None = None
        self.last_result: Any = None
        self.last_outcome: str | None = None

    def given(self, test_case_id: str, test_case: Mapping[str, Any]) -> None:
        self.reset()
        self.fixtures = fixture_namespace(self.contract, list(test_case.get("given", {}).get("seed_fixtures", [])))
        for fact in test_case.get("given", {}).get("domain_facts", []):
            kind, body = next(iter(fact.items()))
            if kind == "absent":
                where = self._resolve_map(body["where"])
                self.store[body["entity_type"]] = [r for r in self.store[body["entity_type"]] if not _matches(r, where)]
            elif kind == "present":
                values = self._complete_record(body["entity_type"], self._resolve_map(body["values"]))
                self.store[body["entity_type"]].append(values)
            else:  # pragma: no cover - schema prevents this.
                raise AssertionError(f"Unsupported fact kind: {kind}")

    def when(self, test_case_id: str, test_case: Mapping[str, Any]) -> None:
        kind, body = next(iter(test_case["when"].items()))
        if kind == "open_entry_point":
            self.last_state_machine = self._open_entry_point(body["ref"], self._resolve_map(body.get("input", {})))
        elif kind == "call_entry_point":
            self.response = self._call_entry_point(body["ref"], self._resolve_map(body.get("input", {})), test_case["then"].get("outcome"))
        elif kind == "invoke_application_action":
            self.last_result = self._invoke(body["ref"], self._resolve_map(body.get("input", {})), test_case["then"].get("outcome"))
        elif kind == "emit_domain_event":
            self._emit(body["ref"], self._resolve_map(body.get("payload", {})))
        else:  # pragma: no cover - schema prevents this.
            raise AssertionError(f"Unsupported when kind: {kind}")

    def then(self, test_case_id: str, test_case: Mapping[str, Any]) -> None:
        assertions = test_case["then"]
        if "state_machine" in assertions:
            assert self.last_state_machine is not None, "Expected a rendered state machine"
            expected = assertions["state_machine"]
            assert self.last_state_machine["ref"] == expected["ref"]
            if "view_state" in expected:
                assert self.last_state_machine["view_state"] == expected["view_state"]
                assert self.last_state_machine["surface"] == expected["surface"]
            if "instances" in expected:
                assert set(self.last_state_machine["instances"]) == set(expected["instances"])
                for instance_id, state_machine_expected in expected["instances"].items():
                    actual = self.last_state_machine["instances"][instance_id]
                    assert actual["view_state"] == state_machine_expected["view_state"]
                    assert actual["surface"] == state_machine_expected["surface"]
                for sync_id in (expected.get("signal_sync_rules") or {}).get("observed_rules", []):
                    assert sync_id in self.last_state_machine.get("signal_sync_rules", [])
        requires = assertions.get("requires", {})
        if requires:
            assert self.last_state_machine is not None, "state-machine requirements need a rendered state machine"
            rendered_state_machines = self._rendered_state_machine_ids()
            rendered_text = self._rendered_values("text")
            rendered_assets = self._rendered_values("assets")
            rendered_actions = self._rendered_values("action_bindings")
            for state_machine in requires.get("surfaces", []):
                assert state_machine in self.surfaces
                assert state_machine in rendered_state_machines
            for key in requires.get("text", []):
                assert key in rendered_text
            for key in requires.get("assets", []):
                assert key in rendered_assets
            for cap in requires.get("action_bindings", []):
                assert cap in rendered_actions
            rendered_queries = self._rendered_values("data_loaders")
            for query in requires.get("data_loaders", []):
                assert query in rendered_queries
        for cap in assertions.get("enables", []):
            assert cap in self._rendered_application_action_refs()
        for cap in assertions.get("forbids", []):
            assert cap not in self._rendered_application_action_refs()
        exists = (assertions.get("entity_type") or {}).get("exists")
        if exists:
            where = self._resolve_map(exists["where"])
            assert any(_matches(record, where) for record in self.store[exists["entity_type"]]), f"Missing entity_type {exists}"
        domain_events = assertions.get("domain_events") or {}
        for event_id in domain_events.get("emitted", []):
            assert event_id in self.emitted
        for event_id in domain_events.get("not_emitted", []):
            assert event_id not in self.emitted
        workflow = assertions.get("workflow")
        if workflow:
            if workflow["executed"]:
                assert workflow["ref"] in self.workflows_executed
            else:
                assert workflow["ref"] not in self.workflows_executed
            if "outcome" in workflow:
                assert self.workflow_outcomes.get(workflow["ref"]) == workflow["outcome"]
        for cap in assertions.get("invoked", []):
            assert cap in self.invoked
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
            assert self._authorization_assertion_allowed(assertion), f"Expected authorization policy to allow {assertion}"
        for assertion in policy.get("denied", []):
            assert not self._authorization_assertion_allowed(assertion), f"Expected authorization policy to deny {assertion}"
        for fact in assertions.get("expected_facts", []):
            kind, body = next(iter(fact.items()))
            if kind == "present":
                values = self._resolve_map(body["values"])
                assert any(_matches(record, values) for record in self.store[body["entity_type"]]), f"Missing assertion fact {body}"
            elif kind == "absent":
                where = self._resolve_map(body["where"])
                assert not any(_matches(record, where) for record in self.store[body["entity_type"]]), f"Unexpected assertion fact {body}"

    def _open_entry_point(self, entry_id: str, input_values: dict[str, Any]) -> dict[str, Any]:
        entry = self.contract["entry_points"][entry_id]
        state_machine_id = entry_state_machine_name(entry)
        state_machine = self.contract["state_machines"][state_machine_id]
        context = self._entry_target_input(entry, input_values)
        records = self._filter(state_machine["entity_type"], context) if state_machine.get("entity_type") else []
        parent_state_name = "ready" if "ready" in state_machine.get("view_states", {}) else next(iter(state_machine.get("view_states", {"ready": {}})))
        state = state_machine["view_states"].get(parent_state_name, {"surface": None, "text": [], "assets": [], "action_bindings": {}, "data_loaders": {}})
        if state.get("child_state_machines"):
            parent_state_machine = state_machine
            state_machines: dict[str, Any] = {}
            for mount in state["child_state_machines"]:
                source_id = mount["state_machine"]
                child_state_machine = self.contract["state_machines"][source_id]
                child_state_name = self._choose_state_machine_view_state(child_state_machine, mount, records, context)
                child_state = child_state_machine["view_states"][child_state_name]
                state_machines[mount["id"]] = {
                    "source": source_id,
                    "view_state": child_state_name,
                    "surface": child_state["surface"],
                    "data_loaders": {
                        **child_state_machine.get("data_loaders", {}),
                        **child_state.get("data_loaders", {}),
                    },
                    "text": child_state["text"],
                    "assets": child_state["assets"],
                    "action_bindings": child_state["action_bindings"],
                }
            return {
                "ref": state_machine_id,
                "view_state": parent_state_name,
                "surface": state.get("surface"),
                "data_loaders": {
                    **parent_state_machine.get("data_loaders", {}),
                    **state.get("data_loaders", {}),
                },
                "text": state.get("text", []),
                "assets": state.get("assets", []),
                "action_bindings": state.get("action_bindings", {}),
                "context": context,
                "instances": state_machines,
                "signal_sync_rules": [rule["id"] for rule in state.get("signal_sync_rules", [])],
            }
        state_name = "empty" if not records and "empty" in state_machine["view_states"] else "ready"
        state = state_machine["view_states"][state_name]
        return {
            "ref": state_machine_id,
            "view_state": state_name,
            "surface": state["surface"],
            "text": state["text"],
            "assets": state["assets"],
            "data_loaders": {
                **state_machine.get("data_loaders", {}),
                **state.get("data_loaders", {}),
            },
            "action_bindings": state["action_bindings"],
        }

    def _choose_state_machine_view_state(self, state_machine: dict[str, Any], mount: dict[str, Any], records: list[dict[str, Any]], context: dict[str, Any]) -> str:
        selected = mount.get("selected")
        if selected:
            if _condition_matches(selected["when"], context):
                return selected["view_state"]
            return mount["initial_view_state"]
        if records and "ready" in state_machine["view_states"] and (state_machine.get("data_loaders") or state_machine["view_states"]["ready"].get("data_loaders")):
            return "ready"
        if not records and "empty" in state_machine["view_states"]:
            return "empty"
        return mount["initial_view_state"]

    def _rendered_state_machine_ids(self) -> set[str]:
        if not self.last_state_machine:
            return set()
        if "instances" in self.last_state_machine:
            state_machines = {state_machine["surface"] for state_machine in self.last_state_machine["instances"].values()}
            if self.last_state_machine.get("surface"):
                state_machines.add(self.last_state_machine["surface"])
            return state_machines
        return {self.last_state_machine["surface"]}

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

    def _rendered_application_action_refs(self) -> set[str]:
        if not self.last_state_machine:
            return set()

        def application_actions(item: dict[str, Any]) -> set[str]:
            invocations = item.get("action_bindings") or {}
            return {invocation["application_action"] for invocation in invocations.values()}

        if "instances" in self.last_state_machine:
            refs = application_actions(self.last_state_machine)
            for state_machine in self.last_state_machine["instances"].values():
                refs.update(application_actions(state_machine))
            return refs
        return application_actions(self.last_state_machine)

    def _call_entry_point(self, entry_id: str, input_values: dict[str, Any], outcome_id: str | None = None) -> dict[str, Any]:
        entry = self.contract["entry_points"][entry_id]
        target_kind, cap_id = entry_target_pair(entry)
        policy_id = entry.get("authorization_policy")
        if policy_id:
            self.authorization_decisions[("entry_point", entry_id, policy_id)] = self._evaluate_policy(policy_id, "entry_point", entry_id, input_values)
        if target_kind == "entry_point":
            target_input = self._entry_delegate_input(entry, input_values)
            delegated_response = self._call_entry_point(cap_id, target_input, outcome_id)
            handler = entry_point_response_handlers(entry)[self.last_outcome]
            if "stdout" in handler:
                return {"exit_code": handler["exit_code"], "stdout": self._cli_output(handler["stdout"], delegated_response, input_values)}
            return {"exit_code": handler["exit_code"], "stderr": self._cli_output(handler["stderr"], delegated_response, input_values)}
        assert target_kind == "application_action"
        target_input = self._entry_target_input(entry, input_values)
        result = self._invoke(cap_id, target_input, outcome_id)
        response = _entry_point_response(entry, self.last_outcome)
        if "status" in response:
            return {"status": response["status"], "body": result}
        if "stdout" in response:
            return {"exit_code": response["exit_code"], "stdout": self._cli_output(response["stdout"], {"body": result}, input_values)}
        return {"exit_code": response["exit_code"], "stderr": self._cli_output(response["stderr"], {"body": result}, input_values)}

    def _entry_target_input(self, entry: dict[str, Any], input_values: dict[str, Any]) -> dict[str, Any]:
        namespace = {"input": {}}
        for section in ("path_params", "query_params", "body", "args"):
            fields = entry_point_input(entry).get(section, {})
            if fields:
                namespace["input"][section] = {name: input_values[name] for name in fields}
        bindings = entry_point_input_bindings(entry)
        return {name: _resolve_binding(source, namespace) for name, source in bindings.items()}

    def _entry_delegate_input(self, entry: dict[str, Any], input_values: dict[str, Any]) -> dict[str, Any]:
        namespace = {"input": {}}
        for section in ("path_params", "query_params", "body", "args"):
            fields = entry_point_input(entry).get(section, {})
            if fields:
                namespace["input"][section] = {name: input_values[name] for name in fields}
        if "payload" in entry_point_input(entry):
            namespace["input"]["payload"] = input_values.get("payload", input_values)
        delegated_input: dict[str, Any] = {}
        for section, section_bindings in entry_point_input_bindings(entry).items():
            if section == "payload" and isinstance(section_bindings, Mapping) and "from" in section_bindings:
                delegated_input["payload"] = _resolve_binding(section_bindings, namespace)
                continue
            if isinstance(section_bindings, Mapping):
                for name, source in section_bindings.items():
                    delegated_input[name] = _resolve_binding(source, namespace)
        return delegated_input

    def _cli_output(self, output: Mapping[str, Any], response: Mapping[str, Any], input_values: Mapping[str, Any]) -> dict[str, Any]:
        namespace = {"response": response, "outcome": {"result": response.get("body")}, "input": dict(input_values)}
        return {
            "text": output["text"],
            "bindings": {
                name: _resolve_binding(binding, namespace)
                for name, binding in (output.get("bindings") or {}).items()
            },
        }

    def _invoke(self, cap_id: str, input_values: dict[str, Any], outcome_id: str | None = None) -> Any:
        cap = self.contract["application_actions"][cap_id]
        authorization = cap.get("authorization")
        if authorization:
            policy_id = authorization["policy"]
            allowed = self._evaluate_policy(policy_id, "application_action", cap_id, input_values)
            self.authorization_decisions[("application_action", cap_id, policy_id)] = allowed
            if not allowed:
                policy = self.contract["authorization_policies"][policy_id]
                outcome_id = (
                    authorization["forbidden_as"]
                    if self._authorization_subject_available(policy, input_values)
                    else authorization["unauthenticated_as"]
                )
                self.last_outcome = outcome_id
                self.last_result = {"code": outcome_id, "message": outcome_id.replace("_", " ")}
                return self.last_result
        self.invoked.append(cap_id)
        outcome_id = outcome_id or _success_outcome_id(cap)
        outcome = cap["outcomes"][outcome_id]
        self.last_outcome = outcome_id
        if outcome["kind"] == "failure":
            self.last_result = {"code": outcome_id, "message": outcome_id.replace("_", " ")}
            return self.last_result
        action_kind = cap["action_kind"]
        if action_kind == "command" and cap.get("creates"):
            entity_type_ref = _single_entity_type(cap, "creates")
            record = self._complete_record(entity_type_ref, input_values)
            entity_lifecycle = self.contract["entity_types"][entity_type_ref].get("entity_lifecycle")
            if entity_lifecycle and entity_lifecycle["field"] not in record:
                record[entity_lifecycle["field"]] = entity_lifecycle["initial_state"]
            self.store[entity_type_ref].append(record)
            for emit in outcome.get("emits", []):
                event_id, payload = self._event_payload_from_emit(emit, cap, outcome, input_values, record)
                self._record_event(event_id, payload)
            self.last_result = record
            return record
        if action_kind == "query" and cap.get("reads") and entity_type_id(outcome["result"]):
            entity_type_ref = _single_entity_type(cap, "reads")
            entity_key = _entity_input_key(entity_type_ref)
            self.last_result = self._find(entity_type_ref, {"id": input_values.get(entity_key) or input_values.get("id")})
            return self.last_result
        if action_kind == "query" and cap.get("reads") and is_array_of_entity_type(outcome["result"], _single_entity_type(cap, "reads")):
            entity_type_ref = _single_entity_type(cap, "reads")
            self.last_result = self._filter(entity_type_ref, input_values)
            return self.last_result
        if action_kind == "lifecycle_transition":
            lifecycle_transition = cap["lifecycle_transition"]
            entity_type_ref = lifecycle_transition["entity_type"]
            entity_key = _entity_input_key(entity_type_ref)
            selected_id = input_values.get(entity_key) or input_values.get("id")
            record = self._find(entity_type_ref, {"id": selected_id})
            assert record[lifecycle_transition["field"]] == lifecycle_transition["from"]
            record[lifecycle_transition["field"]] = lifecycle_transition["to"]
            for emit in outcome.get("emits", []):
                event_id, payload = self._event_payload_from_emit(emit, cap, outcome, input_values, record)
                self._record_event(event_id, payload)
            self.last_result = record
            return record
        # Command/query application_actions are recorded as effects in the spec world.
        result = {"ok": True, "application_action": cap_id, **input_values}
        self.last_result = result
        return result

    def _emit(self, event_id: str, payload: dict[str, Any]) -> None:
        self._record_event(event_id, payload)
        for workflow_id, workflow in self.contract["workflows"].items():
            if workflow["trigger"] == {"domain_event": event_id}:
                self.workflows_executed.append(workflow_id)
                self.workflow_outcomes[workflow_id] = self._run_workflow(workflow, payload)

    def _run_workflow(self, workflow: dict[str, Any], payload: dict[str, Any]) -> str:
        step_by_id = {step["id"]: step for step in workflow["steps"]}
        current = workflow["steps"][0]["id"]
        namespace: dict[str, Any] = {"trigger": {"payload": payload}, "steps": {}}
        while True:
            step = step_by_id[current]
            input_values = {name: _resolve_binding(source, namespace) for name, source in step["input_bindings"].items()}
            result = self._invoke(step["application_action"], input_values)
            outcome_id = self.last_outcome
            assert outcome_id is not None
            namespace["steps"].setdefault(step["id"], {"outcomes": {}})["outcomes"][outcome_id] = {"result": result}
            transition = step["outcome_transitions"][outcome_id]
            if "complete_as" in transition:
                return transition["complete_as"]
            if "fail_as" in transition:
                return transition["fail_as"]
            if "retry_policy" in transition:
                return transition["retry_policy"]["fail_as"]
            if "dead_letter_as" in transition:
                return transition["dead_letter_as"]
            current = transition["next_step"]

    def _event_payload_from_emit(
        self,
        emit: Any,
        application_action: Mapping[str, Any],
        outcome: Mapping[str, Any],
        input_values: Mapping[str, Any],
        result: Mapping[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        if isinstance(emit, str):
            return emit, dict(result)
        namespace = {"input": dict(input_values), "outcome": {"result": dict(result)}}
        if "payload_source" in emit:
            return emit["domain_event"], _resolve_binding(emit["payload_source"], namespace)
        return emit["domain_event"], {field: _resolve_binding(source, namespace) for field, source in emit["payload_bindings"].items()}

    def _record_event(self, event_id: str, payload: dict[str, Any]) -> None:
        self.emitted.append(event_id)

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
        kind = "application_action" if "application_action" in assertion else "entry_point"
        target_ref = assertion[kind]
        authorization_policy = assertion.get("authorization_policy")
        if authorization_policy:
            policy_id = authorization_policy
        elif kind == "application_action":
            authorization = self.contract["application_actions"][target_ref].get("authorization")
            if not authorization:
                return False
            policy_id = authorization["policy"]
        else:
            policy_id = self.contract["entry_points"][target_ref]["authorization_policy"]
        recorded = self.authorization_decisions.get((kind, target_ref, policy_id))
        if recorded is not None:
            return recorded
        input_values = {}
        if self.last_state_machine and "context" in self.last_state_machine:
            input_values.update(self.last_state_machine["context"])
        return self._evaluate_policy(policy_id, kind, target_ref, input_values)

    def _evaluate_policy(self, policy_id: str, kind: str, target_ref: str, input_values: Mapping[str, Any]) -> bool:
        policy = self.contract["authorization_policies"][policy_id]
        if not _authorization_policy_covers_target(policy, kind, target_ref):
            if kind == "entry_point":
                target_kind, target = entry_target_pair(self.contract["entry_points"][target_ref])
                if not _authorization_policy_covers_target(policy, target_kind, target):
                    return False
            else:
                return False
        matched = all(self._authorization_condition_matches(condition, input_values) for condition in policy.get("conditions", []))
        return matched if policy["effect"] == "allow" else not matched

    def _authorization_subject_available(self, policy: Mapping[str, Any], input_values: Mapping[str, Any]) -> bool:
        for subject in policy.get("subjects", []):
            if subject.get("kind") != "actor":
                continue
            source = subject.get("source")
            if source:
                try:
                    return _resolve_binding({"from": source}, {"input": dict(input_values), "fixture": self.fixtures}) is not None
                except (KeyError, ReferenceExpressionError):
                    return False
            actor = self.fixtures.get("actor", {})
            if actor.get("id"):
                return True
        return False

    def _authorization_condition_matches(self, condition: Mapping[str, Any], input_values: Mapping[str, Any]) -> bool:
        if "unconditional" in condition:
            return bool(condition["unconditional"])
        if "input_present" in condition:
            field = condition["input_present"]
            return field in input_values and input_values[field] is not None
        if "entity_exists" in condition:
            return bool(self._authorization_records(condition["entity_exists"]["entity_type"], input_values))
        if "entity_lifecycle_state" in condition:
            body = condition["entity_lifecycle_state"]
            return any(record.get(body["field"]) == body["equals"] for record in self._authorization_records(body["entity_type"], input_values))
        if "subject_has_role" in condition:
            role = condition["subject_has_role"]
            actor = self.fixtures.get("actor", {})
            return role in actor.get("roles", [])
        if "value_equals" in condition:
            body = condition["value_equals"]
            namespace = {"input": dict(input_values), "fixture": self.fixtures}
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


def _single_entity_type(application_action: Mapping[str, Any], field: str) -> str:
    entity_types = application_action[field]
    assert len(entity_types) == 1, f"Expected exactly one {field} entity_type"
    return entity_types[0]


def _entity_input_key(entity_type_ref: str) -> str:
    return f"{entity_type_ref.removeprefix('entity_type.')}_id"


def _success_outcome_id(application_action: Mapping[str, Any]) -> str:
    successes = [outcome_id for outcome_id, outcome in application_action["outcomes"].items() if outcome["kind"] == "success"]
    assert len(successes) == 1, "Expected exactly one success outcome"
    return successes[0]


def _entry_point_response(entry: Mapping[str, Any], outcome_id: str | None) -> Mapping[str, Any]:
    assert outcome_id is not None
    responses = entry_point_responses(dict(entry))
    if outcome_id in responses:
        return responses[outcome_id]
    return entry_point_response_handlers(dict(entry))[outcome_id]


def _resolve_binding(binding: Any, namespace: Mapping[str, Any]) -> Any:
    if isinstance(binding, Mapping):
        if "from" in binding:
            return resolve_reference_expression(binding["from"], namespace)
        if "value" in binding:
            return binding["value"]
    return resolve_reference_expression(binding, namespace)


def _condition_matches(condition: Mapping[str, Any], context: Mapping[str, Any]) -> bool:
    if "context_present" in condition:
        key = condition["context_present"]
        return key in context and context[key] is not None
    if "context_equals" in condition:
        body = condition["context_equals"]
        return context.get(body["field"]) == body["value"]
    return False


def _authorization_policy_covers_target(policy: Mapping[str, Any], kind: str, target_ref: str) -> bool:
    return any(target == {kind: target_ref} for target in policy.get("targets", []))
