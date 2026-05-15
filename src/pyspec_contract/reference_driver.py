from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .io import read_json, read_yaml
from .paths import COMPILED_SPEC_PATH, GENERATED_SPEC_DIR
from .runtime import fixture_namespace, resolve_map
from .runtime_refs import resolve_reference_expression
from .targets import entry_fsm_name
from .type_expr import is_array_of_model, model_name


class ReferenceSpecDriver:
    """A fake/reference world for spec BDD. It proves scenarios are coherent, not that prod works."""

    def __init__(self, root: Path):
        self.root = root
        self.contract = read_yaml(root / COMPILED_SPEC_PATH)
        self.surfaces = {p["id"]: p for p in read_json(root / GENERATED_SPEC_DIR / "product_interfaces" / "web.fsms.json")["fsms"]}
        self.reset()

    def reset(self) -> None:
        self.fixtures: dict[str, Any] = {}
        self.store: dict[str, list[dict[str, Any]]] = {rid: [] for rid in self.contract["models"]}
        self.emitted: list[str] = []
        self.invoked: list[str] = []
        self.workflows_ran: list[str] = []
        self.workflow_outcomes: dict[str, str] = {}
        self.last_fsm: dict[str, Any] | None = None
        self.response: dict[str, Any] | None = None
        self.last_result: Any = None
        self.last_outcome: str | None = None

    def arrange(self, scenario_id: str, scenario: Mapping[str, Any]) -> None:
        self.reset()
        self.fixtures = fixture_namespace(self.contract, list(scenario.get("arrange", {}).get("fixtures", [])))
        for fact in scenario.get("arrange", {}).get("facts", []):
            kind, body = next(iter(fact.items()))
            if kind == "absent":
                where = self._resolve_map(body["where"])
                self.store[body["model"]] = [r for r in self.store[body["model"]] if not _matches(r, where)]
            elif kind == "present":
                values = self._complete_record(body["model"], self._resolve_map(body["values"]))
                self.store[body["model"]].append(values)
            else:  # pragma: no cover - schema prevents this.
                raise AssertionError(f"Unsupported fact kind: {kind}")

    def execute(self, scenario_id: str, scenario: Mapping[str, Any]) -> None:
        kind, body = next(iter(scenario["execute"].items()))
        if kind == "open_entry":
            self.last_fsm = self._open_entry(body["ref"], self._resolve_map(body.get("input", {})))
        elif kind == "call_entry":
            self.response = self._call_entry(body["ref"], self._resolve_map(body.get("input", {})), scenario["assert"].get("outcome"))
        elif kind == "invoke_operation":
            self.last_result = self._invoke(body["ref"], self._resolve_map(body.get("input", {})), scenario["assert"].get("outcome"))
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
        exists = (assertions.get("model") or {}).get("exists")
        if exists:
            where = self._resolve_map(exists["where"])
            assert any(_matches(record, where) for record in self.store[exists["model"]]), f"Missing model {exists}"
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
        policy = assertions.get("policy")
        if policy:
            assert policy in self.contract.get("refs", {}).get("policy", [])

    def _open_entry(self, entry_id: str, params: dict[str, Any]) -> dict[str, Any]:
        entry = self.contract["entries"][entry_id]
        fsm_id = entry_fsm_name(entry)
        fsm = self.contract["fsms"][fsm_id]
        context = self._entry_target_input(entry, params)
        records = self._filter(fsm["model"], context)
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

    def _call_entry(self, entry_id: str, input_values: dict[str, Any], outcome_id: str | None = None) -> dict[str, Any]:
        entry = self.contract["entries"][entry_id]
        cap_id = entry["target"]["operation"]
        target_input = self._entry_target_input(entry, input_values)
        result = self._invoke(cap_id, target_input, outcome_id)
        response = entry["responses"][self.last_outcome]
        if "status" in response:
            return {"status": response["status"], "body": result}
        if "stdout" in response:
            return {"exit_code": response["exit_code"], "stdout": result}
        return {"exit_code": response["exit_code"], "stderr": result}

    def _entry_target_input(self, entry: dict[str, Any], input_values: dict[str, Any]) -> dict[str, Any]:
        namespace = {"input": {}}
        for section in ("params", "body", "args"):
            fields = (entry.get("input") or {}).get(section, {})
            if fields:
                namespace["input"][section] = {name: input_values[name] for name in fields}
        bindings = entry["target"].get("with", {})
        return {name: _resolve_binding(source, namespace) for name, source in bindings.items()}

    def _invoke(self, cap_id: str, input_values: dict[str, Any], outcome_id: str | None = None) -> Any:
        self.invoked.append(cap_id)
        cap = self.contract["operations"][cap_id]
        outcome_id = outcome_id or _success_outcome_id(cap)
        outcome = cap["outcomes"][outcome_id]
        self.last_outcome = outcome_id
        if outcome["kind"] == "failure":
            self.last_result = {"code": outcome_id, "message": outcome_id.replace("_", " ")}
            return self.last_result
        operation_kind = cap["operation_kind"]
        if operation_kind == "command" and cap.get("creates"):
            model_id = _single_model(cap, "creates")
            record = self._complete_record(model_id, input_values)
            lifecycle = self.contract["models"][model_id].get("lifecycle")
            if lifecycle and lifecycle["field"] not in record:
                record[lifecycle["field"]] = lifecycle["initial"]
            self.store[model_id].append(record)
            for emit in outcome.get("emits", []):
                event_id, payload = self._event_payload_from_emit(emit, cap, outcome, input_values, record)
                self._record_event(event_id, payload)
            self.last_result = record
            return record
        if operation_kind == "query" and cap.get("reads") and model_name(outcome["result"]):
            model_id = _single_model(cap, "reads")
            model_key = f"{model_id.lower()}_id"
            self.last_result = self._find(model_id, {"id": input_values.get(model_key) or input_values.get("id")})
            return self.last_result
        if operation_kind == "query" and cap.get("reads") and is_array_of_model(outcome["result"], _single_model(cap, "reads")):
            model_id = _single_model(cap, "reads")
            self.last_result = self._filter(model_id, input_values)
            return self.last_result
        if operation_kind == "transition":
            transition = cap["transition"]
            model_id = transition["model"]
            model_key = f"{model_id.lower()}_id"
            selected_id = input_values.get(model_key) or input_values.get("id")
            record = self._find(model_id, {"id": selected_id})
            assert record[transition["field"]] == transition["from"]
            record[transition["field"]] = transition["to"]
            for emit in outcome.get("emits", []):
                event_id, payload = self._event_payload_from_emit(emit, cap, outcome, input_values, record)
                self._record_event(event_id, payload)
            self.last_result = record
            return record
        # Command/query operations are recorded as effects in the spec world.
        result = {"ok": True, "operation": cap_id, **input_values}
        self.last_result = result
        return result

    def _emit(self, event_id: str, payload: dict[str, Any]) -> None:
        self._record_event(event_id, payload)
        for workflow_id, workflow in self.contract["workflows"].items():
            if workflow["trigger"] == {"event": event_id}:
                self.workflows_ran.append(workflow_id)
                self.workflow_outcomes[workflow_id] = self._run_workflow(workflow, payload)

    def _run_workflow(self, workflow: dict[str, Any], payload: dict[str, Any]) -> str:
        step_by_id = {step["id"]: step for step in workflow["steps"]}
        current = workflow["steps"][0]["id"]
        namespace: dict[str, Any] = {"trigger": {"payload": payload}, "steps": {}}
        while True:
            step = step_by_id[current]
            input_values = {name: _resolve_binding(source, namespace) for name, source in step["with"].items()}
            result = self._invoke(step["operation"], input_values)
            outcome_id = self.last_outcome
            assert outcome_id is not None
            namespace["steps"].setdefault(step["id"], {"outcomes": {}})["outcomes"][outcome_id] = {"result": result}
            route = step["on"][outcome_id]
            if "complete" in route:
                return route["complete"]
            if "fail" in route:
                return route["fail"]
            current = route["next"]

    def _event_payload_from_emit(
        self,
        emit: Any,
        operation: Mapping[str, Any],
        outcome: Mapping[str, Any],
        input_values: Mapping[str, Any],
        result: Mapping[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        if isinstance(emit, str):
            return emit, dict(result)
        namespace = {"input": dict(input_values), "outcome": {"result": dict(result)}}
        if "payload" in emit:
            return emit["event"], _resolve_binding(emit["payload"], namespace)
        return emit["event"], {field: _resolve_binding(source, namespace) for field, source in emit["with"].items()}

    def _record_event(self, event_id: str, payload: dict[str, Any]) -> None:
        self.emitted.append(event_id)

    def _filter(self, model_id: str, where: dict[str, Any]) -> list[dict[str, Any]]:
        return [record for record in self.store[model_id] if _matches(record, where)]

    def _find(self, model_id: str, where: dict[str, Any]) -> dict[str, Any]:
        matches = self._filter(model_id, where)
        assert matches, f"No {model_id} found for {where}"
        return matches[0]

    def _complete_record(self, model_id: str, values: dict[str, Any]) -> dict[str, Any]:
        fields = self.contract["models"][model_id]["fields"]
        record = dict(values)
        if "id" in fields and "id" not in record:
            record["id"] = f"{model_id.lower()}_{len(self.store[model_id]) + 1}"
        if "created_at" in fields and "created_at" not in record:
            record["created_at"] = "2026-05-10T00:00:00Z"
        if "updated_at" in fields and "updated_at" not in record:
            record["updated_at"] = "2026-05-10T00:00:00Z"
        return record

    def _resolve_map(self, values: Mapping[str, Any]) -> dict[str, Any]:
        return resolve_map(values, self.fixtures)


def _matches(record: Mapping[str, Any], where: Mapping[str, Any]) -> bool:
    return all(record.get(key) == value for key, value in where.items())


def _single_model(operation: Mapping[str, Any], field: str) -> str:
    models = operation[field]
    assert len(models) == 1, f"Expected exactly one {field} model"
    return models[0]


def _success_outcome_id(operation: Mapping[str, Any]) -> str:
    successes = [outcome_id for outcome_id, outcome in operation["outcomes"].items() if outcome["kind"] == "success"]
    assert len(successes) == 1, "Expected exactly one success outcome"
    return successes[0]


def _resolve_binding(source: str, namespace: Mapping[str, Any]) -> Any:
    return resolve_reference_expression(source, namespace)


def _condition_matches(condition: Mapping[str, Any], context: Mapping[str, Any]) -> bool:
    if "context_present" in condition:
        key = condition["context_present"]
        return key in context and context[key] is not None
    if "context_equals" in condition:
        body = condition["context_equals"]
        return context.get(body["field"]) == body["value"]
    return False
