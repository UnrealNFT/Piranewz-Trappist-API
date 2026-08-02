"""Post crypto price updates to Telegram with a locally generated image."""

import io
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from trappist_auto_bot.image.branding import overlay_piranewz_branding
from trappist_auto_bot.image.theme import (
    BLOOD_RED,
    INK_BLACK,
    PALE_GRAY,
    ROSE_TINT,
    create_theme_background,
)
from trappist_auto_bot.telegram.poster import TelegramPoster
from trappist_auto_bot.utils.logger import get_logger

logger = get_logger(__name__)

TEXT_COLOR = PALE_GRAY
UP_COLOR = ROSE_TINT
DOWN_COLOR = BLOOD_RED
IMAGE_SIZE = (1200, 630)
MARGIN = 60


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load the tele1000 font (DejaVu Sans), falling back to system defaults."""
    import sys

    candidates = []
    if sys.platform == "win32":
        candidates = [
            "C:/Windows/Fonts/DejaVuSans-Bold.ttf" if bold else "C:/Windows/Fonts/DejaVuSans.ttf",
            "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/arial.ttf",
        ]
    else:
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        ]

    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def build_price_image(
    prices: dict[str, dict[str, Any]],
    logo_path: str = "",
) -> bytes:
    """Generate a 1200x630 Piranewz-themed price card image."""
    img = create_theme_background(IMAGE_SIZE)
    draw = ImageDraw.Draw(img)

    # Fonts.
    font_title = _load_font(52, bold=True)
    font_coin = _load_font(40, bold=True)
    font_price = _load_font(34)
    font_small = _load_font(22)

    # Header (shifted right so it does not overlap the top-left logo).
    header_x = MARGIN + 220
    draw.text((header_x, MARGIN), "Crypto Watch", font=font_title, fill=ROSE_TINT)
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    draw.text((header_x, MARGIN + 65), now, font=font_small, fill=(130, 130, 145))

    # Cards.
    coins = list(prices.items())
    card_height = 110
    gap = 18
    start_y = MARGIN + 150
    for i, (symbol, data) in enumerate(coins):
        y = start_y + i * (card_height + gap)

        card_overlay = Image.new("RGBA", IMAGE_SIZE, (0, 0, 0, 0))
        card_draw = ImageDraw.Draw(card_overlay)
        card_draw.rounded_rectangle(
            [(MARGIN, y), (IMAGE_SIZE[0] - MARGIN, y + card_height)],
            radius=20,
            fill=INK_BLACK + (210,),
            outline=ROSE_TINT + (120,),
            width=2,
        )
        img = Image.alpha_composite(img, card_overlay)
        draw = ImageDraw.Draw(img)

        price = data.get("usd", 0)
        change = data.get("change_24h", 0)
        change_str = f"{change:+.2f}%"
        change_color = UP_COLOR if change >= 0 else DOWN_COLOR

        draw.text((MARGIN + 30, y + 30), symbol, font=font_coin, fill=TEXT_COLOR)
        draw.text(
            (IMAGE_SIZE[0] - MARGIN - 30, y + 35),
            f"${price:,.4f}" if price < 1 else f"${price:,.2f}",
            font=font_price,
            fill=TEXT_COLOR,
            anchor="ra",
        )
        draw.text(
            (IMAGE_SIZE[0] - MARGIN - 30, y + 75),
            change_str,
            font=font_small,
            fill=change_color,
            anchor="ra",
        )

    # Footer watermark.
    draw.text(
        (MARGIN, IMAGE_SIZE[1] - MARGIN),
        "@piranewz · @piranewz_fr",
        font=font_small,
        fill=(120, 120, 130),
        anchor="lb",
    )

    # Add uniform Piranewz branding on the left, matching generated RSS images.
    if logo_path and Path(logo_path).exists():
        return overlay_piranewz_branding(img, logo_path=logo_path, channel_name="@piranewz", corner="top-left")

    output = io.BytesIO()
    img.convert("RGB").save(output, format="PNG")
    return output.getvalue()


def build_price_caption(
    prices: dict[str, dict[str, Any]],
    hashtags: list[str] | None = None,
) -> tuple[str, str]:
    """Return (caption_en, caption_fr) for a price update."""
    lines_en = ["📊 Crypto Price Update\n"]
    lines_fr = ["📊 Mise à jour des prix crypto\n"]
    for symbol, data in prices.items():
        price = data.get("usd", 0)
        change = data.get("change_24h", 0)
        emoji = "🟢" if change >= 0 else "🔴"
        price_str = f"${price:,.4f}" if price < 1 else f"${price:,.2f}"
        line = f"{emoji} **{symbol}**: {price_str} ({change:+.2f}%)"
        lines_en.append(line)
        lines_fr.append(line)

    tags = " ".join(hashtags) if hashtags else "#Crypto #Bitcoin #Ethereum #Casper #Algorand #Dogecoin #Solana #Altcoins"
    return "\n".join(lines_en) + "\n" + tags, "\n".join(lines_fr) + "\n" + tags


async def post_price_update(
    poster: TelegramPoster,
    prices: dict[str, dict[str, Any]],
    logo_path: str = "",
    hashtags: list[str] | None = None,
) -> dict[str, Any]:
    """Generate a price image and post it to Telegram (EN + FR channels)."""
    image_bytes = build_price_image(prices, logo_path=logo_path)
    caption_en, caption_fr = build_price_caption(prices, hashtags=hashtags)
    logger.info("Posting price update for: %s", ", ".join(prices.keys()))
    return await poster.post_image_bytes(
        image_bytes=image_bytes,
        caption_en=caption_en,
        caption_fr=caption_fr,
        add_logo=False,
        logo_path="",
    )
