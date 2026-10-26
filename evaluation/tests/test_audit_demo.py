import pytest
from evaluation.audit_demo import validator_read
from chainguard_sandbox.protocol import ToolError


def test_missing_real_validator_observation_is_failure_never_filled_in():
    for value in [None,False,'unavailable',{}]:
        with pytest.raises(ToolError,match='CHAIN_UNAVAILABLE'):
            validator_read('qbft_getValidatorsByBlockNumber',value)


def test_real_values_are_returned_byte_for_byte_without_synthetic_evidence():
    original=['0x'+'12'*20]
    assert validator_read('qbft_getValidatorsByBlockNumber',original) is original
    assert validator_read('eth_getTransactionReceipt',None) is None
