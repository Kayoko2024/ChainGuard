// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;
import {ProtocolTypes as P} from "./ProtocolTypes.sol";

interface IPolicyRegistry {
    function orgOf(address signer) external view returns (bytes32);
    function hasRole(bytes32 role, address signer) external view returns (bool);
    function isSignerRevoked(address signer) external view returns (bool);
    function isRequesterAuthorized(address requester, bytes32 resourceScope) external view returns (bool);
    function isAgentAuthorized(address requester, address agent) external view returns (bool);
    function isToolSigner(bytes32 toolId, address signer) external view returns (bool);
    function getEffectiveRule(bytes32 policyId) external view returns (P.EffectiveRule memory);
    function paused() external view returns (bool);
    // TODO(POLICY_IMPL): scoped requester/tool registration and two-organization governance.
    // Governance mutation ABI requires its own reviewed signed proposal protocol in that stage.
}
