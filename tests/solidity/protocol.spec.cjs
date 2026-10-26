const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const canonicalize = require('canonicalize');
const { ethers, artifacts } = require('hardhat');
const root = path.resolve(__dirname, '../..');
const vector = JSON.parse(fs.readFileSync(path.join(root, 'spec/vectors/eip712-v1.json'), 'utf8'));
const protocol = JSON.parse(fs.readFileSync(path.join(root, 'spec/eip712.json'), 'utf8'));
const N = 0xfffffffffffffffffffffffffffffffebaaedce6af48a03bbfd25e8cd0364141n;

describe('Phase 0 shared protocol (local Hardhat EVM, no business implementation)', function () {
  let harness;
  before(async function () {
    harness = await (await ethers.getContractFactory('ProtocolHashHarness')).deploy();
    await harness.waitForDeployment();
  });

  it('JCS and salted commitments agree across Python fixture, JS and Solidity', async function () {
    for (const [kind, entry] of Object.entries(vector.commitments)) {
      const canonical = canonicalize(entry.value);
      assert.equal(canonical, entry.canonical_utf8);
      assert.equal(ethers.hexlify(ethers.toUtf8Bytes(canonical)), entry.canonical_utf8_hex);
      const prefix = ethers.toUtf8Bytes(`ChainGuard/${kind}/v1`);
      const preimage = ethers.concat([prefix, '0x00', entry.salt, ethers.toUtf8Bytes(canonical)]);
      assert.equal(preimage, entry.preimage_hex);
      assert.equal(ethers.keccak256(preimage), entry.commitment);
      assert.equal(await harness.commitment(prefix, entry.salt, ethers.toUtf8Bytes(canonical)), entry.commitment);
    }
    assert.equal(ethers.hexlify(ethers.toUtf8Bytes(canonicalize(vector.jcs_edge_case.input))), vector.jcs_edge_case.canonical_utf8_hex);
  });

  for (const kind of ['ActionIntent', 'ExecutionReceipt']) {
    describe(kind, function () {
      const entry = vector.vectors[kind];
      const typed = entry.typed_data;
      const types = { [kind]: protocol.types[kind] };
      const isAction = kind === 'ActionIntent';
      const hashMethod = isAction ? 'actionHash' : 'receiptHash';

      it('Solidity tuple ABI matches the normative field names, order and widths', async function () {
        const artifact = await artifacts.readArtifact('ProtocolHashHarness');
        const components = artifact.abi.find(item => item.name === hashMethod).inputs[0].components;
        assert.deepEqual(components.map(({name, type}) => ({name, type})), protocol.types[kind]);
      });

      it('type hash, domain separator, struct hash and digest match ethers and Solidity', async function () {
        const encoder = ethers.TypedDataEncoder.from(types);
        assert.equal(encoder.encodeType(kind), entry.expected.type_string);
        assert.equal(ethers.id(encoder.encodeType(kind)), entry.expected.type_hash);
        assert.equal(await harness[isAction ? 'ACTION_TYPEHASH' : 'RECEIPT_TYPEHASH'](), entry.expected.type_hash);
        assert.equal(ethers.TypedDataEncoder.hashDomain(typed.domain), entry.expected.domain_separator);
        assert.equal(await harness.domainHash(typed.domain.name, typed.domain.version, typed.domain.chainId, typed.domain.verifyingContract), entry.expected.domain_separator);
        assert.equal(encoder.hash(typed.message), entry.expected.struct_hash);
        assert.equal(await harness[hashMethod](typed.message), entry.expected.struct_hash);
        assert.equal(ethers.TypedDataEncoder.hash(typed.domain, types, typed.message), entry.expected.digest);
        assert.equal(await harness.digest(entry.expected.domain_separator, entry.expected.struct_hash), entry.expected.digest);
      });

      for (const signature of entry.signatures) {
        it(`recovers the public ${signature.fixture_role} signer in ethers and OpenZeppelin`, async function () {
          assert.equal(ethers.verifyTypedData(typed.domain, types, typed.message, signature.signature).toLowerCase(), signature.signer);
          assert.equal((await harness.recover(entry.expected.digest, signature.signature)).toLowerCase(), signature.signer);
        });
      }

      for (const field of protocol.types[kind]) {
        it(`changing ${field.name} invalidates all original signatures`, async function () {
          const message = structuredClone(typed.message);
          if (field.type.startsWith('uint')) message[field.name] = (BigInt(message[field.name]) + 1n).toString();
          else if (field.type === 'address') message[field.name] = '0x3333333333333333333333333333333333333333';
          else {
            const bytes = ethers.getBytes(message[field.name]);
            bytes[0] ^= 1;
            message[field.name] = ethers.hexlify(bytes);
          }
          const structHash = await harness[hashMethod](message);
          const digest = await harness.digest(entry.expected.domain_separator, structHash);
          assert.notEqual(digest, entry.expected.digest);
          assert.equal(digest, ethers.TypedDataEncoder.hash(typed.domain, types, message));
          for (const sig of entry.signatures) assert.notEqual((await harness.recover(digest, sig.signature)).toLowerCase(), sig.signer);
        });
      }

      for (const [field, value] of Object.entries({name: 'Other Registry', version: '2', chainId: '31338', verifyingContract: '0x4444444444444444444444444444444444444444'})) {
        it(`domain ${field} prevents signature reuse`, async function () {
          const domain = {...typed.domain, [field]: value};
          const separator = await harness.domainHash(domain.name, domain.version, domain.chainId, domain.verifyingContract);
          const digest = await harness.digest(separator, entry.expected.struct_hash);
          assert.equal(digest, ethers.TypedDataEncoder.hash(domain, types, typed.message));
          assert.notEqual(digest, entry.expected.digest);
          for (const sig of entry.signatures) assert.notEqual((await harness.recover(digest, sig.signature)).toLowerCase(), sig.signer);
        });
      }

      it('OpenZeppelin rejects truncated, invalid-v, zero and high-s signatures', async function () {
        const signature = ethers.getBytes(entry.signatures[0].signature);
        const invalidV = signature.slice(); invalidV[64] = 0;
        const s = BigInt(ethers.hexlify(signature.slice(32, 64)));
        const highS = ethers.concat([signature.slice(0, 32), ethers.toBeHex(N - s, 32), ethers.toBeHex(signature[64] === 27 ? 28 : 27, 1)]);
        for (const invalid of ['0x1234', new Uint8Array(65), invalidV, highS]) {
          await assert.rejects(harness.recover(entry.expected.digest, invalid));
        }
      });
    });
  }

  it('uses decimal strings to preserve uint64 values beyond JS safe integers', function () {
    const entry = vector.vectors.ActionIntent;
    assert.equal(entry.typed_data.message.nonce, '9007199254740993');
    const types = {ActionIntent: protocol.types.ActionIntent};
    const unsafe = {...entry.typed_data.message, nonce: Number(entry.typed_data.message.nonce)};
    assert.throws(() => ethers.TypedDataEncoder.hash(entry.typed_data.domain, types, unsafe));
    const overflow = {...entry.typed_data.message, nonce: (1n << 64n).toString()};
    assert.throws(() => ethers.TypedDataEncoder.hash(entry.typed_data.domain, types, overflow));
  });
});
