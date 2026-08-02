const fs = require('fs');
const casper = require('casper-js-sdk');

const keyPath = process.argv[2];
const inputJson = process.argv[3];
if (!keyPath || !inputJson) {
  console.error('Usage: node sign_casper_transfer.js <path-to-pem> \'<json-input>\'');
  process.exit(1);
}
const input = JSON.parse(inputJson);

(async () => {
  const pem = fs.readFileSync(keyPath, 'utf8');
  const privateKey = casper.PrivateKey.fromPem(pem, casper.KeyAlgorithm.SECP256K1);
  const publicKey = casper.PublicKey.fromHex(input.wallet);

  const targetHex = input.payTo;
  const targetKey = casper.PublicKey.fromHex(targetHex);

  const deploy = casper.makeCsprTransferDeploy({
    senderPublicKeyHex: input.wallet,
    recipientPublicKeyHex: input.payTo,
    transferAmount: input.amountMotes,
    paymentAmount: '100000000',
    chainName: input.chainName || 'casper',
    memo: input.transferId || Math.floor(Math.random() * 1e15),
    ttl: 1800000,
  });

  deploy.sign(privateKey);
  // Reconstruct a plain JSON representation compatible with the Casper RPC.
  const approvals = deploy.approvals.map(a => ({
    signature: a.signature.toHex(),
    signer: a.signer.toHex(),
  }));

  function headerToRpc(h) {
    return {
      account: h.account?.toHex ? h.account.toHex() : h.account,
      body_hash: h.bodyHash?.toHex ? h.bodyHash.toHex() : h.bodyHash,
      chain_name: h.chainName,
      dependencies: h.dependencies || [],
      gas_price: h.gasPrice,
      timestamp: h.timestamp,
      ttl: h.ttl,
    };
  }

  function argsToRpc(argsObj) {
    if (!argsObj || !argsObj.args) return [];
    const raw = argsObj.args;
    const namedArgs = raw.namedArgs || raw.args;
    if (!Array.isArray(namedArgs)) return [];
    return namedArgs.map(arg => {
      const name = arg.name;
      const value = arg.value;
      const parsed = arg.parsed;
      return { name, value: { ...value, parsed } };
    });
  }

  function executableToRpc(item) {
    if (item.moduleBytes) {
      return {
        ModuleBytes: {
          module_bytes: "",
          args: argsToRpc(item.moduleBytes),
        },
      };
    }
    if (item.transfer) {
      return {
        Transfer: {
          args: argsToRpc(item.transfer),
        },
      };
    }
    return JSON.parse(JSON.stringify(item));
  }

  const out = {
    deploy: {
      hash: deploy.hash.toHex(),
      header: headerToRpc(deploy.header),
      payment: executableToRpc(deploy.payment),
      session: executableToRpc(deploy.session),
      approvals,
    },
  };
  console.log(JSON.stringify(out));
})();
