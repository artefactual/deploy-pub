@shard-dashboard @needs-browser
Feature: 15 - Administration

  @item-15.11
  Scenario: The version page shows the installed version and its agent code
    When the user logs in to the dashboard
    And the user opens Administration > Version
    Then the version number on the page matches the X-Archivematica-Version header
    And the agent code corresponds to the version

  @item-15.1
  Scenario: The processing configuration can be edited and saved
    Given the user is logged in to the dashboard
    When the user opens Administration > Processing configuration and selects Edit for "default"
    Then the processing configuration form opens
    And the user can make changes
    And the user can save the form

  @item-15.2
  Scenario: A transfer started from the dashboard follows the default processing configuration
    Given the user is logged in to the dashboard
    And the default processing configuration is completed with the "automated" decisions
    And the "Choose thumbnail mode" decision of the default processing configuration is set to "Yes"
    When a "standard" transfer of "SampleTransfers/Images/pictures" is processed with the "default" processing configuration
    Then the transfer follows the decisions set in the default processing configuration

  @item-15.3
  Scenario: The processing configuration can be downloaded
    Given the user is logged in to the dashboard
    When the user selects Download for the "default" processing configuration
    Then an XML file with the processing configuration decisions is downloaded

  @item-15.4
  Scenario: The processing configuration can be reset
    Given the user is logged in to the dashboard
    And the "Choose thumbnail mode" decision of the default processing configuration is changed
    When the user selects Reset for the "default" processing configuration
    Then the configuration is reset to the standard pre-sets

  @item-15.5
  Scenario: A processing configuration can be added
    Given the user is logged in to the dashboard
    When the user adds a processing configuration named "rt15_5"
    Then a processing configuration form opens
    And the user can select decision points
    And the user can save the form

  @item-15.6
  Scenario: The used storage of a location grows when an AIP is stored
    Given the user is logged in to the dashboard
    When the user opens Administration > Storage locations
    And a "standard" transfer of "SampleTransfers/Images/pictures" is processed
    Then the Used storage value of the AIP storage location increases

  @item-15.7
  Scenario: The processing storage usage can be calculated
    Given the user is logged in to the dashboard
    When the user opens Administration > Processing storage usage and selects "Calculate disk usage"
    Then the disk usage is calculated and displayed

  @item-15.10
  Scenario: The dashboard appears in the chosen language
    Given the user is logged in to the dashboard
    When the user changes the language to "fr" in Administration > Language
    Then the interface items appear in that language
