Feature: Project Approval Notice

  @spec @test_case_project_approval_notice_workflow
  Scenario: Approval event sends notice
    Given spec test case "test_case.project.approval_notice.workflow" is given
    When spec test case "test_case.project.approval_notice.workflow" runs when
    Then spec test case "test_case.project.approval_notice.workflow" then holds
