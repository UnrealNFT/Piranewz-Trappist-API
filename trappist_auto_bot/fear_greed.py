"""Fear & Greed gauge generation and scheduling."""

import io
import math
import os
import random
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from PIL import Image, ImageDraw, ImageFont

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


def create_gauge_image(
    fear_greed_data: dict[str, Any],
    logo_path: str | None = None,
    telegram_logo_path: str | None = None,
    channel_name: str = "@Piranewz",
) -> bytes:
    """Create a horizontal-bar Fear & Greed gauge image."""
    width, height = 1200, 1200
    img = Image.new("RGB", (width, height), color=(10, 5, 20))
    draw = ImageDraw.Draw(img)

    # Dark vertical gradient
    for y in range(height):
        progress = y / height
        r = int(15 * (1 - progress))
        g = int(10 * (1 - progress))
        b = int(35 * (1 - progress) + 15)
        draw.rectangle([(0, y), (width, y + 1)], fill=(r, g, b))

    # Stars
    random.seed(42)
    for _ in range(80):
        x = random.randint(0, width)
        y = random.randint(0, height)
        size = random.randint(1, 2)
        brightness = random.randint(150, 255)
        draw.ellipse([x, y, x + size, y + size], fill=(brightness, brightness, brightness))

    # Fonts
    try:
        font_dir = "C:/Windows/Fonts" if os.name == "nt" else "/usr/share/fonts/truetype/liberation"
        title_font = ImageFont.truetype(f"{font_dir}/arialbd.ttf" if os.name == "nt" else f"{font_dir}/LiberationSans-Bold.ttf", 52)
        value_font = ImageFont.truetype(f"{font_dir}/arialbd.ttf" if os.name == "nt" else f"{font_dir}/LiberationSans-Bold.ttf", 160)
        label_font = ImageFont.truetype(f"{font_dir}/arial.ttf" if os.name == "nt" else f"{font_dir}/LiberationSans-Regular.ttf", 32)
        small_font = ImageFont.truetype(f"{font_dir}/arial.ttf" if os.name == "nt" else f"{font_dir}/LiberationSans-Regular.ttf", 22)
    except Exception:
        title_font = ImageFont.load_default()
        value_font = ImageFont.load_default()
        label_font = ImageFont.load_default()
        small_font = ImageFont.load_default()

    # Title
    title = "FEAR & GREED INDEX"
    title_bbox = draw.textbbox((0, 0), title, font=title_font)
    draw.text(((width - (title_bbox[2] - title_bbox[0])) // 2, 120), title, font=title_font, fill=(255, 255, 255))

    value = fear_greed_data.get("value", 50)
    classification = fear_greed_data.get("value_classification", "Neutral")
    current_color = get_gauge_color(value)

    # Horizontal bar gauge
    bar_x, bar_y, bar_width, bar_height = 150, 450, 900, 80
    zones = [
        {"start": 0, "end": 20, "color": (220, 53, 69)},
        {"start": 20, "end": 40, "color": (253, 126, 20)},
        {"start": 40, "end": 60, "color": (255, 193, 7)},
        {"start": 60, "end": 80, "color": (40, 167, 69)},
        {"start": 80, "end": 100, "color": (25, 135, 84)},
    ]

    for zone in zones:
        segment_width = (zone["end"] - zone["start"]) * bar_width / 100
        segment_x = bar_x + (zone["start"] * bar_width / 100)
        draw.rectangle([segment_x, bar_y, segment_x + segment_width, bar_y + bar_height], fill=zone["color"])

    draw.rectangle([bar_x, bar_y, bar_x + bar_width, bar_y + bar_height], outline=(255, 255, 255), width=3)

    # Scale markers
    for marker in [0, 25, 50, 75, 100]:
        mx = bar_x + (marker * bar_width / 100)
        draw.line([(mx, bar_y + bar_height), (mx, bar_y + bar_height + 20)], fill=(255, 255, 255), width=2)
        mbbox = draw.textbbox((0, 0), str(marker), font=small_font)
        draw.text((mx - (mbbox[2] - mbbox[0]) // 2, bar_y + bar_height + 30), str(marker), font=small_font, fill=(220, 220, 220))

    # Indicator
    ix = bar_x + (value * bar_width / 100)
    draw.polygon([(ix, bar_y - 15), (ix - 20, bar_y - 40), (ix + 20, bar_y - 40)], fill=(255, 255, 255))
    draw.line([(ix, bar_y - 15), (ix, bar_y)], fill=(255, 255, 255), width=3)

    # Value
    value_text = str(value)
    value_bbox = draw.textbbox((0, 0), value_text, font=value_font)
    draw.text(((width - (value_bbox[2] - value_bbox[0])) // 2, 650), value_text, font=value_font, fill=current_color)

    # Classification
    class_text = classification.upper()
    class_bbox = draw.textbbox((0, 0), class_text, font=label_font)
    draw.text(((width - (class_bbox[2] - class_bbox[0])) // 2, 830), class_text, font=label_font, fill=(200, 200, 200))

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
            draw.text((lx - (lbbox[2] - lbbox[0]) // 2, ly + i * 25), line, font=small_font, fill=(180, 180, 190))

    # Logo top-left
    if logo_path and Path(logo_path).exists():
        try:
            logo = Image.open(logo_path).convert("RGBA")
            logo = logo.resize((80, int(logo.height * 80 / logo.width)), Image.LANCZOS)
            img.paste(logo, (40, 40), logo)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to add logo: %s", exc)

    # Channel name + Telegram logo at bottom
    channel_y = 950
    if telegram_logo_path and Path(telegram_logo_path).exists():
        try:
            tg_logo = Image.open(telegram_logo_path).convert("RGBA")
            tg_logo_height = 40
            tg_logo_width = int(tg_logo.width * (tg_logo_height / tg_logo.height))
            tg_logo = tg_logo.resize((tg_logo_width, tg_logo_height), Image.LANCZOS)

            channel_bbox = draw.textbbox((0, 0), channel_name, font=label_font)
            total_width = tg_logo_width + 15 + (channel_bbox[2] - channel_bbox[0])
            start_x = (width - total_width) // 2
            img.paste(tg_logo, (start_x, channel_y), tg_logo)
            draw.text((start_x + tg_logo_width + 15, channel_y + (tg_logo_height - (channel_bbox[3] - channel_bbox[1])) // 2), channel_name, font=label_font, fill=(255, 255, 255))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to add Telegram logo: %s", exc)
    else:
        channel_bbox = draw.textbbox((0, 0), f"📱 {channel_name}", font=label_font)
        draw.text(((width - (channel_bbox[2] - channel_bbox[0])) // 2, channel_y), f"📱 {channel_name}", font=label_font, fill=(255, 255, 255))

    output = io.BytesIO()
    img.save(output, format="PNG", quality=95)
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
    caption += "\n#Crypto #Bitcoin #MarketSentiment #Piranewz"
    return caption
