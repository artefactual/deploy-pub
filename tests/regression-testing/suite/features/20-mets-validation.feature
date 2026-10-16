@shard-transfer
Feature: 20 - METS Validation

  @item-20.1
  Scenario: The AIP METS validates against its schemas
    When a "standard" transfer of "SampleTransfers/DemoTransferCSV" is processed
    And the AIP METS is validated against the METS schema and the schemas it references
    Then no errors are reported
    And the validation is successful

  @item-20.2
  Scenario: The AIP METS follows the Archivematica METS rules
    When a "standard" transfer of "SampleTransfers/DemoTransferCSV" is processed
    And the AIP METS is checked against the Archivematica rules of metsrw
    Then the expected METS and PREMIS sections are present and they match expected values
