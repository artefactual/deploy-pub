@shard-identification
Feature: 5 - File Identification with Fido

  @item-5.3
  Scenario: Fido identifies formats and versions
    Given Fido is the enabled identification command
    When a "standard" transfer of "SampleTransfers/Images" is processed
    Then Fido identifies the file formats and versions accurately
    And one format identification PREMIS event per file is present in the METS
    And the format identification event detail indicates that Fido was the tool used

  @item-5.4
  Scenario: Fido identifies the formats of a transfer with known formats
    Given Fido is the enabled identification command
    When a "standard" transfer of "SampleTransfers/Images" is processed
    Then Fido identifies the formats during the Identify file format microservice
