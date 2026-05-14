from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .io import read_json, read_yaml
from .paths import COMPILED_SPEC_PATH, GENERATED_SPEC_DIR
from .runtime import fixture_namespace, resolve_map
from .targets import entry_fsm_name


class ReferenceSpecDriver:
    """A fake/reference world for spec BDD. It proves scenarios are coherent, not that prod works."""

    def __init__(self, root: Path):
        self.root = root
        self.contract = read_yaml(root / COMPILED_SPEC_PATH)
        self.surfaces = {p["id"]: p for p in read_json(root / GENERATED_SPEC_DIR / "product_interfaces" / "web.fsms.json")["fsms"]}
        self.reset()

    def reset(self) -> None:
        self.fixtures: dict[str, Any] = {}
        self.store: dict[str, list[dict[str, Any]]] = {rid: [] for rid in self.contract["resources"]}
        self.emitted: list[str] = []
        self.invoked: list[str] = []
        self.workflows_ran: list[str] = []
        self.last_fsm: dict[str, Any] | None = None
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
            self.last_fsm = self._open_entry(body["ref"], self._resolve_map(body.get("input", {})))
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
        if "fsm" in assertions:
            assert self.last_fsm is not None, "Expected a rendered FSM"
            expected = assertions["fsm"]
            assert self.last_fsm["ref"] == expected["ref"]
            if "state" in expected:
                assert self.last_fsm["state"] == expected["state"]
                assert self.last_fsm["surface"] == expected["surface"]
            if "instances" in expected:
                assert set(self.last_fsm["instances"]) == set(expected["instances"])
                for instance_id, fsm_expected in expected["instances"].items():
                    actual = self.last_fsm["instances"][instance_id]
                    assert actual["state"] == fsm_expected["state"]
                    assert actual["surface"] == fsm_expected["surface"]
                for sync_id in (expected.get("sync") or {}).get("observed", []):
                    assert sync_id in self.last_fsm.get("sync", [])
        requires = assertions.get("requires", {})
        if requires:
            assert self.last_fsm is not None, "FSM requirements need a rendered FSM"
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
            fsm = self.contract["fsms"][self.last_fsm["ref"]]
            queries = [datum["query"] for datum in fsm.get("data", [])]
            if "instances" in self.last_fsm:
                for instance in self.last_fsm["instances"].values():
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
        fsm_id = entry_fsm_name(entry)
        fsm = self.contract["fsms"][fsm_id]
        context = self._entry_target_input(entry, params)
        records = self._filter(fsm["resource"], context)
        parent_state_name = "ready" if "ready" in fsm.get("states", {}) else next(iter(fsm.get("states", {"ready": {}})))
        state = fsm["states"].get(parent_state_name, {"surface": None, "copy": [], "assets": [], "actions": [], "data": []})
        if state.get("mounts"):
            fsms: dict[str, Any] = {}
            for mount in state["mounts"]:
                source_id = mount["fsm"]
                fsm = self.contract["fsms"][source_id]
                child_state_name = self._choose_fsm_state(fsm, mount, records, context)
                child_state = fsm["states"][child_state_name]
                fsms[mount["id"]] = {
                    "source": source_id,
                    "state": child_state_name,
                    "surface": child_state["surface"],
                    "data": list(fsm.get("data", [])) + list(child_state.get("data", [])),
                    "copy": child_state["copy"],
                    "assets": child_state["assets"],
                    "actions": child_state["actions"],
                }
            return {
                "ref": fsm_id,
                "state": parent_state_name,
                "surface": state.get("surface"),
                "data": list(fsm.get("data", [])) + list(state.get("data", [])),
                "copy": state.get("copy", []),
                "assets": state.get("assets", []),
                "actions": state.get("actions", []),
                "context": context,
                "instances": fsms,
                "sync": [rule["id"] for rule in state.get("sync", [])],
            }
        state_name = "empty" if not records and "empty" in fsm["states"] else "ready"
        state = fsm["states"][state_name]
        return {
            "ref": fsm_id,
            "state": state_name,
            "surface": state["surface"],
            "copy": state["copy"],
            "assets": state["assets"],
            "actions": state["actions"],
        }

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
        if not self.last_fsm:
            return set()
        if "instances" in self.last_fsm:
            fsms = {fsm["surface"] for fsm in self.last_fsm["instances"].values()}
            if self.last_fsm.get("surface"):
                fsms.add(self.last_fsm["surface"])
            return fsms
        return {self.last_fsm["surface"]}

    def _rendered_values(self, key: str) -> set[str]:
        if not self.last_fsm:
            return set()
        if "instances" in self.last_fsm:
            values: set[str] = set()
            values.update(self.last_fsm.get(key, []))
            for fsm in self.last_fsm["instances"].values():
                values.update(fsm.get(key, []))
            return values
        return set(self.last_fsm.get(key, []))

    def _call_entry(self, entry_id: str, input_values: dict[str, Any]) -> dict[str, Any]:
        entry = self.contract["entries"][entry_id]
        cap_id = entry["target"]["capability"]
        target_input = self._entry_target_input(entry, input_values)
        result = self._invoke(cap_id, target_input)
        output = entry["output"]
        if "status" in output:
            return {"status": output["status"], "body": result}
        return {"exit_code": output["exit_code"], "stdout": result}

    def _entry_target_input(self, entry: dict[str, Any], input_values: dict[str, Any]) -> dict[str, Any]:
        namespace = {"input": {}}
        for section in ("params", "body", "args"):
            fields = (entry.get("input") or {}).get(section, {})
            if fields:
                namespace["input"][section] = {name: input_values[name] for name in fields}
        bindings = entry["target"].get("with", {})
        return {name: _resolve_binding(source, namespace) for name, source in bindings.items()}

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
