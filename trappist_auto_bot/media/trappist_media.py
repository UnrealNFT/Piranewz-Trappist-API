"""Generate speech, music, video and 3D assets for an article on TrappistAI.

Every call goes through the same x402 flow as images: 402 challenge, signed
native CSPR transfer, then the resource. Music, video and 3D are jobs that
must be polled on /api/jobs/{job_id}.
"""

import base64
import re
from dataclasses import dataclass
from typing import Any

from trappist_auto_bot.image.generator import TrappistImageGenerator
from trappist_auto_bot.utils.logger import get_logger
from trappist_auto_bot.x402.client import IMAGE_ENDPOINT, PaymentDetails, X402Error

logger = get_logger(__name__)

TTS_ENDPOINT = "/api/v1/agent/tts"
MUSIC_ENDPOINT = "/api/v1/agent/generate/music"
VIDEO_ENDPOINT = "/api/v1/agent/generate/video"
MODEL_3D_ENDPOINT = "/api/v1/agent/generate/3d"

ENDPOINTS = {
    "image": IMAGE_ENDPOINT,
    "speech": TTS_ENDPOINT,
    "music": MUSIC_ENDPOINT,
    "video": VIDEO_ENDPOINT,
    "3d": MODEL_3D_ENDPOINT,
}


@dataclass
class MediaResult:
    """One generated asset plus what was paid for it."""

    kind: str
    payment: PaymentDetails
    url: str = ""
    data: bytes = b""
    transaction: str = ""


def _strip_hashtags(text: str) -> str:
    return re.sub(r"#\w+", "", text).strip()


def build_media_prompts(title: str, summary: str) -> dict[str, Any]:
    """Derive every media prompt from the same article title and summary."""
    title = _strip_hashtags(title)
    summary = _strip_hashtags(summary)
    subject = f"{title}. {summary}".strip(". ")
    style = "dark cyberpunk anime, manga art style, dramatic neon lighting, cinematic"
    return {
        "image": f"{subject}. {style}, ultra detailed, 8k",
        "speech": f"{title}. {summary}",
        "music": {
            "lyrics": (
                f"[verse]\n{title}\n{summary}\n"
                f"[chorus]\n{title}\nPiranewz, crypto news never sleeps\n"
            ),
            "tags": "electronic, dark, cinematic, cyberpunk, energetic, news",
        },
        "video": f"{subject}. Cinematic camera motion, {style}",
        # A single object on pure black gives Tripo3D a clean silhouette to mesh.
        "3d_image": (
            f"A single 3D-printable sculpture symbolizing: {title}. "
            "Centered isolated object, pure solid black background, no text, "
            "no scenery, studio lighting, highly detailed, physically based materials"
        ),
    }


class TrappistMediaGenerator:
    """Pay TrappistAI for each media type and return the generated asset."""

    def __init__(
        self,
        image_generator: TrappistImageGenerator,
        max_payment_motes: int = 0,
        job_timeout: int = 900,
    ) -> None:
        self.paid = image_generator
        self.max_payment_motes = max_payment_motes
        self.job_timeout = job_timeout

    def quote(self, kind: str, body: dict[str, Any]) -> PaymentDetails:
        """Fetch the 402 challenge only (no payment) to show the current price."""
        challenge = self.paid.x402.request_challenge(endpoint=ENDPOINTS[kind], body=body)
        return self.paid.x402.extract_payment_details(challenge)

    def _pay(self, endpoint: str, body: dict[str, Any]) -> tuple[dict[str, Any], PaymentDetails]:
        result = self.paid.paid_request(endpoint, body, max_payment_motes=self.max_payment_motes)
        return result["api_response"], result["payment_details"]

    def _pay_job(self, kind: str, endpoint: str, body: dict[str, Any]) -> MediaResult:
        response, payment = self._pay(endpoint, body)
        job_id = response.get("job_id")
        if not job_id:
            raise X402Error(f"No job_id in {kind} response: {response}")
        logger.info("%s job %s started (tx %s)", kind, job_id, response.get("transaction"))
        job = self.paid.x402.wait_for_job(job_id, timeout=self.job_timeout)
        url = (job.get("result") or {}).get("url", "")
        if not url:
            raise X402Error(f"{kind} job {job_id} completed without result.url: {job}")
        return MediaResult(kind, url=url, payment=payment, transaction=response.get("transaction", ""))

    def image(self, prompt: str) -> MediaResult:
        response, payment = self._pay(IMAGE_ENDPOINT, {"prompt": prompt})
        url = response.get("imageUrl") or response.get("url", "")
        if not url:
            raise X402Error(f"No image URL in response: {response}")
        return MediaResult("image", url=url, payment=payment, transaction=response.get("transaction", ""))

    def speech(self, text: str, voice: str = "auto") -> MediaResult:
        response, payment = self._pay(TTS_ENDPOINT, {"text": text[:2000], "voice": voice})
        audio_b64 = response.get("audioBase64", "")
        if not audio_b64:
            raise X402Error(f"No audioBase64 in TTS response: {response}")
        return MediaResult(
            "speech",
            data=base64.b64decode(audio_b64),
            payment=payment,
            transaction=response.get("transaction", ""),
        )

    def music(self, lyrics: str, tags: str, quality: str = "hm") -> MediaResult:
        body = {"lyrics": lyrics, "tags": tags, "quality": quality}
        return self._pay_job("music", MUSIC_ENDPOINT, body)

    def video(
        self,
        prompt: str,
        image_url: str | None = None,
        duration: int = 5,
        aspect_ratio: str = "16:9",
        audio: bool = True,
    ) -> MediaResult:
        body = {
            "prompt": prompt,
            "imageUrl": image_url,
            "duration": duration,
            "aspectRatio": aspect_ratio,
            "audio": audio,
        }
        return self._pay_job("video", VIDEO_ENDPOINT, body)

    def model_3d(self, image_url: str, with_texture: bool = True) -> MediaResult:
        body = {"imageUrl": image_url, "withTexture": with_texture}
        return self._pay_job("3d", MODEL_3D_ENDPOINT, body)
