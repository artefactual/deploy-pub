@shard-dashboard @needs-browser
Feature: 11 - Add Metadata (dashboard)

  @item-11.1
  Scenario: Rights metadata is recorded through the GUI form
    Given the user is logged in to the dashboard
    And the "Reminder: add metadata if desired" decision is left for the user
    When a "standard" transfer of "SampleTransfers/Images/pictures" is processed
    And the user adds, edits and deletes rights metadata for the SIP through the GUI form
    And the SIP continues processing
    Then the user can add, edit and delete rights metadata using the GUI form
    And the rights metadata is written to the METS

  @item-11.2
  Scenario: Descriptive metadata is recorded through the GUI form
    Given the user is logged in to the dashboard
    And the "Reminder: add metadata if desired" decision is left for the user
    When a "standard" transfer of "SampleTransfers/Images/pictures" is processed
    And the user adds, edits and deletes descriptive metadata for the SIP through the GUI form
    And the SIP continues processing
    Then the user can add, edit and delete descriptive metadata using the GUI form
    And the descriptive metadata is written to the METS
