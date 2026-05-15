Feature: Feature Project Board

  @spec @scenario_project_board_empty
  Scenario: Empty dispatch board
    Given spec scenario "scenario.project.board.empty" is arranged
    When spec scenario "scenario.project.board.empty" is executed
    Then spec scenario "scenario.project.board.empty" obligations hold

  @spec @scenario_project_board_ready
  Scenario: Ready dispatch board
    Given spec scenario "scenario.project.board.ready" is arranged
    When spec scenario "scenario.project.board.ready" is executed
    Then spec scenario "scenario.project.board.ready" obligations hold
