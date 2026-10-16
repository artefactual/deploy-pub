@shard-transfer
Feature: 11 - Add Metadata

  @item-11.3
  Scenario: The accession number of a transfer is recorded as a registration event
    Given the accession number "RT-2026-0011"
    When a "standard" transfer of "SampleTransfers/Images" with accession number "RT-2026-0011" is processed
    Then the accession number is recorded in the METS as a registration event outcome detail note
