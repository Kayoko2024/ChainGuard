// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {EIP712} from "@openzeppelin/contracts/utils/cryptography/EIP712.sol";
import {ECDSA} from "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import {ExecutionRegistry} from "./ExecutionRegistry.sol";
import {PolicyRegistry} from "./PolicyRegistry.sol";
import {IAuditRegistry} from "./interfaces/IAuditRegistry.sol";
import {ProtocolTypes as P} from "./interfaces/ProtocolTypes.sol";

contract AuditRegistry is EIP712, IAuditRegistry {
    bytes32 public constant RECEIPT_TYPEHASH = keccak256("ExecutionReceipt(uint16 schemaVersion,bytes32 actionId,bytes32 paramsCommit,bytes32 resultCommit,bytes32 evidenceIndexCommit,uint64 executedAt,uint8 outcome)");
    ExecutionRegistry public immutable executionRegistry;
    PolicyRegistry public immutable policyRegistry;
    uint64 public immutable maxFutureSkew;
    mapping(bytes32 => bytes32) public receiptHash;
    mapping(bytes32 => address) public receiptSigner;
    mapping(bytes32 => bytes32) public unknownReason;
    error InvalidReceipt();
    error InvalidState();
    error InvalidToolSigner();
    error Unauthorized();

    constructor(PolicyRegistry policy, ExecutionRegistry execution, uint64 futureSkew)
        EIP712("ChainGuard AuditRegistry", "1")
    {
        if (execution.auditRegistry() != address(this) || address(execution.policyRegistry()) != address(policy) || futureSkew > 30) revert Unauthorized();
        executionRegistry = execution;
        policyRegistry = policy;
        maxFutureSkew = futureSkew; // Explicit deployment setting; no execution expiry grace.
    }
    function receiptDigest(P.ExecutionReceipt calldata receipt) public view returns (bytes32) {
        return _hashTypedDataV4(keccak256(abi.encode(RECEIPT_TYPEHASH, receipt)));
    }
    function finalize(P.ExecutionReceipt calldata receipt, bytes calldata signature) external override {
        _record(receipt, signature, false);
    }
    function reconcile(P.ExecutionReceipt calldata receipt, bytes calldata signature) external override {
        _record(receipt, signature, true);
    }
    function _record(P.ExecutionReceipt calldata receipt, bytes calldata signature, bool reconciliation) private {
        P.Reservation memory reservation = executionRegistry.getReservation(receipt.actionId);
        if (receipt.schemaVersion != 1 || receipt.actionId == bytes32(0) || receipt.paramsCommit != reservation.intent.paramsCommit ||
            receipt.resultCommit == bytes32(0) || receipt.evidenceIndexCommit == bytes32(0) || receipt.outcome > 2 ||
            receipt.executedAt < reservation.intent.issuedAt || receipt.executedAt > block.timestamp + maxFutureSkew) revert InvalidReceipt();
        bytes32 digest = receiptDigest(receipt);
        address signer = ECDSA.recover(digest, signature);
        if (!policyRegistry.isToolSigner(reservation.intent.toolId, signer)) revert InvalidToolSigner();
        if (receiptHash[receipt.actionId] != bytes32(0)) {
            if (receiptHash[receipt.actionId] != digest || receiptSigner[receipt.actionId] != signer) revert InvalidReceipt();
            return; // Identical confirmed receipt, no extra state transition or duplicate event.
        }
        if (reservation.status != (reconciliation ? P.ReservationStatus.UNKNOWN : P.ReservationStatus.RESERVED)) revert InvalidState();
        receiptHash[receipt.actionId] = digest;
        receiptSigner[receipt.actionId] = signer;
        executionRegistry.recordAuditOutcome(receipt.actionId, P.Outcome(receipt.outcome));
        if (reconciliation) {
            uint8 next = uint8((executionRegistry.getReservation(receipt.actionId)).status);
            emit ActionReconciled(receipt.actionId, uint8(reservation.status), next, receipt.evidenceIndexCommit);
        }
        emit ActionFinalized(receipt.actionId, receipt.resultCommit, signer, receipt.outcome);
    }
    function markUnknown(bytes32 id, bytes32 reason) external override {
        if (!policyRegistry.hasRole(policyRegistry.RECONCILER(), msg.sender)) revert Unauthorized();
        if (reason == bytes32(0) || (executionRegistry.getReservation(id)).status != P.ReservationStatus.RESERVED) revert InvalidState();
        unknownReason[id] = reason;
        executionRegistry.recordAuditOutcome(id, P.Outcome.UNKNOWN);
        emit ActionUnknown(id, reason);
    }
}
