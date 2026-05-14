from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from pyspec_contract.io import read_json, read_yaml
from pyspec_contract.paths import COMPILED_SPEC_PATH, GENERATED_SPEC_DIR
from pyspec_contract.runtime import fixture_namespace, resolve_map
from pyspec_contract.targets import entry_fsm_name


class ProductApp:
    """A minimal real app surface for the starter's prod BDD harness.

    It is intentionally small, but the prod driver calls this app instead of the
    reference spec driver. Real projects replace this module, not the generated
    BDD protocol.
    """

    def __init__(self, root: Path):
        self.root = root
        self.contract = read_yaml(root / COMPILED_SPEC_PATH)
        self.surfaces = {p["id"]: p for p in read_json(root / GENERATED_SPEC_DIR / "product_interfaces" / "web.fsms.json")["fsms"]}
        self.reset()

    def reset(self) -> None:
        self.fixtures: dict[str, Any] = {}
        self.projects: list[dict[str, Any]] = []
        self.emitted_events: list[str] = []
        self.invoked_capabilities: list[str] = []
        self.ran_workflows: list[str] = []
        self.rendered_fsm: dict[str, Any] | None = None
        self.http_response: dict[str, Any] | None = None

    def arrange(self, arrange: Mapping[str, Any]) -> None:
        self.reset()
        self.fixtures = fixture_namespace(self.contract, list(arrange.get("fixtures", [])))
        for fact in arrange.get("facts", []):
            kind, body = next(iter(fact.items()))
            if body["resource"] != "Project":
                raise AssertionError("Example app only implements Project")
            if kind == "absent":
                where = self._resolve_map(body["where"])
                self.projects = [p for p in self.projects if not _matches(p, where)]
            elif kind == "present":
                self.projects.append(self._project(self._resolve_map(body["values"])))

    def open_web_entry(self, entry_id: str, params: Mapping[str, Any]) -> dict[str, Any]:
        entry = self.contract["entries"][entry_id]
        assert entry["surface"] == "web"
        fsm_id = entry_fsm_name(entry)
        fsm = self.contract["fsms"][fsm_id]
        context = self._entry_target_input(entry, params)
        workspace_id = context.get("workspace_id")
        matching = [p for p in self.projects if p.get("workspace_id") == workspace_id]
        parent_state_name = "ready" if "ready" in fsm.get("states", {}) else next(iter(fsm.get("states", {"ready": {}})))
        parent_state = fsm["states"].get(parent_state_name, {"surface": None, "copy": [], "assets": [], "actions": [], "data": []})
        if parent_state.get("mounts"):
            fsms: dict[str, Any] = {}
            for mount in parent_state["mounts"]:
                source_id = mount["fsm"]
                fsm = self.contract["fsms"][source_id]
                state_name = self._choose_fsm_state(fsm, mount, matching, context)
                state = fsm["states"][state_name]
                fsms[mount["id"]] = {
                    "source": source_id,
                    "state": state_name,
                    "surface": state["surface"],
                    "data": list(fsm.get("data", [])) + list(state.get("data", [])),
                    "copy": list(state["copy"]),
                    "assets": list(state["assets"]),
                    "actions": list(state["actions"]),
                }
            self.rendered_fsm = {
                "ref": fsm_id,
                "state": parent_state_name,
                "surface": parent_state.get("surface"),
                "data": list(fsm.get("data", [])) + list(parent_state.get("data", [])),
                "copy": list(parent_state.get("copy", [])),
                "assets": list(parent_state.get("assets", [])),
                "actions": list(parent_state.get("actions", [])),
                "context": context,
                "instances": fsms,
                "sync": [rule["id"] for rule in parent_state.get("sync", [])],
            }
            return self.rendered_fsm
        state_name = "ready" if matching else "empty"
        state = fsm["states"][state_name]
        self.rendered_fsm = {
            "ref": fsm_id,
            "state": state_name,
            "surface": state["surface"],
            "copy": list(state["copy"]),
            "assets": list(state["assets"]),
            "actions": list(state["actions"]),
        }
        return self.rendered_fsm

    def _choose_fsm_state(self, fsm: dict[str, Any], mount: dict[str, Any], records: list[dict[str, Any]], context: dict[str, Any]) -> str:
        selected = mount.get("selected")
        if selected:
            if _condition_matches(selected["when"], context):
                return selected["state"]
            return mount["initial"]
        if records and "ready" in fsm["states"] and (fsm.get("data") or fsm["states"]["ready"].get("data")):
            return "ready"
        if not records and "empty" in fsm["states"]:
            return "empty"
        return mount["initial"]

    def _rendered_fsm_ids(self) -> set[str]:
        if not self.rendered_fsm:
            return set()
        if "instances" in self.rendered_fsm:
            fsms = {fsm["surface"] for fsm in self.rendered_fsm["instances"].values()}
            if self.rendered_fsm.get("surface"):
                fsms.add(self.rendered_fsm["surface"])
            return fsms
        return {self.rendered_fsm["surface"]}

    def _rendered_values(self, key: str) -> set[str]:
        if not self.rendered_fsm:
            return set()
        if "instances" in self.rendered_fsm:
            values: set[str] = set()
            values.update(self.rendered_fsm.get(key, []))
            for fsm in self.rendered_fsm["instances"].values():
                values.update(fsm.get(key, []))
            return values
        return set(self.rendered_fsm.get(key, []))

    def call_entry(self, entry_id: str, input_values: Mapping[str, Any]) -> dict[str, Any]:
        entry = self.contract["entries"][entry_id]
        assert entry["surface"] in {"api", "cli"}
        target_input = self._entry_target_input(entry, input_values)
        result = self.invoke_capability(entry["target"]["capability"], target_input)
        output = entry["output"]
        self.http_response = (
            {"status": output["status"], "body": result}
            if "status" in output
            else {"exit_code": output["exit_code"], "stdout": result}
        )
        return self.http_response

    def _entry_target_input(self, entry: Mapping[str, Any], input_values: Mapping[str, Any]) -> dict[str, Any]:
        namespace = {"input": {}}
        for section in ("params", "body", "args"):
            fields = (entry.get("input") or {}).get(section, {})
            if fields:
                namespace["input"][section] = {name: input_values[name] for name in fields}
        bindings = entry["target"].get("with", {})
        return {name: _resolve_binding(source, namespace) for name, source in bindings.items()}

    def invoke_capability(self, capability_id: str, input_values: Mapping[str, Any]) -> Any:
        self.invoked_capabilities.append(capability_id)
        values = dict(input_values)
        if capability_id == "project.create":
            project = self._project(values)
            self.projects.append(project)
            self._record_event("project.created")
            return project
        if capability_id == "project.list":
            return [p for p in self.projects if p["workspace_id"] == values.get("workspace_id")]
        if capability_id == "project.submit":
            project = self._find_project(values["project_id"])
            assert project["status"] == "draft"
            project["status"] = "submitted"
            self._record_event("project.submitted")
            return project
        if capability_id == "project.approve":
            project = self._find_project(values["project_id"])
            assert project["status"] == "submitted"
            project["status"] = "approved"
            self._record_event("project.approved")
            return project
        if capability_id == "project.archive":
            project = self._find_project(values["project_id"])
            assert project["status"] == "approved"
            project["status"] = "archived"
            self._record_event("project.archived")
            return project
        if capability_id == "project.send_approval_notice":
            return {"ok": True, "sent": True, **values}
        raise AssertionError(f"Unsupported capability: {capability_id}")

    def emit_event(self, event_id: str, payload: Mapping[str, Any]) -> None:
        self._record_event(event_id)
        for workflow_id, workflow in self.contract["workflows"].items():
            if workflow["trigger"] == {"event": event_id}:
                self.ran_workflows.append(workflow_id)
                for step in workflow["steps"]:
                    self.invoke_capability(step["capability"], payload)

    def assert_contract(self, assertions: Mapping[str, Any]) -> None:
        if "fsm" in assertions:
            expected = assertions["fsm"]
            assert self.rendered_fsm is not None
            assert self.rendered_fsm["ref"] == expected["ref"]
            if "state" in expected:
                assert self.rendered_fsm["state"] == expected["state"]
                assert self.rendered_fsm["surface"] == expected["surface"]
            if "instances" in expected:
                assert set(self.rendered_fsm["instances"]) == set(expected["instances"])
                for instance_id, fsm_expected in expected["instances"].items():
                    actual = self.rendered_fsm["instances"][instance_id]
                    assert actual["state"] == fsm_expected["state"]
                    assert actual["surface"] == fsm_expected["surface"]
                for sync_id in (expected.get("sync") or {}).get("observed", []):
                    assert sync_id in self.rendered_fsm.get("sync", [])
        requires = assertions.get("requires", {})
        if requires:
            assert self.rendered_fsm is not None
            rendered_fsms = self._rendered_fsm_ids()
            rendered_copy = self._rendered_values("copy")
            rendered_assets = self._rendered_values("assets")
            rendered_actions = self._rendered_values("actions")
            for fsm in requires.get("surfaces", []):
                assert fsm in self.surfaces
                assert fsm in rendered_fsms
            for key in requires.get("copy", []):
                assert key in rendered_copy
            for key in requires.get("assets", []):
                assert key in rendered_assets
            for cap in requires.get("actions", []):
                assert cap in rendered_actions
        for cap in assertions.get("enables", []):
            assert cap in self._rendered_values("actions")
        for cap in assertions.get("forbids", []):
            assert cap not in self._rendered_values("actions")
        exists = (assertions.get("resource") or {}).get("exists")
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
            assert (workflow["ref"] in self.ran_workflows) is workflow["ran"]
        for cap in assertions.get("invoked", []):
            assert cap in self.invoked_capabilities
        response = assertions.get("response")
        if response:
            assert self.http_response is not None
            assert self.http_response["status"] == response["status"]
        policy = assertions.get("policy")
        if policy:
            assert policy in self.contract.get("refs", {}).get("policy", [])

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
    current: Any = namespace
    for part in source.split("."):
        current = current[part]
    return current


def _condition_matches(condition: Mapping[str, Any], context: Mapping[str, Any]) -> bool:
    if "context_present" in condition:
        key = condition["context_present"]
        return key in context and context[key] is not None
    if "context_equals" in condition:
        body = condition["context_equals"]
        return context.get(body["field"]) == body["value"]
    return False
