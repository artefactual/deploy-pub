@shard-dashboard @needs-browser
Feature: 10 - Performance & Resilience

  @item-10.4
  Scenario: A completed transfer can be removed from the Transfer tab
    Given the user is logged in to the dashboard
    And a completed transfer of "SampleTransfers/Images/pictures" exists
    When the user clicks Remove for the completed transfer on the Transfer tab
    Then a popup asks the user to confirm the removal
    And the transfer no longer appears in the Transfer tab

  @item-10.5
  Scenario: All completed transfers can be removed from the Transfer tab
    Given the user is logged in to the dashboard
    And the "Assign UUIDs to directories?" decision is left for the user
    And a completed transfer of "SampleTransfers/Images/pictures" exists
    And a transfer of "SampleTransfers/Images/pictures" is waiting for a decision
    When the user clicks "Remove all completed" on the Transfer tab
    Then a popup asks the user to confirm the removal
    And the completed transfers no longer appear in the Transfer tab
    And the transfers still in progress remain in the Transfer tab
