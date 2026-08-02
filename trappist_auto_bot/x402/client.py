"""x402 payment flow client for TrappistAI.

Heavily inspired by agent_x402_client.py but packaged for autonomous use.
"""

import base64
import json
import time
from dataclasses import dataclass
from typing import Any

import requests

from trappist_auto_bot.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class PaymentDetails:
    """Human-readable payment details extracted from an x402 challenge."""

    resource: str | None
    description: str | None
    network: str | None
    asset: str | None
    amount_motes: int | None
    pay_to: str | None
    cost_usd: str | None
    cost_cspr: str | None
    decimals: int
    memo: str | None


def _to_int(value: Any) -> int | None:
    """Coerce a value to int if possible."""
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value)
    return int(value)


class X402Client:
    """Client for the TrappistAI x402 agent payment flow."""

    def __init__(
        self,
        api_url: str,
        wallet_public_key: str,
        casper_rpc_url: str = "https://node.mainnet.casper.network/rpc",
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.wallet = wallet_public_key
        self.casper_rpc_url = casper_rpc_url

    def _decode_header(self, header_value: str) -> dict[str, Any]:
        """Decode a base64-encoded x402 header."""
        return json.loads(base64.b64decode(header_value).decode())

    def _encode_signature(self, deploy_json: dict[str, Any]) -> str:
        """Build the base64 PAYMENT-SIGNATURE payload.

        The backend expects {"deployJson": <raw deploy object>, "wallet": "01..."}.
        Some callers wrap the deploy under a top-level "deploy" key, so unwrap it
        when present to match the expected wire format.
        """
        raw_deploy = deploy_json.get("deploy", deploy_json)
        payload = {"deployJson": raw_deploy, "wallet": self.wallet}
        return base64.b64encode(json.dumps(payload).encode()).decode()

    def request_challenge(self, prompt: str, timeout: int = 30) -> dict[str, Any]:
        """Request generation without payment and parse the 402 challenge."""
        url = f"{self.api_url}/api/v1/agent/generate/image"
        body = {"wallet": self.wallet, "prompt": prompt}

        logger.info("Requesting challenge for prompt: %s", prompt[:60])
        response = requests.post(url, json=body, timeout=timeout)
        logger.info("Challenge response HTTP %s", response.status_code)

        if response.status_code != 402:
            raise X402Error(
                f"Expected HTTP 402, got {response.status_code}: {response.text}"
            )

        header = response.headers.get("PAYMENT-REQUIRED")
        if not header:
            raise X402Error("Missing PAYMENT-REQUIRED header in 402 response")

        return self._decode_header(header)

    @staticmethod
    def extract_payment_details(challenge: dict[str, Any]) -> PaymentDetails:
        """Extract human-readable payment details from the challenge."""
        accepts = challenge.get("accepts", [{}])[0]
        extra = accepts.get("extra", {})
        resource = challenge.get("resource", {})
        return PaymentDetails(
            resource=resource.get("url"),
            description=resource.get("description"),
            network=accepts.get("network"),
            asset=accepts.get("asset"),
            amount_motes=_to_int(accepts.get("amount")),
            pay_to=accepts.get("payTo"),
            cost_usd=extra.get("usdPrice"),
            cost_cspr=extra.get("csprPrice"),
            decimals=int(extra.get("decimals", 9)),
            memo=extra.get("memo"),
        )

    def _broadcast_deploy(self, deploy_json: dict[str, Any]) -> str:
        """Broadcast the signed deploy to Casper mainnet ourselves.

        TrappistAI's backend sometimes cannot broadcast the deploy before the
        gateway timeout fires. Pre-broadcasting guarantees the deploy is
        on-chain when the server tries to verify the payment.
        """
        raw_deploy = deploy_json.get("deploy", deploy_json)
        deploy_hash = raw_deploy.get("hash", "N/A")
        logger.info("Broadcasting deploy to Casper mainnet: %s", deploy_hash)

        response = requests.post(
            self.casper_rpc_url,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "account_put_deploy",
                "params": {"deploy": raw_deploy},
            },
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
        if "error" in data:
            raise X402Error(f"Casper broadcast failed: {data['error']}")
        logger.info("Deploy broadcast accepted: %s", data["result"]["deploy_hash"])
        return deploy_hash

    def submit_payment(
        self,
        prompt: str,
        deploy_json: dict[str, Any],
        timeout: int = 300,
        max_retries: int = 2,
    ) -> dict[str, Any]:
        """Submit the signed deploy and return the generated image response."""
        url = f"{self.api_url}/api/v1/agent/generate/image"
        body = {"wallet": self.wallet, "prompt": prompt}
        payment_signature = self._encode_signature(deploy_json)

        deploy_hash = deploy_json.get("deploy", {}).get("hash", "N/A")
        logger.info("Submitting payment proof (deploy hash: %s)", deploy_hash)

        # Ensure the deploy is on-chain before asking TrappistAI to verify it.
        self._broadcast_deploy(deploy_json)

        last_error: Exception | None = None
        for attempt in range(1, max_retries + 1):
            try:
                response = requests.post(
                    url,
                    json=body,
                    headers={"PAYMENT-SIGNATURE": payment_signature},
                    timeout=timeout,
                )
                logger.info("Submit response HTTP %s", response.status_code)

                if response.status_code == 200:
                    return response.json()

                # Server-side timeouts can happen while generation is still running.
                # Retry a few times before giving up.
                if response.status_code in (502, 503, 504) and attempt < max_retries:
                    logger.warning(
                        "Gateway timeout (HTTP %s), retrying in %ss... (attempt %s/%s)",
                        response.status_code,
                        attempt * 5,
                        attempt,
                        max_retries,
                    )
                    time.sleep(attempt * 5)
                    continue

                raise X402Error(
                    f"Payment or generation failed (HTTP {response.status_code}): {response.text}"
                )
            except requests.RequestException as exc:
                last_error = exc
                logger.warning("Request exception on attempt %s: %s", attempt, exc)
                if attempt < max_retries:
                    time.sleep(attempt * 5)

        raise X402Error(f"All {max_retries} payment submission attempts failed: {last_error}")


class X402Error(Exception):
    """Raised when the x402 payment flow fails."""
