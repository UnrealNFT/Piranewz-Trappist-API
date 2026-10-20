"""Run every paid TrappistAI media type on one article and post it to Telegram."""

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from trappist_auto_bot.media.trappist_media import TrappistMediaGenerator, build_media_prompts
from trappist_auto_bot.storage.db import Database
from trappist_auto_bot.utils.logger import get_logger

logger = get_logger(__name__)

STEPS = ["image", "speech", "music", "video", "3d"]
LABELS = {
    "image": "🖼 Image FLUX Schnell",
    "speech": "🎙 Speech",
    "music": "🎵 Music",
    "video": "🎬 Video",
    "3d": "🧊 3D Tripo (texture)",
}


@dataclass(frozen=True)
class SuiteArticle:
    title: str
    summary: str
    hashtags: str = ""
    source: str = ""


DEFAULT_ARTICLE = SuiteArticle(
    title="Mesh & Visa Unite: Spend Crypto Directly From Your Wallet",
    summary=(
        "Mesh partners with Visa to enable instant crypto and stablecoin spending directly "
        "from wallet apps, eliminating the need to sell or transfer funds first. The "
        "integration brings seamless payment capabilities to everyday users."
    ),
    hashtags="#MeshWallet #VisaCrypto #StablecoinPayments #CryptoSpending #WalletIntegration",
    source=(
        "[📰 The Block](https://www.theblock.co/news/business/"
        "2026-10-19-mesh-visa-partner-spend-crypto-stablecoins-421058)"
    ),
)


def _download(url: str) -> bytes:
    response = requests.get(url, timeout=300)
    response.raise_for_status()
    return response.content


def _generate_step(
    media: TrappistMediaGenerator,
    step: str,
    prompts: dict[str, Any],
    image_url: str,
    voice: str,
) -> tuple[str, bytes, str, str]:
    """Pay and generate one step. Returns (url, data, filename, telegram_kind)."""
    if step == "image":
        result = media.image(prompts["image"])
        return result.url, _download(result.url), "article.png", "photo"
    if step == "speech":
        result = media.speech(prompts["speech"], voice=voice)
        return "", result.data, "article_speech.mp3", "audio"
    if step == "music":
        result = media.music(prompts["music"]["lyrics"], prompts["music"]["tags"])
        return result.url, _download(result.url), "article_music.mp3", "audio"
    if step == "video":
        # Animate the article image when we have one, else text-to-video.
        result = media.video(prompts["video"], image_url=image_url or None)
        return result.url, _download(result.url), "article_video.mp4", "video"
    black_bg = media.image(prompts["3d_image"])
    logger.info("3D source image (black background): %s", black_bg.url)
    result = media.model_3d(black_bg.url, with_texture=True)
    return result.url, _download(result.url), "article_model.glb", "document"


async def run_media_suite(
    media: TrappistMediaGenerator,
    poster: Any,
    article: SuiteArticle = DEFAULT_ARTICLE,
    *,
    db: Database | None = None,
    steps: list[str] | None = None,
    voice: str = "en-male",
    out_dir: Path | None = None,
) -> dict[str, str]:
    """Generate and post each media step once; returns {step: url or error}."""
    prompts = build_media_prompts(article.title, article.summary)
    loop = asyncio.get_running_loop()
    results: dict[str, str] = {}
    image_url = ""

    for step in steps or STEPS:
        state_key = f"media_suite:{article.title}:{step}"
        previous = db.get_state(state_key) if db else None
        if previous:
            # Recorded before paying, so a restart never pays the same step twice.
            logger.info("Media suite step %s already run (%s), skipping", step, previous[:80])
            if step == "image" and previous.startswith("done:"):
                image_url = previous[len("done:"):]
            results[step] = previous
            continue
        if db:
            db.set_state(state_key, "started")

        logger.info("Media suite: %s for '%s'", LABELS[step], article.title)
        try:
            url, data, filename, kind = await loop.run_in_executor(
                None, _generate_step, media, step, prompts, image_url, voice
            )
            if step == "image":
                image_url = url
            if out_dir:
                out_dir.mkdir(parents=True, exist_ok=True)
                (out_dir / filename).write_bytes(data)

            caption = "\n\n".join(
                part for part in (LABELS[step], f"**{article.title}**", article.hashtags, article.source) if part
            )
            if kind == "photo":
                await poster.post_image_bytes(data, caption_en=caption)
            else:
                await poster.post_media(kind, data, filename, caption_en=caption)

            results[step] = f"done:{url or filename}"
            logger.info("✅ Media suite %s done: %s", step, url or filename)
        except Exception as exc:  # noqa: BLE001
            results[step] = f"failed:{exc}"
            logger.error("❌ Media suite %s failed: %s", step, exc)
        if db:
            db.set_state(state_key, results[step][:500])

    return results
