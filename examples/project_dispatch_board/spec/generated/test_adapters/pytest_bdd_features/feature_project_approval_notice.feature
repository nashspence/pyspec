Feature: Feature Project Approval Notice

  @spec @scenario_project_approval_notice_workflow
  Scenario: Approval event sends notice
    Given spec scenario "scenario.project.approval_notice.workflow" is arranged
    When spec scenario "scenario.project.approval_notice.workflow" is executed
    Then spec scenario "scenario.project.approval_notice.workflow" obligations hold
