@shard-transfer
Feature: 1 - Transfer Types

  @item-1.2
  Scenario: A zipped directory is processed with the Zipped directory transfer type
    When a "zipfile" transfer of "SampleTransfers/ZippedDirectoryTransfers/DemoTransferCSV.zip" is processed
    Then the "Extract zipped transfer" job completes successfully
    And all jobs complete successfully
    And the standard AIP structure and METS structure criteria apply

  @item-1.3
  Scenario: A zipped bag is processed with the Zipped bag transfer type
    When a "zipped bag" transfer of "SampleTransfers/ZippedBag.zip" is processed
    Then the "Verify bag, and restructure for compliance" job completes successfully
    And the standard AIP structure and METS structure criteria apply
    And the contents of bag-info.txt are parsed into the METS

  @item-1.4
  Scenario: A DSpace export is processed with the DSpace transfer type
    When a "dspace" transfer of "SampleTransfers/DSpaceExport/ITEM@2429-2696.zip" is processed
    Then the "Identify DSpace files" microservice completes successfully
    And the standard AIP structure and METS structure criteria apply
