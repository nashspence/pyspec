from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from pyspec_contract.io import read_json, read_yaml
from pyspec_contract.paths import COMPILED_SPEC_PATH, GENERATED_SPEC_DIR
from pyspec_contract.runtime import fixture_namespace, resolve_map


class ProductApp:
    """A minimal real app surface for the starter's prod BDD harness.

    It is intentionally small, but the prod driver calls this app instead of the
    reference spec driver. Real projects replace this module, not the generated
    BDD protocol.
    """

    def __init__(self, root: Path):
        self.root = root
        self.contract = read_yaml(root / COMPILED_SPEC_PATH)
        self.panels = {p["id"]: p for p in read_json(root / GENERATED_SPEC_DIR / "product_interfaces" / "web.panels.json")["panels"]}
        self.reset()

    def reset(self) -> None:
        self.fixtures: dict[str, Any] = {}
        self.projects: list[dict[str, Any]] = []
        self.emitted_events: list[str] = []
        self.invoked_capabilities: list[str] = []
        self.ran_workflows: list[str] = []
        self.rendered_view: dict[str, Any] | None = None
        self.http_response: dict[str, Any] | None = None

    def arrange(self, arrange: Mapping[str, Any]) -> None:
        self.reset()
        self.fixtures = fixture_namespace(self.contract, list(arrange.get("fixtures", [])))
        for fact in arrange.get("facts", []):
            kind, body = next(iter(fact.items()))
            if body["resource"] != "Project":
                raise AssertionError("Sample app only implements Project")
            if kind == "absent":
                where = self._resolve_map(body["where"])
                self.projects = [p for p in self.projects if not _matches(p, where)]
            elif kind == "present":
                self.projects.append(self._project(self._resolve_map(body["values"])))

    def open_web_entry(self, entry_id: str, params: Mapping[str, Any]) -> dict[str, Any]:
        entry = self.contract["entries"][entry_id]
        assert entry["surface"] == "web"
        view_id = entry["target"]["view"]
        view = self.contract["views"][view_id]
        workspace_id = params.get("workspace_id")
        matching = [p for p in self.projects if p.get("workspace_id") == workspace_id]
        if view.get("includes"):
            panels: dict[str, Any] = {}
            context = dict(params)
            for include in view["includes"]:
                source_id = include["panel"]
                panel = self.contract["panels"][source_id]
                state_name = self._choose_panel_state(panel, include, matching, context)
                state = panel["states"][state_name]
                panels[include["id"]] = {
                    "source": source_id,
                    "state": state_name,
                    "panel": state["panel"],
                    "data": list(panel.get("data", [])) + list(state.get("data", [])),
                    "copy": list(state["copy"]),
                    "assets": list(state["assets"]),
                    "actions": list(state["actions"]),
                }
            state_name = "ready" if "ready" in view.get("states", {}) else next(iter(view.get("states", {"ready": {}})))
            state = view.get("states", {}).get(state_name, {"panel": None, "copy": [], "assets": [], "actions": [], "data": []})
            self.rendered_view = {
                "ref": view_id,
                "state": state_name,
                "panel": state.get("panel"),
                "data": list(panel.get("data", [])) + list(state.get("data", [])),
                "copy": list(state.get("copy", [])),
                "assets": list(state.get("assets", [])),
                "actions": list(state.get("actions", [])),
                "context": context,
                "panels": panels,
                "sync": [rule["id"] for rule in view.get("sync", [])],
            }
            return self.rendered_view
        state_name = "ready" if matching else "empty"
        state = view["states"][state_name]
        self.rendered_view = {
            "ref": view_id,
            "state": state_name,
            "panel": state["panel"],
            "copy": list(state["copy"]),
            "assets": list(state["assets"]),
            "actions": list(state["actions"]),
        }
        return self.rendered_view

    def _choose_panel_state(self, panel: dict[str, Any], include: dict[str, Any], records: list[dict[str, Any]], context: dict[str, Any]) -> str:
        selected = include.get("selected")
        if selected:
            if _condition_matches(selected["when"], context):
                return selected["state"]
            return include["initial"]
        if records and "ready" in panel["states"] and (panel.get("data") or panel["states"]["ready"].get("data")):
            return "ready"
        if not records and "empty" in panel["states"]:
            return "empty"
        return include["initial"]

    def _rendered_panel_ids(self) -> set[str]:
        if not self.rendered_view:
            return set()
        if "panels" in self.rendered_view:
            panels = {panel["panel"] for panel in self.rendered_view["panels"].values()}
            if self.rendered_view.get("panel"):
                panels.add(self.rendered_view["panel"])
            return panels
        return {self.rendered_view["panel"]}

    def _rendered_values(self, key: str) -> set[str]:
        if not self.rendered_view:
            return set()
        if "panels" in self.rendered_view:
            values: set[str] = set()
            values.update(self.rendered_view.get(key, []))
            for panel in self.rendered_view["panels"].values():
                values.update(panel.get(key, []))
            return values
        return set(self.rendered_view.get(key, []))

    def call_entry(self, entry_id: str, input_values: Mapping[str, Any]) -> dict[str, Any]:
        entry = self.contract["entries"][entry_id]
        assert entry["surface"] in {"api", "cli"}
        result = self.invoke_capability(entry["target"]["capability"], input_values)
        self.http_response = {"status": 200, "body": result}
        return self.http_response

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
        if "view" in assertions:
            expected = assertions["view"]
            assert self.rendered_view is not None
            assert self.rendered_view["ref"] == expected["ref"]
            if "state" in expected:
                assert self.rendered_view["state"] == expected["state"]
                assert self.rendered_view["panel"] == expected["panel"]
            if "panels" in expected:
                assert set(self.rendered_view["panels"]) == set(expected["panels"])
                for instance_id, panel_expected in expected["panels"].items():
                    actual = self.rendered_view["panels"][instance_id]
                    assert actual["state"] == panel_expected["state"]
                    assert actual["panel"] == panel_expected["panel"]
                for sync_id in (expected.get("sync") or {}).get("observed", []):
                    assert sync_id in self.rendered_view.get("sync", [])
        requires = assertions.get("requires", {})
        if requires:
            assert self.rendered_view is not None
            rendered_panels = self._rendered_panel_ids()
            rendered_copy = self._rendered_values("copy")
            rendered_assets = self._rendered_values("assets")
            rendered_actions = self._rendered_values("actions")
            for panel in requires.get("panel", []):
                assert panel in self.panels
                assert panel in rendered_panels
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


def _condition_matches(condition: Mapping[str, Any], context: Mapping[str, Any]) -> bool:
    if "context_present" in condition:
        key = condition["context_present"]
        return key in context and context[key] is not None
    if "context_equals" in condition:
        body = condition["context_equals"]
        return context.get(body["field"]) == body["value"]
    return False
