// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

/// @notice Immutable publisher and append-only roots. A root proves inclusion, not tool honesty or execution authorization.
contract LowRiskAuditAnchor {
    address public immutable publisher;
    struct Batch { bytes32 root; uint32 count; uint64 firstSequence; uint64 lastSequence; }
    mapping(bytes32 => Batch) public batches;
    error InvalidBatch();
    event BatchAnchored(bytes32 indexed batchId, bytes32 root, uint32 count, uint64 firstSequence, uint64 lastSequence);
    constructor(address account) { if (account == address(0)) revert InvalidBatch(); publisher = account; }
    function anchor(bytes32 batchId, bytes32 root, uint32 count, uint64 firstSequence, uint64 lastSequence) external {
        if (msg.sender != publisher || batchId == bytes32(0) || root == bytes32(0) || count == 0 || count > 50 || lastSequence < firstSequence || lastSequence - firstSequence + 1 != count) revert InvalidBatch();
        Batch memory old = batches[batchId];
        if (old.root != bytes32(0)) {
            if (old.root != root || old.count != count || old.firstSequence != firstSequence || old.lastSequence != lastSequence) revert InvalidBatch();
            return;
        }
        batches[batchId] = Batch(root, count, firstSequence, lastSequence);
        emit BatchAnchored(batchId, root, count, firstSequence, lastSequence);
    }
}
