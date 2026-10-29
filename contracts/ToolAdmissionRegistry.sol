// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {ECDSA} from "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import {EIP712} from "@openzeppelin/contracts/utils/cryptography/EIP712.sol";
import {IPolicyRegistry} from "./interfaces/IPolicyRegistry.sol";

/// @notice Additive tool admission and session domain; does not replace R2/R3 authorization.
contract ToolAdmissionRegistry is EIP712 {
    IPolicyRegistry public immutable policyRegistry;
    bytes32 public immutable reviewerOrganization;
    bytes32 public constant SECURITY = keccak256("ChainGuard/role/SECURITY_APPROVER");
    bytes32 public constant ADMIN = keccak256("ChainGuard/role/GOVERNANCE_ADMIN");
    bytes32 public constant REQUESTER = keccak256("ChainGuard/role/REQUESTER");
    bytes32 public constant REVIEW_TYPEHASH = keccak256("ToolReview(bytes32 revision,uint8 riskLevel,bool enabled,uint64 nonce,uint64 epoch,uint64 issuedAt,uint64 expiresAt)");
    bytes32 public constant SESSION_TYPEHASH = keccak256("SessionGrant(address requester,address agent,bytes32 taskId,bytes32 toolsHash,uint64 nonce,uint64 issuedAt,uint64 expiresAt,uint32 maxCalls)");
    struct Admission { uint8 riskLevel; bool enabled; uint64 generation; address reviewer; }
    struct SessionGrant { address requester; address agent; bytes32 taskId; bytes32 toolsHash; uint64 nonce; uint64 issuedAt; uint64 expiresAt; uint32 maxCalls; }
    mapping(bytes32 => Admission) public tools;
    mapping(address => mapping(uint64 => bool)) public usedReviewNonce;
    uint64 public epoch = 1;
    error InvalidAdmission();
    error InvalidSession();
    event ToolReviewed(bytes32 indexed revision, uint8 riskLevel, bool enabled, uint64 generation, address reviewer);

    constructor(address registry, bytes32 organization) EIP712("ChainGuard ToolAdmissionRegistry", "1") {
        if (registry.code.length == 0 || organization == bytes32(0)) revert InvalidAdmission();
        policyRegistry = IPolicyRegistry(registry);
        reviewerOrganization = organization;
    }

    function reviewDigest(bytes32 revision, uint8 riskLevel, bool enabled, uint64 nonce, uint64 ruleEpoch, uint64 issuedAt, uint64 expiresAt) public view returns (bytes32) {
        return _hashTypedDataV4(keccak256(abi.encode(REVIEW_TYPEHASH, revision, riskLevel, enabled, nonce, ruleEpoch, issuedAt, expiresAt)));
    }

    function review(bytes32 revision, uint8 riskLevel, bool enabled, uint64 nonce, uint64 ruleEpoch, uint64 issuedAt, uint64 expiresAt, bytes calldata signature) external {
        if (policyRegistry.paused() || revision == bytes32(0) || (riskLevel != 1 && riskLevel != 2) || ruleEpoch != epoch || issuedAt > block.timestamp || expiresAt <= block.timestamp || expiresAt <= issuedAt || expiresAt - issuedAt > 1 days) revert InvalidAdmission();
        address signer = ECDSA.recover(reviewDigest(revision, riskLevel, enabled, nonce, ruleEpoch, issuedAt, expiresAt), signature);
        if (policyRegistry.orgOf(signer) != reviewerOrganization || policyRegistry.isSignerRevoked(signer) || (!policyRegistry.hasRole(SECURITY, signer) && !policyRegistry.hasRole(ADMIN, signer)) || usedReviewNonce[signer][nonce]) revert InvalidAdmission();
        usedReviewNonce[signer][nonce] = true;
        uint64 generation = tools[revision].generation + 1;
        tools[revision] = Admission(riskLevel, enabled, generation, signer);
        ++epoch;
        emit ToolReviewed(revision, riskLevel, enabled, generation, signer);
    }

    function sessionDigest(SessionGrant calldata grant) public view returns (bytes32) {
        return _hashTypedDataV4(keccak256(abi.encode(SESSION_TYPEHASH, grant.requester, grant.agent, grant.taskId, grant.toolsHash, grant.nonce, grant.issuedAt, grant.expiresAt, grant.maxCalls)));
    }

    /// @dev Validation is read-only. Enrollment nonce and atomic call quota live in each trusted gate's durable DB.
    function validateSession(SessionGrant calldata grant, bytes calldata signature) external view returns (address) {
        if (policyRegistry.paused() || grant.taskId == bytes32(0) || grant.toolsHash == bytes32(0) || grant.issuedAt > block.timestamp || grant.expiresAt <= block.timestamp || grant.expiresAt <= grant.issuedAt || grant.expiresAt - grant.issuedAt > 1 days || grant.maxCalls == 0 || grant.maxCalls > 10000 || ECDSA.recover(sessionDigest(grant), signature) != grant.requester || !policyRegistry.hasRole(REQUESTER, grant.requester) || policyRegistry.isSignerRevoked(grant.requester) || !policyRegistry.isAgentAuthorized(grant.requester, grant.agent)) revert InvalidSession();
        return grant.requester;
    }
}
