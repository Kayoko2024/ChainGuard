require('@nomicfoundation/hardhat-ethers');
const { subtask } = require('hardhat/config');
const { TASK_COMPILE_SOLIDITY_GET_SOLC_BUILD } = require('hardhat/builtin-tasks/task-names');

// Use the npm-locked solc-js build; compilation never downloads a separate compiler.
subtask(TASK_COMPILE_SOLIDITY_GET_SOLC_BUILD).setAction(async ({ solcVersion }, _hre, runSuper) => {
  if (solcVersion !== '0.8.28') return runSuper();
  return {
    compilerPath: require.resolve('solc/soljson.js'),
    isSolcJs: true,
    version: solcVersion,
    longVersion: require('solc').version(),
  };
});

module.exports = {
  solidity: { version: '0.8.28', settings: { optimizer: { enabled: true, runs: 200 }, evmVersion: 'paris' } },
  paths: { sources: './contracts', tests: './tests/solidity', cache: './cache', artifacts: './artifacts' },
  networks: { hardhat: { chainId: 31337 } },
};
