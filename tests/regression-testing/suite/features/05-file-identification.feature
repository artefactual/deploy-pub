@shard-transfer
Feature: 5 - File Identification

  @item-5.1
  Scenario: Siegfried identifies the formats of a transfer
    When a "standard" transfer of "SampleTransfers/Images" is processed
    Then Siegfried identifies the formats during the Identify file format microservice

  @item-5.7
  Scenario: File format identification is skipped when turned off
    Given the "Do you want to perform file format identification?" decision is set to "No"
    And the "Do you want to perform file format identification?" decision is set to "No, use existing data"
    When a "standard" transfer of "SampleTransfers/Images" is processed
    Then the standard output of the "Identify file format" job is "Skipping file format identification"
    And there are no format identification PREMIS events for the transfer objects in the METS
