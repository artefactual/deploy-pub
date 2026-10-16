@shard-storage
Feature: 13 - Archival storage

  @item-13.5 @needs-browser
  Scenario: The AIP is downloaded from its storage page
    Given a stored AIP of "SampleTransfers/Images/pictures" exists
    And the user is logged in to the dashboard
    When the user clicks "Download" on the AIP storage page
    Then the AIP is downloaded

  @item-13.6 @needs-browser
  Scenario: The METS file is viewed from the AIP storage page
    Given a stored AIP of "SampleTransfers/Images/pictures" exists
    And the user is logged in to the dashboard
    When the user clicks "View" next to the METS file on the AIP storage page
    Then the METS file is downloaded

  @item-13.7 @needs-browser
  Scenario: The pointer file is viewed from the AIP storage page
    Given a stored AIP of "SampleTransfers/Images/pictures" exists
    And the user is logged in to the dashboard
    When the user clicks "View" next to the pointer file on the AIP storage page
    Then the pointer file is downloaded

  @item-13.8 @needs-browser
  Scenario: A metadata re-ingest takes new metadata into the stored AIP
    Given a stored AIP of "SampleTransfers/Images/pictures" exists
    And the user is logged in to the dashboard
    And the "Reminder: add metadata if desired" decision is left for the user
    When the user starts a "Metadata re-ingest" of the AIP with the scenario's processing configuration
    And the user selects "Approve AIP reingest" at the "Approve AIP reingest" job
    And the user adds descriptive metadata to the re-ingested SIP through the GUI form
    And the SIP continues processing
    Then the AIP is sent to the Ingest tab where the re-ingest can be approved
    And the microservices follow the selected processing configuration
    And metadata can be added using the metadata icon in the GUI
    And the new AIP overwrites the old one in storage
    And the METS of the new AIP has a reingestion event

  @item-13.9 @needs-browser
  Scenario: A partial re-ingest creates a DIP on demand
    Given a stored AIP of "SampleTransfers/Images/pictures" exists
    And the user is logged in to the dashboard
    And the "Normalize" decision is set to "Normalize for access"
    When the user starts a "Partial re-ingest" of the AIP with the scenario's processing configuration
    And the user selects "Approve AIP reingest" at the "Approve AIP reingest" job
    Then the AIP is sent to the Ingest tab where the re-ingest can be approved
    And the microservices follow the selected processing configuration
    And a DIP is created from the re-ingested AIP
    And the new AIP overwrites the old one in storage
    And the METS of the new AIP has a reingestion event

  @item-13.10 @needs-browser
  Scenario: A deletion request marks the AIP as deletion requested
    Given a stored AIP of "SampleTransfers/Images/pictures" exists
    And the user is logged in to the dashboard
    When the user requests the deletion of the AIP from its storage page
    Then the status of the AIP is "Deletion requested"

  @item-13.11
  Scenario: An AIP stored in an encrypted location is encrypted, downloadable and re-ingestable
    Given an encrypted AIP storage location exists
    And the scenario stores its AIP in that location
    When a "standard" transfer of "SampleTransfers/Images/pictures" is processed
    Then the pointer file includes an encryption event and the public key
    And the AIP can be downloaded
    And the AIP can be re-ingested and downloaded again

  @item-13.12
  Scenario: An AIP stored in a replicated location gets a second copy
    Given an AIP storage location with a replicator location exists
    And the scenario stores its AIP in that location
    When a "standard" transfer of "SampleTransfers/Images/pictures" is processed
    Then the AIP is saved in the storage location
    And a second copy of the AIP is saved in the replicator location
