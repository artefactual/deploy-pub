@shard-storage @needs-browser
Feature: 19 - Storage Service

  @item-19.2
  Scenario: A DIP is deleted from the Packages tab
    Given a stored AIP of "SampleTransfers/Images/pictures" exists with a DIP
    And the user is logged in to the Storage Service
    When the user deletes the DIP from the Packages tab
    Then the DIP is deleted

  @item-19.4
  Scenario: An approved deletion request deletes the AIP
    Given a stored AIP of "SampleTransfers/Images/pictures" exists
    And the deletion of the AIP was requested from the dashboard
    And the user is logged in to the dashboard
    And the user is logged in to the Storage Service
    When the Storage Service admin approves the deletion request
    Then the AIP is deleted
    And the AIP is no longer listed in the Archival storage tab
    And the decision appears in the Closed Requests table

  @item-19.5
  Scenario: A rejected deletion request keeps the AIP
    Given a stored AIP of "SampleTransfers/Images/pictures" exists
    And the deletion of the AIP was requested from the dashboard
    And the user is logged in to the dashboard
    And the user is logged in to the Storage Service
    When the Storage Service admin rejects the deletion request
    Then the AIP is not deleted
    And the status of the AIP in the Archival storage tab is back to "Stored"
    And the decision appears in the Closed Requests table
