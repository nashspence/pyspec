Feature: Feature Project Board

  @spec @test_case_project_board_empty
  Scenario: Empty dispatch board
    Given spec test case "test_case.project.board.empty" is given
    When spec test case "test_case.project.board.empty" runs when
    Then spec test case "test_case.project.board.empty" then holds

  @spec @test_case_project_board_ready
  Scenario: Ready dispatch board
    Given spec test case "test_case.project.board.ready" is given
    When spec test case "test_case.project.board.ready" runs when
    Then spec test case "test_case.project.board.ready" then holds
