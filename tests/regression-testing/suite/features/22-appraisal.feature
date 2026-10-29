@shard-dashboard @needs-browser
Feature: 22 - Appraisal

  @item-22.1
  Scenario: The backlog is searched by every parameter of the Appraisal tab
    Given a transfer of "SampleTransfers/Images/pictures" with an accession number is in the backlog
    And the user is logged in to the dashboard
    When the user searches the backlog by each parameter on the Appraisal tab
    Then the searches by file name, file extension, accession number, ingest date and transfer UUID find the transfer
    And the search results are displayed in the backlog pane

  @item-22.2
  Scenario: The directories of the backlog pane expand and collapse together
    Given a transfer of "SampleTransfers/Images/pictures" is in the backlog
    And the user is logged in to the dashboard
    And the user has searched for the transfer on the Appraisal tab
    When the user selects Expand all and then Collapse all
    Then all directories expand and then collapse

  @item-22.3
  Scenario: The selected files of the backlog pane are deselected together
    Given a transfer of "SampleTransfers/Images/pictures" is in the backlog
    And the user is logged in to the dashboard
    And the user has searched for the transfer on the Appraisal tab
    And the user has selected several files in the backlog pane
    When the user selects Deselect all
    Then the files are deselected

  @item-22.4
  Scenario: A tag added to the selected files shows across the panes and can make a SIP
    Given a transfer of "SampleTransfers/Images/pictures" is in the backlog
    And the user is logged in to the dashboard
    And the user has searched for the transfer on the Appraisal tab
    And the user has selected several files in the backlog pane
    When the user adds a tag to the selected files
    Then the tag is visible in the backlog pane and in the tags dropdown
    And the tag is visible in the Tags tab of the Analysis pane
    And the tag is visible in the File list pane
    And a SIP can be created from the tag in the Arrangement pane

  @item-22.5
  Scenario: A SIP created from a tag starts and appears on the Ingest tab
    Given a transfer of "SampleTransfers/Images/pictures" is in the backlog
    And the user is logged in to the dashboard
    And the user has searched for the transfer on the Appraisal tab
    And the user has tagged several files in the backlog pane
    When the user creates a SIP from the tag in the Arrangement pane
    Then the SIP is started
    And the SIP appears on the Ingest tab
