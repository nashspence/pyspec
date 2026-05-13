Feature: Project Approve

  @spec @project_approve_success
  Scenario: Approve submitted dispatch project
    Given spec scenario "project.approve.success" is arranged
    When spec scenario "project.approve.success" is executed
    Then spec scenario "project.approve.success" obligations hold
