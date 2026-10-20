"""Autonomous image generation through the x402 payment flow."""

from typing import Any

from trappist_auto_bot.utils.logger import get_logger
from trappist_auto_bot.x402.client import IMAGE_ENDPOINT, PaymentDetails, X402Client, X402Error
from trappist_auto_bot.x402.signer import Signer, SignerError

logger = get_logger(__name__)


class TrappistImageGenerator:
    """Generate images on TrappistAI by automatically paying x402 challenges."""

    def __init__(
        self,
        api_url: str,
        wallet_public_key: str,
        signer: Signer,
        max_payment_motes: int = 0,
    ) -> None:
        self.x402 = X402Client(api_url, wallet_public_key)
        self.signer = signer
        self.max_payment_motes = max_payment_motes

    def generate(self, prompt: str) -> dict[str, Any]:
        """Generate an image and return API response plus payment details."""
        logger.info("Starting paid generation for prompt: %s", prompt[:80])
        return self.paid_request(IMAGE_ENDPOINT, {"prompt": prompt})

    def paid_request(
        self,
        endpoint: str,
        body: dict[str, Any],
        max_payment_motes: int | None = None,
    ) -> dict[str, Any]:
        """Pay the x402 challenge of any agent endpoint and return its response."""
        limit = self.max_payment_motes if max_payment_motes is None else max_payment_motes

        # 1. Request challenge
        challenge = self.x402.request_challenge(endpoint=endpoint, body=body)
        details = X402Client.extract_payment_details(challenge)

        logger.info(
            "Challenge accepted: %s CSPR ($%s USD) to %s",
            details.cost_cspr,
            details.cost_usd,
            details.pay_to,
        )

        # 2. Validate amount
        amount = details.amount_motes or 0
        if limit and amount > limit:
            raise X402Error(
                f"Requested amount ({amount} motes) exceeds configured "
                f"maximum ({limit} motes). Refusing to pay."
            )

        if not details.pay_to:
            raise X402Error("Missing payTo address in challenge")

        # 3. Sign transfer
        try:
            deploy = self.signer.sign_transfer(
                amount_motes=amount,
                pay_to=details.pay_to,
                memo=details.memo,
                chain_name=details.network,
            )
        except SignerError as exc:
            raise X402Error(f"Failed to sign deploy: {exc}") from exc

        # 4. Submit payment and receive the result (URL, base64 or job id)
        api_response = self.x402.submit_payment("", deploy, endpoint=endpoint, body=body)
        logger.info("Paid request successful on %s", endpoint)
        return {"api_response": api_response, "payment_details": details}
