Feature: Feature Project Approve

  @spec @scenario_project_approve_success
  Scenario: Approve submitted dispatch project
    Given spec scenario "scenario.project.approve.success" is arranged
    When spec scenario "scenario.project.approve.success" is executed
    Then spec scenario "scenario.project.approve.success" obligations hold
