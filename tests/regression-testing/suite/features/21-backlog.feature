@shard-storage @needs-browser
Feature: 21 - Backlog

  @item-21.1
  Scenario: A transfer sent to the backlog is downloaded from the Backlog tab
    Given a transfer of "SampleTransfers/Images/pictures" is in the backlog
    And the user is logged in to the dashboard
    When the user downloads the transfer from the Backlog tab
    Then the package downloaded from the backlog is a valid bag
    And it contains a transfer METS file

  @item-21.2
  Scenario: The backlog is searched by every parameter of the Backlog tab
    Given a transfer of "SampleTransfers/Images/pictures" with an accession number is in the backlog
    And the user is logged in to the dashboard
    When the user searches the backlog by each parameter on the Backlog tab
    Then the searches by file name, file extension, accession number, ingest date and transfer UUID list the transfer

  @item-21.3
  Scenario: An approved deletion request removes a transfer from the backlog
    Given a transfer of "SampleTransfers/Images/pictures" is in the backlog
    And the user is logged in to the dashboard
    When the user requests the deletion of the transfer from the Backlog tab
    And the Storage Service administrator approves the deletion request
    Then the transfer is removed from the backlog
