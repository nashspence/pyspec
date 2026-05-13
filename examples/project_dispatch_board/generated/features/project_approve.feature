Feature: Project Approve

  @contract @project_approve_success
  Scenario: Approve submitted dispatch project
    Given contract scenario "project.approve.success" is arranged
    When contract scenario "project.approve.success" is executed
    Then contract scenario "project.approve.success" obligations hold
