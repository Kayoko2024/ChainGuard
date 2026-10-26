// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;
import {ProtocolTypes as P} from "./ProtocolTypes.sol";

interface IExecutionRegistry {
    event ActionReserved(bytes32 indexed actionId, bytes32 indexed taskId, bytes32 toolId, bytes32 paramsCommit, uint64 policyEpoch);
    function reserve(P.ActionIntent calldata intent, bytes calldata requesterSignature, P.Approval[] calldata approvals) external returns (bytes32 actionId);
    function getReservation(bytes32 actionId) external view returns (P.Reservation memory);
    function usedNonce(address requester, uint64 nonce) external view returns (bool);
    /// @dev Future implementation MUST restrict this to the configured AuditRegistry.
    function recordAuditOutcome(bytes32 actionId, P.Outcome outcome) external;
}
