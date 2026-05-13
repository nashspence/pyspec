Feature: Project Create

  @spec @project_create_api_success
  Scenario: Create dispatch project through API
    Given spec scenario "project.create.api.success" is arranged
    When spec scenario "project.create.api.success" is executed
    Then spec scenario "project.create.api.success" obligations hold
