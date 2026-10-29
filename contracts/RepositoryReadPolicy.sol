// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {ECDSA} from "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import {EIP712} from "@openzeppelin/contracts/utils/cryptography/EIP712.sol";
import {IPolicyRegistry} from "./interfaces/IPolicyRegistry.sol";

/// @notice Additive R0 GitHub repository admission. Does not authorize R2/R3 actions.
contract RepositoryReadPolicy is EIP712 {
    IPolicyRegistry public immutable policyRegistry;
    bytes32 public constant GOVERNANCE_ADMIN = keccak256("ChainGuard/role/GOVERNANCE_ADMIN");
    bytes32 public constant CHANGE_TYPEHASH = keccak256(
        "RepositoryRuleChange(bytes32 repositoryHash,bool enabled,uint64 nonce,uint64 epoch,uint64 issuedAt,uint64 expiresAt)"
    );
    mapping(bytes32 => bool) public repositoryAllowed;
    mapping(uint64 => bool) public usedNonce;
    uint64 public epoch = 1;
    error InvalidGovernance();
    error RepositoryDenied(bytes32 repositoryHash);
    event RepositoryRuleChanged(bytes32 indexed repositoryHash, bool enabled, uint64 epoch,
        uint64 nonce, address signerA, address signerB);

    constructor(address registry) EIP712("ChainGuard RepositoryReadPolicy", "1") {
        if (registry.code.length == 0) revert InvalidGovernance();
        policyRegistry = IPolicyRegistry(registry);
    }

    function ruleDigest(bytes32 repositoryHash, bool enabled, uint64 nonce, uint64 ruleEpoch,
        uint64 issuedAt, uint64 expiresAt) public view returns (bytes32) {
        return _hashTypedDataV4(keccak256(abi.encode(CHANGE_TYPEHASH, repositoryHash, enabled,
            nonce, ruleEpoch, issuedAt, expiresAt)));
    }

    function setRepository(bytes32 repositoryHash, bool enabled, uint64 nonce, uint64 ruleEpoch,
        uint64 issuedAt, uint64 expiresAt, bytes calldata signatureA, bytes calldata signatureB) external {
        if (policyRegistry.paused() || repositoryHash == bytes32(0) || usedNonce[nonce] || ruleEpoch != epoch ||
            issuedAt > block.timestamp || expiresAt <= block.timestamp || expiresAt <= issuedAt ||
            expiresAt - issuedAt > 1 days) revert InvalidGovernance();
        bytes32 digest = ruleDigest(repositoryHash, enabled, nonce, ruleEpoch, issuedAt, expiresAt);
        address a = ECDSA.recover(digest, signatureA);
        address b = ECDSA.recover(digest, signatureB);
        if (a == b || !policyRegistry.hasRole(GOVERNANCE_ADMIN, a) ||
            !policyRegistry.hasRole(GOVERNANCE_ADMIN, b) || policyRegistry.orgOf(a) == bytes32(0) ||
            policyRegistry.orgOf(b) == bytes32(0) || policyRegistry.orgOf(a) == policyRegistry.orgOf(b))
            revert InvalidGovernance();
        usedNonce[nonce] = true;
        ++epoch;
        repositoryAllowed[repositoryHash] = enabled;
        emit RepositoryRuleChanged(repositoryHash, enabled, epoch, nonce, a, b);
    }

    function requireRepository(bytes32 repositoryHash) external view returns (uint64) {
        if (policyRegistry.paused() || !repositoryAllowed[repositoryHash]) revert RepositoryDenied(repositoryHash);
        return epoch;
    }
}
