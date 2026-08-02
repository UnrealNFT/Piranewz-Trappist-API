"""Telegram channel poster."""

import io
from pathlib import Path
from typing import Any

import requests
from PIL import Image
from telegram import Bot

from trappist_auto_bot.image.branding import overlay_piranewz_branding
from trappist_auto_bot.utils.logger import get_logger

logger = get_logger(__name__)


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
            image_bytes = overlay_piranewz_branding(
                image_bytes,
                logo_path=logo_path,
                channel_name="@piranewz",
                corner="top-left",
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
        caption_en: str,
        caption_fr: str = "",
        *,
        add_logo: bool = False,
        logo_path: str = "",
    ) -> dict[str, Any]:
        logger.info("Telegram disabled. Image URL: %s", image_url)
        return {"message_id": None, "caption": caption_en}

    async def post_image_bytes(
        self,
        image_bytes: bytes,
        caption_en: str,
        caption_fr: str = "",
        *,
        add_logo: bool = False,
        logo_path: str = "",
    ) -> dict[str, Any]:
        logger.info("Telegram disabled. Image bytes: %s bytes", len(image_bytes))
        return {"message_id": None, "caption": caption_en}

    async def post_text(self, caption_en: str, caption_fr: str = "") -> dict[str, Any]:
        logger.info("Telegram disabled. Text caption: %s", caption_en[:80])
        return {"message_id": None, "caption": caption_en}
