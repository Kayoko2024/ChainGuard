// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;
import {ProtocolTypes as P} from "./ProtocolTypes.sol";

interface IAuditRegistry {
    event ActionFinalized(bytes32 indexed actionId, bytes32 resultCommit, address indexed toolSigner, uint8 outcome);
    event ActionReconciled(bytes32 indexed actionId, uint8 oldState, uint8 newState, bytes32 proofCommit);
    event ActionUnknown(bytes32 indexed actionId, bytes32 reasonCommit);
    function finalize(P.ExecutionReceipt calldata receipt, bytes calldata toolSignature) external;
    function reconcile(P.ExecutionReceipt calldata receipt, bytes calldata toolSignature) external;
    /// @dev RECONCILER only; UNKNOWN is not execution permission or proof of failure.
    function markUnknown(bytes32 actionId, bytes32 reasonCommit) external;
}
