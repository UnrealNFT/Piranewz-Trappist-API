"""Fear & Greed gauge generation and scheduling."""

import io
import os
import random
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from PIL import Image, ImageDraw, ImageFont

from trappist_auto_bot.image.branding import overlay_piranewz_branding
from trappist_auto_bot.image.theme import (
    BLOOD_RED,
    INK_BLACK,
    PALE_GRAY,
    ROSE_TINT,
    create_theme_background,
)
from trappist_auto_bot.utils.logger import get_logger

logger = get_logger(__name__)


def fetch_index() -> dict[str, Any]:
    """Fetch the latest Fear & Greed index from Alternative.me."""
    try:
        response = requests.get("https://api.alternative.me/fng/", timeout=15)
        response.raise_for_status()
        data = response.json()
        if "data" not in data or not data["data"]:
            raise ValueError("Unexpected API response")
        latest = data["data"][0]
        return {
            "value": int(latest["value"]),
            "value_classification": latest["value_classification"],
            "timestamp": int(latest["timestamp"]),
            "time_until_update": latest.get("time_until_update", "Unknown"),
        }
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to fetch Fear & Greed index: %s", exc)
        return {"value": 50, "value_classification": "Neutral", "timestamp": 0, "time_until_update": "Unknown"}


def get_gauge_color(value: int) -> tuple[int, int, int]:
    """Return a color for the current index value."""
    if value < 25:
        return (220, 38, 38)
    if value < 45:
        return (249, 115, 22)
    if value < 56:
        return (234, 179, 8)
    if value < 76:
        return (132, 204, 22)
    return (34, 197, 94)


