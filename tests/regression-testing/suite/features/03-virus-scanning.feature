@shard-transfer
Feature: 3 - Virus scanning

  @item-3.1
  Scenario: A transfer containing viruses fails at the virus scan
    Given the transfer is expected to fail
    When a "standard" transfer of "TestTransfers/virusTests" is processed
    Then the virus scan job fails
    And the standard streams report which files failed virus scanning
