@shard-transfer
Feature: 8 - Validation

  @item-8.1
  Scenario: Matroska files are validated with MediaConch
    When a "standard" transfer of "SampleTransfers/Matroska" is processed
    Then the "Validate formats" job completes successfully
    And the validation information for the Matroska files is accurate
    And one validation PREMIS event per file is present in the METS
    And the validation event detail indicates that MediaConch was the tool used
