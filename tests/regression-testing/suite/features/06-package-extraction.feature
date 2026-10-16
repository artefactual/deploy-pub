@shard-transfer
Feature: 6 - Package Extraction

  @item-6.1
  Scenario: Extracted packages are deleted when requested
    Given the "Extract packages?" decision is set to "Yes"
    And the "Delete package after extraction?" decision is set to "Yes"
    When a "standard" transfer of "SampleTransfers/OfficeDocs" is processed
    Then the AIP does not contain the original packages

  @item-6.2
  Scenario: Extracted packages are kept when requested
    Given the "Extract packages?" decision is set to "Yes"
    And the "Delete package after extraction?" decision is set to "No"
    When a "standard" transfer of "SampleTransfers/OfficeDocs" is processed
    Then the AIP contains the original packages
