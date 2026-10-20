"""Run every paid TrappistAI media type on one article and post it to Telegram."""

import asyncio
import io
import tempfile
import urllib.parse
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from trappist_auto_bot.media.trappist_media import TrappistMediaGenerator, build_media_prompts
from trappist_auto_bot.storage.db import Database
from trappist_auto_bot.utils.logger import get_logger

logger = get_logger(__name__)

STEPS = ["image", "speech", "music", "video", "3d"]
VIEWER_3D_URL = "https://trappist.land/viewer3d.html?url="
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


def viewer_3d_url(glb_url: str) -> str:
    """Link to the trappist.land 3D viewer, as used by the TrappistAI Telegram bot."""
    return VIEWER_3D_URL + urllib.parse.quote(glb_url, safe="")


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
    try:
        data = _download(result.url)
    except requests.RequestException as exc:
        # Already paid: still publish the viewer link instead of losing the model.
        logger.warning("Could not download GLB, posting viewer link only: %s", exc)
        data = b""
    return result.url, data, "article_model.glb", "document"


async def _post_3d(poster: Any, data: bytes, filename: str, caption: str) -> None:
    """Send the GLB with viewer links; fall back to a links-only message like the TrappistAI bot."""
    if data:
        try:
            await poster.post_media("document", data, filename, caption_en=caption)
        except Exception as exc:  # noqa: BLE001
            logger.warning("GLB upload refused by Telegram, posting viewer link only: %s", exc)
            await poster.post_text(caption_en=caption)
        try:
            obj_zip = await asyncio.get_running_loop().run_in_executor(None, glb_to_obj_zip, data)
            await poster.post_media(
                "document", obj_zip, "article_model_obj.zip",
                caption_en="🧊 OBJ + texture — unzip, then Blender: File > Import > Wavefront (.obj)",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("OBJ conversion/upload failed: %s", exc)
        return
    await poster.post_text(caption_en=caption)


def glb_to_obj_zip(glb: bytes) -> bytes:
    """Convert a GLB to a zip of model.obj + material.mtl + texture images."""
    import trimesh

    scene = trimesh.load(io.BytesIO(glb), file_type="glb", force="scene")
    with tempfile.TemporaryDirectory() as tmp:
        scene.export(str(Path(tmp) / "model.obj"), file_type="obj")
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(Path(tmp).iterdir()):
                archive.write(path, path.name)
    return buffer.getvalue()


async def run_media_suite(
    media: TrappistMediaGenerator,
    poster: Any,
    article: SuiteArticle = DEFAULT_ARTICLE,
    *,
    db: Database | None = None,
    steps: list[str] | None = None,
    voice: str = "en-male",
    out_dir: Path | None = None,
    run_id: str = "1",
) -> dict[str, str]:
    """Generate and post each media step once per run_id; returns {step: url or error}."""
    prompts = build_media_prompts(article.title, article.summary)
    loop = asyncio.get_running_loop()
    results: dict[str, str] = {}
    image_url = ""
    # Run "1" keeps the original key format so already-paid steps stay recorded.
    key_prefix = "media_suite" if run_id == "1" else f"media_suite:run{run_id}"

    for step in steps or STEPS:
        state_key = f"{key_prefix}:{article.title}:{step}"
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
            if out_dir and data:
                out_dir.mkdir(parents=True, exist_ok=True)
                (out_dir / filename).write_bytes(data)

            links = ""
            if step == "3d":
                links = f"🔗 [View in 3D]({viewer_3d_url(url)})\n💾 [Direct download]({url})"
            caption = "\n\n".join(
                part
                for part in (LABELS[step], f"**{article.title}**", links, article.hashtags, article.source)
                if part
            )
            if kind == "photo":
                await poster.post_image_bytes(data, caption_en=caption)
            elif kind == "document":
                await _post_3d(poster, data, filename, caption)
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
