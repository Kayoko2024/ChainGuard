// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {EIP712} from "@openzeppelin/contracts/utils/cryptography/EIP712.sol";
import {ECDSA} from "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import {PolicyRegistry} from "./PolicyRegistry.sol";
import {ProtocolTypes as P} from "./interfaces/ProtocolTypes.sol";

/// @notice Explicit, two-organization opt-in to a 24h R2 mail window.
/// Identity, revocation, pause and every other rule remain on the original policy.
contract MailApprovalWindowPolicy is EIP712 {
    PolicyRegistry public immutable sourcePolicy;
    uint64 public constant mailLifetime = 1 days;
    bytes32 public constant WINDOW_TYPEHASH = keccak256("MailApprovalWindow(address sourcePolicy,uint64 mailLifetime,uint64 nonce,uint64 issuedAt,uint64 expiresAt)");
    error InvalidWindowApproval();

    constructor(PolicyRegistry source, uint64 nonce, uint64 issuedAt, uint64 expiresAt, bytes[] memory signatures)
        EIP712("ChainGuard MailApprovalWindowPolicy", "1")
    {
        if (address(source).code.length == 0 || signatures.length != 2 ||
            issuedAt > block.timestamp || expiresAt <= block.timestamp || expiresAt <= issuedAt ||
            expiresAt - issuedAt > 1 days) revert InvalidWindowApproval();
        sourcePolicy = source;
        bytes32 digest = _hashTypedDataV4(keccak256(abi.encode(WINDOW_TYPEHASH, address(source), mailLifetime, nonce, issuedAt, expiresAt)));
        address first = ECDSA.recover(digest, signatures[0]);
        address second = ECDSA.recover(digest, signatures[1]);
        if (first == second || !source.hasRole(source.GOVERNANCE_ADMIN(), first) ||
            !source.hasRole(source.GOVERNANCE_ADMIN(), second) || source.orgOf(first) == source.orgOf(second)) revert InvalidWindowApproval();
    }

    function getEffectiveRule(bytes32 id) external view returns (P.EffectiveRule memory rule) {
        rule = sourcePolicy.getEffectiveRule(id);
        // A later governance tightening (<120), revocation or pause is never bypassed.
        if (id == keccak256("ChainGuard/policy/POLICY_R2_MAIL") && rule.risk == 2 &&
            rule.toolId == keccak256("ChainGuard/tool/mail.send") &&
            rule.resourceScope == keccak256("ChainGuard/scope/ORG_A_INTERNAL_MAIL") && rule.maxLifetime == 120) {
            rule.maxLifetime = mailLifetime;
        }
    }

    // STATICCALL delegates original getters, including role constants and current
    // authorization. Mutation selectors cannot write through this read-only facade.
    fallback(bytes calldata input) external returns (bytes memory) {
        (bool ok, bytes memory output) = address(sourcePolicy).staticcall(input);
        if (!ok) assembly { revert(add(output, 32), mload(output)) }
        return output;
    }
}
