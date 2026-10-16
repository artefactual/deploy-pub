@shard-atom @needs-browser @needs-atom
Feature: 13 - Archival storage (AtoM)

  @item-13.1
  Scenario: The metadata of an AIP is uploaded to an AtoM description from the AIP storage page
    Given the AtoM integration is configured
    And a stored AIP of "SampleTransfers/Images/pictures" exists
    And the user is logged in to the dashboard
    When the user uploads the AIP metadata to the target description from the AIP storage page
    Then the user can navigate to the AIP information page
    And the Upload DIP action of the page accepts the slug of the target description
    And archival descriptions with the digital object metadata but no digital objects are created in AtoM
