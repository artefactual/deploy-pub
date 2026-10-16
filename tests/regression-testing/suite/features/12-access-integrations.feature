@shard-atom @needs-browser @needs-atom
Feature: 12 - Access integrations

  @item-12.1
  Scenario: A DIP is uploaded to an AtoM description
    Given the AtoM integration is configured
    And the user is logged in to the dashboard
    When a "standard" transfer of "SampleTransfers/DemoTransferCSV" is processed up to the Upload DIP decision
    And the user selects "Upload DIP to AtoM" at the Upload DIP job and enters the slug of the target description
    Then the digital objects are uploaded to the AtoM target description

  @item-12.3
  Scenario: A transfer with an access system ID uploads its DIP without asking for the slug
    Given the AtoM integration is configured
    And the user is logged in to the dashboard
    When a "standard" transfer of "SampleTransfers/DemoTransferCSV" with the target description as access system ID is processed up to the Upload DIP decision
    And the user selects "Upload DIP to AtoM" at the Upload DIP job
    Then Archivematica does not prompt the user for the slug
    And the digital objects are uploaded to the AtoM target description