def get_classification_emoji(classification: str) -> str:
    """Return an emoji for the classification."""
    mapping = {
        "Extreme Fear": "😱",
        "Fear": "😨",
        "Neutral": "😐",
        "Greed": "🤑",
        "Extreme Greed": "🚀",
    }
    return mapping.get(classification, "📊")


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load the tele1000 font (DejaVu Sans), falling back to system defaults."""
    candidates = []
    if os.name == "nt":
        candidates = [
            f"C:/Windows/Fonts/DejaVuSans{'-Bold' if bold else ''}.ttf",
            f"C:/Windows/Fonts/arial{'bd' if bold else ''}.ttf",
            "C:/Windows/Fonts/arial.ttf",
        ]
    else:
        candidates = [
            f"/usr/share/fonts/truetype/dejavu/DejaVuSans{'-Bold' if bold else ''}.ttf",
            f"/usr/share/fonts/truetype/liberation/LiberationSans{'-Bold' if bold else '-Regular'}.ttf",
        ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def create_gauge_image(
    fear_greed_data: dict[str, Any],
    logo_path: str | None = None,
    telegram_logo_path: str | None = None,
    channel_name: str = "@piranewz",
) -> bytes:
    """Create a Piranewz-themed Fear & Greed gauge image."""
    width, height = 1024, 1024
    MARGIN = 60
    img = create_theme_background((width, height))
    draw = ImageDraw.Draw(img)

    # Fonts
    title_font = _load_font(52, bold=True)
    value_font = _load_font(160, bold=True)
    label_font = _load_font(32)
    small_font = _load_font(22)

    # Title (top-left area, aligned like CRYPTO WATCH)
    title_x = MARGIN + 180
    draw.text((title_x, MARGIN), "FEAR & GREED INDEX", font=title_font, fill=PALE_GRAY)
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    draw.text((title_x, MARGIN + 60), now, font=small_font, fill=(150, 150, 165))

    value = fear_greed_data.get("value", 50)
    classification = fear_greed_data.get("value_classification", "Neutral")
    current_color = get_gauge_color(value)

    # Horizontal bar gauge (centered in 1024px width)
    bar_width, bar_height = 900, 80
    bar_x = (width - bar_width) // 2
    bar_y = 500
    zones = [
        {"start": 0, "end": 20, "color": BLOOD_RED},
        {"start": 20, "end": 40, "color": (253, 126, 20)},
        {"start": 40, "end": 60, "color": (255, 193, 7)},
        {"start": 60, "end": 80, "color": (132, 204, 22)},
        {"start": 80, "end": 100, "color": (34, 197, 94)},
    ]

    for zone in zones:
        segment_width = (zone["end"] - zone["start"]) * bar_width / 100
        segment_x = bar_x + (zone["start"] * bar_width / 100)
        draw.rectangle([segment_x, bar_y, segment_x + segment_width, bar_y + bar_height], fill=zone["color"])

    draw.rectangle([bar_x, bar_y, bar_x + bar_width, bar_y + bar_height], outline=PALE_GRAY, width=3)

    # Scale markers
    for marker in [0, 25, 50, 75, 100]:
        mx = bar_x + (marker * bar_width / 100)
        draw.line([(mx, bar_y + bar_height), (mx, bar_y + bar_height + 20)], fill=PALE_GRAY, width=2)
        mbbox = draw.textbbox((0, 0), str(marker), font=small_font)
        draw.text((mx - (mbbox[2] - mbbox[0]) // 2, bar_y + bar_height + 30), str(marker), font=small_font, fill=PALE_GRAY)

    # Indicator
    ix = bar_x + (value * bar_width / 100)
    draw.polygon([(ix, bar_y - 15), (ix - 20, bar_y - 40), (ix + 20, bar_y - 40)], fill=PALE_GRAY)
    draw.line([(ix, bar_y - 15), (ix, bar_y)], fill=PALE_GRAY, width=3)

    # Value
    value_text = str(value)
    value_bbox = draw.textbbox((0, 0), value_text, font=value_font)
    draw.text(((width - (value_bbox[2] - value_bbox[0])) // 2, 700), value_text, font=value_font, fill=current_color)

    # Classification
    class_text = classification.upper()
    class_bbox = draw.textbbox((0, 0), class_text, font=label_font)
    draw.text(((width - (class_bbox[2] - class_bbox[0])) // 2, 880), class_text, font=label_font, fill=PALE_GRAY)

    # Zone labels
    label_specs = [
        (bar_x + 10 * bar_width / 100, bar_y - 80, "EXTREME\nFEAR"),
        (bar_x + 30 * bar_width / 100, bar_y - 80, "FEAR"),
        (bar_x + 50 * bar_width / 100, bar_y - 80, "NEUTRAL"),
        (bar_x + 70 * bar_width / 100, bar_y - 80, "GREED"),
        (bar_x + 90 * bar_width / 100, bar_y - 80, "EXTREME\nGREED"),
    ]
    for lx, ly, label in label_specs:
        for i, line in enumerate(label.split("\n")):
            lbbox = draw.textbbox((0, 0), line, font=small_font)
            draw.text((lx - (lbbox[2] - lbbox[0]) // 2, ly + i * 25), line, font=small_font, fill=(160, 160, 170))

    # Add uniform Piranewz branding top-left.
    if logo_path and Path(logo_path).exists():
        return overlay_piranewz_branding(
            img,
            logo_path=logo_path,
            channel_name=channel_name,
            corner="top-left",
        )

    output = io.BytesIO()
    img.convert("RGB").save(output, format="PNG", quality=95)
    return output.getvalue()


def build_caption(data: dict[str, Any]) -> str:
    """Build a Telegram caption for the Fear & Greed gauge."""
    emoji = get_classification_emoji(data.get("value_classification", "Neutral"))
    date_str = ""
    if data.get("timestamp"):
        try:
            date_str = datetime.utcfromtimestamp(int(data["timestamp"])).strftime("%Y-%m-%d")
        except ValueError:
            pass
    caption = (
        f"{emoji} **Fear & Greed Index**\n\n"
        f"Value: **{data['value']}** ({data.get('value_classification', 'Neutral')})\n"
    )
    if date_str:
        caption += f"Date: {date_str}\n"
    caption += "\n#Crypto #Bitcoin #Ethereum #MarketSentiment #Piranewz"
    return caption
