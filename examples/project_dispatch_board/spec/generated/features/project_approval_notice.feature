Feature: Project Approval Notice

  @spec @project_approval_notice_workflow
  Scenario: Approval event sends notice
    Given spec scenario "project.approval_notice.workflow" is arranged
    When spec scenario "project.approval_notice.workflow" is executed
    Then spec scenario "project.approval_notice.workflow" obligations hold
