"""Post crypto price updates to Telegram with a locally generated image."""

from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from trappist_auto_bot.telegram.poster import TelegramPoster
from trappist_auto_bot.utils.logger import get_logger

logger = get_logger(__name__)

# Colors and layout for the price card.
BG_COLOR = (15, 15, 25)
CARD_COLOR = (30, 30, 45)
TEXT_COLOR = (255, 255, 255)
UP_COLOR = (0, 255, 128)
DOWN_COLOR = (255, 80, 80)
ACCENT_COLOR = (100, 80, 255)

IMAGE_SIZE = (1200, 630)
MARGIN = 60
CARD_RADIUS = 24


def build_price_image(
    prices: dict[str, dict[str, Any]],
    logo_path: str = "",
) -> bytes:
    """Generate a 1200x630 price card image."""
    img = Image.new("RGB", IMAGE_SIZE, BG_COLOR)
    draw = ImageDraw.Draw(img)

    # Try to load fonts; fall back to defaults.
    try:
        font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 48)
        font_coin = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 42)
        font_price = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 36)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
    except OSError:
        font_title = ImageFont.load_default()
        font_coin = font_title
        font_price = font_title
        font_small = font_title

    # Header line.
    draw.text((MARGIN, MARGIN), "Crypto Watch", font=font_title, fill=ACCENT_COLOR)
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    draw.text((MARGIN, MARGIN + 60), now, font=font_small, fill=(180, 180, 180))

    # Draw a card for each coin.
    coins = list(prices.items())
    card_height = 100
    gap = 20
    start_y = MARGIN + 140
    for i, (symbol, data) in enumerate(coins):
        y = start_y + i * (card_height + gap)
        draw.rounded_rectangle(
            [(MARGIN, y), (IMAGE_SIZE[0] - MARGIN, y + card_height)],
            radius=16,
            fill=CARD_COLOR,
        )

        price = data.get("usd", 0)
        change = data.get("change_24h", 0)
        change_str = f"{change:+.2f}%"
        change_color = UP_COLOR if change >= 0 else DOWN_COLOR

        draw.text((MARGIN + 30, y + 25), symbol, font=font_coin, fill=TEXT_COLOR)
        draw.text(
            (IMAGE_SIZE[0] - MARGIN - 30, y + 30),
            f"${price:,.4f}" if price < 1 else f"${price:,.2f}",
            font=font_price,
            fill=TEXT_COLOR,
            anchor="ra",
        )
        draw.text(
            (IMAGE_SIZE[0] - MARGIN - 30, y + 70),
            change_str,
            font=font_small,
            fill=change_color,
            anchor="ra",
        )

    # Footer / watermark.
    draw.text(
        (IMAGE_SIZE[0] - MARGIN, IMAGE_SIZE[1] - MARGIN),
        "@piranewz · @piranewz_fr",
        font=font_small,
        fill=(120, 120, 120),
        anchor="rb",
    )

    # Optional logo overlay.
    if logo_path and Path(logo_path).exists():
        try:
            logo = Image.open(logo_path).convert("RGBA")
            logo.thumbnail((100, 100))
            img.paste(logo, (IMAGE_SIZE[0] - MARGIN - 120, MARGIN), logo)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not overlay logo: %s", exc)

    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# BytesIO is needed for the image buffer.
from io import BytesIO  # noqa: E402


def build_price_caption(prices: dict[str, dict[str, Any]]) -> tuple[str, str]:
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

    footer_en = "\n#Crypto #Bitcoin #Ethereum #Casper #Algorand #Dogecoin #Solana #Altcoins"
    footer_fr = "\n#Crypto #Bitcoin #Ethereum #Casper #Algorand #Dogecoin #Solana #Altcoins"
    return "\n".join(lines_en) + footer_en, "\n".join(lines_fr) + footer_fr


async def post_price_update(
    poster: TelegramPoster,
    prices: dict[str, dict[str, Any]],
    logo_path: str = "",
) -> dict[str, Any]:
    """Generate a price image and post it to Telegram (EN + FR channels)."""
    image_bytes = build_price_image(prices, logo_path=logo_path)
    caption_en, caption_fr = build_price_caption(prices)
    logger.info("Posting price update for: %s", ", ".join(prices.keys()))
    return await poster.post_image_bytes(
        image_bytes=image_bytes,
        caption_en=caption_en,
        caption_fr=caption_fr,
        add_logo=False,
        logo_path="",
    )
