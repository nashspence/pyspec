Feature: Project Approval Notice

  @spec @behavior_scenario_project_approval_notice_workflow
  Scenario: Approval domain event sends notice
    Given spec behavior scenario "behavior_scenario.project.approval_notice.workflow" is given
    When spec behavior scenario "behavior_scenario.project.approval_notice.workflow" runs when
    Then spec behavior scenario "behavior_scenario.project.approval_notice.workflow" then holds
