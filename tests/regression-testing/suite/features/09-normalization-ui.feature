@shard-dashboard @needs-browser
Feature: 9 - Normalization (dashboard)

  @item-9.6
  Scenario: Manually normalized files are processed after approval
    Given the user is logged in to the dashboard
    And the "Normalize" decision is left for the user
    And the "Approve normalization" decision is left for the user
    When a "standard" transfer of "SampleTransfers/Images/pictures" is processed
    And the user selects "Normalize manually" at the "Normalize" job
    And the user inserts manually normalized files into the SIP
    And the user selects "Yes" at the "Approve normalization" job
    Then the "Process manually normalized files" microservice completes successfully
    And the manually normalized preservation derivative is added to the AIP with a UUID suffix and the appropriate file extension
    And the manually normalized access derivative is added to the DIP

  @item-9.7
  Scenario: The manual normalization event detail is recorded
    Given the user is logged in to the dashboard
    And the "Normalize" decision is left for the user
    And the "Approve normalization" decision is left for the user
    And the "Reminder: add metadata if desired" decision is left for the user
    When a "standard" transfer of "SampleTransfers/Images/pictures" is processed
    And the user selects "Normalize manually" at the "Normalize" job
    And the user inserts manually normalized files into the SIP
    And the user selects "Yes" at the "Approve normalization" job
    And the user fills in the manual normalization event detail
    And the SIP continues processing
    Then the user can enter normalization event information for the manual normalization
    And the event information is added to the METS
