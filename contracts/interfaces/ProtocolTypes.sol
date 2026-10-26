// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

/// @notice Phase 0 wire types only. No authorization or execution implementation.
library ProtocolTypes {
    enum Risk { R0, R1, R2, R3 }
    enum Outcome { OK, ERROR, REJECTED, UNKNOWN }
    enum ReservationStatus { NONE, RESERVED, UNKNOWN, FINALIZED_OK, FINALIZED_ERROR, FINALIZED_REJECTED }

    struct ActionIntent {
        uint16 schemaVersion;
        bytes32 actionId;
        bytes32 taskId;
        address requester;
        address agent;
        bytes32 toolId;
        bytes32 resourceScope;
        bytes32 paramsCommit;
        bytes32 policyId;
        uint64 policyEpoch;
        uint64 nonce;
        uint64 issuedAt;
        uint64 expiresAt;
        uint8 risk;
    }

    struct ExecutionReceipt {
        uint16 schemaVersion;
        bytes32 actionId;
        bytes32 paramsCommit;
        bytes32 resultCommit;
        bytes32 evidenceIndexCommit;
        uint64 executedAt;
        uint8 outcome;
    }

    // The recovered address is authoritative; do not trust an off-chain claimed signer/organization.
    struct Approval { bytes signature; }
    struct Reservation {
        ActionIntent intent;
        bytes32 intentHash;
        ReservationStatus status;
        uint64 reservedAt;
        address[] approvers;
    }
    struct EffectiveRule {
        bytes32 toolId;
        bytes32 resourceScope;
        uint64 policyEpoch;
        uint64 maxLifetime;
        uint8 risk;
        bool enabled;
    }
}
