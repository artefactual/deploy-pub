@shard-transfer
Feature: 2 - Transfer Variants

  @item-2.1
  Scenario: Descriptive and rights metadata CSV files are written to the AIP METS
    When a "standard" transfer of "SampleTransfers/DemoTransferCSV" is processed
    Then the AIP METS contains descriptive metadata for each object described in metadata.csv
    And the AIP METS contains rights metadata for each object described in rights.csv

  @item-2.2
  Scenario: Submission documentation is listed in the AIP METS
    When a "standard" transfer of "SampleTransfers/DemoTransferCSV" is processed
    Then submission documentation is listed in the METS with fileGrp USE="submissionDocumentation"

  @item-2.3
  Scenario: Multi-level descriptive metadata is written for directories
    When a "standard" transfer of "SampleTransfers/CSVmultiLevel" is processed
    Then the AIP METS contains descriptive metadata for each directory described in metadata.csv

  @item-2.4
  Scenario: Descriptive metadata is written for individual files
    When a "standard" transfer of "SampleTransfers/CSVmetadata" is processed
    Then the AIP METS contains descriptive metadata for each file described in metadata.csv

  @item-2.7
  Scenario: Service files are normalized for access when that option is chosen
    Given the "Normalize" decision is set to "Normalize service files for access"
    When a "standard" transfer of "SampleTransfers/ServiceCopies" is processed
    Then the "Normalize service files for access" job completes successfully
    And the task output shows that the service files were used to create access copies

  @item-2.8
  Scenario: A transfer with its own processing configuration follows it
    When a "standard" transfer of "SampleTransfers/ProcessingMCP" is processed
    Then the transfer and ingest follow the decisions of the processing configuration XML file included in the transfer

  @item-2.10
  Scenario: Events and agents from a premis.xml file are imported
    When a "standard" transfer of "SampleTransfers/PremisImporter" is processed
    Then the events and agents from premis.xml are added to the AIP METS
    And the imported events retain their original field values, including the event details
    And the imported events are linked to the same agents as in premis.xml

  @item-2.11
  Scenario: Identifiers from an identifiers.json file are recorded
    When a "standard" transfer of "SampleTransfers/DemoTransferCSV" is processed
    Then the identifiers from identifiers.json are recorded as objectIdentifiers in the METS
