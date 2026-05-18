Feature: Project Approve

  @spec @test_case_project_approve_access_denied
  Scenario: Approval authorization maps access_denied outcome
    Given spec test case "test_case.project.approve.access_denied" is given
    When spec test case "test_case.project.approve.access_denied" runs when
    Then spec test case "test_case.project.approve.access_denied" then holds

  @spec @test_case_project_approve_success
  Scenario: Approve submitted dispatch project
    Given spec test case "test_case.project.approve.success" is given
    When spec test case "test_case.project.approve.success" runs when
    Then spec test case "test_case.project.approve.success" then holds
