from __future__ import annotations

from pathlib import Path

from pyspec_contract import write_agent_prompts
from pyspec_contract.agent_prompts import USER_PROMPT_PLACEHOLDER, active_prompt_layers
from pyspec_contract.cli import main


def test_agent_prompts_can_be_generated_from_layers_without_spec(tmp_path: Path) -> None:
    written = write_agent_prompts(tmp_path, layers="core,http")

    assert written == {
        "spec/generated/agent_prompts/pm_design.md",
        "spec/generated/agent_prompts/test.md",
        "spec/generated/agent_prompts/dev.md",
        "spec/generated/agent_prompts/review.md",
    }
    pm_design = (tmp_path / "spec" / "generated" / "agent_prompts" / "pm_design.md").read_text(encoding="utf-8")
    test = (tmp_path / "spec" / "generated" / "agent_prompts" / "test.md").read_text(encoding="utf-8")
    dev = (tmp_path / "spec" / "generated" / "agent_prompts" / "dev.md").read_text(encoding="utf-8")
    review = (tmp_path / "spec" / "generated" / "agent_prompts" / "review.md").read_text(encoding="utf-8")
    assert f"User request:\n{USER_PROMPT_PLACEHOLDER}" in pm_design
    assert "Active layers: core,http" in pm_design
    assert "Do not author UI state machines" in pm_design
    assert "SQL" not in pm_design
    assert "migrations" not in pm_design
    assert "Do not edit `spec/spec.yaml` as the test agent." in test
    assert "report the exact needed spec change" in test
    assert "http.openapi.yaml" in dev
    assert "html.state_machines.json" not in dev
    assert f"User request:\n{USER_PROMPT_PLACEHOLDER}" in review
    assert "very strict independent third-party auditor" in review
    assert "PM/design audit:" in review
    assert "Test audit:" in review
    assert "Dev audit:" in review
    assert "Ready for merge: yes" in review
    assert "PM/design findings" in review
    assert "Test findings" in review
    assert "Dev findings" in review
    assert "Recommended prompt for <role>:" in review
    assert "fragility, risk, or incorrectness" in review


def test_init_writes_layer_specific_starter_prompts(tmp_path: Path) -> None:
    assert main(["init", str(tmp_path), "--layers", "core,ui,html"]) == 0

    assert (tmp_path / "spec" / "spec.yaml").exists()
    pm_design = (tmp_path / "spec" / "generated" / "agent_prompts" / "pm_design.md").read_text(encoding="utf-8")
    assert "Active layers: core,html,ui" in pm_design
    assert "HTML UI: html renderer layout, presentation, style" in pm_design
    assert "Do not author Textual renderer details" in pm_design


def test_agent_prompts_use_eventing_layer_for_webhook_adapters(tmp_path: Path) -> None:
    written = write_agent_prompts(tmp_path, layers="core,eventing")

    assert written == {
        "spec/generated/agent_prompts/pm_design.md",
        "spec/generated/agent_prompts/test.md",
        "spec/generated/agent_prompts/dev.md",
        "spec/generated/agent_prompts/review.md",
    }
    pm_design = (tmp_path / "spec" / "generated" / "agent_prompts" / "pm_design.md").read_text(encoding="utf-8")
    dev = (tmp_path / "spec" / "generated" / "agent_prompts" / "dev.md").read_text(encoding="utf-8")
    assert "Active layers: core,eventing" in pm_design
    assert "Eventing: webhook external interfaces and AsyncAPI integration-message projections" in pm_design
    assert "integration_messages.asyncapi.yaml" in dev


def test_domain_event_resources_do_not_activate_eventing_layer() -> None:
    assert active_prompt_layers({"project": "events", "domain_events": {"domain_event.ticket.created": {}}}) == {"core"}
    assert active_prompt_layers(
        {
            "project": "webhook",
            "external_interfaces": {
                "external_interface.webhook.ticket.created": {
                    "adapter": {"webhook": {"path": "/webhooks/ticket-created"}},
                    "invokes": {"workflow": {"ref": "workflow.ticket.created"}},
                }
            },
        }
    ) == {"core", "eventing"}
    assert active_prompt_layers(
        {
            "project": "worker",
            "domain_events": {"domain_event.ticket.created": {}},
            "external_interfaces": {
                "external_interface.worker.ticket.created": {
                    "adapter": {"worker": {}},
                    "invokes": {"workflow": {"ref": "workflow.ticket.created"}},
                }
            },
        }
    ) == {"core", "eventing", "workflow"}
