Feature: Project Board

  @contract @project_board_empty
  Scenario: Empty dispatch board
    Given contract scenario "project.board.empty" is arranged
    When contract scenario "project.board.empty" is executed
    Then contract scenario "project.board.empty" obligations hold

  @contract @project_board_ready
  Scenario: Ready dispatch board
    Given contract scenario "project.board.ready" is arranged
    When contract scenario "project.board.ready" is executed
    Then contract scenario "project.board.ready" obligations hold
