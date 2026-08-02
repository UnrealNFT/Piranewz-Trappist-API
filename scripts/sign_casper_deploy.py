"""Example Python signer for Casper native transfers.

Usage:
    python scripts/sign_casper_deploy.py < input.json

Input JSON:
    {
      "wallet": "0202e5a8...",
      "amountMotes": 12300000000,
      "payTo": "01c3d4...",
      "memo": "...",
      "chainName": "casper"
    }

Output JSON:
    { "deploy": { ... signed deploy ... } }

Requires:
    pip install pycspr
"""

import json
import os
import sys


def load_private_key_pem(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def sign_transfer(input_data: dict) -> dict:
    """Sign a native CSPR transfer deploy."""
    key_path = os.environ.get("CASPER_PRIVATE_KEY_PATH")
    if not key_path:
        raise RuntimeError("CASPER_PRIVATE_KEY_PATH not set")

    private_key_pem = load_private_key_pem(key_path)

    # Lazy import because pycspr is optional
    import pycspr
    from pycspr import NodeClient, NodeConnectionInfo
    from pycspr.crypto import KeyAlgorithm
    from pycspr.types.cl import CL_U512, CL_Option, CL_PublicKey
    from pycspr.types.node import TransferDeployParameters

    algo = KeyAlgorithm.SECP256K1 if input_data["wallet"].startswith("02") else KeyAlgorithm.ED25519
    sender_key = pycspr.parse_private_key(private_key_pem, algo, "pem")
    target_key = CL_PublicKey.from_hex(input_data["payTo"])

    params = TransferDeployParameters(
        account=sender_key.account_key,
        amount=input_data["amountMotes"],
        target=target_key,
        correlation_id=input_data.get("memo") or "0",
        chain_name=input_data.get("chainName", "casper"),
    )

    deploy = pycspr.create_transfer_deploy(params)
    deploy.approve(sender_key)

    return {"deploy": deploy.to_json()}


if __name__ == "__main__":
    input_data = json.load(sys.stdin)
    result = sign_transfer(input_data)
    print(json.dumps(result))
