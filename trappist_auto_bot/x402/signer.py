"""Pluggable deploy signing for autonomous x402 payments.

There is no production-grade Python SDK for signing Casper deploys, so the
signing step is intentionally pluggable. In production you should plug in a
hardware wallet, a local signer binary, or an HSM-backed signing service.
"""

import json
import subprocess
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from trappist_auto_bot.utils.logger import get_logger

logger = get_logger(__name__)


class Signer(ABC):
    """Abstract signer interface."""

    @abstractmethod
    def sign_transfer(
        self,
        *,
        amount_motes: int,
        pay_to: str,
        memo: str | None,
        chain_name: str | None,
    ) -> dict[str, Any]:
        """Return a signed deploy JSON dict for a native CSPR transfer."""


class ExternalCommandSigner(Signer):
    """Call an external command to sign a transfer.

    The command receives JSON on stdin:

        {
          "wallet": "01a1b2...",
          "amountMotes": 12300000000,
          "payTo": "01c3d4...",
          "memo": "...",
          "chainName": "casper"
        }

    and must write the signed deploy JSON to stdout.
    """

    def __init__(self, command: str, wallet: str, timeout: int = 60) -> None:
        self.command = command
        self.wallet = wallet
        self.timeout = timeout

    def sign_transfer(
        self,
        *,
        amount_motes: int,
        pay_to: str,
        memo: str | None,
        chain_name: str | None,
    ) -> dict[str, Any]:
        payload = {
            "wallet": self.wallet,
            "amountMotes": amount_motes,
            "payTo": pay_to,
            "memo": memo,
            "chainName": chain_name or "casper",
        }
        logger.info("Calling external signer: %s", self.command)
        result = subprocess.run(
            self.command,
            shell=True,
            input=json.dumps(payload).encode(),
            capture_output=True,
            timeout=self.timeout,
            check=False,
        )
        if result.returncode != 0:
            raise SignerError(
                f"Signer exited with {result.returncode}: "
                f"{result.stderr.decode(errors='replace')}"
            )
        return json.loads(result.stdout.decode())


class LocalCasperSigner(Signer):
    """Sign locally using casper-js-sdk via a Node.js helper.

    pycspr's JSON output is rejected by Casper mainnet RPC nodes because the
    on-chain hash does not match the serialized JSON form. The Node helper
    (scripts/sign_casper_transfer_v2.js) produces a deploy that is accepted by
    account_put_deploy, so we use it as the local signing backend.

    This signer is convenient but **keeps the private key on disk**.
    Use it only in trusted environments. Prefer ExternalCommandSigner with an
    HSM/encrypted keystore for production.
    """

    def __init__(self, key_path: str, wallet: str) -> None:
        self.key_path = Path(key_path)
        self.wallet = wallet
        if not self.key_path.exists():
            raise SignerError(f"Casper private key not found: {key_path}")

        # Path to the bundled Node.js signing helper.
        self._script_path = (
            Path(__file__).parents[2] / "scripts" / "sign_casper_transfer_v2.js"
        )
        if not self._script_path.exists():
            raise SignerError(f"Node signer helper not found: {self._script_path}")

    def sign_transfer(
        self,
        *,
        amount_motes: int,
        pay_to: str,
        memo: str | None,
        chain_name: str | None,
    ) -> dict[str, Any]:
        logger.info("Signing locally with key: %s", self.key_path)

        # Casper native transfers use a U64 correlation id. Use the numeric memo
        # when available, otherwise a random id.
        transfer_id = 0
        if memo and memo.isdigit():
            transfer_id = int(memo)
        if not transfer_id:
            transfer_id = int(time.time() * 1000) % (10**15)

        payload = {
            "wallet": self.wallet,
            "amountMotes": amount_motes,
            "payTo": pay_to,
            "chainName": (chain_name or "casper").split(":")[0],
            "transferId": transfer_id,
        }

        try:
            result = subprocess.run(
                ["node", str(self._script_path), str(self.key_path), json.dumps(payload)],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
        except FileNotFoundError as exc:
            raise SignerError("Node.js is required for local Casper signing") from exc
        except subprocess.TimeoutExpired as exc:
            raise SignerError("Node signer timed out") from exc

        if result.returncode != 0:
            raise SignerError(
                f"Node signer exited with {result.returncode}: {result.stderr[:500]}"
            )

        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise SignerError(f"Node signer returned invalid JSON: {exc}") from exc


class MockSigner(Signer):
    """Return a dummy deploy for integration tests without real signing.

    NEVER use this in production: the generated deploy is not valid and will
    be rejected by the TrappistAI API.
    """

    def __init__(self, wallet: str) -> None:
        self.wallet = wallet

    def sign_transfer(
        self,
        *,
        amount_motes: int,
        pay_to: str,
        memo: str | None,
        chain_name: str | None,
    ) -> dict[str, Any]:
        logger.warning("Using MockSigner - deploy will be rejected by the API")
        return {
            "deploy": {
                "hash": "0000000000000000000000000000000000000000000000000000000000000000",
                "header": {
                    "account": self.wallet,
                    "timestamp": "2024-01-01T00:00:00.000Z",
                    "ttl": "30m",
                    "gas_price": 1,
                    "chain_name": chain_name or "casper",
                    "body_hash": "0000000000000000000000000000000000000000000000000000000000000000",
                    "dependencies": [],
                },
                "payment": {"ModuleBytes": {"module_bytes": "", "args": []}},
                "session": {
                    "Transfer": {
                        "args": [
                            {"name": "amount", "value": {"cl_type": "U512", "bytes": str(amount_motes)}},
                            {"name": "target", "value": {"cl_type": "PublicKey", "bytes": pay_to}},
                            {"name": "id", "value": {"cl_type": "Option", "bytes": memo}},
                        ]
                    }
                },
                "approvals": [],
            }
        }


class SignerError(Exception):
    """Raised when signing fails."""
