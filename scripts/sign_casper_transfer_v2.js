const fs = require('fs');
const { DeployUtil, Keys, CLPublicKey } = require('casper-js-sdk');

const keyPath = process.argv[2];
const inputJson = process.argv[3];
if (!keyPath || !inputJson) {
  console.error('Usage: node sign_casper_transfer_v2.js <path-to-pem> \'<json-input>\'');
  process.exit(1);
}
const input = JSON.parse(inputJson);

(async () => {
  const privateKey = keyPath.toLowerCase().endsWith('.pem')
    ? (input.wallet.startsWith('02')
        ? Keys.Secp256K1.loadKeyPairFromPrivateFile(keyPath)
        : Keys.Ed25519.loadKeyPairFromPrivateFile(keyPath))
    : null;
  if (!privateKey) {
    console.error('Only PEM files are supported');
    process.exit(1);
  }
  const publicKey = privateKey.publicKey;

  const sender = publicKey;
  const recipient = CLPublicKey.fromHex(input.payTo);

  const deployParams = new DeployUtil.DeployParams(
    sender,
    input.chainName || 'casper',
    1,
    1800000,
  );

  const transferId = input.transferId || Math.floor(Math.random() * 1e15);

  const session = DeployUtil.ExecutableDeployItem.newTransfer(
    input.amountMotes,
    recipient,
    undefined,
    transferId,
  );

  const payment = DeployUtil.standardPayment(100000000);
  const deploy = DeployUtil.makeDeploy(deployParams, session, payment);
  DeployUtil.signDeploy(deploy, privateKey);

  const out = DeployUtil.deployToJson(deploy);
  console.log(JSON.stringify(out));
})();
