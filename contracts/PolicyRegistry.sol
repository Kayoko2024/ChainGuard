// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";
import {EIP712} from "@openzeppelin/contracts/utils/cryptography/EIP712.sol";
import {ECDSA} from "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import {IPolicyRegistry} from "./interfaces/IPolicyRegistry.sol";
import {ProtocolTypes as P} from "./interfaces/ProtocolTypes.sol";

/// @notice All expanding mutations require current consent from two organizations.
contract PolicyRegistry is AccessControl, EIP712, IPolicyRegistry {
    bytes32 public constant REQUESTER = keccak256("ChainGuard/role/REQUESTER");
    bytes32 public constant AGENT = keccak256("ChainGuard/role/AGENT");
    bytes32 public constant BUSINESS_APPROVER = keccak256("ChainGuard/role/BUSINESS_APPROVER");
    bytes32 public constant SECURITY_APPROVER = keccak256("ChainGuard/role/SECURITY_APPROVER");
    bytes32 public constant HUMAN_APPROVER = keccak256("ChainGuard/role/HUMAN_APPROVER");
    bytes32 public constant TOOL_SIGNER = keccak256("ChainGuard/role/TOOL_SIGNER");
    bytes32 public constant AUDITOR = keccak256("ChainGuard/role/AUDITOR");
    bytes32 public constant RECONCILER = keccak256("ChainGuard/role/RECONCILER");
    bytes32 public constant GOVERNANCE_ADMIN = keccak256("ChainGuard/role/GOVERNANCE_ADMIN");
    bytes32 public constant GOVERNANCE_TYPEHASH = keccak256("GovernanceChange(bytes32 changesHash,uint64 nonce,uint64 governanceEpoch,uint64 issuedAt,uint64 expiresAt)");

    // Payloads and exact hash encoding are specified in spec/phase5/governance.json.
    struct Change { uint8 kind; bytes data; }
    mapping(address => bytes32) public override orgOf;
    mapping(address => bool) public override isSignerRevoked;
    mapping(address => mapping(bytes32 => bool)) private scopes;
    mapping(address => mapping(address => bool)) private agents;
    mapping(bytes32 => mapping(address => bool)) private tools;
    mapping(bytes32 => P.EffectiveRule) private rules;
    mapping(uint64 => bool) public usedGovernanceNonce;
    uint64 public governanceEpoch = 1;
    bool public override paused;
    address[] private admins;
    mapping(address => bool) private knownAdmin;

    error GovernanceOnly();
    error InvalidGovernance();
    error InvalidChange();
    event GovernanceApplied(bytes32 indexed digest, uint64 indexed nonce, uint64 epoch, address[] signers);
    event ChangeApplied(uint8 indexed kind, bytes32 payloadHash);
    event EmergencyPaused(address indexed signer);
    event RuleChanged(bytes32 indexed policyId, uint64 epoch, bool enabled);

    constructor(address adminA, bytes32 orgA, address adminB, bytes32 orgB)
        EIP712("ChainGuard PolicyRegistry", "1")
    {
        if (adminA == address(0) || adminB == address(0) || adminA == adminB ||
            orgA == bytes32(0) || orgB == bytes32(0) || orgA == orgB) revert InvalidGovernance();
        orgOf[adminA] = orgA;
        orgOf[adminB] = orgB;
        _grantRole(GOVERNANCE_ADMIN, adminA);
        _grantRole(GOVERNANCE_ADMIN, adminB);
        _rememberAdmin(adminA);
        _rememberAdmin(adminB);
    }

    function hasRole(bytes32 role, address account) public view override(AccessControl, IPolicyRegistry) returns (bool) {
        return orgOf[account] != bytes32(0) && !isSignerRevoked[account] && super.hasRole(role, account);
    }
    function grantRole(bytes32, address) public pure override { revert GovernanceOnly(); }
    function revokeRole(bytes32, address) public pure override { revert GovernanceOnly(); }
    function renounceRole(bytes32, address) public pure override { revert GovernanceOnly(); }
    function hasScope(address account, bytes32 scope) public view returns (bool) {
        return orgOf[account] != bytes32(0) && !isSignerRevoked[account] && scopes[account][scope];
    }
    function isRequesterAuthorized(address account, bytes32 scope) external view override returns (bool) {
        return hasRole(REQUESTER, account) && hasScope(account, scope);
    }
    function isAgentAuthorized(address requester, address agent) external view override returns (bool) {
        return hasRole(REQUESTER, requester) && hasRole(AGENT, agent) && agents[requester][agent];
    }
    function isToolSigner(bytes32 toolId, address signer) external view override returns (bool) {
        return hasRole(TOOL_SIGNER, signer) && tools[toolId][signer];
    }
    function getEffectiveRule(bytes32 id) external view override returns (P.EffectiveRule memory) { return rules[id]; }

    function governanceDigest(Change[] calldata changes, uint64 nonce, uint64 epoch, uint64 issuedAt, uint64 expiresAt)
        public view returns (bytes32)
    {
        return _hashTypedDataV4(keccak256(abi.encode(GOVERNANCE_TYPEHASH, keccak256(abi.encode(changes)), nonce, epoch, issuedAt, expiresAt)));
    }

    function executeGovernance(Change[] calldata changes, uint64 nonce, uint64 epoch,
        uint64 issuedAt, uint64 expiresAt, bytes[] calldata signatures) external
    {
        if (changes.length == 0 || changes.length > 128 || epoch != governanceEpoch || usedGovernanceNonce[nonce] ||
            issuedAt > block.timestamp || expiresAt <= block.timestamp || expiresAt <= issuedAt ||
            expiresAt - issuedAt > 1 days || signatures.length < 2 || signatures.length > 16) revert InvalidGovernance();
        bytes32 digest = governanceDigest(changes, nonce, epoch, issuedAt, expiresAt);
        address[] memory signers = new address[](signatures.length);
        bytes32 firstOrg;
        bool independent;
        for (uint256 i; i < signatures.length; ++i) {
            address signer = ECDSA.recover(digest, signatures[i]);
            if (!hasRole(GOVERNANCE_ADMIN, signer)) revert InvalidGovernance();
            for (uint256 j; j < i; ++j) if (signers[j] == signer) revert InvalidGovernance();
            signers[i] = signer;
            if (i == 0) firstOrg = orgOf[signer];
            else if (orgOf[signer] != firstOrg) independent = true;
        }
        if (!independent) revert InvalidGovernance();
        usedGovernanceNonce[nonce] = true;
        ++governanceEpoch; // Invalidates other previously signed governance proposals.
        for (uint256 i; i < changes.length; ++i) {
            _apply(changes[i]);
            emit ChangeApplied(changes[i].kind, keccak256(changes[i].data));
        }
        _checkGovernanceSurvives();
        emit GovernanceApplied(digest, nonce, governanceEpoch, signers);
    }

    function emergencyPause() external onlyRole(GOVERNANCE_ADMIN) {
        paused = true;
        emit EmergencyPaused(msg.sender);
    }

    function _apply(Change calldata change) private {
        if (change.kind == 0) { // Current identity and global revocation.
            (address account, bytes32 org, bool active) = abi.decode(change.data, (address, bytes32, bool));
            if (account == address(0) || org == bytes32(0)) revert InvalidChange();
            orgOf[account] = org;
            isSignerRevoked[account] = !active;
        } else if (change.kind == 1) {
            (address account, bytes32 role, bool enabled) = abi.decode(change.data, (address, bytes32, bool));
            if (orgOf[account] == bytes32(0) || !_knownRole(role)) revert InvalidChange();
            if (enabled) _grantRole(role, account); else _revokeRole(role, account);
            if (role == GOVERNANCE_ADMIN) _rememberAdmin(account);
        } else if (change.kind == 2) {
            (address account, bytes32 scope, bool enabled) = abi.decode(change.data, (address, bytes32, bool));
            if (orgOf[account] == bytes32(0) || scope == bytes32(0)) revert InvalidChange();
            scopes[account][scope] = enabled;
        } else if (change.kind == 3) {
            (address requester, address agent, bool enabled) = abi.decode(change.data, (address, address, bool));
            if (orgOf[requester] == bytes32(0) || orgOf[agent] == bytes32(0)) revert InvalidChange();
            agents[requester][agent] = enabled;
        } else if (change.kind == 4) {
            (bytes32 toolId, address signer, bool enabled) = abi.decode(change.data, (bytes32, address, bool));
            if (toolId == bytes32(0) || orgOf[signer] == bytes32(0)) revert InvalidChange();
            tools[toolId][signer] = enabled;
        } else if (change.kind == 5) {
            (bytes32 id, bytes32 toolId, bytes32 scope, uint64 lifetime, uint8 risk, bool enabled) =
                abi.decode(change.data, (bytes32, bytes32, bytes32, uint64, uint8, bool));
            // Governance can tighten/revoke frozen MVP rules, never lower their risk.
            bool mail = id == keccak256("ChainGuard/policy/POLICY_R2_MAIL") &&
                toolId == keccak256("ChainGuard/tool/mail.send") && scope == keccak256("ChainGuard/scope/ORG_A_INTERNAL_MAIL") && risk == 2 && lifetime <= 120;
            bool deletion = id == keccak256("ChainGuard/policy/POLICY_R3_DELETE") &&
                toolId == keccak256("ChainGuard/tool/doc.delete") && scope == keccak256("ChainGuard/scope/ORG_A_DISPOSABLE_DOCS") && risk == 3 && lifetime <= 60;
            if ((!mail && !deletion) || lifetime == 0) revert InvalidChange();
            uint64 nextEpoch = rules[id].policyEpoch + 1;
            rules[id] = P.EffectiveRule(toolId, scope, nextEpoch, lifetime, risk, enabled);
            emit RuleChanged(id, nextEpoch, enabled);
        } else if (change.kind == 6) {
            if (change.data.length != 0) revert InvalidChange();
            paused = false;
        } else revert InvalidChange();
    }
    function _knownRole(bytes32 role) private pure returns (bool) {
        return role == REQUESTER || role == AGENT || role == BUSINESS_APPROVER || role == SECURITY_APPROVER ||
            role == HUMAN_APPROVER || role == TOOL_SIGNER || role == AUDITOR || role == RECONCILER || role == GOVERNANCE_ADMIN;
    }
    function _rememberAdmin(address account) private {
        if (!knownAdmin[account]) { knownAdmin[account] = true; admins.push(account); }
    }
    function _checkGovernanceSurvives() private view {
        bytes32 firstOrg;
        for (uint256 i; i < admins.length; ++i) if (hasRole(GOVERNANCE_ADMIN, admins[i])) {
            if (firstOrg == bytes32(0)) firstOrg = orgOf[admins[i]];
            else if (firstOrg != orgOf[admins[i]]) return;
        }
        revert InvalidGovernance();
    }
}
