@shard-dashboard @needs-browser
Feature: 1 - Transfer Types (dashboard)

  @item-1.1
  Scenario: A transfer is started with a custom processing configuration
    Given the user is logged in to the dashboard
    And a processing configuration named "rt1_1" exists with the "Choose thumbnail mode" decision set to "Yes"
    When the user starts a transfer of "SampleTransfers/Images/pictures" from the Transfer tab with the "rt1_1" processing configuration
    Then the custom configuration appears in the dropdown next to Start transfer
    And a notification says the transfer started with the custom configuration
    And the processing follows the decisions of the custom configuration
    And the next transfer started without selecting a configuration is announced with the default configuration

  @item-1.5
  Scenario: A disk image transfer carries its metadata into the AIP METS
    Given the user is logged in to the dashboard
    When the user starts a "Disk image" transfer of "SampleTransfers/ISODiskImage" from the Transfer tab with disk image metadata
    Then the disk image metadata ends up in the AIP METS
    And the standard AIP structure and METS structure criteria apply to the disk image AIP
