from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .io import read_json, read_yaml
from .paths import COMPILED_SPEC_PATH, GENERATED_SPEC_DIR
from .runtime import fixture_namespace, resolve_map
from .targets import entry_view_name


class ReferenceSpecDriver:
    """A fake/reference world for spec BDD. It proves scenarios are coherent, not that prod works."""

    def __init__(self, root: Path):
        self.root = root
        self.contract = read_yaml(root / COMPILED_SPEC_PATH)
        self.panels = {p["id"]: p for p in read_json(root / GENERATED_SPEC_DIR / "product_interfaces" / "web.panels.json")["panels"]}
        self.reset()

    def reset(self) -> None:
        self.fixtures: dict[str, Any] = {}
        self.store: dict[str, list[dict[str, Any]]] = {rid: [] for rid in self.contract["resources"]}
        self.emitted: list[str] = []
        self.invoked: list[str] = []
        self.workflows_ran: list[str] = []
        self.last_view: dict[str, Any] | None = None
        self.response: dict[str, Any] | None = None
        self.last_result: Any = None

    def arrange(self, scenario_id: str, scenario: Mapping[str, Any]) -> None:
        self.reset()
        self.fixtures = fixture_namespace(self.contract, list(scenario.get("arrange", {}).get("fixtures", [])))
        for fact in scenario.get("arrange", {}).get("facts", []):
            kind, body = next(iter(fact.items()))
            if kind == "absent":
                where = self._resolve_map(body["where"])
                self.store[body["resource"]] = [r for r in self.store[body["resource"]] if not _matches(r, where)]
            elif kind == "present":
                values = self._complete_record(body["resource"], self._resolve_map(body["values"]))
                self.store[body["resource"]].append(values)
            else:  # pragma: no cover - schema prevents this.
                raise AssertionError(f"Unsupported fact kind: {kind}")

    def execute(self, scenario_id: str, scenario: Mapping[str, Any]) -> None:
        kind, body = next(iter(scenario["execute"].items()))
        if kind == "open_entry":
            self.last_view = self._open_entry(body["ref"], self._resolve_map(body.get("params", {})))
        elif kind == "call_entry":
            self.response = self._call_entry(body["ref"], self._resolve_map(body.get("input", {})))
        elif kind == "invoke_capability":
            self.last_result = self._invoke(body["ref"], self._resolve_map(body.get("input", {})))
        elif kind == "emit_event":
            self._emit(body["ref"], self._resolve_map(body.get("payload", {})))
        else:  # pragma: no cover - schema prevents this.
            raise AssertionError(f"Unsupported execute kind: {kind}")

    def assert_obligations(self, scenario_id: str, scenario: Mapping[str, Any]) -> None:
        assertions = scenario["assert"]
        if "view" in assertions:
            assert self.last_view is not None, "Expected a rendered view"
            expected = assertions["view"]
            assert self.last_view["ref"] == expected["ref"]
            if "state" in expected:
                assert self.last_view["state"] == expected["state"]
                assert self.last_view["panel"] == expected["panel"]
            if "panels" in expected:
                assert set(self.last_view["panels"]) == set(expected["panels"])
                for instance_id, panel_expected in expected["panels"].items():
                    actual = self.last_view["panels"][instance_id]
                    assert actual["state"] == panel_expected["state"]
                    assert actual["panel"] == panel_expected["panel"]
                for sync_id in (expected.get("sync") or {}).get("observed", []):
                    assert sync_id in self.last_view.get("sync", [])
        requires = assertions.get("requires", {})
        if requires:
            assert self.last_view is not None, "View requirements need a rendered view"
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
            view = self.contract["views"][self.last_view["ref"]]
            queries = [datum["query"] for datum in view.get("data", [])]
            if "panels" in self.last_view:
                for instance in self.last_view["panels"].values():
                    queries.extend(datum["query"] for datum in instance.get("data", []))
            for query in requires.get("queries", []):
                assert query in queries
        for cap in assertions.get("enables", []):
            assert cap in self._rendered_values("actions")
        for cap in assertions.get("forbids", []):
            assert cap not in self._rendered_values("actions")
        exists = (assertions.get("resource") or {}).get("exists")
        if exists:
            where = self._resolve_map(exists["where"])
            assert any(_matches(record, where) for record in self.store[exists["resource"]]), f"Missing resource {exists}"
        events = assertions.get("events") or {}
        for event_id in events.get("emitted", []):
            assert event_id in self.emitted
        for event_id in events.get("not_emitted", []):
            assert event_id not in self.emitted
        workflow = assertions.get("workflow")
        if workflow:
            if workflow["ran"]:
                assert workflow["ref"] in self.workflows_ran
            else:
                assert workflow["ref"] not in self.workflows_ran
        for cap in assertions.get("invoked", []):
            assert cap in self.invoked
        response = assertions.get("response")
        if response:
            assert self.response is not None
            assert self.response["status"] == response["status"]
        policy = assertions.get("policy")
        if policy:
            assert policy in self.contract.get("refs", {}).get("policy", [])

    def _open_entry(self, entry_id: str, params: dict[str, Any]) -> dict[str, Any]:
        entry = self.contract["entries"][entry_id]
        view_id = entry_view_name(entry)
        view = self.contract["views"][view_id]
        records = self._filter(view["resource"], params)
        if view.get("includes"):
            panels: dict[str, Any] = {}
            context = {**params}
            for include in view["includes"]:
                source_id = include["panel"]
                panel = self.contract["panels"][source_id]
                state_name = self._choose_panel_state(panel, include, records, context)
                state = panel["states"][state_name]
                panels[include["id"]] = {
                    "source": source_id,
                    "state": state_name,
                    "panel": state["panel"],
                    "data": list(panel.get("data", [])) + list(state.get("data", [])),
                    "copy": state["copy"],
                    "assets": state["assets"],
                    "actions": state["actions"],
                }
            state_name = "ready" if "ready" in view.get("states", {}) else next(iter(view.get("states", {"ready": {}})))
            state = view.get("states", {}).get(state_name, {"panel": None, "copy": [], "assets": [], "actions": [], "data": []})
            return {
                "ref": view_id,
                "state": state_name,
                "panel": state.get("panel"),
                "data": list(panel.get("data", [])) + list(state.get("data", [])),
                "copy": state.get("copy", []),
                "assets": state.get("assets", []),
                "actions": state.get("actions", []),
                "context": context,
                "panels": panels,
                "sync": [rule["id"] for rule in view.get("sync", [])],
            }
        state_name = "empty" if not records and "empty" in view["states"] else "ready"
        state = view["states"][state_name]
        return {
            "ref": view_id,
            "state": state_name,
            "panel": state["panel"],
            "copy": state["copy"],
            "assets": state["assets"],
            "actions": state["actions"],
        }

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
        if not self.last_view:
            return set()
        if "panels" in self.last_view:
            panels = {panel["panel"] for panel in self.last_view["panels"].values()}
            if self.last_view.get("panel"):
                panels.add(self.last_view["panel"])
            return panels
        return {self.last_view["panel"]}

    def _rendered_values(self, key: str) -> set[str]:
        if not self.last_view:
            return set()
        if "panels" in self.last_view:
            values: set[str] = set()
            values.update(self.last_view.get(key, []))
            for panel in self.last_view["panels"].values():
                values.update(panel.get(key, []))
            return values
        return set(self.last_view.get(key, []))

    def _call_entry(self, entry_id: str, input_values: dict[str, Any]) -> dict[str, Any]:
        entry = self.contract["entries"][entry_id]
        cap_id = entry["target"]["capability"]
        result = self._invoke(cap_id, input_values)
        return {"status": 200, "body": result}

    def _invoke(self, cap_id: str, input_values: dict[str, Any]) -> Any:
        self.invoked.append(cap_id)
        cap = self.contract["capabilities"][cap_id]
        resource_id = cap["resource"]
        if cap["archetype"] == "create":
            record = self._complete_record(resource_id, input_values)
            lifecycle = self.contract["resources"][resource_id].get("lifecycle")
            if lifecycle and lifecycle["field"] not in record:
                record[lifecycle["field"]] = lifecycle["initial"]
            self.store[resource_id].append(record)
            for event_id in cap["emits"]:
                self._record_event(event_id, {"id": record["id"], **record})
            self.last_result = record
            return record
        if cap["archetype"] == "list":
            self.last_result = self._filter(resource_id, input_values)
            return self.last_result
        if cap["archetype"] == "transition":
            project_id = input_values.get("project_id") or input_values.get("id")
            record = self._find(resource_id, {"id": project_id})
            transition = cap["transition"]
            assert record[transition["field"]] == transition["from"]
            record[transition["field"]] = transition["to"]
            for event_id in cap["emits"]:
                self._record_event(event_id, {"project_id": record["id"], "approved_by": self.fixtures.get("actor", {}).get("id")})
            self.last_result = record
            return record
        # Command/query capabilities are recorded as effects in the spec world.
        result = {"ok": True, "capability": cap_id, **input_values}
        self.last_result = result
        return result

    def _emit(self, event_id: str, payload: dict[str, Any]) -> None:
        self._record_event(event_id, payload)
        for workflow_id, workflow in self.contract["workflows"].items():
            if workflow["trigger"] == {"event": event_id}:
                self.workflows_ran.append(workflow_id)
                for step in workflow["steps"]:
                    self._invoke(step["capability"], payload)

    def _record_event(self, event_id: str, payload: dict[str, Any]) -> None:
        self.emitted.append(event_id)

    def _filter(self, resource_id: str, where: dict[str, Any]) -> list[dict[str, Any]]:
        return [record for record in self.store[resource_id] if _matches(record, where)]

    def _find(self, resource_id: str, where: dict[str, Any]) -> dict[str, Any]:
        matches = self._filter(resource_id, where)
        assert matches, f"No {resource_id} found for {where}"
        return matches[0]

    def _complete_record(self, resource_id: str, values: dict[str, Any]) -> dict[str, Any]:
        fields = self.contract["resources"][resource_id]["fields"]
        record = dict(values)
        if "id" in fields and "id" not in record:
            record["id"] = f"{resource_id.lower()}_{len(self.store[resource_id]) + 1}"
        if "created_at" in fields and "created_at" not in record:
            record["created_at"] = "2026-05-10T00:00:00Z"
        if "updated_at" in fields and "updated_at" not in record:
            record["updated_at"] = "2026-05-10T00:00:00Z"
        return record

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
