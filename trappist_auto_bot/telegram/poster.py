"""Telegram channel poster."""

import io
from pathlib import Path
from typing import Any

import requests
from PIL import Image, ImageDraw, ImageFont
import sys
from telegram import Bot

from trappist_auto_bot.utils.logger import get_logger

logger = get_logger(__name__)


def _overlay_piranewz_branding(
    image_bytes: bytes,
    *,
    logo_path: str,
    channel_name: str = "@piranewz",
) -> bytes:
    """Add the Piranewz logo top-left + Telegram handle badge just below it.

    Matches the original tele10001 watermark layout:
    - brand logo in top-left at ~15% image width
    - Telegram logo + @piranewz on a dark pill directly under the logo
    """
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
        draw = ImageDraw.Draw(img)
        img_width, img_height = img.size

        left_x = 20
        top_y = 20

        # --- Brand logo top-left ---
        logo_width = int(img_width * 0.15)
        logo_height = 0
        if Path(logo_path).exists():
            logo = Image.open(logo_path).convert("RGBA")
            logo_height = int(logo.height * (logo_width / logo.width))
            logo = logo.resize((logo_width, logo_height), Image.Resampling.LANCZOS)
            img.paste(logo, (left_x, top_y), logo)

        # --- Telegram logo + @piranewz below the brand logo ---
        tg_logo_path = Path(logo_path).parent / "telegram-logo.png"
        font = _load_font(24, bold=True)

        channel_text = channel_name
        channel_bbox = draw.textbbox((0, 0), channel_text, font=font)
        text_width = channel_bbox[2] - channel_bbox[0]
        text_height = channel_bbox[3] - channel_bbox[1]

        tg_h = 28
        tg_w = tg_h
        tg_logo = None
        if tg_logo_path.exists():
            tg_logo = Image.open(str(tg_logo_path)).convert("RGBA")
            tg_w = int(tg_logo.width * (tg_h / tg_logo.height))
            tg_logo = tg_logo.resize((tg_w, tg_h), Image.Resampling.LANCZOS)

        spacing = 8
        total_w = tg_w + spacing + text_width
        tg_y = top_y + logo_height + 8

        # Semi-transparent dark pill background
        pad = 7
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        overlay_draw.rounded_rectangle(
            [left_x - pad, tg_y - pad, left_x + total_w + pad, tg_y + tg_h + pad],
            radius=10,
            fill=(0, 0, 0, 140),
        )
        img = Image.alpha_composite(img, overlay)
        draw = ImageDraw.Draw(img)

        if tg_logo:
            img.paste(tg_logo, (left_x, tg_y), tg_logo)

        text_x = left_x + tg_w + spacing
        text_y = tg_y + (tg_h - text_height) // 2
        draw.text((text_x + 1, text_y + 1), channel_text, font=font, fill=(0, 0, 0, 160))
        draw.text((text_x, text_y), channel_text, font=font, fill=(255, 255, 255, 230))

        output = io.BytesIO()
        img.convert("RGB").save(output, format="JPEG", quality=95)
        return output.getvalue()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Piranewz branding overlay failed: %s", exc)
        return image_bytes


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load a TrueType font, falling back to default."""
    try:
        if sys.platform == "win32":
            font_name = "arialbd.ttf" if bold else "arial.ttf"
            font_path = Path(f"C:/Windows/Fonts/{font_name}")
            if font_path.exists():
                return ImageFont.truetype(str(font_path), size)
            # Fallback to regular arial if bold missing
            return ImageFont.truetype("C:/Windows/Fonts/arial.ttf", size)
        families = (
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
            if bold
            else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
        )
        return ImageFont.truetype(families, size)
    except Exception:
        return ImageFont.load_default()


class TelegramPoster:
    """Post generated images and captions to one or more Telegram channels."""

    def __init__(self, bot_token: str, chat_id: str, chat_id_fr: str = "") -> None:
        self.bot = Bot(token=bot_token)
        self.chat_id = chat_id
        self.chat_id_fr = chat_id_fr

    async def post_image(
        self,
        image_url: str,
        caption_en: str,
        caption_fr: str = "",
        *,
        add_logo: bool = False,
        logo_path: str = "",
    ) -> dict[str, Any]:
        """Download an image, optionally watermark it, and post to Telegram."""
        logger.info("Downloading image from %s", image_url)
        response = requests.get(image_url, timeout=60)
        response.raise_for_status()
        image_bytes = response.content
        return await self.post_image_bytes(
            image_bytes,
            caption_en=caption_en,
            caption_fr=caption_fr,
            add_logo=add_logo,
            logo_path=logo_path,
        )

    async def post_image_bytes(
        self,
        image_bytes: bytes,
        caption_en: str,
        caption_fr: str = "",
        *,
        add_logo: bool = False,
        logo_path: str = "",
    ) -> dict[str, Any]:
        """Post already-generated image bytes to Telegram (EN + optional FR)."""
        if add_logo and logo_path and Path(logo_path).exists():
            image_bytes = _overlay_piranewz_branding(
                image_bytes,
                logo_path=logo_path,
                channel_name="@piranewz",
            )

        # English channel
        logger.info("Posting image to Telegram chat %s", self.chat_id)
        message_en = await self.bot.send_photo(
            chat_id=self.chat_id,
            photo=io.BytesIO(image_bytes),
            caption=caption_en[:1024],
            parse_mode="Markdown",
            disable_notification=True,
        )

        # French channel (reuse the same image bytes)
        if self.chat_id_fr and caption_fr:
            logger.info("Posting image to Telegram chat %s", self.chat_id_fr)
            await self.bot.send_photo(
                chat_id=self.chat_id_fr,
                photo=io.BytesIO(image_bytes),
                caption=caption_fr[:1024],
                parse_mode="Markdown",
                disable_notification=True,
            )

        return {"message_id": message_en.message_id, "caption": caption_en}

    async def post_text(self, caption_en: str, caption_fr: str = "") -> dict[str, Any]:
        """Post a text-only message to Telegram (EN + optional FR)."""
        logger.info("Posting text-only to Telegram chat %s", self.chat_id)
        message_en = await self.bot.send_message(
            chat_id=self.chat_id,
            text=caption_en[:4096],
            parse_mode="Markdown",
            link_preview_options={"is_disabled": True},
        )

        if self.chat_id_fr and caption_fr:
            logger.info("Posting text-only to Telegram chat %s", self.chat_id_fr)
            await self.bot.send_message(
                chat_id=self.chat_id_fr,
                text=caption_fr[:4096],
                parse_mode="Markdown",
                link_preview_options={"is_disabled": True},
            )

        return {"message_id": message_en.message_id, "caption": caption_en}


class NoOpPoster:
    """Poster that does nothing. Useful for local image generation without Telegram."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    async def post_image(
        self,
        image_url: str,
        caption: str,
        *,
        add_logo: bool = False,
        logo_path: str = "",
    ) -> dict[str, Any]:
        logger.info("Telegram disabled. Image URL: %s", image_url)
        return {"message_id": None, "caption": caption}

    async def post_image_bytes(
        self,
        image_bytes: bytes,
        caption: str,
        *,
        add_logo: bool = False,
        logo_path: str = "",
    ) -> dict[str, Any]:
        logger.info("Telegram disabled. Image bytes: %s bytes", len(image_bytes))
        return {"message_id": None, "caption": caption}

    async def post_text(self, caption: str) -> dict[str, Any]:
        logger.info("Telegram disabled. Text caption: %s", caption[:80])
        return {"message_id": None, "caption": caption}
