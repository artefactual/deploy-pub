@shard-dashboard @needs-browser
Feature: 16 - Users & Permissions

  @item-16.1
  Scenario: An administrator manages users
    Given the user is logged in to the dashboard
    When the user adds, edits and deletes a user named "rt16_1" in Administration > Users
    Then the user can add, edit and delete users

  @item-16.2
  Scenario: A non-administrator does not see the Users menu
    Given the user is logged in to the dashboard
    And a non-administrator user named "rt16_2" exists
    When that user logs in to the dashboard and opens the Administration tab
    Then the Users menu item is not shown
