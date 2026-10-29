// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {ECDSA} from "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import {EIP712} from "@openzeppelin/contracts/utils/cryptography/EIP712.sol";
import {IPolicyRegistry} from "./interfaces/IPolicyRegistry.sol";

/// @notice Independent LOW conversation domain. Never authorizes a HIGH action.
contract ConversationSessionRegistry is EIP712 {
    IPolicyRegistry public immutable policyRegistry;
    address public immutable publisher;
    bytes32 public constant GRANT_TYPEHASH = keccak256("ConversationGrant(address requester,address agent,bytes32 sessionId,bytes32 toolsHash,uint64 nonce,uint64 issuedAt,uint64 expiresAt,uint32 maxCalls)");
    struct Grant { address requester; address agent; bytes32 sessionId; bytes32 toolsHash; uint64 nonce; uint64 issuedAt; uint64 expiresAt; uint32 maxCalls; }
    struct Checkpoint { bytes32 root; uint32 count; uint64 blockNumber; bool closed; }
    mapping(bytes32 => mapping(uint64 => Checkpoint)) public checkpoints;
    mapping(bytes32 => uint64) public latest;
    error InvalidGrant();
    error InvalidCheckpoint();
    event SessionAnchored(bytes32 indexed sessionId, uint64 indexed index, bytes32 root, uint32 count, bytes32 previousRoot, bool closed);

    constructor(address policy, address account) EIP712("ChainGuard ConversationSessionRegistry", "1") {
        if (policy.code.length == 0 || account == address(0)) revert InvalidGrant();
        policyRegistry = IPolicyRegistry(policy); publisher = account;
    }
    function grantDigest(Grant calldata g) public view returns (bytes32) {
        return _hashTypedDataV4(keccak256(abi.encode(GRANT_TYPEHASH,g.requester,g.agent,g.sessionId,g.toolsHash,g.nonce,g.issuedAt,g.expiresAt,g.maxCalls)));
    }
    function validateGrant(Grant calldata g, bytes calldata signature) external view returns (address) {
        if (policyRegistry.paused() || g.sessionId == bytes32(0) || g.toolsHash == bytes32(0) ||
            g.issuedAt > block.timestamp || g.expiresAt <= block.timestamp || g.expiresAt <= g.issuedAt || g.expiresAt-g.issuedAt > 1 days ||
            g.maxCalls == 0 || g.maxCalls > 10000 || ECDSA.recover(grantDigest(g),signature) != g.requester ||
            !policyRegistry.hasRole(keccak256("ChainGuard/role/REQUESTER"),g.requester) || policyRegistry.isSignerRevoked(g.requester) ||
            !policyRegistry.isAgentAuthorized(g.requester,g.agent)) revert InvalidGrant();
        return g.requester;
    }
    function anchor(bytes32 sessionId,uint64 index,bytes32 root,uint32 count,bytes32 previousRoot,bool closed) external {
        if (msg.sender != publisher || sessionId == bytes32(0) || index == 0 || root == bytes32(0) || count == 0 || count > 100000) revert InvalidCheckpoint();
        Checkpoint memory old = checkpoints[sessionId][index];
        if (old.root != bytes32(0)) {
            if (old.root != root || old.count != count || old.closed != closed) revert InvalidCheckpoint();
            return;
        }
        uint64 last = latest[sessionId]; Checkpoint memory prior = checkpoints[sessionId][last];
        if (index != last+1 || prior.closed || previousRoot != prior.root || count < prior.count || (count == prior.count && !closed)) revert InvalidCheckpoint();
        checkpoints[sessionId][index] = Checkpoint(root,count,uint64(block.number),closed); latest[sessionId] = index;
        emit SessionAnchored(sessionId,index,root,count,previousRoot,closed);
    }
}
