@shard-identification @needs-browser
Feature: 14 - Preservation Planning

  @item-14.1
  Scenario: Enabling Fido disables Siegfried and Fido identifies the next transfer
    Given the user is logged in to the dashboard
    And Siegfried is the enabled identification command
    When the user enables the Fido identification command in Preservation planning
    And a "standard" transfer of "SampleTransfers/Images/pictures" is processed
    Then the Siegfried command is disabled
    And the Fido command is enabled
    And the transfer is identified by Fido instead of Siegfried

  @item-14.2
  Scenario: A disabled command does not run
    Given the user is logged in to the dashboard
    And the "ExifTool" characterization command is enabled
    When the user disables the "ExifTool" characterization command in Preservation planning
    And a "standard" transfer of "SampleTransfers/Images/pictures" is processed
    Then the "ExifTool" command does not run
    And the task output does not show that the "ExifTool" command ran
    And the METS does not show that the "ExifTool" command ran
    And the "ExifTool" command can be re-enabled

  @item-14.3
  Scenario: An edited command runs
    Given the user is logged in to the dashboard
    When the user edits the "Transcoding to tif with convert" command to print a marker
    And a "standard" transfer of "SampleTransfers/Images/pictures" is processed
    Then the edited version of the "Transcoding to tif with convert" command runs
    And the task output and the METS show that the updated command ran

  @item-14.4
  Scenario: A command is reverted through its revision history
    Given the user is logged in to the dashboard
    And the user has edited the "Transcoding to tif with convert" command
    When the user reverts the "Transcoding to tif with convert" command through its revision history
    And a "standard" transfer of "SampleTransfers/Images/pictures" is processed
    Then the user can click on "Revision history"
    And the user can select the previous version to revert to
    And the task output and the METS show that the reverted version of the command ran
