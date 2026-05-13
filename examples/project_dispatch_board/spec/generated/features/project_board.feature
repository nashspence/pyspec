Feature: Project Board

  @spec @project_board_empty
  Scenario: Empty dispatch board
    Given spec scenario "project.board.empty" is arranged
    When spec scenario "project.board.empty" is executed
    Then spec scenario "project.board.empty" obligations hold

  @spec @project_board_ready
  Scenario: Ready dispatch board
    Given spec scenario "project.board.ready" is arranged
    When spec scenario "project.board.ready" is executed
    Then spec scenario "project.board.ready" obligations hold
