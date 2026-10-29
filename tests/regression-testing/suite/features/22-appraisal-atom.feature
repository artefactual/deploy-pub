@shard-atom @needs-browser @needs-atom
Feature: 22 - Appraisal (AtoM)

  @item-22.6
  Scenario: An arrangement made in the Arrangement pane reaches AtoM and the METS
    Given the AtoM integration is configured
    And a transfer of "SampleTransfers/Images/pictures" is in the backlog
    And the user is logged in to the dashboard
    And the default processing configuration normalizes for access and stops at the Upload DIP decision
    And the user has searched for the transfer on the Appraisal tab
    When the user arranges files of the transfer in a directory of the Arrangement pane
    And the user creates a SIP from the arrangement
    And the user selects "Upload DIP to AtoM" at the Upload DIP job and enters the slug of the target description
    Then the arrangement is reflected in AtoM
    And a logical structMap reflecting the arrangement is in the METS

  @item-22.7
  Scenario: A level of description applied in the Arrangement pane reaches AtoM and the METS
    Given the AtoM integration is configured
    And the levels of description have been fetched from AtoM
    And a transfer of "SampleTransfers/Images/pictures" is in the backlog
    And the user is logged in to the dashboard
    And the default processing configuration normalizes for access and stops at the Upload DIP decision
    And the user has searched for the transfer on the Appraisal tab
    When the user arranges files of the transfer in a directory of the Arrangement pane
    And the user applies the "Series" level of description to the directory
    And the user creates a SIP from the arrangement
    And the user selects "Upload DIP to AtoM" at the Upload DIP job and enters the slug of the target description
    Then the level of description is reflected in AtoM
    And a logical structMap reflecting the arrangement is in the METS
