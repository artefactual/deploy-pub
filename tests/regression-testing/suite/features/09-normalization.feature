@shard-normalization
Feature: 9 - Normalization

  @item-9.1
  Scenario: Files are normalized for preservation and access
    Given the "Normalize" decision is set to "Normalize for preservation and access"
    When a "standard" transfer of "SampleTransfers/Images" is processed
    Then the files are normalized for preservation and access as per the rules
    And the preservation derivatives are added to the AIP with a UUID suffix and the appropriate file extension
    And the access derivatives are added to the DIP
    And normalization PREMIS events are added to the METS

  @item-9.2
  Scenario: Thumbnails are generated for every object
    Given the "Choose thumbnail mode" decision is set to "Yes"
    When a "standard" transfer of "SampleTransfers/Images" is processed
    Then thumbnails are created for all digital objects in the AIP

  @item-9.3
  Scenario: Files are normalized for preservation
    Given the "Normalize" decision is set to "Normalize for preservation"
    When a "standard" transfer of "SampleTransfers/Images" is processed
    Then the files are normalized for preservation as per the rules
    And the preservation derivatives are added to the AIP with a UUID suffix and the appropriate file extension
    And normalization PREMIS events are added to the METS

  @item-9.4
  Scenario: Service files are used for the access derivatives
    Given the "Normalize" decision is set to "Normalize service files for access"
    When a "standard" transfer of "SampleTransfers/ServiceCopies" is processed
    Then the service files are used to create the access derivatives
    And the access derivatives are added to the DIP

  @item-9.5
  Scenario: Nothing is normalized when "Do not normalize" is chosen
    Given the "Normalize" decision is set to "Do not normalize"
    When a "standard" transfer of "SampleTransfers/Images" is processed
    Then normalization does not occur
    And the AIP contains originals only

  @item-9.8
  Scenario: Files are normalized for access only
    Given the "Normalize" decision is set to "Normalize for access"
    When a "standard" transfer of "SampleTransfers/Images" is processed
    Then access derivatives are created and added to the DIP
    And the AIP contains originals only

  @item-9.10
  Scenario: Manually normalized preservation copies are used
    Given the "Normalize" decision is set to "Normalize for preservation"
    When a "standard" transfer of "SampleTransfers/PreservationCopies" is processed
    Then normalization does not occur during the Normalize microservice
    And the "Process manually normalized files" microservice recognizes the manualNormalization/preservation directory
    And UUIDs are assigned to the preservation copies and included in their filenames
    And the AIP contains the originals and the preservation copies as if Archivematica had normalized for preservation
    And the AIP includes normalization events

  @item-9.11
  Scenario: Thumbnails are generated without default icons
    Given the "Choose thumbnail mode" decision is set to "Yes, without default icons"
    When a "standard" transfer of "SampleTransfers/DemoTransferCSV" is processed
    Then thumbnails are created for all digital objects in the AIP where meaningful thumbnails can be created
    And no thumbnail is the default icon

  @item-9.12
  Scenario: No thumbnails are generated
    Given the "Choose thumbnail mode" decision is set to "No"
    When a "standard" transfer of "SampleTransfers/Images" is processed
    Then no thumbnails are created

  @item-9.13
  Scenario: Files are transcribed with OCR
    Given the "Transcribe SIP contents?" decision is set to "Yes"
    When a "standard" transfer of "SampleTransfers/OCRImage" is processed
    Then the "Transcribe SIP contents" microservice completes successfully
    And the AIP contains a text file of the transcribed contents in the metadata/OCRfiles directory
