"""Shared Piranewz branding overlay for all generated images."""

import io
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from trappist_auto_bot.utils.logger import get_logger

logger = get_logger(__name__)


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


def overlay_piranewz_branding(
    image: Image.Image | bytes,
    *,
    logo_path: str,
    channel_name: str = "@piranewz",
    corner: str = "top-right",
) -> bytes:
    """Add the Piranewz logo + Telegram handle badge to an image.

    Args:
        image: PIL Image or raw image bytes.
        logo_path: Path to the brand logo (e.g. assets/logo.png).
        channel_name: Telegram handle to display.
        corner: "top-left" or "top-right".

    Returns:
        JPEG-encoded image bytes.
    """
    try:
        if isinstance(image, bytes):
            img = Image.open(io.BytesIO(image)).convert("RGBA")
        else:
            img = image.convert("RGBA")

        draw = ImageDraw.Draw(img)
        img_width, img_height = img.size

        margin = 20
        logo_width = int(img_width * 0.15)

        # --- Brand logo ---
        logo_height = 0
        if Path(logo_path).exists():
            logo = Image.open(logo_path).convert("RGBA")
            logo_height = int(logo.height * (logo_width / logo.width))
            logo = logo.resize((logo_width, logo_height), Image.Resampling.LANCZOS)
            if corner == "top-right":
                logo_x = img_width - margin - logo_width
            else:
                logo_x = margin
            img.paste(logo, (logo_x, margin), logo)

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
        badge_y = margin + logo_height + 8
        if corner == "top-right":
            badge_x = img_width - margin - total_w
        else:
            badge_x = margin

        pad = 7
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        overlay_draw.rounded_rectangle(
            [badge_x - pad, badge_y - pad, badge_x + total_w + pad, badge_y + tg_h + pad],
            radius=10,
            fill=(0, 0, 0, 140),
        )
        img = Image.alpha_composite(img, overlay)
        draw = ImageDraw.Draw(img)

        if tg_logo:
            img.paste(tg_logo, (badge_x, badge_y), tg_logo)

        text_x = badge_x + tg_w + spacing
        text_y = badge_y + (tg_h - text_height) // 2
        draw.text((text_x + 1, text_y + 1), channel_text, font=font, fill=(0, 0, 0, 160))
        draw.text((text_x, text_y), channel_text, font=font, fill=(255, 255, 255, 230))

        output = io.BytesIO()
        img.convert("RGB").save(output, format="JPEG", quality=95)
        return output.getvalue()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Piranewz branding overlay failed: %s", exc)
        if isinstance(image, bytes):
            return image
        out = io.BytesIO()
        image.convert("RGB").save(out, format="JPEG", quality=95)
        return out.getvalue()
