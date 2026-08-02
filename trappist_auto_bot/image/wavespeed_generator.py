"""Free image generation via WaveSpeed API."""

import requests

from trappist_auto_bot.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_WAVESPEED_URL = "https://api.wavespeed.ai"


class WaveSpeedImageGenerator:
    """Generate images using the WaveSpeed API (no blockchain payment)."""

    def __init__(self, api_key: str, api_url: str = DEFAULT_WAVESPEED_URL) -> None:
        self.api_key = api_key.replace("wavespeed ", "").strip()
        self.api_url = api_url.rstrip("/")

    def generate(
        self,
        prompt: str,
        *,
        model: str = "wavify-lumina",
        width: int = 1024,
        height: int = 1024,
        num_inference_steps: int = 4,
        guidance_scale: float = 3.5,
        timeout: int = 120,
    ) -> dict:
        """Generate an image and return a dict with the image URL."""
        logger.info("Generating image with WaveSpeed: %s", prompt[:80])

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "prompt": prompt,
            "width": width,
            "height": height,
            "num_inference_steps": num_inference_steps,
            "guidance_scale": guidance_scale,
        }

        response = requests.post(
            f"{self.api_url}/{model}/predictions",
            headers=headers,
            json=body,
            timeout=timeout,
        )
        logger.info("WaveSpeed response HTTP %s", response.status_code)

        if response.status_code != 200:
            raise WaveSpeedError(
                f"WaveSpeed generation failed (HTTP {response.status_code}): {response.text}"
            )

        data = response.json()
        logger.info("WaveSpeed prediction: %s", data.get("id"))

        # Poll for result if async
        if data.get("status") in ("processing", "queued", "starting"):
            return self._poll_result(data["id"], model, timeout=timeout)

        return {"imageUrl": data.get("output") or data.get("url"), "raw": data}

    def _poll_result(
        self, prediction_id: str, model: str, timeout: int = 120
    ) -> dict:
        """Poll WaveSpeed until the prediction completes."""
        import time

        headers = {"Authorization": f"Bearer {self.api_key}"}
        deadline = time.time() + timeout
        while time.time() < deadline:
            response = requests.get(
                f"{self.api_url}/{model}/predictions/{prediction_id}",
                headers=headers,
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            status = data.get("status")
            logger.info("WaveSpeed status: %s", status)

            if status == "succeeded":
                return {
                    "imageUrl": data.get("output") or data.get("url"),
                    "raw": data,
                }
            if status == "failed":
                raise WaveSpeedError(f"WaveSpeed prediction failed: {data}")

            time.sleep(2)

        raise WaveSpeedError("WaveSpeed prediction timed out")


class WaveSpeedError(Exception):
    """Raised when WaveSpeed generation fails."""
