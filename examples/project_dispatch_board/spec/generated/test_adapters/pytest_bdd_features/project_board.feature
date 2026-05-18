Feature: Project Board

  @spec @behavior_scenario_project_board_empty
  Scenario: Empty dispatch board
    Given spec behavior scenario "behavior_scenario.project.board.empty" is given
    When spec behavior scenario "behavior_scenario.project.board.empty" runs when
    Then spec behavior scenario "behavior_scenario.project.board.empty" then holds

  @spec @behavior_scenario_project_board_ready
  Scenario: Ready dispatch board
    Given spec behavior scenario "behavior_scenario.project.board.ready" is given
    When spec behavior scenario "behavior_scenario.project.board.ready" runs when
    Then spec behavior scenario "behavior_scenario.project.board.ready" then holds
