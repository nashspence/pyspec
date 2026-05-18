Feature: Project Approve

  @spec @behavior_scenario_project_approve_access_denied
  Scenario: Approval authorization maps access_denied outcome
    Given spec behavior scenario "behavior_scenario.project.approve.access_denied" is given
    When spec behavior scenario "behavior_scenario.project.approve.access_denied" runs when
    Then spec behavior scenario "behavior_scenario.project.approve.access_denied" then holds

  @spec @behavior_scenario_project_approve_success
  Scenario: Approve submitted dispatch project
    Given spec behavior scenario "behavior_scenario.project.approve.success" is given
    When spec behavior scenario "behavior_scenario.project.approve.success" runs when
    Then spec behavior scenario "behavior_scenario.project.approve.success" then holds
