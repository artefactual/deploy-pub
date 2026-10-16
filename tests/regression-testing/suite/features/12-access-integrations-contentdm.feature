@shard-transfer
Feature: 12 - Access integrations (CONTENTdm)

  @item-12.4
  Scenario: Upload DIP to CONTENTdm adds the CSV metadata to the DIP
    Given the "Normalize" decision is set to "Normalize for preservation and access"
    And the "Upload DIP" decision is set to "Upload DIP to CONTENTdm"
    When a "standard" transfer of "SampleTransfers/DemoTransferCSV" is processed
    Then a simple.txt or compound.txt file is added to the DIP
    And the simple.txt or compound.txt file contains the descriptive metadata from the CSV
