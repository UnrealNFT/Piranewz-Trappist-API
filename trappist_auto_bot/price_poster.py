"""Post crypto price updates to Telegram with a locally generated image."""

import io
import math
import random
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from trappist_auto_bot.image.branding import overlay_piranewz_branding
from trappist_auto_bot.telegram.poster import TelegramPoster
from trappist_auto_bot.utils.logger import get_logger

logger = get_logger(__name__)

# Price card palette — dark underwater / chaotic manga vibe.
DEEP_BLUE = (8, 12, 28)
MID_BLUE = (18, 28, 58)
AQUA_GLOW = (0, 220, 180)
TEAL = (0, 160, 200)
PURPLE = (120, 60, 200)
TEXT_COLOR = (245, 245, 255)
UP_COLOR = (0, 255, 150)
DOWN_COLOR = (255, 70, 100)

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


def _draw_underwater_background(draw: ImageDraw.Draw, size: tuple[int, int]) -> None:
    """Draw a dark underwater chaotic background with wave streaks and bubbles."""
    width, height = size

    # Chaotic wave streaks.
    for i in range(12):
        y_base = int(height * (0.1 + 0.08 * i))
        amplitude = random.randint(20, 60)
        freq = random.uniform(0.01, 0.03)
        phase = random.uniform(0, math.pi * 2)
        alpha = random.randint(20, 60)
        color = (*TEAL, alpha) if i % 2 == 0 else (*PURPLE, alpha)
        points = []
        for x in range(0, width + 20, 20):
            y = y_base + int(amplitude * math.sin(freq * x + phase))
            points.append((x, y))
        for thickness in range(3):
            offset_points = [(x, y + thickness) for x, y in points]
            draw.line(offset_points, fill=color, width=2)

    # Bubble clusters.
    for _ in range(40):
        x = random.randint(0, width)
        y = random.randint(0, height)
        r = random.randint(2, 8)
        alpha = random.randint(30, 80)
        draw.ellipse([x - r, y - r, x + r, y + r], fill=(*AQUA_GLOW, alpha))


def build_price_image(
    prices: dict[str, dict[str, Any]],
    logo_path: str = "",
) -> bytes:
    """Generate a 1200x630 underwater-themed price card image."""
    img = Image.new("RGBA", IMAGE_SIZE, DEEP_BLUE)
    draw = ImageDraw.Draw(img)

    # Deep gradient base.
    for y in range(IMAGE_SIZE[1]):
        ratio = y / IMAGE_SIZE[1]
        r = int(DEEP_BLUE[0] + (MID_BLUE[0] - DEEP_BLUE[0]) * ratio)
        g = int(DEEP_BLUE[1] + (MID_BLUE[1] - DEEP_BLUE[1]) * ratio)
        b = int(DEEP_BLUE[2] + (MID_BLUE[2] - DEEP_BLUE[2]) * ratio)
        draw.line([(0, y), (IMAGE_SIZE[0], y)], fill=(r, g, b, 255))

    _draw_underwater_background(draw, IMAGE_SIZE)

    # Soft vignette.
    vignette = Image.new("RGBA", IMAGE_SIZE, (0, 0, 0, 0))
    v_draw = ImageDraw.Draw(vignette)
    for i in range(120):
        alpha = int(80 * (i / 120))
        v_draw.rectangle([i, i, IMAGE_SIZE[0] - i, IMAGE_SIZE[1] - i], outline=(0, 0, 0, alpha))
    img = Image.alpha_composite(img, vignette)
    draw = ImageDraw.Draw(img)

    # Fonts.
    font_title = _load_font(52, bold=True)
    font_coin = _load_font(40, bold=True)
    font_price = _load_font(34)
    font_small = _load_font(22)

    # Header (shifted right so it does not overlap the top-left logo).
    header_x = MARGIN + 220
    draw.text((header_x, MARGIN), "Crypto Watch", font=font_title, fill=AQUA_GLOW)
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    draw.text((header_x, MARGIN + 65), now, font=font_small, fill=(160, 180, 200))

    # Cards.
    coins = list(prices.items())
    card_height = 110
    gap = 18
    start_y = MARGIN + 150
    for i, (symbol, data) in enumerate(coins):
        y = start_y + i * (card_height + gap)

        # Glass card with subtle border.
        card_overlay = Image.new("RGBA", IMAGE_SIZE, (0, 0, 0, 0))
        card_draw = ImageDraw.Draw(card_overlay)
        card_draw.rounded_rectangle(
            [(MARGIN, y), (IMAGE_SIZE[0] - MARGIN, y + card_height)],
            radius=20,
            fill=(10, 18, 38, 220),
            outline=(*AQUA_GLOW, 120),
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
        fill=(120, 140, 160),
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
