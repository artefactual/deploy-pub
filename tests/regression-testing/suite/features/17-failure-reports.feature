@shard-transfer
Feature: 17 - Failure Reports & Notifications

  @item-17.2
  Scenario: A failed transfer is reported by email
    Given the transfer is expected to fail
    When a "standard" transfer of "TestTransfers/virusTests" is processed
    Then the user receives an emailed version of the failure report
