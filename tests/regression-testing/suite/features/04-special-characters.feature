@shard-transfer
Feature: 4 - Special Characters

  @item-4.1
  Scenario: Files and directories with special characters are renamed
    When a "standard" transfer of "TestTransfers/badNames" is processed
    Then the "Change transfer filenames" microservice completes successfully
    And the AIP contains a filename change log
    And a filename change PREMIS event is present in the METS

  @item-4.2
  Scenario: A transfer name with non-ASCII characters is changed
    When a "standard" transfer of "SampleTransfers/Images" named "rt-4.2 Año Çédille Ñandú" is processed
    Then the "Change transfer filenames" microservice completes successfully
    And the transfer name is changed to use ASCII characters

  @item-4.3
  Scenario: Files with diacritics and a metadata.csv file are processed
    When a "standard" transfer of "SampleTransfers/DiacriticsTest" is processed
    Then the "Change transfer filenames" microservice completes successfully
    And the AIP contains a filename change log
    And a filename change PREMIS event is present in the METS
    And the AIP METS contains descriptive metadata for each file described in metadata.csv
