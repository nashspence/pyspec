from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from pyspec_contract.io import read_json, read_yaml
from pyspec_contract.operations import operation_resource_kind, operations
from pyspec_contract.paths import COMPILED_SPEC_PATH, GENERATED_SPEC_DIR
from pyspec_contract.runtime import fixture_namespace, resolve_binding, resolve_map
from pyspec_contract.targets import external_interface_state_machine_name, external_interface_adapter_pair, external_interface_input_bindings, external_interface_input, external_interface_responses, external_interface_target_ref_pair


PROJECT_ENTITY_TYPE = "entity_type.project"


class ProductApp:
    """A minimal real app surface for the starter's prod BDD harness.

    It is intentionally small, but the prod driver calls this app instead of the
    reference spec driver. Real projects replace this module, not the generated
    BDD protocol.
    """

    def __init__(self, root: Path):
        self.root = root
        self.contract = read_yaml(root / COMPILED_SPEC_PATH)
        self.surfaces = {p["id"]: p for p in read_json(root / GENERATED_SPEC_DIR / "product_interfaces" / "html.state_machines.json")["state_machines"]}
        self.reset()

    def reset(self) -> None:
        self.fixtures: dict[str, Any] = {}
        self.projects: list[dict[str, Any]] = []
        self.emitted_domain_events: list[str] = []
        self.invoked_operations: list[str] = []
        self.executed_workflows: list[str] = []
        self.workflow_outcomes: dict[str, str] = {}
        self.authorization_decisions: dict[tuple[str, str, str], bool] = {}
        self.rendered_state_machine: dict[str, Any] | None = None
        self.http_response: dict[str, Any] | None = None
        self.last_outcome: str | None = None

    def given(self, given: Mapping[str, Any]) -> None:
        self.reset()
        self.fixtures = fixture_namespace(self.contract, list(given.get("seed_fixtures", [])))
        for precondition in given.get("preconditions", []):
            kind, body = next(iter(precondition.items()))
            if body["entity_type"] != PROJECT_ENTITY_TYPE:
                raise AssertionError("Example app only implements Project")
            if kind == "absent":
                where = self._resolve_map(body["where"])
                self.projects = [p for p in self.projects if not _matches(p, where)]
            elif kind == "present":
                self.projects.append(self._project(self._resolve_map(body["values"])))

    def open_web_entry(self, entry_id: str, input_values: Mapping[str, Any]) -> dict[str, Any]:
        entry = self.contract["external_interfaces"][entry_id]
        assert external_interface_adapter_pair(entry)[0] == "html_route"
        state_machine_id = external_interface_state_machine_name(entry)
        state_machine = self.contract["state_machines"][state_machine_id]
        context = self._entry_target_input(entry, input_values)
        workspace_id = context.get("workspace_id")
        matching = [p for p in self.projects if p.get("workspace_id") == workspace_id]
        parent_state_name = "ready" if "ready" in state_machine.get("view_states", {}) else next(iter(state_machine.get("view_states", {"ready": {}})))
        parent_state = state_machine["view_states"].get(parent_state_name, {"surface": None, "text": [], "assets": [], "action_bindings": {}, "data_loaders": {}})
        if parent_state.get("child_state_machines"):
            parent_state_machine = state_machine
            state_machines: dict[str, Any] = {}
            for mount in parent_state["child_state_machines"]:
                source_id = mount["state_machine"]
                child_state_machine = self.contract["state_machines"][source_id]
                state_name = self._choose_state_machine_state(child_state_machine, mount, matching, context)
                state = child_state_machine["view_states"][state_name]
                state_machines[mount["id"]] = {
                    "source": source_id,
                    "view_state": state_name,
                    "surface": state["surface"],
                    "data_loaders": {
                        **child_state_machine.get("data_loaders", {}),
                        **state.get("data_loaders", {}),
                    },
                    "text": list(state["text"]),
                    "assets": list(state["assets"]),
                    "action_bindings": dict(state["action_bindings"]),
                }
            self.rendered_state_machine = {
                "ref": state_machine_id,
                "view_state": parent_state_name,
                "surface": parent_state.get("surface"),
                "data_loaders": {
                    **parent_state_machine.get("data_loaders", {}),
                    **parent_state.get("data_loaders", {}),
                },
                "text": list(parent_state.get("text", [])),
                "assets": list(parent_state.get("assets", [])),
                "action_bindings": dict(parent_state.get("action_bindings", {})),
                "context": context,
                "instances": state_machines,
                "signal_sync_rules": [rule["id"] for rule in parent_state.get("signal_sync_rules", [])],
            }
            return self.rendered_state_machine
        state_name = "ready" if matching else "empty"
        state = state_machine["view_states"][state_name]
        self.rendered_state_machine = {
            "ref": state_machine_id,
            "view_state": state_name,
            "surface": state["surface"],
            "text": list(state["text"]),
            "assets": list(state["assets"]),
            "data_loaders": {
                **state_machine.get("data_loaders", {}),
                **state.get("data_loaders", {}),
            },
            "action_bindings": dict(state["action_bindings"]),
        }
        return self.rendered_state_machine

    def _choose_state_machine_state(self, state_machine: dict[str, Any], mount: dict[str, Any], records: list[dict[str, Any]], context: dict[str, Any]) -> str:
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
        if not self.rendered_state_machine:
            return set()
        if "instances" in self.rendered_state_machine:
            state_machines = {state_machine["surface"] for state_machine in self.rendered_state_machine["instances"].values()}
            if self.rendered_state_machine.get("surface"):
                state_machines.add(self.rendered_state_machine["surface"])
            return state_machines
        return {self.rendered_state_machine["surface"]}

    def _rendered_values(self, key: str) -> set[str]:
        if not self.rendered_state_machine:
            return set()
        if "instances" in self.rendered_state_machine:
            values: set[str] = set()
            values.update(self.rendered_state_machine.get(key, []))
            for state_machine in self.rendered_state_machine["instances"].values():
                values.update(state_machine.get(key, []))
            return values
        return set(self.rendered_state_machine.get(key, []))

    def _rendered_operation_refs(self) -> set[str]:
        if not self.rendered_state_machine:
            return set()

        def operation_refs(item: dict[str, Any]) -> set[str]:
            invocations = item.get("action_bindings") or {}
            return {invocation.get("command") or invocation.get("query") for invocation in invocations.values()}

        if "instances" in self.rendered_state_machine:
            refs = operation_refs(self.rendered_state_machine)
            for state_machine in self.rendered_state_machine["instances"].values():
                refs.update(operation_refs(state_machine))
            return refs
        return operation_refs(self.rendered_state_machine)

    def call_external_interface(self, entry_id: str, input_values: Mapping[str, Any]) -> dict[str, Any]:
        entry = self.contract["external_interfaces"][entry_id]
        assert external_interface_adapter_pair(entry)[0] in {"http_api", "cli"}
        target_input = self._entry_target_input(entry, input_values)
        target_kind, operation_ref = external_interface_target_ref_pair(entry)
        assert target_kind in {"command", "query"}
        access_policy = entry.get("access_policy")
        if access_policy:
            self.authorization_decisions[("external_interface", entry_id, access_policy)] = self._evaluate_policy(access_policy, "external_interface", entry_id, target_input)
        result = self.invoke_operation(operation_ref, target_input)
        response = external_interface_responses(entry)[self.last_outcome]
        if "status" in response:
            self.http_response = {"status": response["status"], "body": result}
        elif "stdout" in response:
            self.http_response = {"exit_code": response["exit_code"], "stdout": result}
        else:
            self.http_response = {"exit_code": response["exit_code"], "stderr": result}
        return self.http_response

    def _entry_target_input(self, entry: Mapping[str, Any], input_values: Mapping[str, Any]) -> dict[str, Any]:
        namespace = {"adapter_input": {}}
        for section in ("path_params", "query_params", "body", "args"):
            fields = external_interface_input(dict(entry)).get(section, {})
            if fields:
                namespace["adapter_input"][section] = {name: input_values[name] for name in fields}
        bindings = external_interface_input_bindings(dict(entry))
        return {name: resolve_binding(source, namespace) for name, source in bindings.items()}

    def invoke_operation(self, operation_ref: str, input_values: Mapping[str, Any]) -> Any:
        operation = operations(self.contract)[operation_ref]
        authorization = operation.get("authorization")
        if authorization:
            access_policy = authorization["policy"]
            resource_kind = operation_resource_kind(operation_ref)
            allowed = self._evaluate_policy(access_policy, resource_kind, operation_ref, input_values)
            self.authorization_decisions[(resource_kind, operation_ref, access_policy)] = allowed
            if not allowed:
                policy = self.contract["access_policies"][access_policy]
                self.last_outcome = (
                    authorization["access_denied_as"]
                    if self._subject_available(policy, input_values)
                    else authorization["authentication_required_as"]
                )
                return {"code": self.last_outcome, "message": self.last_outcome.replace("_", " ")}
        self.invoked_operations.append(operation_ref)
        self.last_outcome = _success_outcome_id(operation)
        values = dict(input_values)
        if operation_ref == "command.project.create":
            project = self._project(values)
            self.projects.append(project)
            self._record_domain_event("domain_event.project.created")
            return project
        if operation_ref == "query.project.list":
            return [p for p in self.projects if p["workspace_id"] == values.get("workspace_id")]
        if operation_ref == "command.project.submit":
            project = self._find_project(values["project_id"])
            assert project["status"] == "draft"
            project["status"] = "submitted"
            self._record_domain_event("domain_event.project.submitted")
            return project
        if operation_ref == "command.project.approve":
            project = self._find_project(values["project_id"])
            assert project["status"] == "submitted"
            project["status"] = "approved"
            project["approved_by"] = values["approved_by"]
            self._record_domain_event("domain_event.project.approved")
            return project
        if operation_ref == "command.project.archive":
            project = self._find_project(values["project_id"])
            assert project["status"] == "approved"
            project["status"] = "archived"
            self._record_domain_event("domain_event.project.archived")
            return project
        if operation_ref == "command.project.send_approval_notice":
            return {"ok": True, "sent": True, **values}
        raise AssertionError(f"Unsupported operation: {operation_ref}")

    def emit_domain_event(self, event_id: str, payload: Mapping[str, Any]) -> None:
        self._record_domain_event(event_id)
        for workflow_id, workflow in self.contract["workflows"].items():
            if workflow["trigger"] == {"domain_event": event_id}:
                self.executed_workflows.append(workflow_id)
                self.workflow_outcomes[workflow_id] = self._run_workflow(workflow, payload)

    def _run_workflow(self, workflow: Mapping[str, Any], payload: Mapping[str, Any]) -> str:
        step_by_id = {step["id"]: step for step in workflow["steps"]}
        current = workflow["steps"][0]["id"]
        namespace: dict[str, Any] = {"workflow_input": {"payload": dict(payload)}, "step_outcome": {}}
        while True:
            step = step_by_id[current]
            input_values = {name: resolve_binding(source, namespace) for name, source in step["input_bindings"].items()}
            result = self.invoke_operation(step["command"], input_values)
            assert self.last_outcome is not None
            namespace["step_outcome"].setdefault(step["id"], {})[self.last_outcome] = {"result": result}
            transition = step["outcome_transitions"][self.last_outcome]
            if "complete_as" in transition:
                return transition["complete_as"]
            if "fail_as" in transition:
                return transition["fail_as"]
            if "retry_policy" in transition:
                return transition["retry_policy"]["fail_as"]
            if "dead_letter_as" in transition:
                return transition["dead_letter_as"]
            current = transition["next_step"]

    def assert_contract(self, assertions: Mapping[str, Any]) -> None:
        if "state_machine" in assertions:
            expected = assertions["state_machine"]
            assert self.rendered_state_machine is not None
            assert self.rendered_state_machine["ref"] == expected["ref"]
            if "view_state" in expected:
                assert self.rendered_state_machine["view_state"] == expected["view_state"]
                assert self.rendered_state_machine["surface"] == expected["surface"]
            if "instances" in expected:
                assert set(self.rendered_state_machine["instances"]) == set(expected["instances"])
                for instance_id, state_machine_expected in expected["instances"].items():
                    actual = self.rendered_state_machine["instances"][instance_id]
                    assert actual["view_state"] == state_machine_expected["view_state"]
                    assert actual["surface"] == state_machine_expected["surface"]
                for sync_id in (expected.get("signal_sync_rules") or {}).get("observed_rules", []):
                    assert sync_id in self.rendered_state_machine.get("signal_sync_rules", [])
        requires = assertions.get("requires", {})
        if requires:
            assert self.rendered_state_machine is not None
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
        for cap in assertions.get("enables", []):
            assert cap in self._rendered_operation_refs()
        for cap in assertions.get("forbids", []):
            assert cap not in self._rendered_operation_refs()
        exists = (assertions.get("entity") or {}).get("exists")
        if exists:
            where = self._resolve_map(exists["where"])
            assert any(_matches(project, where) for project in self.projects)
        domain_events = assertions.get("domain_events") or {}
        for event_id in domain_events.get("emitted", []):
            assert event_id in self.emitted_domain_events
        for event_id in domain_events.get("not_emitted", []):
            assert event_id not in self.emitted_domain_events
        workflow = assertions.get("workflow")
        if workflow:
            assert (workflow["ref"] in self.executed_workflows) is workflow["executed"]
            if "outcome" in workflow:
                assert self.workflow_outcomes.get(workflow["ref"]) == workflow["outcome"]
        for cap in assertions.get("invoked", []):
            assert cap in self.invoked_operations
        response = assertions.get("response")
        if response:
            assert self.http_response is not None
            for key in ("status", "exit_code"):
                if key in response:
                    assert self.http_response[key] == response[key]
        outcome = assertions.get("outcome")
        if outcome:
            assert self.last_outcome == outcome
        policy = assertions.get("authorization")
        if policy:
            for assertion in policy.get("allowed", []):
                assert self._authorization_assertion_allowed(assertion)
            for assertion in policy.get("denied", []):
                assert not self._authorization_assertion_allowed(assertion)
        for assertion in assertions.get("postconditions", []):
            kind, body = next(iter(assertion.items()))
            if body["entity_type"] != PROJECT_ENTITY_TYPE:
                raise AssertionError("Example app only implements Project")
            if kind == "present":
                values = self._resolve_map(body["values"])
                assert any(_matches(project, values) for project in self.projects)
            elif kind == "absent":
                where = self._resolve_map(body["where"])
                assert not any(_matches(project, where) for project in self.projects)

    def _project(self, values: Mapping[str, Any]) -> dict[str, Any]:
        project = dict(values)
        project.setdefault("id", f"project_{len(self.projects) + 1}")
        project.setdefault("status", "draft")
        project.setdefault("created_at", "2026-05-10T00:00:00Z")
        project.setdefault("updated_at", "2026-05-10T00:00:00Z")
        return project

    def _find_project(self, project_id: str) -> dict[str, Any]:
        for project in self.projects:
            if project["id"] == project_id:
                return project
        raise AssertionError(f"Project not found: {project_id}")

    def _record_domain_event(self, event_id: str) -> None:
        self.emitted_domain_events.append(event_id)

    def _resolve_map(self, values: Mapping[str, Any]) -> dict[str, Any]:
        return resolve_map(values, self.fixtures)

    def _authorization_assertion_allowed(self, assertion: Mapping[str, Any]) -> bool:
        kind = next((candidate for candidate in ("command", "query", "external_interface") if candidate in assertion), "external_interface")
        resource_ref = assertion[kind]
        access_policy = assertion.get("access_policy")
        if access_policy:
            policy_id = access_policy
        elif kind in {"command", "query"}:
            authorization = operations(self.contract)[resource_ref].get("authorization")
            if not authorization:
                return False
            policy_id = authorization["policy"]
        else:
            policy_id = self.contract["external_interfaces"][resource_ref]["access_policy"]
        recorded = self.authorization_decisions.get((kind, resource_ref, policy_id))
        if recorded is not None:
            return recorded
        input_values: dict[str, Any] = {}
        if self.rendered_state_machine and "context" in self.rendered_state_machine:
            input_values.update(self.rendered_state_machine["context"])
        return self._evaluate_policy(policy_id, kind, resource_ref, input_values)

    def _evaluate_policy(self, policy_id: str, kind: str, resource_ref: str, input_values: Mapping[str, Any]) -> bool:
        policy = self.contract["access_policies"][policy_id]
        if not _access_policy_covers_resource(policy, kind, resource_ref):
            if kind != "external_interface":
                return False
            invoked_kind, invoked_ref = external_interface_target_ref_pair(self.contract["external_interfaces"][resource_ref])
            if not _access_policy_covers_resource(policy, invoked_kind, invoked_ref):
                return False
        matched = all(self._condition_matches(condition, input_values) for condition in policy.get("conditions", []))
        return matched if policy["effect"] == "permit" else not matched

    def _subject_available(self, policy: Mapping[str, Any], input_values: Mapping[str, Any]) -> bool:
        for subject in policy.get("subjects", []):
            if subject.get("kind") != "actor":
                continue
            source = subject.get("source")
            if source:
                try:
                    return resolve_binding({"from": source}, {"operation_input": dict(input_values), "fixture": self.fixtures}) is not None
                except Exception:
                    return False
            if self.fixtures.get("actor", {}).get("id"):
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
            return any(project.get(body["field"]) == body["equals"] for project in self._authorization_records(body["entity_type"], input_values))
        if "subject_has_role" in condition:
            return condition["subject_has_role"] in self.fixtures.get("actor", {}).get("roles", [])
        if "value_equals" in condition:
            body = condition["value_equals"]
            namespace = {"operation_input": dict(input_values), "fixture": self.fixtures}
            return resolve_binding(body["left"], namespace) == resolve_binding(body["right"], namespace)
        return False

    def _authorization_records(self, entity_type_ref: str, input_values: Mapping[str, Any]) -> list[dict[str, Any]]:
        if entity_type_ref != PROJECT_ENTITY_TYPE:
            return []
        records = list(self.projects)
        selected_id = input_values.get("project_id") or input_values.get("id")
        if selected_id is not None:
            records = [project for project in records if project.get("id") == selected_id]
        if "workspace_id" in input_values:
            records = [project for project in records if project.get("workspace_id") == input_values["workspace_id"]]
        return records


def _matches(record: Mapping[str, Any], where: Mapping[str, Any]) -> bool:
    return all(record.get(key) == value for key, value in where.items())


def _success_outcome_id(operation: Mapping[str, Any]) -> str:
    successes = [outcome_id for outcome_id, outcome in operation["outcomes"].items() if outcome["kind"] == "success"]
    assert len(successes) == 1, "Expected exactly one success outcome"
    return successes[0]


def _condition_matches(condition: Mapping[str, Any], context: Mapping[str, Any]) -> bool:
    if "context_present" in condition:
        key = condition["context_present"]
        return key in context and context[key] is not None
    if "context_equals" in condition:
        body = condition["context_equals"]
        return context.get(body["field"]) == body["value"]
    return False


def _authorization_resource_kind(kind: str) -> str:
    return "action" if kind in {"command", "query"} else kind


def _access_policy_covers_resource(policy: Mapping[str, Any], kind: str, resource_ref: str) -> bool:
    return any(resource == {_authorization_resource_kind(kind): resource_ref} for resource in policy.get("resources", []))
