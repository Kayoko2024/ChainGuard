// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;
import {ProtocolTypes as P} from "../interfaces/ProtocolTypes.sol";
import {ECDSA} from "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import {MessageHashUtils} from "@openzeppelin/contracts/utils/cryptography/MessageHashUtils.sol";

/// @notice TEST ONLY: pure EIP-712 encoding/recovery; this grants no permission and stores no state.
contract ProtocolHashHarness {
    bytes32 public constant DOMAIN_TYPEHASH = keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)");
    bytes32 public constant ACTION_TYPEHASH = keccak256("ActionIntent(uint16 schemaVersion,bytes32 actionId,bytes32 taskId,address requester,address agent,bytes32 toolId,bytes32 resourceScope,bytes32 paramsCommit,bytes32 policyId,uint64 policyEpoch,uint64 nonce,uint64 issuedAt,uint64 expiresAt,uint8 risk)");
    bytes32 public constant RECEIPT_TYPEHASH = keccak256("ExecutionReceipt(uint16 schemaVersion,bytes32 actionId,bytes32 paramsCommit,bytes32 resultCommit,bytes32 evidenceIndexCommit,uint64 executedAt,uint8 outcome)");

    function domainHash(string calldata name, string calldata version, uint256 chainId, address verifyingContract) external pure returns (bytes32) {
        return keccak256(abi.encode(DOMAIN_TYPEHASH, keccak256(bytes(name)), keccak256(bytes(version)), chainId, verifyingContract));
    }
    function actionHash(P.ActionIntent calldata intent) external pure returns (bytes32) {
        return keccak256(abi.encode(ACTION_TYPEHASH, intent));
    }
    function receiptHash(P.ExecutionReceipt calldata receipt) external pure returns (bytes32) {
        return keccak256(abi.encode(RECEIPT_TYPEHASH, receipt));
    }
    function digest(bytes32 domainSeparator, bytes32 structHash) external pure returns (bytes32) {
        return MessageHashUtils.toTypedDataHash(domainSeparator, structHash);
    }
    function recover(bytes32 typedDigest, bytes calldata signature) external pure returns (address) {
        return ECDSA.recover(typedDigest, signature);
    }
    function commitment(bytes calldata prefix, bytes32 salt, bytes calldata canonicalJson) external pure returns (bytes32) {
        return keccak256(abi.encodePacked(prefix, bytes1(0), salt, canonicalJson));
    }
}
