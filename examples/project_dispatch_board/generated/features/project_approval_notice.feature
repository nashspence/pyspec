Feature: Project Approval Notice

  @contract @project_approval_notice_workflow
  Scenario: Approval event sends notice
    Given contract scenario "project.approval_notice.workflow" is arranged
    When contract scenario "project.approval_notice.workflow" is executed
    Then contract scenario "project.approval_notice.workflow" obligations hold
