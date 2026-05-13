Feature: Project Create

  @contract @project_create_api_success
  Scenario: Create dispatch project through API
    Given contract scenario "project.create.api.success" is arranged
    When contract scenario "project.create.api.success" is executed
    Then contract scenario "project.create.api.success" obligations hold
