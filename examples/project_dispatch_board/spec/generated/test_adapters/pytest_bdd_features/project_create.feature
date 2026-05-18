Feature: Project Create

  @spec @behavior_scenario_project_create_api_success
  Scenario: Create dispatch project through API
    Given spec behavior scenario "behavior_scenario.project.create.api.success" is given
    When spec behavior scenario "behavior_scenario.project.create.api.success" runs when
    Then spec behavior scenario "behavior_scenario.project.create.api.success" then holds
