from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from pyspec_contract.io import read_json, read_yaml
from pyspec_contract.paths import COMPILED_SPEC_PATH, GENERATED_SPEC_DIR
from pyspec_contract.runtime import fixture_namespace, resolve_map
from pyspec_contract.runtime_refs import resolve_reference_expression
from pyspec_contract.targets import entry_state_machine_name, entry_point_adapter_pair, entry_point_bindings, entry_point_input, entry_point_responses, entry_target_pair


class ProductApp:
    """A minimal real app surface for the starter's prod BDD harness.

    It is intentionally small, but the prod driver calls this app instead of the
    reference spec driver. Real projects replace this module, not the generated
    BDD protocol.
    """

    def __init__(self, root: Path):
        self.root = root
        self.contract = read_yaml(root / COMPILED_SPEC_PATH)
        self.surfaces = {p["id"]: p for p in read_json(root / GENERATED_SPEC_DIR / "product_interfaces" / "web.state_machines.json")["state_machines"]}
        self.reset()

    def reset(self) -> None:
        self.fixtures: dict[str, Any] = {}
        self.projects: list[dict[str, Any]] = []
        self.emitted_events: list[str] = []
        self.invoked_operations: list[str] = []
        self.executed_workflows: list[str] = []
        self.workflow_outcomes: dict[str, str] = {}
        self.rendered_state_machine: dict[str, Any] | None = None
        self.http_response: dict[str, Any] | None = None
        self.last_outcome: str | None = None

    def given(self, given: Mapping[str, Any]) -> None:
        self.reset()
        self.fixtures = fixture_namespace(self.contract, list(given.get("seed_fixtures", [])))
        for fact in given.get("domain_facts", []):
            kind, body = next(iter(fact.items()))
            if body["model"] != "Project":
                raise AssertionError("Example app only implements Project")
            if kind == "absent":
                where = self._resolve_map(body["where"])
                self.projects = [p for p in self.projects if not _matches(p, where)]
            elif kind == "present":
                self.projects.append(self._project(self._resolve_map(body["values"])))

    def open_web_entry(self, entry_id: str, params: Mapping[str, Any]) -> dict[str, Any]:
        entry = self.contract["entry_points"][entry_id]
        assert entry_point_adapter_pair(entry)[0] == "ui"
        state_machine_id = entry_state_machine_name(entry)
        state_machine = self.contract["state_machines"][state_machine_id]
        context = self._entry_target_input(entry, params)
        workspace_id = context.get("workspace_id")
        matching = [p for p in self.projects if p.get("workspace_id") == workspace_id]
        parent_state_name = "ready" if "ready" in state_machine.get("view_states", {}) else next(iter(state_machine.get("view_states", {"ready": {}})))
        parent_state = state_machine["view_states"].get(parent_state_name, {"surface": None, "text": [], "assets": [], "operation_refs": [], "data_dependencies": []})
        if parent_state.get("child_state_machines"):
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
                    "data_dependencies": list(child_state_machine.get("data_dependencies", [])) + list(state.get("data_dependencies", [])),
                    "text": list(state["text"]),
                    "assets": list(state["assets"]),
                    "operation_refs": list(state["operation_refs"]),
                }
            self.rendered_state_machine = {
                "ref": state_machine_id,
                "view_state": parent_state_name,
                "surface": parent_state.get("surface"),
                "data_dependencies": list(state_machine.get("data_dependencies", [])) + list(parent_state.get("data_dependencies", [])),
                "text": list(parent_state.get("text", [])),
                "assets": list(parent_state.get("assets", [])),
                "operation_refs": list(parent_state.get("operation_refs", [])),
                "context": context,
                "instances": state_machines,
                "message_sync_rules": [rule["id"] for rule in parent_state.get("message_sync_rules", [])],
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
            "operation_refs": list(state["operation_refs"]),
        }
        return self.rendered_state_machine

    def _choose_state_machine_state(self, state_machine: dict[str, Any], mount: dict[str, Any], records: list[dict[str, Any]], context: dict[str, Any]) -> str:
        selected = mount.get("selected")
        if selected:
            if _condition_matches(selected["when"], context):
                return selected["view_state"]
            return mount["initial_view_state"]
        if records and "ready" in state_machine["view_states"] and (state_machine.get("data_dependencies") or state_machine["view_states"]["ready"].get("data_dependencies")):
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

    def call_entry(self, entry_id: str, input_values: Mapping[str, Any]) -> dict[str, Any]:
        entry = self.contract["entry_points"][entry_id]
        assert entry_point_adapter_pair(entry)[0] in {"http", "cli"}
        target_input = self._entry_target_input(entry, input_values)
        target_kind, operation_id = entry_target_pair(entry)
        assert target_kind == "operation"
        result = self.invoke_operation(operation_id, target_input)
        response = entry_point_responses(entry)[self.last_outcome]
        if "status" in response:
            self.http_response = {"status": response["status"], "body": result}
        elif "stdout" in response:
            self.http_response = {"exit_code": response["exit_code"], "stdout": result}
        else:
            self.http_response = {"exit_code": response["exit_code"], "stderr": result}
        return self.http_response

    def _entry_target_input(self, entry: Mapping[str, Any], input_values: Mapping[str, Any]) -> dict[str, Any]:
        namespace = {"input": {}}
        for section in ("params", "body", "args"):
            fields = entry_point_input(dict(entry)).get(section, {})
            if fields:
                namespace["input"][section] = {name: input_values[name] for name in fields}
        bindings = entry_point_bindings(dict(entry))
        return {name: _resolve_binding(source, namespace) for name, source in bindings.items()}

    def invoke_operation(self, operation_id: str, input_values: Mapping[str, Any]) -> Any:
        self.invoked_operations.append(operation_id)
        self.last_outcome = _success_outcome_id(self.contract["operations"][operation_id])
        values = dict(input_values)
        if operation_id == "operation.project.create":
            project = self._project(values)
            self.projects.append(project)
            self._record_event("event.project.created")
            return project
        if operation_id == "operation.project.list":
            return [p for p in self.projects if p["workspace_id"] == values.get("workspace_id")]
        if operation_id == "operation.project.submit":
            project = self._find_project(values["project_id"])
            assert project["status"] == "draft"
            project["status"] = "submitted"
            self._record_event("event.project.submitted")
            return project
        if operation_id == "operation.project.approve":
            project = self._find_project(values["project_id"])
            assert project["status"] == "submitted"
            project["status"] = "approved"
            project["approved_by"] = values["approved_by"]
            self._record_event("event.project.approved")
            return project
        if operation_id == "operation.project.archive":
            project = self._find_project(values["project_id"])
            assert project["status"] == "approved"
            project["status"] = "archived"
            self._record_event("event.project.archived")
            return project
        if operation_id == "operation.project.send_approval_notice":
            return {"ok": True, "sent": True, **values}
        raise AssertionError(f"Unsupported operation: {operation_id}")

    def emit_event(self, event_id: str, payload: Mapping[str, Any]) -> None:
        self._record_event(event_id)
        for workflow_id, workflow in self.contract["workflows"].items():
            if workflow["trigger"] == {"event": event_id}:
                self.executed_workflows.append(workflow_id)
                self.workflow_outcomes[workflow_id] = self._run_workflow(workflow, payload)

    def _run_workflow(self, workflow: Mapping[str, Any], payload: Mapping[str, Any]) -> str:
        step_by_id = {step["id"]: step for step in workflow["steps"]}
        current = workflow["steps"][0]["id"]
        namespace: dict[str, Any] = {"trigger": {"payload": dict(payload)}, "steps": {}}
        while True:
            step = step_by_id[current]
            input_values = {name: _resolve_binding(source, namespace) for name, source in step["input_bindings"].items()}
            result = self.invoke_operation(step["operation"], input_values)
            assert self.last_outcome is not None
            namespace["steps"].setdefault(step["id"], {"outcomes": {}})["outcomes"][self.last_outcome] = {"result": result}
            route = step["outcome_routes"][self.last_outcome]
            if "complete_as" in route:
                return route["complete_as"]
            if "fail_as" in route:
                return route["fail_as"]
            if "retry_policy" in route:
                return route["retry_policy"]["fail_as"]
            if "dead_letter" in route:
                return route["dead_letter"]
            current = route["next_step"]

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
                for sync_id in (expected.get("message_sync_rules") or {}).get("observed", []):
                    assert sync_id in self.rendered_state_machine.get("message_sync_rules", [])
        requires = assertions.get("requires", {})
        if requires:
            assert self.rendered_state_machine is not None
            rendered_state_machines = self._rendered_state_machine_ids()
            rendered_text = self._rendered_values("text")
            rendered_assets = self._rendered_values("assets")
            rendered_actions = self._rendered_values("operation_refs")
            for state_machine in requires.get("surfaces", []):
                assert state_machine in self.surfaces
                assert state_machine in rendered_state_machines
            for key in requires.get("text", []):
                assert key in rendered_text
            for key in requires.get("assets", []):
                assert key in rendered_assets
            for cap in requires.get("operation_refs", []):
                assert cap in rendered_actions
        for cap in assertions.get("enables", []):
            assert cap in self._rendered_values("operation_refs")
        for cap in assertions.get("forbids", []):
            assert cap not in self._rendered_values("operation_refs")
        exists = (assertions.get("model") or {}).get("exists")
        if exists:
            where = self._resolve_map(exists["where"])
            assert any(_matches(project, where) for project in self.projects)
        events = assertions.get("events") or {}
        for event_id in events.get("emitted", []):
            assert event_id in self.emitted_events
        for event_id in events.get("not_emitted", []):
            assert event_id not in self.emitted_events
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
        policy = assertions.get("policy")
        if policy:
            assert policy in self.contract.get("refs", {}).get("policy", [])
        for fact in assertions.get("assertion_facts", []):
            kind, body = next(iter(fact.items()))
            if body["model"] != "Project":
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

    def _record_event(self, event_id: str) -> None:
        self.emitted_events.append(event_id)

    def _resolve_map(self, values: Mapping[str, Any]) -> dict[str, Any]:
        return resolve_map(values, self.fixtures)


def _matches(record: Mapping[str, Any], where: Mapping[str, Any]) -> bool:
    return all(record.get(key) == value for key, value in where.items())


def _resolve_binding(source: str, namespace: Mapping[str, Any]) -> Any:
    return resolve_reference_expression(source, namespace)


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
