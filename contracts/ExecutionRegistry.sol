// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {EIP712} from "@openzeppelin/contracts/utils/cryptography/EIP712.sol";
import {ECDSA} from "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import {PolicyRegistry} from "./PolicyRegistry.sol";
import {IExecutionRegistry} from "./interfaces/IExecutionRegistry.sol";
import {ProtocolTypes as P} from "./interfaces/ProtocolTypes.sol";

contract ExecutionRegistry is EIP712, IExecutionRegistry {
    bytes32 public constant ACTION_TYPEHASH = keccak256("ActionIntent(uint16 schemaVersion,bytes32 actionId,bytes32 taskId,address requester,address agent,bytes32 toolId,bytes32 resourceScope,bytes32 paramsCommit,bytes32 policyId,uint64 policyEpoch,uint64 nonce,uint64 issuedAt,uint64 expiresAt,uint8 risk)");
    PolicyRegistry public immutable policyRegistry;
    address public immutable auditRegistry;
    mapping(bytes32 => P.Reservation) private reservations;
    mapping(address => mapping(uint64 => bool)) public override usedNonce;

    error InvalidIntent();
    error InvalidAuthorization();
    error InvalidApproval();
    error AlreadyReserved();
    error InvalidState();
    error AuditOnly();

    constructor(PolicyRegistry policy, address audit) EIP712("ChainGuard ExecutionRegistry", "1") {
        if (address(policy).code.length == 0 || audit == address(0)) revert InvalidAuthorization();
        policyRegistry = policy;
        auditRegistry = audit; // Predicted CREATE address, immutable: no unilateral setter.
    }
    function intentDigest(P.ActionIntent calldata intent) public view returns (bytes32) {
        return _hashTypedDataV4(keccak256(abi.encode(ACTION_TYPEHASH, intent)));
    }
    function reserve(P.ActionIntent calldata intent, bytes calldata requesterSignature, P.Approval[] calldata approvals)
        external override returns (bytes32)
    {
        if (reservations[intent.actionId].status != P.ReservationStatus.NONE || usedNonce[intent.requester][intent.nonce]) revert AlreadyReserved();
        _validateIntent(intent);
        bytes32 digest = intentDigest(intent);
        if (ECDSA.recover(digest, requesterSignature) != intent.requester) revert InvalidAuthorization();
        address[] memory recovered = _validateApprovals(intent, digest, approvals);
        usedNonce[intent.requester][intent.nonce] = true;
        P.Reservation storage reservation = reservations[intent.actionId];
        reservation.intent = intent;
        reservation.intentHash = digest;
        reservation.status = P.ReservationStatus.RESERVED;
        reservation.reservedAt = uint64(block.timestamp);
        reservation.approvers = recovered;
        emit ActionReserved(intent.actionId, intent.taskId, intent.toolId, intent.paramsCommit, intent.policyEpoch);
        return intent.actionId;
    }
    function _validateIntent(P.ActionIntent calldata intent) private view {
        if (intent.schemaVersion != 1 || intent.actionId == bytes32(0) || intent.taskId == bytes32(0) ||
            intent.paramsCommit == bytes32(0) || intent.requester == address(0) || intent.agent == address(0) ||
            intent.issuedAt > block.timestamp || intent.expiresAt <= block.timestamp ||
            intent.expiresAt <= intent.issuedAt || (intent.risk != 2 && intent.risk != 3)) revert InvalidIntent();
        P.EffectiveRule memory rule = policyRegistry.getEffectiveRule(intent.policyId);
        if (policyRegistry.paused() || !rule.enabled || rule.policyEpoch != intent.policyEpoch ||
            rule.toolId != intent.toolId || rule.resourceScope != intent.resourceScope || rule.risk != intent.risk ||
            intent.expiresAt - intent.issuedAt > rule.maxLifetime ||
            !policyRegistry.isRequesterAuthorized(intent.requester, intent.resourceScope) ||
            !policyRegistry.isAgentAuthorized(intent.requester, intent.agent)) revert InvalidAuthorization();
    }
    function _validateApprovals(P.ActionIntent calldata intent, bytes32 digest, P.Approval[] calldata approvals)
        private view returns (address[] memory actors)
    {
        if (approvals.length < (intent.risk == 3 ? 3 : 2) || approvals.length > 16) revert InvalidApproval();
        actors = new address[](approvals.length);
        bool[] memory business = new bool[](approvals.length);
        bool[] memory security = new bool[](approvals.length);
        bool[] memory human = new bool[](approvals.length);
        bytes32[] memory orgs = new bytes32[](approvals.length);
        for (uint256 i; i < approvals.length; ++i) {
            address actor = ECDSA.recover(digest, approvals[i].signature);
            if (actor == intent.requester || actor == intent.agent ||
                policyRegistry.hasRole(policyRegistry.TOOL_SIGNER(), actor) || !policyRegistry.hasScope(actor, intent.resourceScope)) revert InvalidApproval();
            for (uint256 j; j < i; ++j) if (actors[j] == actor) revert InvalidApproval();
            actors[i] = actor;
            orgs[i] = policyRegistry.orgOf(actor);
            business[i] = policyRegistry.hasRole(policyRegistry.BUSINESS_APPROVER(), actor);
            security[i] = policyRegistry.hasRole(policyRegistry.SECURITY_APPROVER(), actor);
            human[i] = intent.risk == 3 && policyRegistry.hasRole(policyRegistry.HUMAN_APPROVER(), actor);
            if (!business[i] && !security[i] && !human[i]) revert InvalidApproval();
        }
        // Role assignment, not greedy counting: multi-role accounts occupy one seat.
        for (uint256 b; b < actors.length; ++b) if (business[b]) {
            for (uint256 s; s < actors.length; ++s) if (security[s] && b != s && orgs[b] != orgs[s]) {
                if (intent.risk == 2) return actors;
                for (uint256 h; h < actors.length; ++h) if (human[h] && h != b && h != s) return actors;
            }
        }
        revert InvalidApproval();
    }
    function getReservation(bytes32 id) external view override returns (P.Reservation memory) { return reservations[id]; }
    function recordAuditOutcome(bytes32 id, P.Outcome outcome) external override {
        if (msg.sender != auditRegistry) revert AuditOnly();
        P.Reservation storage reservation = reservations[id];
        P.ReservationStatus old = reservation.status;
        if (old != P.ReservationStatus.RESERVED && old != P.ReservationStatus.UNKNOWN) revert InvalidState();
        if (outcome == P.Outcome.UNKNOWN) {
            if (old != P.ReservationStatus.RESERVED) revert InvalidState();
            reservation.status = P.ReservationStatus.UNKNOWN;
        } else if (outcome == P.Outcome.OK) reservation.status = P.ReservationStatus.FINALIZED_OK;
        else if (outcome == P.Outcome.ERROR) reservation.status = P.ReservationStatus.FINALIZED_ERROR;
        else reservation.status = P.ReservationStatus.FINALIZED_REJECTED;
    }
}
