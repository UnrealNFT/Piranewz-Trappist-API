"""Free image generation via Pollinations.ai.

Pollinations provides a simple, no-API-key image generation endpoint.
This is useful for testing and running the bot when paid providers fail.
"""

import urllib.parse

import requests

from trappist_auto_bot.utils.logger import get_logger

logger = get_logger(__name__)

BASE_URL = "https://image.pollinations.ai/prompt"


class PollinationsImageGenerator:
    """Generate images using the free Pollinations.ai endpoint."""

    def __init__(self, base_url: str = BASE_URL) -> None:
        self.base_url = base_url.rstrip("/")

    def generate(
        self,
        prompt: str,
        *,
        width: int = 1024,
        height: int = 1024,
        seed: int = 42,
        nologo: bool = True,
        timeout: int = 120,
    ) -> dict:
        """Return a dict with the image URL. The URL itself triggers generation."""
        logger.info("Generating image with Pollinations: %s", prompt[:80])

        params = {
            "width": width,
            "height": height,
            "seed": seed,
            "nologo": "true" if nologo else "false",
        }
        encoded_prompt = urllib.parse.quote(prompt)
        image_url = f"{self.base_url}/{encoded_prompt}?{urllib.parse.urlencode(params)}"

        # Pollinations streams the image on GET. A HEAD request can create a
        # cached empty response, so we skip it and let the consumer fetch the
        # real payload.
        logger.info("Pollinations URL ready: %s", image_url)
        return {"imageUrl": image_url}


class PollinationsError(Exception):
    """Raised when Pollinations generation fails."""
