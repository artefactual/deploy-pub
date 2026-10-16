@shard-dashboard @needs-browser
Feature: 17 - Failure Reports & Notifications (dashboard)

  @item-17.1
  Scenario: A failed transfer produces a failure report
    Given the user is logged in to the dashboard
    And the transfer is expected to fail
    When a "standard" transfer of "TestTransfers/virusTests" is processed
    And the user opens Administration > Failures
    Then the user sees a failure report
    And the user can click on the report to see which job failed
    And the user can delete the failure report
